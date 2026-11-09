"""Backtracking matcher (continuation passing). May import nodes and parser."""
from . import nodes
from .parser import parse


def _in_class(ch, cls):
    hit = any(lo <= ch <= hi for lo, hi in cls.members)
    return hit != cls.neg


def _has_backref(node):
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, nodes.Backref):
            return True
        elif isinstance(cur, nodes.Group):
            stack.append(cur.node)
        elif isinstance(cur, nodes.Concat):
            stack.extend(cur.items)
        elif isinstance(cur, nodes.Alt):
            stack.extend(cur.branches)
        elif isinstance(cur, nodes.Repeat):
            stack.append(cur.node)
    return False


def _dedup(seq):
    """Remove duplicate (end, delta) entries, keeping first occurrence (priority order)."""
    seen = set()
    out = []
    for end, delta in seq:
        key = (end, frozenset(delta.items()))
        if key not in seen:
            seen.add(key)
            out.append((end, delta))
    return tuple(out)


def match(pattern: str, text: str):
    """Behave like re.match(pattern, text): anchored at index 0, leftmost-first backtracking."""
    ast = parse(pattern)
    n = len(text)
    has_backref = _has_backref(ast)

    def caps_key(caps):
        return frozenset(caps.items()) if has_backref else ()

    ends_memo = {}

    def ends(node, pos, caps):
        """All (end, delta) ways `node` matches at `pos`, in CPS priority order, deduplicated.

        `delta` is the captures this node sets (absolute positions); independent of the
        caller's `caps`, so results memoise on (node, pos, caps_key).
        """
        key = (id(node), pos, caps_key(caps))
        cached = ends_memo.get(key)
        if cached is not None:
            return cached
        result = _dedup(_ends(node, pos, caps))
        ends_memo[key] = result
        return result

    def _ends(node, pos, caps):
        t = type(node)
        if t is nodes.Empty:
            return ((pos, {}),)
        if t is nodes.Lit:
            return ((pos + 1, {}),) if pos < n and text[pos] == node.ch else ()
        if t is nodes.Dot:
            return ((pos + 1, {}),) if pos < n and text[pos] != "\n" else ()
        if t is nodes.CharClass:
            return ((pos + 1, {}),) if pos < n and _in_class(text[pos], node) else ()
        if t is nodes.Anchor:
            ok = pos == 0 if node.kind == "^" else pos == n
            return ((pos, {}),) if ok else ()
        if t is nodes.Backref:
            span = caps.get(node.ref)
            if span is None:
                return ()
            sub = text[span[0]:span[1]]
            return ((pos + len(sub), {}),) if text.startswith(sub, pos) else ()
        if t is nodes.Group:
            out = []
            for (p2, d2) in ends(node.node, pos, caps):
                out.append((p2, {**d2, node.number: (pos, p2)}))
            return tuple(out)
        if t is nodes.Alt:
            out = []
            for branch in node.branches:
                out.extend(ends(branch, pos, caps))
            return tuple(out)
        if t is nodes.Concat:
            def step(i, p, c, delta):
                if i == len(node.items):
                    return ((p, delta),)
                out = []
                seen = set()
                for (p2, d2) in ends(node.items[i], p, c):
                    nd = {**delta, **d2}
                    k = (p2, frozenset(nd.items()))
                    if k not in seen:
                        seen.add(k)
                        out.extend(step(i + 1, p2, {**c, **d2}, nd))
                return tuple(out)
            return step(0, pos, caps, {})
        if t is nodes.Repeat:
            def gen_more(count, p, c, last, forced):
                if node.max is not None and count >= node.max:
                    return ()
                out = []
                seen = set()
                import sys as _sys
                print("DBG gen_more count=",count,"p=",p,"c=",c,"last=",last,"forced=",forced,"ends=",ends(node.node,p,c), file=_sys.stderr)
                for (p2, d2) in ends(node.node, p, c):
                    nl = last if forced else p
                    k = (p2, frozenset({**c, **d2}.items()))
                    if k not in seen:
                        seen.add(k)
                        r = gen_loop(count + 1, p2, {**c, **d2}, nl)
                        print("DBG   iter p2=",p2,"d2=",d2,"->",r, file=_sys.stderr)
                        out.extend(r)
                return tuple(out)

            def gen_loop(count, p, c, last):
                if count < node.min:                      # must iterate: `last` unchanged
                    return gen_more(count, p, c, last, True)
                if p == last:                             # previous iteration was empty: stop
                    return ((p, c),)
                if node.lazy:
                    return _dedup(((p, c),) + gen_more(count, p, c, last, False))
                return _dedup(gen_more(count, p, c, last, False) + ((p, c),))
            return gen_loop(0, pos, caps, -1)
        raise TypeError(node)

    def m(node, pos, caps, k):
        """Match node at pos; call k(new_pos, new_caps) for each way, best first; first non-None wins."""
        for (end, delta) in ends(node, pos, caps):
            r = k(end, {**caps, **delta})
            if r is not None:
                return r
        return None

    def done(end, caps):
        return end, caps

    res = m(ast, 0, {}, done)
    import sys as _sys
    print("DBG ends(ast,0,{}) =", ends(ast, 0, {}), file=_sys.stderr)
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
