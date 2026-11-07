"""Ratchet: every failure the fuzzer ever found stays fixed. Solver agents append to corpus.jsonl."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fuzz  # noqa: E402


class CorpusTest(unittest.TestCase):
    def test_every_corpus_case_passes(self):
        engine = fuzz.load_engine()
        with open(os.path.join(ROOT, "tests", "corpus.jsonl")) as fh:
            cases = [json.loads(line) for line in fh if line.strip()]
        for case in cases:
            with self.subTest(pattern=case["pattern"], text=case["text"]):
                failure = fuzz.run_case(engine, case["pattern"], case["text"], case.get("level", fuzz.MAX_LEVEL))
                self.assertIsNone(failure)


if __name__ == "__main__":
    unittest.main()
