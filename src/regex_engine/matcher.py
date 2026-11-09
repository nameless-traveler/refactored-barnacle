"""Backtracking matcher (continuation passing). May import nodes and parser."""
from . import nodes
from .parser import parse


def _in_class(ch, cls):
    hit = any(lo <= ch <= hi for lo, hi in cls.members)
    return hit != cls.neg


def _min_width(node):
    t = type(node)
    if t is nodes.Empty:
        return 0
    if t is nodes.Lit:
        return 1
    if t is nodes.Dot:
        return 1
    if t is nodes.CharClass:
        return 1
    if t is nodes.Anchor:
        return 0
    if t is nodes.Backref:
        return 0
    if t is nodes.Group:
        return _min_width(node.node)
    if t is nodes.Alt:
        return min(_min_width(b) for b in node.branches)
    if t is nodes.Concat:
        return sum(_min_width(i) for i in node.items)
    if t is nodes.Repeat:
        return node.min * _min_width(node.node)
    raise TypeError(node)


def match(pattern: str, text: str):
    ast = parse(pattern)
    n = len(text)
    if n < _min_width(ast):
        return None
    fail_memo = {}
    def _fail(node, pos, caps, key):
        fail_memo[key] = None
        return None
    def m(node, pos, caps, k):
        t = type(node)
        if t is nodes.Empty:
            return k(pos, caps)
        if t is nodes.Lit:
            key = (id(node), pos)
            if key in fail_memo:
                return None
            if pos < n and text[pos] == node.ch:
                return k(pos + 1, caps)
            return _fail(node, pos, caps, key)
        if t is nodes.Dot:
            key = (id(node), pos)
            if key in fail_memo:
                return None
            if pos < n and text[pos] != "\n":
                return k(pos + 1, caps)
            return _fail(node, pos, caps, key)
        if t is nodes.CharClass:
            key = (id(node), pos)
            if key in fail_memo:
                return None
            if pos < n and _in_class(text[pos], node):
                return k(pos + 1, caps)
            return _fail(node, pos, caps, key)
        if t is nodes.Anchor:
            key = (id(node), pos)
            if key in fail_memo:
                return None
            ok = pos == 0 if node.kind == "^" else pos == n
            if ok:
                return k(pos, caps)
            return _fail(node, pos, caps, key)
        if t is nodes.Backref:
            key = (id(node), pos, caps.get(node.ref))
            if key in fail_memo:
                return None
            span = caps.get(node.ref)
            if span is None:
                return _fail(node, pos, caps, key)
            sub = text[span[0]:span[1]]
            if text.startswith(sub, pos):
                return k(pos + len(sub), caps)
            return _fail(node, pos, caps, key)
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
                if count < node.min:
                    return m(node.node, p, c, lambda p2, c2: loop(count + 1, p2, c2, last))
                if p == last:
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
