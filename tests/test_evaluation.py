import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from epbench import evaluation
from epbench.codex_backend import Launch

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "examples" / "solutions" / "hall-transport"

AGENT = """
import json, os, sys, time
mode, source = sys.argv[1], sys.argv[2]
sys.stdin.read()

def emit(event):
    print(json.dumps(event), flush=True)

emit({"type": "thread.started", "thread_id": "mock-thread"})
emit({"type": "turn.started"})
if mode == "solve":
    for name in ("physics.py", "model.py"):
        open(name, "w").write(open(os.path.join(source, name)).read())
    emit({"type": "item.completed", "item": {"id": "a1", "type": "file_change"}})
    emit({"type": "item.completed", "item": {"id": "a1", "type": "file_change"}})
elif mode == "idle":
    emit({"type": "item.completed", "item": {"id": "a1", "type": "command_execution"}})
elif mode == "hang":
    time.sleep(600)
elif mode == "garbage":
    print("this is not an event", flush=True)
elif mode == "leak":
    emit({"type": "item.completed", "item": {"id": "a1", "type": "command_execution",
                                             "text": "Authorization: Bearer mock-token-value"}})
elif mode == "quota":
    emit({"type": "error", "message": "mock provider quota exhausted"})
    emit({"type": "turn.failed", "error": {"message": "mock backend failure"}})
    raise SystemExit(1)
elif mode == "fail":
    emit({"type": "item.completed", "item": {"id": "a1", "type": "command_execution"}})
    emit({"type": "error", "message": "mock provider died mid-run"})
    emit({"type": "turn.failed", "error": {"message": "mock backend failure"}})
    raise SystemExit(1)
emit({"type": "turn.completed"})
"""


class MockBackend:
    """Stands in for the Codex CLI: same Launch contract, no network and no model."""

    def __init__(self, mode, secrets=()):
        self.mode, self.secrets, self.calls, self.withheld = mode, secrets, 0, []

    def prepare(self, workspace, control, model, unreadable):
        self.calls += 1
        self.withheld = [Path(path) for path in unreadable]
        control.joinpath("auth.json").write_text('{"token": "mock-token-value"}')
        return Launch(
            [sys.executable, "-c", AGENT, self.mode, str(REFERENCE)],
            dict(os.environ) | {"PYTHONDONTWRITEBYTECODE": "1"},
            {"name": "mock", "version": "0", "model_requested": model,
             "model_observed": None, "config": "# mock profile\n"},
            self.secrets,
        )


class RefusingBackend:
    def __init__(self):
        self.calls = 0

    def prepare(self, workspace, control, model, unreadable):
        self.calls += 1
        raise RuntimeError("isolation preflight failed (readable: /somewhere/hall.py)")


