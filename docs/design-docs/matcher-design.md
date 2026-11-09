# Matcher design: continuation-passing backtracking

Why this exists: an earlier matcher listed *every* possible end position of every sub-pattern and
memoised on the captured groups. That is exponential on nested repeats (`(a*)*`, `(a|b*)*`) and timed out.
Do **not** enumerate all matches. Real `re` is leftmost-first: take the first way that works, in priority
order, and stop. That is also the simplest design.

## The idea

`m(node, pos, caps, k, kid)` tries to match `node` at `pos` (`kid` only names `k` for the failure cache; see
"Why it does not blow up" below). For each way it can match, in preference order, it
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
- **Empty-iteration guard:** an *optional* iteration (one beyond `min`) is not started if the previous
  optional iteration began at the same position it is now at (it matched the empty string). The empty
  iteration is still kept, with its captures, and the loop then just continues with `k`.
  **Forced iterations (`count < min`) never update that remembered position**: pass `last` through unchanged
  and set it only when you start an optional iteration (this is the `more()` branch in the code below).
  - `(a*)*` on `aab` -> group 1 is `''` (the final empty iteration overwrites `aa`).
  - `(a?)*` on `aa` -> group 1 is `''`.
  - `(a*?)*` on `aa` -> matches `''`, group 1 is `''`.
  - `(a*)*?b` on `aaab` -> group 1 is `aaa` (lazy outer: try `b` first).
  - `([c]??a?){1,2}a(.{1})?` on `ca` -> group 2 is `c`, span `(0, 1)`. The forced first iteration is empty,
    and a second, optional iteration is still allowed to start at the same position.
- Groups inside a repeat keep their value from earlier iterations unless a later iteration sets them:
  `(?:(a)|b)*` on `ab` -> group 1 is `a`.
- A group that did not take part is `None`; a backreference to such a group fails.

## Reference implementation (this is the engine's matcher; tested on 14 seeds at level 10 and on levels 1-9)

Use it as is, or write your own along the same lines. Keep the failure cache; do not build lists of all matches.

