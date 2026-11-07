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
        """All end positions reachable by matching `node` at `pos`, in preference order."""
        key = (id(node), pos)
        if key in memo:
            return memo[key]
        if key in computing:
            # Empty-match loop: only the zero-length option is safe to return.
            return (pos,)
        computing.add(key)
        try:
            result = _ends(node, pos)
        finally:
            computing.discard(key)
        memo[key] = result
        return result

    def _ends(node, pos):
        if isinstance(node, nodes.Empty):
            return (pos,)
        if isinstance(node, nodes.Lit):
            if pos < n and text[pos] == node.ch:
                return (pos + 1,)
            return ()
        if isinstance(node, nodes.Dot):
            if pos < n and text[pos] != "\n":
                return (pos + 1,)
            return ()
        if isinstance(node, nodes.CharClass):
            if pos < n and _in_class(text[pos], node):
                return (pos + 1,)
            return ()
        if isinstance(node, nodes.Concat):
            acc = (pos,)
            for item in node.items:
                nxt = ()
                for p in acc:
                    nxt += ends(item, p)
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
            return ends(node.node, pos)
        if isinstance(node, nodes.Anchor):
            if node.kind == "^":
                return (pos,) if pos == 0 else ()
            return (pos,) if pos == n else ()
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

        def add(e):
            if e not in seen:
                seen.add(e)
                results.append(e)

        def dfs(cur, count):
            # Greedy leftmost-first backtracking: try to extend (more iterations)
            # before settling, trying the subpattern's ends in preference order.
            # An empty match counts as an iteration; it terminates the repeat once
            # the minimum is satisfied (extra phase), but still counts toward min.
            if mx is None or count < mx:
                for e in ends(node.node, cur):
                    if e == cur:
                        nc = count + 1
                        if nc >= mn:
                            # Extra phase: an empty match terminates the repeat.
                            add(cur)
                        else:
                            # Still satisfying the minimum: keep iterating at cur.
                            dfs(cur, nc)
                    else:
                        nc = count + 1
                        dfs(e, nc)
                        if nc >= mn:
                            add(e)
            # Stopping here with `count` iterations is a valid (backtrack) option.
            if count >= mn:
                add(cur)

        dfs(pos, 0)
        return tuple(results)

    ends0 = ends(ast, 0)
    if not ends0:
        return None
    return nodes.Match(0, ends0[0])
