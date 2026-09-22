import json
import math
from pathlib import Path
import tempfile
import unittest

from epbench import thrust
from epbench.grader import grade

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "examples" / "solutions" / "hall-thrust"
STARTER = ROOT / "src" / "epbench" / "tasks" / "hall-thrust"


def workspace(directory, physics=None, momentum=None):
    path = Path(directory)
    path.joinpath("physics.py").write_text(physics or (REFERENCE / "physics.py").read_text())
    path.joinpath("momentum.py").write_text(momentum or (REFERENCE / "momentum.py").read_text())
    return path


def patched(old, new):
    source = (REFERENCE / "momentum.py").read_text()
    assert old in source, old
    return source.replace(old, new)


UPDATE = "        u_next = speed[-1] + dx * (electric + mass_addition) / flux_next"


class TestThrustVerifier(unittest.TestCase):
    def grade_source(self, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            return grade("hall-thrust", workspace(directory, **kwargs))

    def test_reference_passes_and_starter_fails(self):
        reference = grade("hall-thrust", REFERENCE)
        self.assertEqual(reference["status"], "passed")
        self.assertEqual(reference["passed"], reference["total"])
        starter = grade("hall-thrust", STARTER)
        self.assertEqual(starter["status"], "failed")
        self.assertEqual(starter["passed"], 3, "only the sound speed and the no-source limit survive")
        self.assertNotIn(str(ROOT), json.dumps(starter))
        self.assertNotIn('"expected"', json.dumps(starter))

    def test_momentum_balance_is_what_detects_the_missing_term(self):
        starter = grade("hall-thrust", STARTER)
        failing = [name for case in starter["cases"] for name, check in case["diagnostics"].items()
                   if not check["passed"]]
        self.assertTrue(any("momentum_balance" in name for name in failing))
        self.assertTrue(any("thrust_routes_agree" in name for name in failing))
        self.assertFalse(any("continuity" in name for name in failing),
                         "particle conservation must not distinguish the defect")

    def test_reference_conserves_momentum_to_round_off(self):
        reference = grade("hall-thrust", REFERENCE)
        residuals = [check["error"] for case in reference["cases"]
                     for name, check in case["diagnostics"].items() if "momentum_balance" in name]
        self.assertTrue(residuals)
        self.assertLess(max(residuals), 1e-12)

    def test_each_module_is_independently_required(self):
        broken_physics = "def bohm_speed(te_ev):\n    return 1234.0\n"
        result = self.grade_source(physics=broken_physics)
        self.assertEqual(result["status"], "failed")
        result = self.grade_source(momentum=(STARTER / "momentum.py").read_text())
        self.assertEqual(result["status"], "failed")

    def test_hardcoded_thrust_is_rejected(self):
        source = patched(
            '    return {\n        **prescribed,',
            '    momentum, force = 20.75309521225382, 20.753095212253804\n    return {\n        **prescribed,')
        result = self.grade_source(momentum=source)
        self.assertEqual(result["status"], "failed")

    def test_faked_thrust_agreement_on_a_wrong_solution_is_rejected(self):
        # Copying one route into the other hides the disagreement but not the cause.
        source = (STARTER / "momentum.py").read_text().replace(
            "    return {\n        **prescribed,", "    force = momentum\n    return {\n        **prescribed,")
        result = self.grade_source(momentum=source)
        self.assertEqual(result["status"], "failed")
        names = [n for c in result["cases"] for n, k in c["diagnostics"].items() if not k["passed"]]
        self.assertTrue(any("reported_force_thrust" in n for n in names),
                        "the verifier recomputes the force route from its own field and source")
        self.assertTrue(any("momentum_balance" in n for n in names))

    def test_internally_consistent_wrong_neutral_speed_is_rejected(self):
        # Self-consistent solution of a different problem: neutrals born at the ion speed.
        source = patched(
            "        mass_addition = (p.u_neutral_m_per_s - speed[-1]) * s_face",
            "        mass_addition = 0.0 * s_face")
        result = self.grade_source(momentum=source)
        self.assertEqual(result["status"], "failed")

    def test_grid_independent_wrong_solution_is_rejected(self):
        # Converges under refinement but ignores the source entirely in the momentum march.
        source = patched(UPDATE, "        u_next = math.sqrt(speed[-1] ** 2 + 2 * dx * electric / max(density[-1], 1e-30))")
        source = source.replace("from math import exp, isfinite", "import math\nfrom math import exp, isfinite")
        result = self.grade_source(momentum=source)
        self.assertEqual(result["status"], "failed")

    def test_rescaled_state_is_rejected(self):
        source = patched("        density.append(flux_next / u_next)", "        density.append(1.000001 * flux_next / u_next)")
        result = self.grade_source(momentum=source)
        self.assertEqual(result["status"], "failed")

    def test_malformed_outputs(self):
        for name, replacement in [
            ("short array", '    return {\n        **prescribed,\n        "n_per_m3": density[:-1],'),
            ("non numeric", '    return {\n        **prescribed,\n        "n_per_m3": ["x"] * len(density),'),
            ("nonfinite", '    return {\n        **prescribed,\n        "n_per_m3": [float("nan")] * len(density),'),
        ]:
            with self.subTest(name=name):
                source = patched('    return {\n        **prescribed,\n        "n_per_m3": density,', replacement)
                result = self.grade_source(momentum=source)
                self.assertEqual(result["status"], "failed")
                self.assertTrue(any(c["status"] == "invalid_output" for c in result["cases"]))

    def test_reference_rejects_invalid_parameters(self):
        import sys
        sys.path.insert(0, str(REFERENCE))
        try:
            from momentum import Parameters, solve  # type: ignore
            from physics import bohm_speed  # type: ignore
            for kwargs in ({"n_cells": 3}, {"n_cells": 4.0}, {"length_m": 0.0}, {"te_ev": 0.0},
                           {"n_inlet_per_m3": -1.0}, {"field_width": 0.0}, {"source_width": -1.0},
                           {"e_peak_v_per_m": -1.0}, {"u_neutral_m_per_s": -1.0},
                           {"s0_per_m3_s": float("inf")}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    solve(Parameters(**kwargs))
            for bad in (0.0, -1.0, float("nan"), True):
                with self.subTest(te=bad), self.assertRaises(ValueError):
                    bohm_speed(bad)
        finally:
            sys.path.remove(str(REFERENCE))
            for name in ("momentum", "physics"):
                sys.modules.pop(name, None)

    def test_cases_vary_conditions_and_grids(self):
        cases = list(thrust.cases())
        self.assertEqual(len(cases), 13)
        model = [p for c in cases if c["operation"] != "bohm" for p in c["parameters"]]
        for field in ("n_cells", "s0_per_m3_s", "source_width", "e_peak_v_per_m",
                      "u_neutral_m_per_s", "te_ev", "n_inlet_per_m3", "length_m"):
            self.assertGreater(len({p[field] for p in model}), 1, field)
        grids = [c["parameters"] for c in cases if c["operation"] == "refinement"]
        self.assertTrue(all([p["n_cells"] for p in g] == [160, 320, 640] for g in grids))

    def test_limits_are_analytic_and_exact(self):
        no_source = next(c for c in thrust.cases() if c["operation"] == "no_source")
        self.assertEqual(no_source["parameters"][0]["s0_per_m3_s"], 0.0)
        zero_field = next(c for c in thrust.cases() if c["operation"] == "zero_field")
        self.assertEqual(zero_field["parameters"][0]["e_peak_v_per_m"], 0.0)
        self.assertEqual(zero_field["parameters"][0]["u_neutral_m_per_s"], 0.0)

    def test_bohm_speed_dimensional_scaling(self):
        speeds = [math.sqrt(thrust.E * t / thrust.M_XE) for t in (1.0, 4.0, 16.0)]
        self.assertAlmostEqual(speeds[1] / speeds[0], 2.0, places=12)
        self.assertAlmostEqual(speeds[2] / speeds[1], 2.0, places=12)


if __name__ == "__main__":
    unittest.main()
