"""Regex engine under construction. The contract lives in docs/references/semantics.md.

Agents: replace the stub below. Keep modules layered (see ARCHITECTURE.md).
"""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    # One entry per capture group, in order of the opening parenthesis:
    # (start, end) if the group took part in the match, otherwise None.
    groups: Tuple[Optional[Tuple[int, int]], ...] = ()


def match(pattern: str, text: str) -> Optional[Match]:
    """Behave like re.match(pattern, text): anchored at index 0, leftmost-first backtracking."""
    raise NotImplementedError("regex engine not implemented yet")
