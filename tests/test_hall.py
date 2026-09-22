from copy import deepcopy
from importlib.resources import files
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from epbench import hall
from epbench.cli import init
from epbench.grader import _run_case, grade

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "examples/solutions/hall-transport"


class TestHall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = {name: (REFERENCE / name).read_bytes() for name in ("physics.py", "model.py")}
        cls.starter = {
            name: files("epbench").joinpath("tasks", "hall-transport", name).read_bytes()
            for name in ("physics.py", "model.py")
        }
        cls.case = {"operation": "model", "parameters": [dict(hall.DEFAULTS)]}
        cls.default_output = _run_case(cls.reference, cls.case, 5, mode="hall")["value"]

    def test_reference_and_intentionally_defective_starter(self):
        reference = grade("hall-transport", REFERENCE)
        self.assertEqual((reference["passed"], reference["total"]), (13, 13))
        self.assertEqual(reference["status"], "passed")
        with tempfile.TemporaryDirectory() as directory:
            init("hall-transport", Path(directory))
            starter = grade("hall-transport", directory)
        self.assertEqual((starter["passed"], starter["total"]), (2, 13))
        self.assertEqual(starter["status"], "failed")
        for case in starter["cases"]:
            self.assertIn(case["status"], ("passed", "mismatch"))
            if case["kind"] == "mobility":
                self.assertFalse(case["diagnostics"]["mobility_law"]["passed"])
            if case["case"] == "case-06":
                self.assertFalse(case["diagnostics"]["model-1/face_current"]["passed"])
                self.assertTrue(case["diagnostics"]["model-1/potential_boundaries"]["passed"])
        for report in (reference, starter):
            serialized = json.dumps(report, allow_nan=False)
            for forbidden in ("parameters", "expected", str(ROOT)):
                self.assertNotIn(forbidden, serialized)
            self.assertEqual(report["success_rate"], report["passed"] / report["total"])

    def test_each_injected_defect_is_independently_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for defective in ("physics.py", "model.py"):
                with self.subTest(defective=defective):
                    for name, content in self.reference.items():
                        (path / name).write_bytes(self.starter[name] if name == defective else content)
                    report = grade("hall-transport", path)
                    self.assertEqual(report["status"], "failed")
                    mobility = report["cases"][0]["diagnostics"]["mobility_law"]
                    self.assertEqual(mobility["passed"], defective != "physics.py")
                    diagnostics = report["cases"][5]["diagnostics"]
                    self.assertEqual(diagnostics["model-1/face_mobility"]["passed"], defective != "physics.py")
                    self.assertFalse(diagnostics["model-1/face_current"]["passed"])
                    self.assertTrue(diagnostics["model-1/potential_boundaries"]["passed"])

    def test_all_parameters_and_resolutions_vary(self):
        parameters = [p for case in hall.cases() for p in case.get("parameters", [])]
        for name in hall.DEFAULTS:
            with self.subTest(parameter=name):
                self.assertGreater(len({p[name] for p in parameters}), 1)
        self.assertTrue({4, 80, 160, 320}.issubset({p["n_cells"] for p in parameters}))

    def test_hardcoded_default_profile_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name, content in self.reference.items():
                (path / name).write_bytes(content)
            model = path / "model.py"
            model.write_text(model.read_text() + f"\ndef solve(p):\n    return {self.default_output[0]!r}\n")
            report = grade("hall-transport", path)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["cases"][5]["passed"])
        self.assertTrue(any(case["status"] == "invalid_output" for case in report["cases"]))

    def test_self_consistent_wrong_profiles_do_not_define_the_verifier(self):
        value = deepcopy(self.default_output)
        out = value[0]
        for key in ("n_per_m3", "pressure_pa", "pressure_gradient_pa_per_m"):
            out[key] = [2 * x for x in out[key]]
        out["electron_current_density_a_per_m2"] *= 2
        result = hall.verify(self.case, value)
        self.assertEqual(result["status"], "mismatch")
        self.assertFalse(result["diagnostics"]["model-1/n_per_m3"]["passed"])
        self.assertFalse(result["diagnostics"]["model-1/face_current"]["passed"])
        self.assertTrue(result["diagnostics"]["model-1/potential_boundaries"]["passed"])

    def test_face_inputs_are_averaged_before_mobility(self):
        source = dict(self.reference)
        source["model.py"] = source["model.py"].replace(
            b"mu = cross_field_mobility(bf, nuf)",
            b"mu = (cross_field_mobility(b[i], nu[i]) + cross_field_mobility(b[i+1], nu[i+1])) / 2",
        )
        result = _run_case(source, self.case, 5, mode="hall")
        diagnostics = hall.verify(self.case, result["value"])["diagnostics"]
        self.assertFalse(diagnostics["model-1/face_mobility"]["passed"])

    def test_grid_independent_wrong_solution_cannot_pass(self):
        case = next(case for case in hall.cases() if case["operation"] == "refinement")
        outputs = _run_case(self.reference, case, 5, mode="hall")["value"]
        for p, out in zip(case["parameters"], outputs):
            out["potential_v"] = [p["voltage_v"] * (1 - i / p["n_cells"]) for i in range(p["n_cells"] + 1)]
            out["electric_field_v_per_m"] = [p["voltage_v"] / p["length_m"]] * p["n_cells"]
            out["electron_current_density_a_per_m2"] = 1.0
        report = hall.verify(case, outputs)
        self.assertEqual(report["status"], "mismatch")
        for key in ("refinement_current", "refinement_potential", "current_contraction", "potential_contraction"):
            self.assertTrue(report["diagnostics"][key]["passed"])
        self.assertFalse(report["diagnostics"]["model-1/face_current"]["passed"])

    def test_malformed_model_outputs(self):
        for key, bad_value in (
            ("potential_v", []), ("potential_v", [True] * 81),
            ("mu_face_m2_per_vs", [0.0] * 81), ("ion_speed_m_per_s", [float("nan")] * 81),
            ("electron_current_density_a_per_m2", "1"),
        ):
            with self.subTest(key=key, value=str(bad_value)[:40]):
                value = deepcopy(self.default_output)
                value[0][key] = bad_value
                self.assertEqual(hall.verify(self.case, value)["status"], "invalid_output")
        for value in (None, {}, [], [None], [{}]):
            self.assertEqual(hall.verify(self.case, value)["status"], "invalid_output")
        huge = deepcopy(self.default_output)
        huge[0]["ion_speed_m_per_s"] = [1e308] * 81
        report = hall.verify(self.case, huge)
        self.assertEqual(report["status"], "mismatch")
        json.dumps(report, allow_nan=False)

    def test_workspace_execution_errors_and_timeout(self):
        for body, status in (
            ("def solve(:", "runtime_error"),
            ("raise RuntimeError('simulation failed')", "runtime_error"),
            ("from missing_module import solve", "runtime_error"),
            ("def solve(p): return float('inf')", "invalid_output"),
        ):
            with self.subTest(body=body):
                source = dict(self.reference)
                source["model.py"] += ("\n" + body + "\n").encode()
                self.assertEqual(_run_case(source, self.case, 5, mode="hall")["status"], status)
        source = dict(self.reference)
        source["model.py"] += b"\nwhile True: pass\n"
        self.assertEqual(_run_case(source, self.case, 0.2, mode="hall")["status"], "timeout")

    def test_workspace_only_copies_required_modules_and_resets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name, content in self.reference.items():
                (path / name).write_bytes(content)
            model = path / "model.py"
            model.write_text(model.read_text() + """
from pathlib import Path
assert {p.name for p in Path.cwd().iterdir()} == {'physics.py', 'model.py'}
Path('state').write_text('used')
print('submission diagnostic')
""")
            (path / "unrelated.txt").write_text("must not be copied")
            self.assertEqual(grade("hall-transport", path)["status"], "passed")
            self.assertFalse((path / "state").exists())

    def test_missing_and_symlinked_modules(self):
        with self.assertRaises(ValueError):
            grade("hall-transport", REFERENCE / "model.py")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with self.assertRaises(ValueError):
                grade("hall-transport", path)
            for name in self.reference:
                (path / name).symlink_to(REFERENCE / name)
            with self.assertRaises(ValueError):
                grade("hall-transport", path)

    def test_reference_rejects_invalid_parameters_and_imaginary_ion_energy(self):
        for changes in (
            {"n_cells": 4.5}, {"n_cells": True}, {"n_cells": 3}, {"voltage_v": float("nan")},
            {"b_peak_t": float("inf")}, {"length_m": 0}, {"nu0_per_s": 0},
            {"n0_per_m3": -1}, {"te0_ev": 0}, {"voltage_v": -1}, {"ion_inlet_m_per_s": -1},
            {"density_bump": 1}, {"temperature_bump": -1}, {"nu_variation": 1},
            {"voltage_v": 0, "density_bump": 0, "b_peak_t": 0,
             "temperature_bump": 0.5, "ion_inlet_m_per_s": 0},
        ):
            with self.subTest(changes=changes):
                case = {"operation": "model", "parameters": [hall.DEFAULTS | changes]}
                result = _run_case(self.reference, case, 5, mode="hall")
                self.assertEqual(result["status"], "runtime_error")
                self.assertIn("ValueError", result["detail"])
        for nu in (0, -1, float("inf"), float("nan"), True, "1"):
            case = {"operation": "mobility", "b_t": [0.02], "nu_per_s": nu}
            self.assertEqual(_run_case(self.reference, case, 5, mode="hall")["status"], "runtime_error")
        for b in (float("nan"), float("inf"), True, "0.02"):
            case = {"operation": "mobility", "b_t": [b], "nu_per_s": 1e8}
            result = _run_case(self.reference, case, 5, mode="hall")
            self.assertEqual(result["status"], "runtime_error")
            self.assertIn("ValueError", result["detail"])

    def test_exported_example_runs_from_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hall task-with-hyphens"
            init("hall-transport", path)
            result = subprocess.run(
                [sys.executable, "-B", str(path / "run.py")], cwd=directory,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertAlmostEqual(json.loads(result.stdout)["exit_potential_v"], 0.0, delta=1e-9)
