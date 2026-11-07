# Contract

`match(pattern, text)` must behave exactly like `re.match(pattern, text)` on CPython 3.12:
- Anchored at index 0 (not a search, not a full match).
- Returns `None` when `re.match` returns `None`.
- Otherwise returns `Match(start, end, groups)`. `groups` is only compared from level 9 up: one entry per
  capture group in order of the opening parenthesis, `(start, end)` or `None` if the group did not participate.
- Backtracking, **leftmost-first** (Perl style), not POSIX leftmost-longest. `a|ab` on `"ab"` matches `"a"`.
- Alphabet for fuzzing is `abc`; texts are up to 7 characters; no newlines.
- Every call must finish within 0.5 s. Loops that make no progress on empty matches (`(a*)*`) must terminate.

All syntax is capturing groups only. Unsupported or invalid patterns never occur in the fuzzer: it only
generates patterns that `re.compile` accepts.
