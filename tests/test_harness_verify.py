"""Tests of harness logic: the regression ratchet and the consecutive-failure cap."""
import datetime
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import finder  # noqa: E402
import verify  # noqa: E402


def run(conclusion, status="completed", created="2026-11-08T10:00:00Z"):
    return {"status": status, "conclusion": conclusion, "createdAt": created}


class RatchetTest(unittest.TestCase):
    def test_only_new_failures_count(self):
        new, fixed, compared = verify.compare({"done": 100, "failed": [3, 50, 99]}, {"done": 80, "failed": [3, 60]})
        self.assertEqual(new, [60])      # 3 failed on main too; 99 lies beyond the shared range
        self.assertEqual(fixed, 1)       # 50 now passes
        self.assertEqual(compared, 80)

    def test_unrelated_old_failures_do_not_block(self):
        new, _, _ = verify.compare({"done": 10, "failed": [1, 2, 3]}, {"done": 10, "failed": [1, 2, 3]})
        self.assertEqual(new, [])


class FailureCapTest(unittest.TestCase):
    def test_counts_until_last_success(self):
        runs = [run(None, "in_progress"), run("failure"), run("failure"), run("success"), run("failure")]
        self.assertEqual(finder.count_failures(runs), 2)

    def test_cancelled_runs_are_ignored(self):
        self.assertEqual(finder.count_failures([run("cancelled"), run("failure")]), 1)

    def test_resume_boundary_resets_the_count(self):
        runs = [run("failure", created="2026-11-08T12:00:00Z"), run("failure", created="2026-11-08T08:00:00Z")]
        since = datetime.datetime(2026, 11, 8, 10, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(finder.count_failures(runs, since), 1)


if __name__ == "__main__":
    unittest.main()
