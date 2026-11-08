#!/usr/bin/env python3
"""Finder: advance the difficulty level when the engine is clean, otherwise file ONE issue for the
smallest new failure and dispatch the solver. Deterministic: it costs no LLM requests.

  python tools/finder.py --dry-run     # show what it would do, touch nothing
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fuzz  # noqa: E402

MAX_SOLVER_RUNS_PER_DAY = int(os.environ.get("MAX_SOLVER_RUNS_PER_DAY", "20"))


def gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("gh %s failed: %s" % (" ".join(args[:3]), r.stderr.strip()))
    return r.stdout


def in_flight() -> bool:
    return bool(json.loads(gh("issue", "list", "--label", "agent", "--state", "open", "--json", "number")))


def solver_runs_last_day() -> int:
    runs = json.loads(gh("run", "list", "--workflow", "solver.yml", "--limit", "100", "--json", "createdAt"))
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    return sum(1 for r in runs if datetime.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) > cutoff)


def known_fingerprints() -> set[str]:
    issues = json.loads(gh("issue", "list", "--label", "fuzz", "--state", "all", "--limit", "500", "--json", "body"))
    found = set()
    for issue in issues:
        body = issue.get("body") or ""
        if "<!-- fp:" in body:
            found.add(body.split("<!-- fp:")[1].split(" -->")[0])
    return found


MAX_CONSECUTIVE_FAILURES = int(os.environ.get("MAX_CONSECUTIVE_FAILURES", "4"))


def parse_time(text: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def count_failures(runs: list, since=None) -> int:
    """runs: solver runs, newest first. Failed runs since the last success (or since `since`)."""
    n = 0
    for r in runs:
        if r["status"] != "completed":
            continue
        if since is not None and parse_time(r["createdAt"]) <= since:
            break
        if r["conclusion"] == "success":
            break
        if r["conclusion"] in ("failure", "timed_out"):
            n += 1
    return n


def last_pause_change():
    out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", "harness/PAUSE"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    return parse_time(out) if out else None


def auto_pause(n: int) -> None:
    """Too many failures in a row: stop spending requests and ask a human."""
    note = "Auto-paused after %d consecutive solver failures. Delete this file to resume.\n" % n
    with open(os.path.join(ROOT, "harness", "PAUSE"), "w") as fh:
        fh.write(note)
    subprocess.run(["git", "add", "harness/PAUSE"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", "harness: auto-pause after %d consecutive solver failures" % n], cwd=ROOT, check=True)
    subprocess.run(["git", "push"], cwd=ROOT, check=True)
    subprocess.run(["gh", "label", "create", "needs-human", "--color", "d93f0b", "--force"], capture_output=True)
    gh("issue", "create", "--label", "needs-human", "--title", "Harness auto-paused: %d solver runs failed in a row" % n,
       "--body", "The finder stopped itself to avoid wasting free requests.\n\nLook at the latest failed solver runs "
       "(Actions -> solver) and their transcript artifacts. When ready, delete `harness/PAUSE` to resume; "
       "counting restarts from that moment.")
    print("auto-paused after %d consecutive failures" % n)


def issue_text(f: dict) -> tuple[str, str]:
    title = "[L%d] %s: pattern=%r text=%r" % (f["level"], f["kind"], f["pattern"], f["text"])
    case = json.dumps({"pattern": f["pattern"], "text": f["text"], "level": f["level"]})
    body = "\n".join([
        "The differential fuzzer found a disagreement between `regex_engine.match` and CPython's `re.match`.",
        "",
        "```",
        "kind     : %s" % f["kind"],
        "pattern  : %r" % f["pattern"],
        "text     : %r" % f["text"],
        "expected : %s" % (f["expected"],),
        "actual   : %s" % (f["actual"] if f["error"] is None else f["error"]),
        "```",
        "",
        "Hint: %s" % fuzz.HINTS[f["kind"]],
        "",
        "CASE: " + case,
        "<!-- fp:%s -->" % f["fp"],
    ])
    return title[:120], body


def bump_level(level: int, dry: bool) -> None:
    print("engine clean; advancing to level %d" % level)
    if dry:
        return
    with open(os.path.join(ROOT, "harness", "level.txt"), "w") as fh:
        fh.write("%d\n" % level)
    subprocess.run(["git", "add", "harness/level.txt"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", "harness: advance fuzz level to %d" % level], cwd=ROOT, check=True)
    subprocess.run(["git", "push"], cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    dry = args.dry_run
    fuzz.check_python()

    if os.path.exists(os.path.join(ROOT, "harness", "PAUSE")):
        print("harness/PAUSE exists; doing nothing")
        return 0
    if not dry:
        runs = json.loads(gh("run", "list", "--workflow", "solver.yml", "--limit", "30", "--json", "status,conclusion,createdAt"))
        failures = count_failures(runs, last_pause_change()) + (1 if os.environ.get("JUST_FAILED") == "true" else 0)
        if failures >= MAX_CONSECUTIVE_FAILURES:
            auto_pause(failures)
            return 0
        if in_flight():
            print("an issue is already in flight; doing nothing")
            return 0
        if solver_runs_last_day() >= MAX_SOLVER_RUNS_PER_DAY:
            print("daily solver cap reached; doing nothing")
            return 0

    engine = fuzz.load_engine()
    level = fuzz.current_level()
    seed = args.seed if args.seed is not None else int(time.time())
    failures = fuzz.fuzz(engine, level, seed, args.iters)
    while not failures and level < fuzz.MAX_LEVEL:
        level += 1
        bump_level(level, dry)
        failures = fuzz.fuzz(engine, level, seed, args.iters)
    if not failures:
        print("engine is clean at the maximum level (%d)" % level)
        return 0

    seen = set() if dry else known_fingerprints()
    fresh = [f for f in failures if f["fp"] not in seen]
    if not fresh:
        print("every current failure already has an issue; a human should look at the agent-failed ones")
        return 0
    title, body = issue_text(fresh[0])
    if dry:
        print("DRY RUN: would file issue\n  title: %s\n%s" % (title, body))
        return 0
    for label, color in (("fuzz", "ededed"), ("agent", "5319e7"), ("agent-failed", "b60205")):
        subprocess.run(["gh", "label", "create", label, "--color", color, "--force"], capture_output=True)
    url = gh("issue", "create", "--title", title, "--body", body, "--label", "fuzz,agent").strip()
    number = url.rstrip("/").split("/")[-1]
    gh("workflow", "run", "solver.yml", "-f", "issue=%s" % number)
    print("filed %s and dispatched the solver" % url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
