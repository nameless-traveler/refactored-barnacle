#!/usr/bin/env python3
"""One command that decides "done": protected paths, lint, unit tests, fuzz, and the issue's own case.

  python tools/verify.py                              # what an agent runs locally
  python tools/verify.py --base origin/main --case case.json --seed 123   # what the CI verifier runs

Agents cannot edit this file.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import random
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fuzz  # noqa: E402


def run(name: str, cmd: list[str]) -> None:
    print("== %s: %s" % (name, " ".join(cmd)), flush=True)
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        print("\nVERIFY FAILED at step: %s" % name)
        sys.exit(1)


def protected_paths_untouched(base: str) -> None:
    print("== protected paths vs %s" % base, flush=True)
    out = subprocess.run(["git", "diff", "--name-only", "%s...HEAD" % base], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    with open(os.path.join(ROOT, "harness", "protected.txt")) as fh:
        patterns = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    bad = [f for f in out if any(fnmatch.fnmatch(f, p) for p in patterns)]
    if bad:
        print("The change touches files the agent may not edit:\n  " + "\n  ".join(bad))
        print("\nVERIFY FAILED at step: protected paths")
        sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="git ref to diff against for the protected-paths check")
    ap.add_argument("--case", help="JSON case from the issue that must now pass")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--iters", type=int, default=1500)
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else int(os.environ.get("VERIFY_SEED") or random.randrange(10**9))
    level = fuzz.current_level()
    py = sys.executable

    if args.base:
        protected_paths_untouched(args.base)
    run("lint", [py, "tools/lint_arch.py"])
    run("unit tests", [py, "-m", "unittest", "discover", "-s", "tests", "-t", "."])
    if args.case:
        run("issue case", [py, "tools/fuzz.py", "--case", args.case])
    run("fuzz level %d seed %d" % (level, seed),
        [py, "tools/fuzz.py", "--level", str(level), "--seed", str(seed), "--iters", str(args.iters)])
    print("\nVERIFY OK (level %d, seed %d)" % (level, seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
