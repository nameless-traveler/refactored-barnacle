# Matcher design: continuation-passing backtracking

Why this exists: an earlier matcher listed *every* possible end position of every sub-pattern and
memoised on the captured groups. That is exponential on nested repeats (`(a*)*`, `(a|b*)*`) and timed out.
Do **not** enumerate all matches. Real `re` is leftmost-first: take the first way that works, in priority
order, and stop. That is also the simplest design.

## The idea

`m(node, pos, caps, k)` tries to match `node` at `pos`. For each way it can match, in preference order, it
calls the continuation `k(new_pos, new_caps)` ("what must match after this"). The first non-`None` answer
wins and is returned all the way up. Returning `None` means "this way failed, backtrack".

- `caps` is an **immutable** dict `{group_number: (start, end)}`. Make a new dict when a group closes
  (`{**caps, n: (start, end)}`). Backtracking then restores captures for free.
- Concat: match item 0, with a continuation that matches item 1, and so on; the last continuation is `k`.
- Alt: try each branch in order with the same `k`; the first non-`None` result wins (this gives `a|ab` on
  `ab` -> `a`).
- Group: match the inner node, and in the continuation record `(start, end)` before calling `k`.
- Repeat: a small `loop(count, pos, caps, last)`; see the rules below.

## Repeat rules (checked against CPython by experiment)

- Below `min` you must iterate. At or above `min`: greedy tries one more iteration first and then stops
  (`k`); lazy tries stopping first and then one more iteration. Respect `max`.
- **Empty-iteration guard:** do not start another iteration if the previous iteration started at the same
  position it ended (it matched the empty string). The empty iteration is still kept, with its captures,
  and the loop then just continues with `k`.
  - `(a*)*` on `aab` -> group 1 is `''` (the final empty iteration overwrites `aa`).
  - `(a?)*` on `aa` -> group 1 is `''`.
  - `(a*?)*` on `aa` -> matches `''`, group 1 is `''`.
  - `(a*)*?b` on `aaab` -> group 1 is `aaa` (lazy outer: try `b` first).
- Groups inside a repeat keep their value from earlier iterations unless a later iteration sets them:
  `(?:(a)|b)*` on `ab` -> group 1 is `a`.
- A group that did not take part is `None`; a backreference to such a group fails.

## Reference implementation (fuzzed against `re`: level 10, 3 seeds x 1500 patterns, no differences)

Use it as is, or write your own along the same lines. Keep it small: no memo tables, no result lists.

```python
"""Backtracking matcher (continuation passing). May import nodes and parser."""
from . import nodes
from .parser import parse


def _in_class(ch, cls):
    hit = any(lo <= ch <= hi for lo, hi in cls.members)
    return hit != cls.neg


def match(pattern: str, text: str):
    ast = parse(pattern)
    n = len(text)

    def m(node, pos, caps, k):
        """Match node at pos; call k(new_pos, new_caps) for each way, best first; return the first non-None."""
        t = type(node)
        if t is nodes.Empty:
            return k(pos, caps)
        if t is nodes.Lit:
            return k(pos + 1, caps) if pos < n and text[pos] == node.ch else None
        if t is nodes.Dot:
            return k(pos + 1, caps) if pos < n and text[pos] != "\n" else None
        if t is nodes.CharClass:
            return k(pos + 1, caps) if pos < n and _in_class(text[pos], node) else None
        if t is nodes.Anchor:
            ok = pos == 0 if node.kind == "^" else pos == n
            return k(pos, caps) if ok else None
        if t is nodes.Backref:
            span = caps.get(node.ref)
            if span is None:
                return None
            sub = text[span[0]:span[1]]
            return k(pos + len(sub), caps) if text.startswith(sub, pos) else None
        if t is nodes.Group:
            return m(node.node, pos, caps, lambda p, c: k(p, {**c, node.number: (pos, p)}))
        if t is nodes.Alt:
            for branch in node.branches:
                r = m(branch, pos, caps, k)
                if r is not None:
                    return r
            return None
        if t is nodes.Concat:
            def step(i, p, c):
                if i == len(node.items):
                    return k(p, c)
                return m(node.items[i], p, c, lambda p2, c2: step(i + 1, p2, c2))
            return step(0, pos, caps)
        if t is nodes.Repeat:
            def loop(count, p, c, last):
                def more():
                    if node.max is not None and count >= node.max:
                        return None
                    return m(node.node, p, c, lambda p2, c2: loop(count + 1, p2, c2, p))
                if count < node.min:                      # must iterate: no choice
                    return m(node.node, p, c, lambda p2, c2: loop(count + 1, p2, c2, p))
                if p == last:                             # previous iteration was empty: stop looping
                    return k(p, c)
                if node.lazy:
                    r = k(p, c)
                    return r if r is not None else more()
                r = more()
                return r if r is not None else k(p, c)
            return loop(0, pos, caps, -1)
        raise TypeError(node)

    def done(end, caps):
        return end, caps

    res = m(ast, 0, {}, done)
    if res is None:
        return None
    end, caps = res
    return nodes.Match(0, end, tuple(caps.get(i) for i in range(1, _ngroups(ast) + 1)))


def _ngroups(node):
    best, stack = 0, [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, nodes.Group):
            best = max(best, cur.number)
            stack.append(cur.node)
        elif isinstance(cur, nodes.Concat):
            stack.extend(cur.items)
        elif isinstance(cur, nodes.Alt):
            stack.extend(cur.branches)
        elif isinstance(cur, nodes.Repeat):
            stack.append(cur.node)
    return best
```

## Debugging checklist

1. Reproduce with `python tools/fuzz.py --case '{"pattern": ..., "text": ...}'`.
2. To see what `re` does, write a scratch script **outside `src/`** (`re` is allowed there, never in `src/`).
3. Wrong captures: check you copy `caps` instead of mutating it, and the empty-iteration rule above.
4. Timeouts: look for a loop that can run again without consuming text, or code that builds lists of all matches.
5. Deep recursion is not a problem here: fuzz texts are at most 7 characters.
