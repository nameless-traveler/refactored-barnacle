#!/usr/bin/env python3
"""Differential fuzzer: compares src/regex_engine against CPython's `re` (the oracle).

Usage:
  python tools/fuzz.py --level 3 --seed 1 --iters 2000
  python tools/fuzz.py --case '{"pattern": "a*", "text": "aa"}'

Exit code 0 = the engine agrees with `re` on everything tried, 1 = at least one disagreement.
The fuzzer, not the agent, decides what "correct" means. Agents cannot edit this file.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import random
import re
import signal
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALPHA = "abc"
CASE_TIMEOUT = 0.5  # seconds the engine gets per (pattern, text)
MAX_LEVEL = 10


def current_level() -> int:
    with open(os.path.join(ROOT, "harness", "level.txt")) as fh:
        return int(fh.read().strip())


def required_python() -> str:
    with open(os.path.join(ROOT, "harness", "python-version.txt")) as fh:
        return fh.read().strip()


def check_python() -> None:
    """The oracle is CPython's `re`; its behaviour must be identical everywhere. Fail loudly on drift."""
    want, have = required_python(), "%d.%d" % sys.version_info[:2]
    if want != have and not os.environ.get("ALLOW_PYTHON_MISMATCH"):
        raise SystemExit("ORACLE VERSION MISMATCH: harness/python-version.txt requires Python %s but this is %s. "
                         "Fix the workflow's setup-python step (do not edit the version file)." % (want, have))


def load_engine():
    sys.path.insert(0, os.environ.get("ENGINE_SRC") or os.path.join(ROOT, "src"))
    return importlib.import_module(os.environ.get("ENGINE_MODULE", "regex_engine"))


# --------------------------------------------------------------------------- generator
class Gen:
    """Random pattern generator. Features unlock with the level (see feature-ladder.md)."""

    def __init__(self, rng: random.Random, level: int):
        self.r = rng
        self.level = level
        self.opened = 0
        self.closed: list[int] = []

    def pattern(self) -> str:
        self.opened = 0
        self.closed = []
        return self.alt(0)

    def alt(self, depth: int) -> str:
        branches = 1
        if self.level >= 4 and self.r.random() < 0.3:
            branches = self.r.randint(2, 3)
        return "|".join(self.seq(depth) for _ in range(branches))

    def seq(self, depth: int) -> str:
        n = self.r.choice([0, 1, 1, 2, 2, 3, 3, 4]) if depth == 0 else self.r.choice([1, 1, 2, 3])
        return "".join(self.item(depth) for _ in range(n))

    def item(self, depth: int) -> str:
        if self.level >= 6 and self.r.random() < 0.08:
            return self.r.choice("^$")
        return self.atom(depth) + self.quant()

    def atom(self, depth: int) -> str:
        options = [("lit", 8)]
        if self.level >= 2:
            options.append(("dot", 2))
        if self.level >= 4 and depth < 3:
            options.append(("group", 3))
        if self.level >= 5:
            options.append(("class", 2))
        usable = [n for n in self.closed if n <= 9]
        if self.level >= 10 and usable:
            options.append(("backref", 1))
        kinds, weights = zip(*options)
        kind = self.r.choices(kinds, weights)[0]
        if kind == "lit":
            return self.r.choice(ALPHA)
        if kind == "dot":
            return "."
        if kind == "class":
            return self.char_class()
        if kind == "backref":
            return "\\%d" % self.r.choice(usable)
        self.opened += 1
        number = self.opened
        inner = self.alt(depth + 1)
        self.closed.append(number)
        return "(" + inner + ")"

    def char_class(self) -> str:
        parts = []
        for _ in range(self.r.randint(1, 2)):
            lo = self.r.choice(ALPHA)
            if self.r.random() < 0.3:
                hi = self.r.choice([c for c in ALPHA if c >= lo])
                parts.append(lo + "-" + hi if hi != lo else lo)
            else:
                parts.append(lo)
        return "[" + ("^" if self.r.random() < 0.3 else "") + "".join(parts) + "]"

    def quant(self) -> str:
        if self.level < 3 or self.r.random() < 0.55:
            return ""
        options = ["*", "+", "?"]
        if self.level >= 7:
            m = self.r.randint(0, 3)
            options += ["{%d}" % m, "{%d,}" % m, "{%d,%d}" % (m, m + self.r.randint(0, 2))]
        q = self.r.choice(options)
        if self.level >= 8 and self.r.random() < 0.3:
            q += "?"
        return q


_BRACES = re.compile(r"\{(\d+)(?:(,)(\d*))?\}")


