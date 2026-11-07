"""Public API: `match(pattern, text)` and `Match`, behaving like CPython's `re.match`."""
from .matcher import match
from .nodes import Match

__all__ = ["match", "Match"]
