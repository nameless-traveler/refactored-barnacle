# Architecture

```
src/regex_engine/
  nodes.py     pattern AST types              (lowest layer; imports nothing from the package)
  parser.py    pattern string -> nodes        (may import nodes)
  matcher.py   backtracking matcher           (may import nodes, parser)
  __init__.py  public `match()` + `Match`     (may import everything below)
```

Dependencies point downward only. `tools/lint_arch.py` enforces this and prints how to fix violations.
Other helper modules are allowed; the order above applies to the four named ones.

Why a layered design for a small engine: with agents writing the code, strict boundaries are what let many
small changes land without the structure decaying. Constraints are enforced centrally; how each module is
written inside its layer is up to the agent.

The oracle is CPython 3.12 `re`, exercised by `tools/fuzz.py`. See `docs/references/semantics.md`.
