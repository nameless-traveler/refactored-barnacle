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
