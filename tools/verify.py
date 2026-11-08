#!/usr/bin/env python3
"""One command that decides "done".

  python tools/verify.py                                   # what an agent runs locally (baseline = HEAD)
  python tools/verify.py --base origin/main --case case.json --seed 123   # what the CI verifier runs

A change passes when: it touches no protected path, adds at most the issue's own case to the corpus,
lint and unit tests pass, the issue's case now passes, and NO case that main already got right now fails
(a ratchet). Unrelated bugs that main also has do not block a fix.  Agents cannot edit this file.
"""
from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import random
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fuzz  # noqa: E402


def run(name: str, cmd: list, env=None) -> None:
    print("== %s: %s" % (name, " ".join(cmd)), flush=True)
    if subprocess.run(cmd, cwd=ROOT, env=env).returncode != 0:
        print("\nVERIFY FAILED at step: %s" % name)
        sys.exit(1)


def fail(step: str, lines: list) -> None:
    print("\n".join(lines))
    print("\nVERIFY FAILED at step: %s" % step)
    sys.exit(1)


def git_diff(base: str, *args: str) -> str:
    return subprocess.run(["git", "diff", "%s...HEAD" % base, *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def protected_paths_untouched(base: str) -> None:
    print("== protected paths vs %s" % base, flush=True)
    changed = git_diff(base, "--name-only").split()
    with open(os.path.join(ROOT, "harness", "protected.txt")) as fh:
        patterns = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    bad = [f for f in changed if any(fnmatch.fnmatch(f, p) for p in patterns)]
    if bad:
        fail("protected paths", ["The change touches files the agent may not edit:"] + ["  " + f for f in bad])


def corpus_additions_ok(base: str, case_path) -> None:
    print("== corpus may only gain this issue's own case", flush=True)
    added, removed = [], []
    for line in git_diff(base, "--unified=0", "--", "tests/corpus.jsonl").splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    allowed = None
    if case_path:
        c = json.load(open(case_path))
        allowed = (c["pattern"], c["text"])
    problems = ["existing corpus cases were removed or edited"] if removed else []
    for a in added:
        try:
            j = json.loads(a)
            ok = allowed is not None and (j.get("pattern"), j.get("text")) == allowed
        except ValueError:
            ok = False
        if not ok:
            problems.append("corpus gained a case that is not this issue's: %s" % a[:120])
    if problems:
        fail("corpus", problems + ["FIX: do not edit tests/corpus.jsonl; the harness records the issue's case itself."])


def compare(base: dict, branch: dict):
    """Both dicts are {"done": n, "failed": [indices]} for the same seed. Returns (new_failures, fixed, compared)."""
    m = min(base["done"], branch["done"])
    base_failed = {i for i in base["failed"] if i < m}
    branch_failed = {i for i in branch["failed"] if i < m}
    return sorted(branch_failed - base_failed), len(base_failed - branch_failed), m


def baseline_src(base: str) -> str:
    tar = subprocess.run(["git", "archive", base, "src"], cwd=ROOT, capture_output=True, check=True).stdout
    d = tempfile.mkdtemp(prefix="baseline-")
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        tf.extractall(d, filter="data")
    return os.path.join(d, "src")


def dump(src, level: int, seed: int, iters: int, label: str) -> dict:
    out = os.path.join(tempfile.mkdtemp(), label + ".json")
    env = dict(os.environ)
    if src:
        env["ENGINE_SRC"] = src
    cmd = [sys.executable, "tools/fuzz.py", "--level", str(level), "--seed", str(seed), "--iters", str(iters),
           "--max-seconds", "150", "--dump-failures", out]
    print("-- %s engine: %s" % (label, " ".join(cmd[1:])), flush=True)
    if subprocess.run(cmd, cwd=ROOT, env=env).returncode != 0:
        fail("regression check", ["could not run the fuzzer for the %s engine" % label])
    return json.load(open(out))


def regression_check(base: str, level: int, seed: int, iters: int) -> None:
    print("== regression check: nothing main already handled may break (level %d, seed %d)" % (level, seed), flush=True)
    before = dump(baseline_src(base), level, seed, iters, "main")
    after = dump(None, level, seed, iters, "branch")
    new, fixed, compared = compare(before, after)
    print("compared %d cases: main fails %d, branch fails %d, newly broken %d, newly fixed %d" % (
        compared, len([i for i in before["failed"] if i < compared]),
        len([i for i in after["failed"] if i < compared]), len(new), fixed))
    if new:
        cases = list(fuzz.iter_cases(level, seed, iters))
        lines = ["These cases passed on main and now FAIL on your branch:"]
        for i in new[:5]:
            lines.append("  pattern=%r text=%r" % cases[i])
        fail("regression check", lines + ["FIX: your change broke existing behaviour. Reproduce one with "
                                          "python tools/fuzz.py --case '{\"pattern\": ..., \"text\": ...}'"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="git ref of main; enables the protected-path and corpus checks")
    ap.add_argument("--case", help="JSON case from the issue that must now pass")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--iters", type=int, default=1500)
    args = ap.parse_args()

    fuzz.check_python()
    seed = args.seed if args.seed is not None else int(os.environ.get("VERIFY_SEED") or random.randrange(10**9))
    level = fuzz.current_level()
    py = sys.executable

    if args.base:
        protected_paths_untouched(args.base)
        corpus_additions_ok(args.base, args.case)
    run("lint", [py, "tools/lint_arch.py"])
    run("unit tests", [py, "-m", "unittest", "discover", "-s", "tests", "-t", "."])
    if args.case:
        run("issue case", [py, "tools/fuzz.py", "--case", args.case])
    regression_check(args.base or "HEAD", level, seed, args.iters)
    print("\nVERIFY OK (level %d, seed %d)" % (level, seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
