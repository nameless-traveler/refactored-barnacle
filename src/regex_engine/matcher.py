"""Backtracking matcher (continuation passing). May import nodes and parser."""
from . import nodes
from .parser import parse


def _in_class(ch, cls):
    hit = any(lo <= ch <= hi for lo, hi in cls.members)
    return hit != cls.neg


def match(pattern: str, text: str):
    """Behave like re.match(pattern, text): anchored at index 0, leftmost-first backtracking."""
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
