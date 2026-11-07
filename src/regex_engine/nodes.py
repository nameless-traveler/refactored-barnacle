"""Pattern AST nodes. Lowest layer: imports nothing from the package."""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    groups: Tuple[Optional[Tuple[int, int]], ...] = ()


class Node:
    """Base class for pattern AST nodes."""


@dataclass(frozen=True)
class Empty(Node):
    """The empty pattern; matches the empty string."""


@dataclass(frozen=True)
class Lit(Node):
    """A literal character."""
    ch: str


@dataclass(frozen=True)
class Dot(Node):
    """Matches any single character except newline."""


@dataclass(frozen=True)
class Concat(Node):
    """Concatenation of items."""
    items: Tuple[Node, ...]


@dataclass(frozen=True)
class Alt(Node):
    """Alternation of branches, tried left to right (leftmost-first)."""
    branches: Tuple[Node, ...]


@dataclass(frozen=True)
class Repeat(Node):
    """A quantified repetition: match `node` between min and max times."""
    node: Node
    min: int
    max: Optional[int]  # None means unbounded
    lazy: bool = False


@dataclass(frozen=True)
class Group(Node):
    """A capturing group, transparent for the end position."""
    node: Node
    number: int


@dataclass(frozen=True)
class Anchor(Node):
    """Start (^) or end ($) anchor."""
    kind: str  # '^' or '$'


@dataclass(frozen=True)
class CharClass(Node):
    """A character class [..] or [^..]. members is a list of (lo, hi) inclusive char pairs."""
    members: Tuple[Tuple[str, str], ...]
    neg: bool = False


@dataclass(frozen=True)
class Backref(Node):
    """A backreference to a previously opened group number."""
    ref: int
