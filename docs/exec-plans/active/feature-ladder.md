# Feature ladder

`harness/level.txt` holds the current level. The finder raises it by one when the engine is clean at
the current level, so difficulty ramps up without a human. Each level includes all earlier ones.

| Level | Adds | Status |
|---|---|---|
| 1 | literals `a b c`, concatenation, empty pattern | done |
| 2 | `.` | done |
| 3 | greedy `*` `+` `?` | done |
| 4 | alternation `|`, groups `( )` | done |
| 5 | classes `[ab]` `[^a]` `[a-c]` | todo |
| 6 | anchors `^` `$` | todo |
| 7 | counted repeats `{m}` `{m,}` `{m,n}` | done |
| 8 | lazy quantifiers `*?` `+?` `??` `{m,n}?` | done |
| 9 | capture group spans compared | done |
| 10 | backreferences `\1`..`\9` | todo |

Level 9 is the hardest to match exactly: CPython has specific behaviour for groups inside repeats that
match empty. Expect the agent to need several attempts there.

Update the Status column when a level's issues are all closed.
