# AGENTS.md: a map, not a manual

Goal: `src/regex_engine/` implements `match(pattern, text)` so that it agrees with CPython's
`re.match` (Python 3.12). You write the engine yourself, with no `re` and no wrappers.

Read next, only as needed:
- [Architecture and layers](ARCHITECTURE.md)
- [Exact semantics and the Match type](docs/references/semantics.md)
- [Feature ladder: what each level adds](docs/exec-plans/active/feature-ladder.md)
- [Matcher design: how to write the matcher so it is correct and does not time out](docs/design-docs/matcher-design.md)
- [Core beliefs](docs/design-docs/core-beliefs.md)
- [Known harness weaknesses](docs/exec-plans/tech-debt-tracker.md)

## Commands
```
python tools/verify.py                   # everything CI runs; "VERIFY OK" means done
python tools/fuzz.py --level N --seed S  # differential fuzz against re
python tools/fuzz.py --case '{"pattern": "a*", "text": "aa"}'
python tools/lint_arch.py
```

## Hard rules (enforced mechanically, errors tell you the fix)
- No `re`, `os`, `sys`, `subprocess`, `importlib`, `eval`, `exec` in `src/`.
- Layers only import downward: nodes < parser < matcher < `__init__`.
- Files under 400 lines. This file stays under 120.
- Never edit paths listed in `harness/protected.txt`.

## Working on an issue
1. Reproduce with the `--case` command in the issue.
2. Fix the engine. If the matcher times out or is hard to patch, rewrite it the way
   `docs/design-docs/matcher-design.md` describes instead of patching around it.
3. Run `python tools/verify.py` until it prints VERIFY OK. It passes when the issue's case is fixed and
   nothing that worked before broke; failures that exist on main and are unrelated are not your job.
4. Do not edit `tests/corpus.jsonl` (the harness records the issue's case itself), docs, or protected paths.
   Do not commit or push; the harness does.

## Do not waste requests
- If an edit tool call fails twice on the same file, stop editing in pieces: rewrite the whole function
  or file in one go.
- If two serious approaches have both failed, stop and say what you learned. The harness pauses itself
  after repeated failures and a human looks at it; extra attempts only burn quota.