class TestEvaluation(unittest.TestCase):
    def run_attempt(self, backend, seconds=90):
        directory = tempfile.TemporaryDirectory(prefix="epbench-eval-")
        self.addCleanup(directory.cleanup)
        report = evaluation.evaluate("hall-transport", Path(directory.name), "mock-model",
                                     seconds=seconds, backend=backend)
        return report, Path(report["paths"]["workspace"]).parent

    def test_solved_attempt_scores_and_preserves_artifacts(self):
        backend = MockBackend("solve")
        report, attempt = self.run_attempt(backend)
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["grading"]["status"], "passed")
        self.assertEqual(report["grading"]["result"]["passed"], 13)
        self.assertEqual(report["execution"]["status"], "completed")
        self.assertEqual(report["execution"]["tool_calls"], 1, "duplicate item IDs must count once")
        for name in ("trace.jsonl", "changes.patch", "report.json", "prompt.txt", "backend-config.toml"):
            self.assertTrue((attempt / name).is_file(), name)
        self.assertTrue((attempt / "workspace" / "model.py").is_file())
        self.assertTrue((attempt / "initial" / "model.py").is_file())
        self.assertFalse((attempt / "live").exists(), "the live workspace must not outlive the attempt")
        self.assertFalse((attempt / "control").exists(), "backend credentials must not outlive the attempt")
        self.assertNotEqual(report["initial_sha256"]["model.py"], report["final_sha256"]["model.py"])
        self.assertIn("physics.py", (attempt / "changes.patch").read_text())
        self.assertEqual(json.loads((attempt / "report.json").read_text())["status"], "success")
        self.assertEqual(backend.calls, 1, "an attempt is never retried")

    def test_untouched_workspace_fails_grading(self):
        report, attempt = self.run_attempt(MockBackend("idle"))
        self.assertEqual(report["status"], "grading_failed")
        self.assertEqual(report["grading"]["result"]["passed"], 2)
        self.assertEqual(report["initial_sha256"], report["final_sha256"])
        self.assertEqual((attempt / "changes.patch").read_text(), "")

    def test_budget_is_enforced_and_partial_work_is_kept(self):
        report, attempt = self.run_attempt(MockBackend("hang"), seconds=3)
        self.assertEqual(report["status"], "timed_out")
        self.assertEqual(report["execution"]["termination_reason"], "wall_time_budget_exceeded")
        self.assertLess(report["execution"]["elapsed_seconds"], 30)
        self.assertTrue((attempt / "workspace" / "physics.py").is_file())

    def test_backend_failures_are_classified(self):
        for mode, status, reason in [
            ("fail", "agent_failed", "backend_turn_failed"),
            ("garbage", "infrastructure_error", "invalid_backend_event_stream"),
        ]:
            with self.subTest(mode=mode):
                report, _ = self.run_attempt(MockBackend(mode))
                self.assertEqual(report["status"], status)
                self.assertEqual(report["execution"]["termination_reason"], reason)
                expected = "mock provider died mid-run" if mode == "fail" else None
                self.assertEqual(report["execution"]["backend_error"], expected)

    def test_scoreable_attempts_carry_a_score(self):
        for mode, reason in [("solve", None), ("idle", None), ("fail", None)]:
            with self.subTest(mode=mode):
                report, _ = self.run_attempt(MockBackend(mode))
                self.assertTrue(report["scored"], "the agent ran, so the attempt counts")
                self.assertIsNone(report["exclusion_reason"])
                self.assertEqual(report["score"]["total"], 13)
                self.assertEqual(report["score"]["passed"], report["grading"]["result"]["passed"])

    def test_failures_before_agent_work_are_excluded_from_aggregates(self):
        cases = [
            (MockBackend("quota"), "backend_error_before_agent_work", "mock provider quota exhausted"),
            (RefusingBackend(), "no_attempt", None),
        ]
        for backend, reason, backend_error in cases:
            with self.subTest(reason=reason):
                report, _ = self.run_attempt(backend)
                self.assertFalse(report["scored"])
                self.assertEqual(report["exclusion_reason"], reason)
                self.assertIsNone(report["score"], "an unscored attempt must expose no benchmark score")
                self.assertEqual(report["execution"]["backend_error"], backend_error)
        # The raw starter grade stays available for debugging even when excluded.
        report, _ = self.run_attempt(MockBackend("quota"))
        self.assertEqual(report["grading"]["result"]["passed"], 2)

    def test_timeout_still_scores(self):
        report, _ = self.run_attempt(MockBackend("hang"), seconds=3)
        self.assertTrue(report["scored"], "a budget overrun is agent behaviour, not backend failure")
        self.assertEqual(report["score"]["passed"], 2)

    def test_refused_isolation_never_launches_or_grades(self):
        backend = RefusingBackend()
        report, attempt = self.run_attempt(backend)
        self.assertEqual(report["status"], "infrastructure_error")
        self.assertEqual(report["grading"]["status"], "not_run")
        self.assertIsNone(report["grading"]["result"])
        self.assertIn("preflight failed", report["execution"]["termination_reason"])
        self.assertFalse(report["scored"])
        self.assertIsNone(report["score"])
        self.assertEqual(backend.calls, 1)
        self.assertEqual((attempt / "trace.jsonl").read_text(), "")

    def test_credentials_are_redacted_from_preserved_output(self):
        backend = MockBackend("leak", secrets=("mock-token-value",))
        report, attempt = self.run_attempt(backend)
        trace = (attempt / "trace.jsonl").read_text()
        self.assertNotIn("mock-token-value", trace)
        self.assertIn("[REDACTED]", trace)
        self.assertNotIn("mock-token-value", json.dumps(report))

    def test_grader_and_task_answers_are_declared_unreadable(self):
        backend = MockBackend("idle")
        self.run_attempt(backend)
        names = {path.name for path in backend.withheld}
        self.assertIn("hall.py", names, "withheld cases must be declared to the sandbox")
        self.assertIn("grader.py", names)
        for path in backend.withheld:
            self.assertTrue(path.is_absolute())

    def test_invalid_requests_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for task, model, seconds in [
                ("ion-acceleration", "m", 60), ("hall-transport", "  ", 60),
                ("hall-transport", "m", 0), ("hall-transport", "m", float("inf")),
            ]:
                with self.subTest(model=model, seconds=seconds), self.assertRaises(ValueError):
                    evaluation.evaluate(task, Path(directory), model, seconds=seconds,
                                        backend=MockBackend("idle"))


if __name__ == "__main__":
    unittest.main()
