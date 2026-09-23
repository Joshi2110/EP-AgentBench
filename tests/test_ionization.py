from copy import deepcopy
from importlib.resources import files
import json
import math
from pathlib import Path
import tempfile
import unittest

from epbench import ionization
from epbench.cli import init
from epbench.grader import _run_case, grade

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "examples/solutions/hall-ionization"


class TestIonization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = {name: (REFERENCE / name).read_bytes() for name in ("physics.py", "continuity.py")}
        cls.starter = {name: files("epbench").joinpath("tasks/hall-ionization", name).read_bytes()
                       for name in cls.reference}
        cls.default = {"operation": "model", "parameters": [dict(ionization.DEFAULTS)]}
        cls.output = _run_case(cls.reference, cls.default, 5, mode="ionization")["value"]
        cls.reference_grade = grade("hall-ionization", REFERENCE)
        with tempfile.TemporaryDirectory() as directory:
            init("hall-ionization", Path(directory))
            cls.starter_grade = grade("hall-ionization", directory)

    def grade_source(self, physics=None, continuity=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name, data in self.reference.items():
                (path / name).write_bytes(data)
            if physics is not None:
                (path / "physics.py").write_text(physics)
            if continuity is not None:
                (path / "continuity.py").write_text(continuity)
            return grade("hall-ionization", path)

    def test_reference_passes_and_starter_fails_kinetics_not_conservation(self):
        self.assertEqual((self.reference_grade["passed"], self.reference_grade["total"]), (13, 13))
        self.assertEqual((self.starter_grade["passed"], self.starter_grade["total"]), (2, 13))
        failures = {name.split('/')[-1] for c in self.starter_grade["cases"]
                    for name, d in c["diagnostics"].items() if not d["passed"]}
        self.assertIn("rate_law", failures)
        self.assertIn("kinetic_source", failures)
        for invariant in ("particle_conservation", "ion_source", "neutral_sink", "inlet_fluxes", "physical_state"):
            self.assertNotIn(invariant, failures)

    def test_nominal_agreement_and_off_nominal_divergence(self):
        starter = _run_case(self.starter, self.default, 5, mode="ionization")["value"]
        self.assertEqual(starter, self.output)
        case = {"operation": "rate", "distributions": [[t, 0, 5] for t in (5, 10, 20, 30)]}
        a = _run_case(self.reference, case, 5, mode="ionization")["value"]
        b = _run_case(self.starter, case, 5, mode="ionization")["value"]
        self.assertEqual(b[0], 0)
        self.assertGreater(a[0], 0)
        self.assertGreater(abs(a[1] / b[1] - 1), 0.5)
        self.assertEqual(a[2], b[2])
        self.assertLess(abs(a[3] / b[3] - 1), 0.01, "a nearby plausible match is not enough")

    def test_fixed_mean_shape_changes_distinguish_temperature_only_models(self):
        case = {"operation": "rate", "distributions": [[t, h, 5] for t in (5, 10) for h in (0, 0.2)]}
        a = _run_case(self.reference, case, 5, mode="ionization")["value"]
        b = _run_case(self.starter, case, 5, mode="ionization")["value"]
        self.assertGreater(a[1] / a[0], 1.5)
        self.assertLess(a[3] / a[2], 0.97, "a hot component does not always increase the rate at fixed mean")
        self.assertEqual(b[0], b[1])
        self.assertAlmostEqual(b[2] / b[3], 1.0)

    def test_independent_energy_quadrature_and_its_resolution(self):
        for t in (0.8, 2, 7.7, 20, 60, 180):
            analytic = math.sqrt(8 * ionization.E * t / (math.pi * ionization.M_E)) * math.exp(-ionization.THRESHOLD_EV / t)
            coarse = ionization._collision_integral(t, 2048)
            fine = ionization._collision_integral(t, 4096)
            self.assertLess(abs(coarse / analytic - 1), 1e-8)
            self.assertLess(abs(fine / analytic - 1), 1e-9)
            self.assertLess(abs(fine - analytic), abs(coarse - analytic))
        # Calibrating the numerical integral cancels its common quadrature bias.
        expected = 3e-14 * math.sqrt(7.7 / 20) * math.exp(ionization.THRESHOLD_EV / 20 - ionization.THRESHOLD_EV / 7.7)
        self.assertAlmostEqual(ionization._rate(7.7) / expected, 1.0, places=12)

    def test_collision_counting_correction_without_closed_form_passes(self):
        # An alternative submission derived from the exported probability model,
        # with midpoint energy quadrature rather than either implementation's law.
        source = self.starter["physics.py"].decode().split("def rate_coefficient")[0] + '''
from functools import lru_cache
from math import exp, pi

@lru_cache(maxsize=4096)
def collision_count(temperature):
    width = 48 * temperature / 1024
    total = 0.0
    for j in range(1024):
        energy = THRESHOLD_EV + (j + 0.5) * width
        sigma_shape = 1 - THRESHOLD_EV / energy
        speed = sqrt(2 * ELEMENTARY_CHARGE * energy / ELECTRON_MASS)
        probability = 2 * sqrt(energy) * exp(-energy / temperature) / (sqrt(pi) * temperature**1.5)
        total += sigma_shape * speed * probability * width
    return total

def rate_coefficient(te_ev, hot_fraction=0.0, hot_ratio=4.0):
    cold = te_ev / (1 - hot_fraction + hot_fraction * hot_ratio)
    count = ((1 - hot_fraction) * collision_count(cold)
             + hot_fraction * collision_count(hot_ratio * cold))
    return CALIBRATION_RATE_M3_PER_S * count / collision_count(CALIBRATION_TE_EV)
'''
        result = self.grade_source(physics=source)
        self.assertEqual((result["passed"], result["total"]), (13, 13))

    def test_hardcoded_nominal_profiles_are_rejected(self):
        source = self.reference["continuity.py"].decode() + f'\ndef solve(p):\n    return {self.output[0]!r}\n'
        result = self.grade_source(continuity=source)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["cases"][3]["passed"])

    def test_public_observation_lookup_is_rejected(self):
        source = self.reference["physics.py"].decode() + '''
def rate_coefficient(te_ev, hot_fraction=0.0, hot_ratio=4.0):
    table = {5: 2.43166012013e-15, 10: 1.15667174803e-14,
             20: 3e-14, 30: 4.49744223394e-14}
    temperatures = sorted(table)
    if te_ev <= temperatures[0]:
        return table[temperatures[0]]
    for lo, hi in zip(temperatures, temperatures[1:]):
        if te_ev <= hi:
            return table[lo] + (table[hi] - table[lo]) * (te_ev - lo) / (hi - lo)
    return table[temperatures[-1]]
'''
        result = self.grade_source(physics=source)
        self.assertFalse(result["cases"][2]["passed"], "off-table distributions must fail")
        self.assertFalse(result["cases"][1]["passed"], "fixed mean does not fix the rate")

    def test_refitting_one_temperature_does_not_repair_the_model(self):
        case = {"operation": "rate", "distributions": [[10, 0, 4]]}
        defective = _run_case(self.starter, case, 5, mode="ionization")["value"][0]
        factor = ionization._rate(10) / defective
        source = self.starter["physics.py"].decode().replace(
            "return normalization * collision_proxy(representative_energy)",
            f"return {factor!r} * normalization * collision_proxy(representative_energy)")
        result = self.grade_source(physics=source)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["cases"][3]["passed"], "refitting breaks nominal agreement")
        self.assertFalse(result["cases"][1]["passed"])

    def test_correct_diagnostics_do_not_hide_wrong_transport(self):
        case = {"operation": "model", "parameters": [ionization.DEFAULTS | {"te_ev": 10}]}
        out = _run_case(self.starter, case, 5, mode="ionization")["value"]
        out[0]["rate_m3_per_s"] = [ionization._rate(10)] * 80
        result = ionization.verify(case, out)
        self.assertTrue(result["diagnostics"]["model-0/rate_law"]["passed"])
        self.assertFalse(result["diagnostics"]["model-0/kinetic_source"]["passed"])
        out[0]["neutral_conversion"] = 0.0621472018139
        self.assertFalse(ionization.verify(case, out)["diagnostics"]["model-0/reported_conversion"]["passed"])

    def test_rescaled_densities_and_modified_profiles_are_rejected(self):
        for key in ("n_i_per_m3", "n_n_per_m3", "te_ev", "ion_speed_m_per_s"):
            out = deepcopy(self.output)
            out[0][key] = [1.01 * v for v in out[0][key]]
            self.assertEqual(ionization.verify(self.default, out)["status"], "mismatch", key)

    def test_no_seed_and_uniform_coefficient_analytic_limit(self):
        p = ionization.DEFAULTS | {"velocity_rise": 0.0}
        case = {"operation": "model", "parameters": [p]}
        out = _run_case(self.reference, case, 5, mode="ionization")["value"][0]
        total = p["ion_flux_in_per_m2_s"] + p["neutral_flux_in_per_m2_s"]
        alpha = total * 3e-14 * p["length_m"] / (p["ion_speed_m_per_s"] * p["neutral_speed_m_per_s"])
        odds = p["ion_flux_in_per_m2_s"] / p["neutral_flux_in_per_m2_s"] * math.exp(alpha)
        expected = total * odds / (1 + odds)
        self.assertAlmostEqual(out["n_i_per_m3"][-1] * p["ion_speed_m_per_s"] / expected, 1, places=12)
        zero = next(c for c in ionization.cases() if c["operation"] == "no_seed")
        out = _run_case(self.reference, zero, 5, mode="ionization")["value"][0]
        self.assertEqual(out["n_i_per_m3"], [0.0] * 81)
        self.assertEqual(out["source_per_m3_s"], [0.0] * 80)
        self.assertEqual(out["neutral_conversion"], 0.0)

    def test_transport_variations_cannot_be_fixed_by_reporting_a_rate(self):
        for field, changed in (("length_m", 0.04), ("neutral_speed_m_per_s", 600),
                               ("neutral_flux_in_per_m2_s", 6e21), ("ion_speed_m_per_s", 24000)):
            p = ionization.DEFAULTS | {field: changed}
            out = _run_case(self.reference, {"operation": "model", "parameters": [p]}, 5, mode="ionization")["value"][0]
            self.assertNotAlmostEqual(out["neutral_conversion"], self.output[0]["neutral_conversion"])
            self.assertEqual(out["rate_m3_per_s"], self.output[0]["rate_m3_per_s"])

    def test_cases_cover_every_parameter_and_refinement(self):
        cases = list(ionization.cases())
        self.assertEqual(len(cases), 13)
        for key in ionization.DEFAULTS:
            self.assertGreater(len({p[key] for c in cases for p in c.get("parameters", [])}), 1, key)
        refinements = [c for c in self.reference_grade["cases"] if c["kind"] == "refinement"]
        for c in refinements:
            self.assertLess(c["diagnostics"]["contraction"]["error"], 0.26)
            self.assertGreater(c["diagnostics"]["contraction"]["error"], 0.24)

    def test_malformed_outputs(self):
        for key, value in (("n_i_per_m3", [1]), ("neutral_conversion", True),
                           ("rate_m3_per_s", [float('nan')] * 80), ("n_n_per_m3", ["x"] * 81)):
            out = deepcopy(self.output)
            out[0][key] = value
            self.assertEqual(ionization.verify(self.default, out)["status"], "invalid_output")

    def test_invalid_parameters_and_distribution_inputs(self):
        for changes in ({"n_cells": True}, {"n_cells": 641}, {"te_ev": float('nan')},
                        {"hot_fraction": 0.4}, {"neutral_speed_m_per_s": 0}, {"temperature_variation": 0.6}):
            case = {"operation": "model", "parameters": [ionization.DEFAULTS | changes]}
            self.assertEqual(_run_case(self.reference, case, 5, mode="ionization")["status"], "runtime_error")
        for args in ((True, 0, 4), (1, 0, 4), (20, -0.1, 4), (20, 0, 7), (float('inf'), 0, 4)):
            case = {"operation": "rate", "distributions": [args]}
            self.assertEqual(_run_case(self.reference, case, 5, mode="ionization")["status"], "runtime_error")

    def test_public_observations_and_export_disclosure_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            init("hall-ionization", path)
            self.assertEqual({p.name for p in path.iterdir()}, {"README.md", "physics.py", "continuity.py", "run.py"})
            readme = (path / "README.md").read_text()
            for line in readme.splitlines():
                cells = [s.strip() for s in line.strip('|').split('|')]
                if len(cells) != 4 or not cells[0].isdigit():
                    continue
                t, h, k, conversion = map(float, cells)
                p = ionization.DEFAULTS | {"te_ev": t, "hot_fraction": h, "hot_ratio": 5}
                out = _run_case(self.reference, {"operation": "model", "parameters": [p]}, 5, mode="ionization")["value"][0]
                self.assertLess(abs(k / ionization._rate(t, h, 5) - 1), 1e-6)
                self.assertLess(abs(conversion / out["neutral_conversion"] - 1), 1e-6)
            compact = ''.join(readme.split()).lower()
            for leak in ("exp(-i/t)", "maxwell_rate", "sqrt(temperature/calibration", "representative_energy"):
                self.assertNotIn(leak, compact)
            for needed in ("sigma(epsilon)", "P_M(epsilon; T)", "synthetic", "calibration", "cell's centre"):
                self.assertIn(needed, readme)
        self.assertNotIn('"expected"', json.dumps(self.reference_grade))


if __name__ == "__main__":
    unittest.main()