def parses(p: str, level: int) -> bool:
    """True if `p` is in the grammar enabled at `level`. Keeps shrunk cases inside the spec."""
    n = len(p)
    i = 0
    opened = 0
    closed: set[int] = set()

    def peek() -> str:
        return p[i] if i < n else ""

    def alt(depth: int) -> bool:
        nonlocal i
        if not seq(depth):
            return False
        while peek() == "|":
            if level < 4:
                return False
            i += 1
            if not seq(depth):
                return False
        return True

    def seq(depth: int) -> bool:
        while peek() and peek() != "|" and not (peek() == ")" and depth > 0):
            if not item(depth):
                return False
        return True

    def item(depth: int) -> bool:
        nonlocal i
        if peek() in ("^", "$") and peek():
            if level < 6:
                return False
            i += 1
            return True
        return atom(depth) and quant()

    def atom(depth: int) -> bool:
        nonlocal i, opened
        c = peek()
        if c and c in ALPHA:
            i += 1
            return True
        if c == "." and level >= 2:
            i += 1
            return True
        if c == "[" and level >= 5:
            return char_class()
        if c == "(" and level >= 4:
            opened += 1
            number = opened
            i += 1
            if not alt(depth + 1) or peek() != ")":
                return False
            i += 1
            closed.add(number)
            return True
        if c == "\\" and level >= 10:
            d = p[i + 1] if i + 1 < n else ""
            if d.isdigit() and d != "0" and int(d) in closed:
                i += 2
                return True
        return False

    def char_class() -> bool:
        nonlocal i
        i += 1
        if peek() == "^":
            i += 1
        count = 0
        while peek() and peek() != "]":
            c = peek()
            if c not in ALPHA:
                return False
            i += 1
            if peek() == "-" and i + 1 < n and p[i + 1] in ALPHA:
                if p[i + 1] < c:
                    return False
                i += 2
            count += 1
        if peek() != "]" or count == 0:
            return False
        i += 1
        return True

    def quant() -> bool:
        nonlocal i
        c = peek()
        if c and c in "*+?" and level >= 3:
            i += 1
        elif c == "{" and level >= 7:
            m = _BRACES.match(p, i)
            if not m:
                return False
            if m.group(3) and int(m.group(1)) > int(m.group(3)):
                return False
            i = m.end()
        else:
            return True
        if level >= 8 and peek() == "?":
            i += 1
        return True

    return alt(0) and i == n


# --------------------------------------------------------------------------- comparison
class CaseTimeout(BaseException):  # BaseException so an engine's `except Exception` can't swallow it
    pass


def _on_alarm(signum, frame):
    raise CaseTimeout()


def norm_ref(m, level):
    if m is None:
        return None
    out = {"span": list(m.span())}
    if level >= 9:
        out["groups"] = [None if m.span(i) == (-1, -1) else list(m.span(i)) for i in range(1, m.re.groups + 1)]
    return out


def norm_actual(m, level):
    if m is None:
        return None
    out = {"span": [m.start, m.end]}
    if level >= 9:
        out["groups"] = [None if g is None else list(g) for g in m.groups]
    return out


def run_case(engine, pattern: str, text: str, level: int):
    """Return None if the engine agrees with `re`, else a failure dict."""
    expected = norm_ref(re.match(pattern, text), level)
    signal.signal(signal.SIGALRM, _on_alarm)
    signal.setitimer(signal.ITIMER_REAL, CASE_TIMEOUT)
    kind, actual, error = None, None, None
    try:
        actual = norm_actual(engine.match(pattern, text), level)
        if actual != expected:
            kind = "mismatch"
    except CaseTimeout:
        kind, error = "timeout", "no answer within %.1fs" % CASE_TIMEOUT
    except Exception as exc:  # noqa: BLE001 - any engine crash is a finding
        kind, error = "exception", "%s: %s" % (type(exc).__name__, exc)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    if kind is None:
        return None
    return {"pattern": pattern, "text": text, "kind": kind, "expected": expected, "actual": actual, "error": error}


def fingerprint(pattern: str, text: str) -> str:
    return hashlib.sha1(json.dumps([pattern, text]).encode()).hexdigest()[:10]


def shrink(engine, pattern: str, text: str, level: int, kind: str, budget: int = 400):
    """Greedily delete characters while the same kind of failure persists and the grammar still holds."""

    def still_fails(p: str, t: str) -> bool:
        nonlocal budget
        if budget <= 0 or not parses(p, level):
            return False
        try:
            re.compile(p)
        except re.error:
            return False
        budget -= 1
        f = run_case(engine, p, t, level)
        return f is not None and f["kind"] == kind

    changed = True
    while changed:
        changed = False
        for j in range(len(text)):
            t = text[:j] + text[j + 1:]
            if still_fails(pattern, t):
                text, changed = t, True
                break
        if changed:
            continue
        for j in range(len(pattern)):
            p = pattern[:j] + pattern[j + 1:]
            if still_fails(p, text):
                pattern, changed = p, True
                break
    return pattern, text


