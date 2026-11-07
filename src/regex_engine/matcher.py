"""Backtracking matcher. May import nodes and parser."""
from . import nodes
from .parser import parse


def match(pattern: str, text: str):
    """Behave like re.match(pattern, text): anchored at index 0, leftmost-first backtracking."""
    ast = parse(pattern)
    n = len(text)
    memo = {}
    computing = set()

    def ends(node, pos):
        """All (end_pos, spans) reachable by matching `node` at `pos`, in preference order.

        `spans` maps a capture-group number to the (start, end) of its last participation
        within this sub-match (last iteration wins for groups inside repeats).
        """
        key = (id(node), pos)
        if key in memo:
            return memo[key]
        if key in computing:
            # Empty-match loop: only the zero-length option is safe to return.
            return ((pos, {}),)
        computing.add(key)
        try:
            result = _ends(node, pos)
        finally:
            computing.discard(key)
        memo[key] = result
        return result

    def _ends(node, pos):
        if isinstance(node, nodes.Empty):
            return ((pos, {}),)
        if isinstance(node, nodes.Lit):
            if pos < n and text[pos] == node.ch:
                return ((pos + 1, {}),)
            return ()
        if isinstance(node, nodes.Dot):
            if pos < n and text[pos] != "\n":
                return ((pos + 1, {}),)
            return ()
        if isinstance(node, nodes.CharClass):
            if pos < n and _in_class(text[pos], node):
                return ((pos + 1, {}),)
            return ()
        if isinstance(node, nodes.Concat):
            acc = ((pos, {}),)
            for item in node.items:
                nxt = ()
                for p, sp in acc:
                    for e, s2 in ends(item, p):
                        nxt += ((e, {**sp, **s2}),)
                acc = nxt
                if not acc:
                    break
            return acc
        if isinstance(node, nodes.Alt):
            acc = ()
            for br in node.branches:
                acc += ends(br, pos)
            return acc
        if isinstance(node, nodes.Repeat):
            return _ends_repeat(node, pos)
        if isinstance(node, nodes.Group):
            out = []
            for end, spans in ends(node.node, pos):
                out.append((end, {**spans, node.number: (pos, end)}))
            return tuple(out)
        if isinstance(node, nodes.Anchor):
            if node.kind == "^":
                return ((pos, {}),) if pos == 0 else ()
            return ((pos, {}),) if pos == n else ()
        if isinstance(node, nodes.Backref):
            return ()
        return ()

    def _in_class(ch, cls):
        for lo, hi in cls.members:
            if lo <= ch <= hi:
                return not cls.neg
        return cls.neg

    def _ends_repeat(node, pos):
        mn = node.min
        mx = node.max
        lazy = node.lazy
        results = []
        seen = set()

        def add(end, spans):
            if end not in seen:
                seen.add(end)
                results.append((end, spans))

        def dfs(cur, count, spans):
            if lazy:
                # Lazy (leftmost-first): prefer fewer iterations first.
                if count >= mn:
                    add(cur, spans)
                if mx is None or count < mx:
                    for end, inner in ends(node.node, cur):
                        merged = {**spans, **inner}
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
                # Greedy: prefer more iterations first.
                if mx is None or count < mx:
                    for end, inner in ends(node.node, cur):
                        merged = {**spans, **inner}
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
                # Stopping here with `count` iterations is a valid (backtrack) option.
                if count >= mn:
                    add(cur, spans)

        dfs(pos, 0, {})
        return tuple(results)

    ends0 = ends(ast, 0)
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
