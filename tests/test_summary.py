import json
from pathlib import Path
import tempfile
import unittest

from epbench.summary import render, summarize


def write(root, name, **overrides):
    report = {
        "attempt_id": name, "status": "success", "scored": True, "exclusion_reason": None,
        "agent": {"model_requested": "test-model"},
        "execution": {"elapsed_seconds": 10.0, "tool_calls": 4},
        "grading": {"status": "passed", "result": {"passed": 13, "total": 13, "success_rate": 1.0}},
        "score": {"passed": 13, "total": 13, "success_rate": 1.0},
    }
    report.update(overrides)
    directory = root / name
    directory.mkdir()
    (directory / "report.json").write_text(json.dumps(report))
    return report


EXCLUDED = {
    "status": "agent_failed", "scored": False, "score": None,
    "exclusion_reason": "backend_error_before_agent_work",
    "grading": {"status": "failed", "result": {"passed": 2, "total": 13, "success_rate": 2 / 13}},
}
FAILED_BUT_VALID = {
    "status": "grading_failed", "scored": True, "exclusion_reason": None,
    "score": {"passed": 5, "total": 13, "success_rate": 5 / 13},
    "grading": {"status": "failed", "result": {"passed": 5, "total": 13, "success_rate": 5 / 13}},
}


class TestSummary(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="epbench-summary-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_empty_directory_states_that_nothing_is_supported(self):
        result = summarize(self.root)
        self.assertEqual(result["attempts_found"], 0)
        self.assertEqual(result["valid_attempts"], 0)
        self.assertIsNone(result["task_success"])
        self.assertIsNone(result["case_score"])
        self.assertIn("No valid agent attempts", " ".join(result["notes"]))
        self.assertIn("valid (scored)      0", render(result))

    def test_excluded_attempts_never_reach_the_score(self):
        write(self.root, "a", **EXCLUDED)
        write(self.root, "b", **EXCLUDED)
        result = summarize(self.root)
        self.assertEqual(result["attempts_found"], 2)
        self.assertEqual(result["valid_attempts"], 0)
        self.assertEqual(result["excluded_attempts"], 2)
        self.assertEqual(result["exclusions"], {"backend_error_before_agent_work": 2})
        self.assertIsNone(result["case_score"], "diagnostic grading must not become a score")
        self.assertNotIn("2/13", json.dumps(result["exclusions"]))

    def test_valid_failures_are_counted_not_discarded(self):
        write(self.root, "pass1")
        write(self.root, "fail1", **FAILED_BUT_VALID)
        write(self.root, "fail2", **FAILED_BUT_VALID)
        write(self.root, "skip1", **EXCLUDED)
        result = summarize(self.root)
        self.assertEqual(result["attempts_found"], 4)
        self.assertEqual(result["valid_attempts"], 3)
        self.assertEqual(result["excluded_attempts"], 1)
        self.assertEqual(result["task_success"], {"successes": 1, "valid_attempts": 3, "rate": 0.333})
        self.assertEqual(result["case_score"]["passed"], {"mean": 7.667, "min": 5, "max": 13})
        self.assertEqual(result["case_score"]["cases_per_attempt"], 13)
        self.assertEqual(result["models"], ["test-model"])

    def test_small_samples_are_flagged_and_cases_are_not_tasks(self):
        write(self.root, "a")
        notes = " ".join(summarize(self.root)["notes"])
        self.assertIn("not independent scientific tasks", notes)
        self.assertIn("too few", notes)

    def test_unreadable_reports_are_reported_not_ignored(self):
        (self.root / "broken").mkdir()
        (self.root / "broken" / "report.json").write_text("{not json")
        (self.root / "partial").mkdir()
        (self.root / "partial" / "report.json").write_text('{"attempt_id": "x"}')
        write(self.root, "good")
        result = summarize(self.root)
        self.assertEqual(sorted(result["unreadable_attempts"]), ["broken", "partial"])
        self.assertEqual(result["attempts_found"], 1)

    def test_every_attempt_appears_in_the_record(self):
        write(self.root, "a")
        write(self.root, "b", **EXCLUDED)
        rows = {row["attempt_id"]: row for row in summarize(self.root)["attempts"]}
        self.assertEqual(set(rows), {"a", "b"})
        self.assertIsNone(rows["b"]["passed"], "an excluded attempt exposes no score")
        self.assertEqual(rows["a"]["passed"], 13)

    def test_missing_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize(self.root / "absent")


if __name__ == "__main__":
    unittest.main()
