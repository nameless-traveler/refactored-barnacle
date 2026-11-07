"""Tests of the harness itself: the oracle must have no false positives and must catch broken engines."""
import os
import random
import re
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fuzz  # noqa: E402


def _ref_match(pattern, text, shift=0):
    m = re.match(pattern, text)
    if m is None:
        return None
    groups = tuple(None if m.span(i) == (-1, -1) else m.span(i) for i in range(1, m.re.groups + 1))
    return types.SimpleNamespace(start=m.start(), end=m.end() + shift, groups=groups)


REFERENCE = types.SimpleNamespace(match=lambda p, t: _ref_match(p, t))
OFF_BY_ONE = types.SimpleNamespace(match=lambda p, t: _ref_match(p, t, shift=1))


class HarnessSelfTest(unittest.TestCase):
    def test_generator_stays_inside_grammar(self):
        for level in range(1, fuzz.MAX_LEVEL + 1):
            rng = random.Random(level)
            bad = 0
            for _ in range(300):
                p = fuzz.Gen(rng, level).pattern()
                self.assertTrue(fuzz.parses(p, level), (level, p))
                try:
                    re.compile(p)
                except re.error:
                    bad += 1
            self.assertLess(bad, 15, "too many generated patterns rejected by re at level %d" % level)

    def test_oracle_has_no_false_positives(self):
        for level in range(1, fuzz.MAX_LEVEL + 1):
            self.assertEqual(fuzz.fuzz(REFERENCE, level, seed=level, iters=150), [], "level %d" % level)

    def test_oracle_catches_a_broken_engine(self):
        found = fuzz.fuzz(OFF_BY_ONE, 1, seed=1, iters=50)
        self.assertTrue(found)
        self.assertLessEqual(len(found[0]["pattern"]) + len(found[0]["text"]), 3)  # shrinking works


if __name__ == "__main__":
    unittest.main()
