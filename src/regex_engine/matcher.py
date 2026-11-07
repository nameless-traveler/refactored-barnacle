"""Backtracking matcher. May import nodes and parser."""
from . import nodes
from .parser import parse


def match(pattern: str, text: str):
    """Behave like re.match(pattern, text): anchored at index 0, leftmost-first backtracking."""
    ast = parse(pattern)
    n = len(text)
    computing = set()

    def ends(node, pos, spans):
        """All (end, new_spans) reachable by matching `node` at `pos`, in preference order.

        `spans` is the capture map accumulated so far; `new_spans` is the merged map after
        this node's captures. Backreferences consult `spans` for previously captured text.
        """
        key = (id(node), pos)
        if key in computing:
            # Empty-match loop: only the zero-length option is safe to return.
            return ((pos, spans),)
        computing.add(key)
        try:
            result = _ends(node, pos, spans)
        finally:
            computing.discard(key)
        return result

    def _ends(node, pos, spans):
        if isinstance(node, nodes.Empty):
            return ((pos, spans),)
        if isinstance(node, nodes.Lit):
            if pos < n and text[pos] == node.ch:
                return ((pos + 1, spans),)
            return ()
        if isinstance(node, nodes.Dot):
            if pos < n and text[pos] != "\n":
                return ((pos + 1, spans),)
            return ()
        if isinstance(node, nodes.CharClass):
            if pos < n and _in_class(text[pos], node):
                return ((pos + 1, spans),)
            return ()
        if isinstance(node, nodes.Concat):
            acc = ((pos, spans),)
            for item in node.items:
                nxt = ()
                for p, sp in acc:
                    for e, s2 in ends(item, p, sp):
                        nxt += ((e, s2),)
                acc = nxt
                if not acc:
                    break
            return acc
        if isinstance(node, nodes.Alt):
            acc = ()
            for br in node.branches:
                acc += ends(br, pos, spans)
            return acc
        if isinstance(node, nodes.Repeat):
            return _ends_repeat(node, pos, spans)
        if isinstance(node, nodes.Group):
            out = []
            for end, s2 in ends(node.node, pos, spans):
                out.append((end, {**s2, node.number: (pos, end)}))
            return tuple(out)
        if isinstance(node, nodes.Anchor):
            if node.kind == "^":
                return ((pos, spans),) if pos == 0 else ()
            return ((pos, spans),) if pos == n else ()
        if isinstance(node, nodes.Backref):
            return _ends_backref(node, pos, spans)
        return ()

    def _ends_backref(node, pos, spans):
        captured = spans.get(node.ref)
        if captured is None:
            return ()
        start, end = captured
        length = end - start
        if text[pos:pos + length] == text[start:end]:
            return ((pos + length, spans),)
        return ()

    def _in_class(ch, cls):
        for lo, hi in cls.members:
            if lo <= ch <= hi:
                return not cls.neg
        return cls.neg

    def _ends_repeat(node, pos, spans):
        mn = node.min
        mx = node.max
        lazy = node.lazy
        results = []
        seen = set()

        def add(end, s2):
            if end not in seen:
                seen.add(end)
                results.append((end, s2))

        def dfs(cur, count, s2):
            if lazy:
                if count >= mn:
                    add(cur, s2)
                if mx is None or count < mx:
                    for end, inner in ends(node.node, cur, s2):
                        merged = {**s2, **inner}
                        if end == cur:
                            nc = count + 1
                            if nc >= mn:
                                add(cur, merged)
                            else:
                                dfs(cur, nc, merged)
                        else:
                            nc = count + 1
                            dfs(end, nc, merged)
                            if nc >= mn:
                                add(end, merged)
            else:
                if mx is None or count < mx:
                    for end, inner in ends(node.node, cur, s2):
                        merged = {**s2, **inner}
                        if end == cur:
                            nc = count + 1
                            if nc >= mn:
                                add(cur, merged)
                            else:
                                dfs(cur, nc, merged)
                        else:
                            nc = count + 1
                            dfs(end, nc, merged)
                            if nc >= mn:
                                add(end, merged)
                if count >= mn:
                    add(cur, s2)

        dfs(pos, 0, spans)
        return tuple(results)

    ends0 = ends(ast, 0, {})
    if not ends0:
        return None
    end, spans = ends0[0]
    ngroups = _count_groups(ast)
    groups = tuple(spans.get(i) for i in range(1, ngroups + 1))
    return nodes.Match(0, end, groups)


def _count_groups(node) -> int:
    """Total number of capturing groups opened in the AST."""
    best = 0
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, nodes.Group):
            if cur.number > best:
                best = cur.number
            stack.append(cur.node)
        elif isinstance(cur, nodes.Concat):
            stack.extend(cur.items)
        elif isinstance(cur, nodes.Alt):
            stack.extend(cur.branches)
        elif isinstance(cur, nodes.Repeat):
            stack.append(cur.node)
    return best