```python
"""Backtracking matcher (continuation passing). May import nodes and parser."""
from . import nodes
from .parser import parse


def _in_class(ch, cls):
    hit = any(lo <= ch <= hi for lo, hi in cls.members)
    return hit != cls.neg


def simplify(node):
    """Semantics-preserving clean-up: X{0} -> Empty, X{1} -> X, drop Empty items in a Concat."""
    t = type(node)
    if t is nodes.Group:
        return nodes.Group(simplify(node.node), node.number)
    if t is nodes.Alt:
        return nodes.Alt(tuple(simplify(b) for b in node.branches))
    if t is nodes.Concat:
        items = tuple(i for i in (simplify(i) for i in node.items) if type(i) is not nodes.Empty)
        if not items:
            return nodes.Empty()
        return items[0] if len(items) == 1 else nodes.Concat(items)
    if t is nodes.Repeat:
        if node.max == 0:
            return nodes.Empty()
        body = simplify(node.node)
        if node.min == 1 and node.max == 1:
            return body
        return nodes.Repeat(body, node.min, node.max, node.lazy)
    return node


def _has_backref(node):
    stack = [node]
    while stack:
        cur = stack.pop()
        t = type(cur)
        if t is nodes.Backref:
            return True
        if t is nodes.Group or t is nodes.Repeat:
            stack.append(cur.node)
        elif t is nodes.Concat:
            stack.extend(cur.items)
        elif t is nodes.Alt:
            stack.extend(cur.branches)
    return False


def match(pattern: str, text: str):
    ast = parse(pattern)
    ngroups = _ngroups(ast)
    ast = simplify(ast)
    n = len(text)
    backrefs = _has_backref(ast)
    ids = {}        # interning: (tuple describing "what must match next") -> small int
    failed = set()  # states already known to fail: the same state can never succeed later

    def kid_of(*key):
        v = ids.get(key)
        if v is None:
            v = ids[key] = len(ids) + 1
        return v

    def m(node, pos, caps, k, kid):
        """Match node at pos, then call k(new_pos, new_caps). `kid` names the continuation k (0 = nothing left)."""
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
        # composite node: skip it if the very same state already failed
        key = (id(node), pos, kid, tuple(sorted(caps.items())) if backrefs else None)
        if key in failed:
            return None
        res = composite(node, t, pos, caps, k, kid)
        if res is None:
            failed.add(key)
        return res

    def composite(node, t, pos, caps, k, kid):
        if t is nodes.Group:
            gk = kid_of("G", id(node), kid, pos if backrefs else 0)
            return m(node.node, pos, caps, lambda p, c: k(p, {**c, node.number: (pos, p)}), gk)
        if t is nodes.Alt:
            for branch in node.branches:
                r = m(branch, pos, caps, k, kid)
                if r is not None:
                    return r
            return None
        if t is nodes.Concat:
            items = node.items

            def step(i, p, c):
                if i == len(items):
                    return k(p, c)
                return m(items[i], p, c, lambda p2, c2: step(i + 1, p2, c2), kid_of("C", id(node), i + 1, kid))
            return step(0, pos, caps)
        if t is nodes.Repeat:
            def loop(count, p, c, last):
                lkey = ("loop", id(node), count if node.max is not None else min(count, node.min), p, last, kid,
                        tuple(sorted(c.items())) if backrefs else None)
                if lkey in failed:
                    return None
                r = loop_body(count, p, c, last)
                if r is None:
                    failed.add(lkey)
                return r

            def next_kid(count, last):
                return kid_of("L", id(node), count if node.max is not None else min(count, node.min), last, kid)

            def loop_body(count, p, c, last):
                def more():
                    if node.max is not None and count >= node.max:
                        return None
                    return m(node.node, p, c, lambda p2, c2: loop(count + 1, p2, c2, p), next_kid(count + 1, p))
                if count < node.min:                      # must iterate; `last` is NOT updated here
                    return m(node.node, p, c, lambda p2, c2: loop(count + 1, p2, c2, last), next_kid(count + 1, last))
                if p == last:                             # previous optional iteration was empty: stop looping
                    return k(p, c)
                if node.lazy:
                    r = k(p, c)
                    return r if r is not None else more()
                r = more()
                return r if r is not None else k(p, c)
            return loop(0, pos, caps, -1)
        raise TypeError(node)

    res = m(ast, 0, {}, lambda end, caps: (end, caps), 0)
    if res is None:
        return None
    end, caps = res
    return nodes.Match(0, end, tuple(caps.get(i) for i in range(1, ngroups + 1)))


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

## Why it does not blow up: remember failed states

Plain backtracking is exponential on stacked, ambiguous repeats such as `((x*)*)*` or
`(((.*b{0,}){2,}){0,}|a){2,}`. CPython's `re` is also exponential there, but it is C code about 50x faster, so it
finishes inside the 0.5 s limit and a plain Python version does not. Measured on four such issues (#20, #25, #26, #27),
the plain version took 0.2 to 2.2 s per case; with the two steps below the same cases take about 1 ms.

1. `simplify()` first: `X{0}` becomes `Empty`, `X{1}` becomes `X`, empty items leave a Concat. This alone only
   saves 10-25%.
2. Remember failures. A state is `(node, position, what must match next, captures if the pattern has a backreference)`.
   If a state failed once it fails every time, so the second visit returns `None` at once. Only failures are
   remembered, never successes.
   - `kid` is a small integer that names "what must match next" (the continuation). Build it with `kid_of(...)` from
     the node, the item index or loop counter, and the outer `kid`; the same description always gives the same number.
   - The key must hold **everything that decides whether the rest can match**: the position, the continuation, the
     loop count (for a repeat with a `max`; for `max=None` only `min(count, min)` matters), the remembered `last`, and,
     only when the pattern has a backreference, the captures and the group's start position. Leaving one out is the
     classic bug: a wrong cached failure makes a correct match disappear.
   - Without backreferences the captures cannot change whether the rest matches, so leaving them out of the key is what
     makes the cache effective.

## Debugging checklist

1. Reproduce with `python tools/fuzz.py --case '{"pattern": ..., "text": ...}'`.
2. To see what `re` does, write a scratch script **outside `src/`** (`re` is allowed there, never in `src/`).
3. Wrong captures: check you copy `caps` instead of mutating it, and the empty-iteration rule above.
4. Timeouts: look for a loop that can run again without consuming text, or code that builds lists of all matches.
5. Deep recursion is not a problem here: fuzz texts are at most 7 characters.