def fuzz(engine, level: int, seed: int, iters: int, max_seconds: float = 240.0, max_findings: int = 25):
    """Return distinct shrunk failures, smallest first."""
    rng = random.Random(seed)
    found: dict[str, dict] = {}
    deadline = time.monotonic() + max_seconds
    for _ in range(iters):
        if time.monotonic() > deadline or len(found) >= max_findings:
            break
        pattern = Gen(rng, level).pattern()
        try:
            re.compile(pattern)
        except re.error:
            continue
        for _ in range(4):
            text = "".join(rng.choice(ALPHA) for _ in range(rng.randint(0, 7)))
            failure = run_case(engine, pattern, text, level)
            if failure is None:
                continue
            sp, st = shrink(engine, pattern, text, level, failure["kind"])
            small = run_case(engine, sp, st, level) or failure
            fp = fingerprint(small["pattern"], small["text"])
            found.setdefault(fp, {**small, "fp": fp, "level": level})
            break
    return sorted(found.values(), key=lambda f: (len(f["pattern"]) + len(f["text"]), f["pattern"], f["text"]))


def iter_cases(level: int, seed: int, iters: int):
    """Engine-independent stream of (pattern, text): one seed gives the same cases for every engine."""
    rng = random.Random(seed)
    for _ in range(iters):
        pattern = Gen(rng, level).pattern()
        texts = ["".join(rng.choice(ALPHA) for _ in range(rng.randint(0, 7))) for _ in range(4)]
        try:
            re.compile(pattern)
        except re.error:
            continue
        for text in texts:
            yield pattern, text


def dump_failures(engine, level: int, seed: int, iters: int, max_seconds: float, path: str):
    """Record which case indices fail, so two engines (main vs branch) can be compared case by case."""
    deadline = time.monotonic() + max_seconds
    done, failed = 0, []
    for idx, (pattern, text) in enumerate(iter_cases(level, seed, iters)):
        if time.monotonic() > deadline:
            break
        done = idx + 1
        if run_case(engine, pattern, text, level) is not None:
            failed.append(idx)
    with open(path, "w") as fh:
        json.dump({"done": done, "failed": failed}, fh)
    return done, failed


HINTS = {
    "mismatch": "compare with re.match(pattern, text); see docs/references/semantics.md (leftmost-first, not longest)",
    "timeout": "the engine must terminate; look for loops that make no progress on empty matches",
    "exception": "the engine raised; implement or handle this construct",
}


def describe(f: dict) -> str:
    lines = ["FAIL [%s] level %s: pattern=%r text=%r" % (f["kind"], f.get("level", "?"), f["pattern"], f["text"])]
    lines.append("  expected: %s" % (f["expected"],))
    lines.append("  actual:   %s" % (f["actual"] if f["error"] is None else f["error"]))
    lines.append("  FIX: %s" % HINTS[f["kind"]])
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", type=int, default=None, help="default: harness/level.txt")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--max-seconds", type=float, default=240.0)
    ap.add_argument("--case", help="JSON object, or path to a JSON file, with pattern and text")
    ap.add_argument("--json", help="write all failures to this file")
    ap.add_argument("--show", type=int, default=5, help="how many failures to print")
    ap.add_argument("--dump-failures", help="write failing case indices (engine-independent stream) to this JSON file")
    args = ap.parse_args(argv)

    check_python()
    level = args.level or current_level()
    engine = load_engine()

    if args.dump_failures:
        done, failed = dump_failures(engine, level, args.seed, args.iters, args.max_seconds, args.dump_failures)
        print("level %d seed %d: %d cases run, %d failing" % (level, args.seed, done, len(failed)))
        return 0

    if args.case:
        raw = args.case if args.case.lstrip().startswith("{") else open(args.case).read()
        case = json.loads(raw)
        f = run_case(engine, case["pattern"], case["text"], case.get("level", level))
        if f:
            f["level"] = case.get("level", level)
            print(describe(f))
            return 1
        print("OK: case passes")
        return 0

    failures = fuzz(engine, level, args.seed, args.iters, args.max_seconds)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(failures, fh, indent=1)
    if failures:
        print("%d distinct failure(s) at level %d (seed %d); smallest first:" % (len(failures), level, args.seed))
        for f in failures[: args.show]:
            print(describe(f))
        return 1
    print("OK: level %d, seed %d, %d patterns, engine agrees with re" % (level, args.seed, args.iters))
    return 0


if __name__ == "__main__":
    sys.exit(main())
