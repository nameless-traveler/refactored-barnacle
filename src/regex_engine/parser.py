"""Parser: pattern string -> AST nodes. May import nodes."""
from . import nodes


class _Parser:
    def __init__(self, s: str):
        self.s = s
        self.i = 0
        self.opened = 0
        self.closed: list = []

    def peek(self) -> str:
        if self.i < len(self.s):
            return self.s[self.i]
        return ""

    def parse(self) -> nodes.Node:
        node = self._alt()
        return node

    def _alt(self) -> nodes.Node:
        branches = [self._seq()]
        while self.peek() == "|":
            self.i += 1
            branches.append(self._seq())
        if len(branches) == 1:
            return branches[0]
        return nodes.Alt(tuple(branches))

    def _seq(self) -> nodes.Node:
        items = []
        while self.peek() and self.peek() not in "|)":
            items.append(self._item())
        if not items:
            return nodes.Empty()
        if len(items) == 1:
            return items[0]
        return nodes.Concat(tuple(items))

    def _item(self) -> nodes.Node:
        node = self._atom()
        q = self._quant()
        if q is None:
            return node
        mn, mx, lazy = q
        return nodes.Repeat(node=node, min=mn, max=mx, lazy=lazy)

    def _atom(self) -> nodes.Node:
        c = self.peek()
        if c == "":
            return nodes.Empty()
        if c in "abc":
            self.i += 1
            return nodes.Lit(ch=c)
        if c == ".":
            self.i += 1
            return nodes.Dot()
        if c == "[":
            return self._char_class()
        if c == "(":
            self.i += 1
            self.opened += 1
            number = self.opened
            inner = self._alt()
            if self.peek() != ")":
                raise ValueError("unclosed group")
            self.i += 1
            self.closed.append(number)
            return nodes.Group(node=inner, number=number)
        if c in "^$":
            self.i += 1
            return nodes.Anchor(kind=c)
        if c == "\\":
            self.i += 1
            d = self.peek()
            if d.isdigit() and d != "0":
                self.i += 1
                return nodes.Backref(ref=int(d))
            raise ValueError("bad escape")
        # Any other character is treated as a literal (defensive; grammar shouldn't reach here).
        self.i += 1
        return nodes.Lit(ch=c)

    def _char_class(self) -> nodes.Node:
        # Produce a CharClass node; keep it simple: store the pattern text for the matcher.
        start = self.i
        self.i += 1  # skip '['
        neg = False
        if self.peek() == "^":
            neg = True
            self.i += 1
        members = []
        while self.peek() and self.peek() != "]":
            lo = self.peek()
            self.i += 1
            if self.peek() == "-" and self.i + 1 < len(self.s) and self.s[self.i + 1] != "]":
                self.i += 1
                hi = self.peek()
                self.i += 1
                members.append((lo, hi))
            else:
                members.append((lo, lo))
        if self.peek() != "]":
            raise ValueError("unclosed class")
        self.i += 1  # skip ']'
        return nodes.CharClass(members=tuple(members), neg=neg)

    def _quant(self):
        c = self.peek()
        if c == "*":
            self.i += 1
            return (0, None, False)
        if c == "+":
            self.i += 1
            return (1, None, False)
        if c == "?":
            self.i += 1
            return (0, 1, False)
        if c == "{":
            return self._braces()
        return None

    def _braces(self):
        s = self.s
        i = self.i
        if i >= len(s) or s[i] != "{":
            return None
        j = i + 1
        num = ""
        while j < len(s) and s[j].isdigit():
            num += s[j]
            j += 1
        if not num:
            return None
        mn = int(num)
        mx = None
        if j < len(s) and s[j] == ",":
            j += 1
            num2 = ""
            while j < len(s) and s[j].isdigit():
                num2 += s[j]
                j += 1
            if num2:
                mx = int(num2)
        if j < len(s) and s[j] == "}":
            j += 1
        else:
            return None
        lazy = False
        if j < len(s) and s[j] == "?":
            lazy = True
            j += 1
        self.i = j
        return (mn, mx, lazy)


def parse(pattern: str) -> nodes.Node:
    return _Parser(pattern).parse()
