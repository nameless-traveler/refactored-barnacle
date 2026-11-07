# AGENTS.md: a map, not a manual

Goal: `src/regex_engine/` implements `match(pattern, text)` so that it agrees with CPython's
`re.match` (Python 3.12). You write the engine yourself, with no `re` and no wrappers.

Read next, only as needed:
- [Architecture and layers](ARCHITECTURE.md)
- [Exact semantics and the Match type](docs/references/semantics.md)
- [Feature ladder: what each level adds](docs/exec-plans/active/feature-ladder.md)
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
2. Fix the engine; append the case to `tests/corpus.jsonl`.
3. Run `python tools/verify.py` until it prints VERIFY OK.
4. Update the feature ladder status. Do not commit or push; the harness does.
