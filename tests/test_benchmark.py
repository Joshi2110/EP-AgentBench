from importlib.resources import files
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epbench.grader import _run_case, grade

ROOT = Path(__file__).resolve().parents[1]


class TestGrading(unittest.TestCase):
    def test_references_pass_and_starters_fail(self):
        starter_passes = {"ion-acceleration": 2, "beam-thrust": 7, "axial-field": 2}
        for task in starter_passes:
            with self.subTest(task=task), tempfile.TemporaryDirectory() as directory:
                reference = grade(task, ROOT / "examples" / "solutions" / f"{task}.py")
                self.assertEqual(reference["status"], "passed")
                self.assertEqual(reference["passed"], reference["total"])
                starter = Path(directory) / "starter.py"
                starter.write_bytes(files("epbench").joinpath("tasks", task, "starter.py").read_bytes())
                result = grade(task, starter)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["passed"], starter_passes[task])
                self.assertEqual(result["success_rate"], result["passed"] / result["total"])
                self.assertNotIn("inputs", json.dumps(result))
                self.assertNotIn("expected", json.dumps(result))
                self.assertNotIn(str(ROOT), json.dumps(result))
                json.dumps(result, allow_nan=False)

    def test_broken_submissions(self):
        cases = [
            ("def solve(:", "runtime_error", "SyntaxError"),
            ("raise RuntimeError('import failed')", "runtime_error", "import failed"),
            ("solve = 3", "runtime_error", "callable solve"),
            ("def solve(): return 1", "runtime_error", "TypeError"),
            ("def solve(**kwargs): raise RuntimeError('simulation failed')", "runtime_error", "simulation failed"),
            ("def solve(**kwargs): raise SystemExit(0)", "runtime_error", "SystemExit"),
            ("def solve(**kwargs): return True", "invalid_output", "finite"),
            ("def solve(**kwargs): return [1]", "invalid_output", "finite"),
            ("def solve(**kwargs): return None", "invalid_output", "finite"),
            ("def solve(**kwargs): return '1'", "invalid_output", "finite"),
            ("def solve(**kwargs): return complex(1, 2)", "invalid_output", "finite"),
            ("def solve(**kwargs): return float('nan')", "invalid_output", "finite"),
            ("def solve(**kwargs): return float('inf')", "invalid_output", "finite"),
            ("def solve(**kwargs): return 10**400", "invalid_output", "too large"),
            ("import os; os._exit(7)", "runtime_error", "code 7"),
            ("import os; os._exit(0)", "invalid_output", "worker result"),
        ]
        for source, status, detail in cases:
            with self.subTest(source=source):
                result = _run_case(source.encode(), {"x": 1}, 5)
                self.assertEqual(result["status"], status)
                self.assertIn(detail, result["detail"])

    def test_timeout(self):
        result = _run_case(b"while True: pass", {}, 0.2)
        self.assertEqual(result["status"], "timeout")

    def test_prints_do_not_corrupt_results(self):
        source = b"""import os
print('import diagnostic')
os.write(2, b'stderr diagnostic')
def solve(**kwargs):
    os.write(1, b'x' * 1000000)
    return 12
"""
        self.assertEqual(_run_case(source, {}, 5)["value"], 12)

    def test_fresh_process_and_workspace_for_each_case(self):
        source = """from pathlib import Path
assert {p.name for p in Path.cwd().iterdir()} == {'submission.py'}
assert not Path('state').exists()
Path('state').write_text('used')
calls = 0
def solve(phi_left_v, phi_right_v, length_m):
    global calls
    calls += 1
    assert calls == 1
    return (phi_left_v - phi_right_v) / length_m
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solution.py"
            path.write_text(source)
            self.assertEqual(grade("axial-field", path)["status"], "passed")
            self.assertEqual({p.name for p in Path(directory).iterdir()}, {"solution.py"})

    def test_tolerances_and_extreme_wrong_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "solution.py"
            cases = [
                (1.0, 1.0 + 5e-7, True), (1.0, 1.0 + 2e-6, False),
                (0.0, 5e-13, True), (0.0, 2e-12, False),
                (1e-7, 0.0, False), (1e-7, 1e308, False),
            ]
            for expected, value, passed in cases:
                with self.subTest(expected=expected, value=value):
                    path.write_text(f"def solve(**kwargs): return {value!r}\n")
                    with patch("epbench.grader._cases", return_value=iter([({}, expected)])):
                        result = grade("beam-thrust", path)
                    self.assertEqual(result["cases"][0]["passed"], passed)
                    json.dumps(result, allow_nan=False)

    def test_common_physics_errors_are_rejected(self):
        mutations = {
            "ion-acceleration": "return (2 * 1.602176634e-19 * discharge_v / 2.1801714e-25)**0.5",
            "beam-thrust": "return beam_current_a * 2.1801714e-25 * ion_speed_m_s * charge_state / 1.602176634e-19",
            "axial-field": "return abs(phi_left_v - phi_right_v) / length_m",
        }
        with tempfile.TemporaryDirectory() as directory:
            for task, body in mutations.items():
                with self.subTest(task=task):
                    reference = (ROOT / "examples" / "solutions" / f"{task}.py").read_text()
                    signature = next(line for line in reference.splitlines() if line.startswith("def solve"))
                    path = Path(directory) / "mutant.py"
                    path.write_text(signature + "\n    " + body + "\n")
                    self.assertEqual(grade(task, path)["status"], "failed")

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            grade("unknown", "missing.py")
        with self.assertRaises(FileNotFoundError):
            grade("axial-field", "missing.py")
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                grade("axial-field", "missing.py", timeout=timeout)
