import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from collect_experiment02 import filled, pending  # noqa: E402

SCHEDULE = json.loads((ROOT / "docs/experiment-02-schedule.json").read_text())


def write(out, task, protocol, scored=True, attempt_id=None):
    directory = out / (attempt_id or f"{task}-{protocol}-{len(list(out.iterdir()))}")
    directory.mkdir()
    (directory / "report.json").write_text(json.dumps({
        "task": task, "protocol": protocol, "scored": scored,
        "benchmark_version": "0.5.0", "started_at": f"2026-09-22T{len(list(out.iterdir())):02d}:00:00",
        "agent": {"model_requested": "gpt-5.6-luna", "model_observed": None},
        "exclusion_reason": None if scored else "backend_error_before_agent_work",
    }))
    return directory


class TestCollectorResumption(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_schedule_slots_have_stable_identity(self):
        order = SCHEDULE["order"]
        self.assertEqual(len(order), 60)
        self.assertEqual([s["index"] for s in order], list(range(1, 61)))
        from collections import Counter
        self.assertEqual(set(Counter((s["task"], s["protocol"]) for s in order).values()), {10})

    def test_pending_from_empty_is_the_committed_order(self):
        todo = pending(SCHEDULE, filled(self.out))
        self.assertEqual([s["index"] for s in todo], [s["index"] for s in SCHEDULE["order"]])

    def test_completed_valid_slots_are_never_rerun(self):
        first = SCHEDULE["order"][0]
        write(self.out, first["task"], first["protocol"])
        todo = pending(SCHEDULE, filled(self.out))
        self.assertEqual(len(todo), 59)
        remaining = [s for s in todo if (s["task"], s["protocol"]) == (first["task"], first["protocol"])]
        self.assertEqual(len(remaining), 9, "one cell slot consumed, nine left")

    def test_resumption_preserves_the_randomized_order(self):
        for slot in SCHEDULE["order"][:12]:
            write(self.out, slot["task"], slot["protocol"])
        todo = pending(SCHEDULE, filled(self.out))
        expected = [s["index"] for s in SCHEDULE["order"] if s["index"] > 12]
        self.assertEqual([s["index"] for s in todo], expected,
                         "resumption must not reorder the registered sequence")

    def test_excluded_attempts_are_preserved_and_do_not_fill_a_slot(self):
        slot = SCHEDULE["order"][0]
        write(self.out, slot["task"], slot["protocol"], scored=False)
        self.assertEqual(sum(filled(self.out).values()), 0)
        self.assertEqual(len(pending(SCHEDULE, filled(self.out))), 60, "an exclusion fills nothing")
        self.assertEqual(len(list(self.out.iterdir())), 1, "the excluded record is preserved")

    def test_reports_retain_condition_task_model_and_version(self):
        slot = SCHEDULE["order"][0]
        directory = write(self.out, slot["task"], slot["protocol"])
        report = json.loads((directory / "report.json").read_text())
        for key, value in (("task", slot["task"]), ("protocol", slot["protocol"]),
                           ("benchmark_version", "0.5.0")):
            self.assertEqual(report[key], value)
        self.assertEqual(report["agent"]["model_requested"], SCHEDULE["model_requested"])
        self.assertIsNone(report["agent"]["model_observed"])

    def test_unreadable_report_does_not_crash_or_fill_a_slot(self):
        broken = self.out / "broken"
        broken.mkdir()
        (broken / "report.json").write_text("{not json")
        self.assertEqual(sum(filled(self.out).values()), 0)
        self.assertEqual(len(pending(SCHEDULE, filled(self.out))), 60)

    def test_schedule_matches_registered_configuration(self):
        self.assertEqual(SCHEDULE["seed"], 20260922)
        self.assertEqual(SCHEDULE["model_requested"], "gpt-5.6-luna")
        self.assertEqual(SCHEDULE["seconds"], 900)
        self.assertEqual(SCHEDULE["valid_per_cell"], 10)
        self.assertEqual(SCHEDULE["total_valid"], 60)


if __name__ == "__main__":
    unittest.main()
