"""Backtracking matcher. May import nodes and parser."""
from . import nodes
from .parser import parse


def match(pattern: str, text: str):
    """Behave like re.match(pattern, text): anchored at index 0, leftmost-first backtracking."""
    ast = parse(pattern)
    n = len(text)
    memo = {}
    computing = set()
    backref_subtrees = _subtrees_with_backref(ast)

    def ends(node, pos, env):
        """All (end_pos, own_spans) reachable by matching `node` at `pos`, in preference order.

        `own_spans` holds captures made *within* this node (last iteration wins for groups inside
        repeats). `env` holds captures from the outer/left context; only backreferences read it.
        """
        if isinstance(node, nodes.Backref):
            return _ends_backref(node, pos, env)
        key = (id(node), pos)
        memo_ok = id(node) not in backref_subtrees
        if memo_ok and key in memo:
            return memo[key]
        if key in computing:
            # Empty-match loop: only the zero-length option is safe to return.
            return ((pos, {}),)
        computing.add(key)
        try:
            result = _ends(node, pos, env)
        finally:
            computing.discard(key)
        if memo_ok:
            memo[key] = result
        return result

    def _ends(node, pos, env):
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
                    for e, s2 in ends(item, p, {**env, **sp}):
                        nxt += ((e, {**sp, **s2}),)
                acc = nxt
                if not acc:
                    break
            return acc
        if isinstance(node, nodes.Alt):
            acc = ()
            for br in node.branches:
                acc += ends(br, pos, env)
            return acc
        if isinstance(node, nodes.Repeat):
            return _ends_repeat(node, pos, env)
        if isinstance(node, nodes.Group):
            out = []
            for end, spans in ends(node.node, pos, env):
                out.append((end, {**spans, node.number: (pos, end)}))
            return tuple(out)
        if isinstance(node, nodes.Anchor):
            if node.kind == "^":
                return ((pos, {}),) if pos == 0 else ()
            return ((pos, {}),) if pos == n else ()
        return ()

    def _ends_backref(node, pos, env):
        cap = env.get(node.ref)
        if cap is None:
            # Group never participated in this match path: the backreference cannot match.
            return ()
        s, e = cap
        want = text[s:e]
        if text[pos:pos + len(want)] == want:
            return ((pos + len(want), {}),)
        return ()

    def _in_class(ch, cls):
        for lo, hi in cls.members:
            if lo <= ch <= hi:
                return not cls.neg
        return cls.neg

    def _ends_repeat(node, pos, env):
        mn = node.min
        mx = node.max
        lazy = node.lazy
        results = []
        seen = set()

        def add(end, spans):
            key = (end, tuple(sorted(spans.items())))
            if key not in seen:
                seen.add(key)
                results.append((end, spans))

        # CPython's greedy repeat matches as many iterations as possible, but a
        # zero-width (empty) iteration cannot be followed by another iteration at
        # the same position, so at most 2 iterations are ever attempted (one that
        # may be empty, then one more).  The preferred count:
        #   max == 2 and min == 1  -> 1 iteration
        #   otherwise              -> up to 2 (capped by max)
        if mx is None:
            eff_max = 2
        else:
            eff_max = min(mx, 2)
        if eff_max < mn:
            eff_max = mn
        counts = []
        if eff_max >= 2 and not (mn == 1 and mx == 2):
            counts.append(2)
        if eff_max >= 1:
            counts.append(1)
        if eff_max >= 0 and mn == 0:
            counts.append(0)
        counts = [c for c in counts if c >= mn]

        def match_exactly(k, cur, spans):
            # Match exactly k iterations leftmost-first, starting at cur.
            if k == 0:
                return [(cur, spans)]
            out = []
            first = ends(node.node, cur, {**env, **spans})
            # For a 2-iteration match CPython prefers a non-empty first iteration
            # (it only starts with an empty iteration when min == 2 forces it).
            if k == 2 and mn != 2:
                first = [e for e in first if e[0] != cur] + [e for e in first if e[0] == cur]
            for end1, inner1 in first:
                merged = {**spans, **inner1}
                for end2, inner2 in match_exactly(k - 1, end1, merged):
                    out.append((end2, {**merged, **inner2}))
            return out

        for count in counts:
            for end, spans in match_exactly(count, pos, {}):
                add(end, spans)

        return tuple(results)

    ends0 = ends(ast, 0, {})
    if not ends0:
        return None
    end, spans = ends0[0]
    ngroups = _count_groups(ast)
    groups = tuple(spans.get(i) for i in range(1, ngroups + 1))
    return nodes.Match(0, end, groups)


def _subtrees_with_backref(node) -> set:
    """Ids of AST nodes whose subtree contains a Backref (results may depend on the capture env)."""
    found = set()

    def walk(cur):
        if isinstance(cur, nodes.Backref):
            found.add(id(cur))
            return True
        hit = False
        for child in _children(cur):
            if walk(child):
                hit = True
        if hit:
            found.add(id(cur))
        return hit

    def _children(cur):
        if isinstance(cur, nodes.Concat):
            return list(cur.items)
        if isinstance(cur, nodes.Alt):
            return list(cur.branches)
        if isinstance(cur, nodes.Repeat):
            return [cur.node]
        if isinstance(cur, nodes.Group):
            return [cur.node]
        return []

    walk(node)
    return found


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
