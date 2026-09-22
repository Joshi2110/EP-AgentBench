"""Withheld-at-runtime cases and independent discrete Hall verification."""

from __future__ import annotations

import math
from typing import Any, Iterator

E = 1.602176634e-19
M_E = 9.1093837139e-31
M_XE = 131.293 * 1.66053906892e-27
TOLERANCE = {
    "scaled_residual": 1e-8,
    "refinement_current_relative": 1e-3,
    "refinement_potential_v": 0.02,
    "refinement_contraction": 0.4,
}
DEFAULTS = {
    "voltage_v": 300.0, "length_m": 0.038, "n0_per_m3": 2e18,
    "te0_ev": 20.0, "b_peak_t": 0.02, "nu0_per_s": 2e7,
    "ion_inlet_m_per_s": 5000.0, "n_cells": 80,
    "density_bump": 0.25, "temperature_bump": 0.20, "nu_variation": 0.10,
}


def cases() -> Iterator[dict[str, Any]]:
    for nu in (1e7, 8e8, 5e9):
        transition = M_E * nu / E
        yield {
            "operation": "mobility", "nu_per_s": nu,
            "b_t": [0.0, transition / 10, transition, transition * 10, 0.02, -0.02, 0.04, -0.04],
        }
    conditions = [
        dict(b_peak_t=0, density_bump=0, temperature_bump=0, nu_variation=0,
             n_cells=4, voltage_v=120, length_m=0.025, n0_per_m3=1e18,
             te0_ev=8, ion_inlet_m_per_s=2000, nu0_per_s=8e8),
        dict(b_peak_t=0, density_bump=0, temperature_bump=0, nu_variation=0,
             n_cells=16, voltage_v=0, ion_inlet_m_per_s=0),
        {},
        dict(n_cells=37, voltage_v=180, length_m=0.02, n0_per_m3=4e18,
             te0_ev=35, b_peak_t=0.008, nu0_per_s=9e7, ion_inlet_m_per_s=9000,
             density_bump=-0.35, temperature_bump=0.5, nu_variation=-0.4),
        dict(n_cells=113, voltage_v=600, length_m=0.07, n0_per_m3=7e18,
             te0_ev=40, b_peak_t=0.045, nu0_per_s=3e8, ion_inlet_m_per_s=15000,
             density_bump=0.65, temperature_bump=-0.45, nu_variation=0.6),
        dict(n_cells=19, voltage_v=70, length_m=0.055, n0_per_m3=8e17,
             te0_ev=9, b_peak_t=0.00015, nu0_per_s=1e9, ion_inlet_m_per_s=7000,
             density_bump=-0.5, temperature_bump=-0.3, nu_variation=0.2),
        dict(n_cells=48, voltage_v=0, density_bump=0, temperature_bump=0.5,
             te0_ev=50, b_peak_t=0, nu_variation=0, nu0_per_s=1e8, ion_inlet_m_per_s=20000),
    ]
    for changes in conditions:
        yield {"operation": "model", "parameters": [DEFAULTS | changes]}
    yield {
        "operation": "magnetic_reversal",
        "parameters": [dict(DEFAULTS), DEFAULTS | {"b_peak_t": -DEFAULTS["b_peak_t"]}],
    }
    for changes in ({}, dict(voltage_v=200, density_bump=-0.2, temperature_bump=-0.1,
                             nu_variation=-0.2, b_peak_t=-0.03, nu0_per_s=9e7, length_m=0.06)):
        yield {
            "operation": "refinement",
            "parameters": [DEFAULTS | changes | {"n_cells": n} for n in (80, 160, 320)],
        }


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must contain finite real numbers, not booleans")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must contain finite real numbers")
    return value


def _array(value: Any, length: int, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{name} has the wrong array shape")
    return [_number(v, name) for v in value]


def _check(actual: list[float], expected: list[float], scale: float, tolerance: float = 1e-8) -> dict:
    error = max(abs(a - b) / max(abs(b), scale) for a, b in zip(actual, expected))
    return _metric(error, tolerance)


def _metric(error: float, tolerance: float) -> dict:
    return {
        "passed": math.isfinite(error) and error <= tolerance,
        "error": error if math.isfinite(error) else None,
        "tolerance": tolerance,
    }


def _mobility(b: float, nu: float) -> float:
    hall_parameter = E * b / (M_E * nu)
    return (E / (M_E * nu)) / (1 + hall_parameter * hall_parameter)


def _profiles(p: dict) -> dict[str, list[float]]:
    # Construct prescribed data from the case, never from submitted diagnostics.
    s = [i / p["n_cells"] for i in range(p["n_cells"] + 1)]
    return {
        "x_m": [x * p["length_m"] for x in s],
        "n_per_m3": [p["n0_per_m3"] * (1 + p["density_bump"] * math.sin(math.pi * x)) for x in s],
        "te_ev": [p["te0_ev"] * (1 + p["temperature_bump"] * math.sin(math.pi * x + 0.2)) for x in s],
        "b_t": [p["b_peak_t"] * (0.12 + 0.88 * math.exp(-((x - 0.76) / 0.24)**2)) for x in s],
        "nu_per_s": [p["nu0_per_s"] * (1 + p["nu_variation"] * math.cos(math.pi * x)) for x in s],
    }


def _model_checks(p: dict, output: Any) -> dict[str, dict]:
    if not isinstance(output, dict):
        raise ValueError("solve must return a dictionary")
    n_cells = p["n_cells"]
    dx = p["length_m"] / n_cells
    prescribed = _profiles(p)
    node_keys = (*prescribed, "pressure_pa", "potential_v", "ion_speed_m_per_s")
    face_keys = ("mu_face_m2_per_vs", "pressure_gradient_pa_per_m", "electric_field_v_per_m")
    nodes = {key: _array(output.get(key), n_cells + 1, key) for key in node_keys}
    faces = {key: _array(output.get(key), n_cells, key) for key in face_keys}
    current = _number(output.get("electron_current_density_a_per_m2"), "electron current")
    scales = {
        "x_m": p["length_m"], "n_per_m3": p["n0_per_m3"], "te_ev": p["te0_ev"],
        "b_t": max(abs(p["b_peak_t"]), 1e-12), "nu_per_s": p["nu0_per_s"],
    }
    checks = {key: _check(nodes[key], prescribed[key], scales[key]) for key in prescribed}
    n, te = prescribed["n_per_m3"], prescribed["te_ev"]
    pressure = [E * ni * ti for ni, ti in zip(n, te)]
    pressure_scale = E * p["n0_per_m3"] * p["te0_ev"]
    checks["pressure"] = _check(nodes["pressure_pa"], pressure, pressure_scale)
    n_face = [(a + b) / 2 for a, b in zip(n, n[1:])]
    b, nu = prescribed["b_t"], prescribed["nu_per_s"]
    mu = [_mobility((b[i] + b[i + 1]) / 2, (nu[i] + nu[i + 1]) / 2) for i in range(n_cells)]
    gradp = [(b - a) / dx for a, b in zip(pressure, pressure[1:])]
    checks["face_mobility"] = _check(faces["mu_face_m2_per_vs"], mu, min(mu))
    checks["pressure_gradient"] = _check(faces["pressure_gradient_pa_per_m"], gradp, pressure_scale / p["length_m"])
    field = faces["electric_field_v_per_m"]
    phi = nodes["potential_v"]
    voltage_scale = max(p["voltage_v"], p["te0_ev"], 1.0)
    checks["potential_boundaries"] = _check([phi[0], phi[-1]], [p["voltage_v"], 0.0], voltage_scale)
    checks["field_gradient"] = _check(
        field, [(a - b) / dx for a, b in zip(phi, phi[1:])], voltage_scale / p["length_m"],
    )
    reconstructed = [E * ni * mi * ei + mi * gi for ni, mi, ei, gi in zip(n_face, mu, field, gradp)]
    resistance = math.fsum(dx / (E * ni * mi) for ni, mi in zip(n_face, mu))
    current_scale = max(p["voltage_v"] / resistance, max(abs(mi * gi) for mi, gi in zip(mu, gradp)), 1.0)
    checks["face_current"] = _check(reconstructed, [current] * n_cells, current_scale)
    pressure_voltage = math.fsum(dx * gi / (E * ni) for ni, gi in zip(n_face, gradp))
    checks["integrated_current"] = _check(
        [current * resistance], [p["voltage_v"] + pressure_voltage], voltage_scale,
    )
    speeds = nodes["ion_speed_m_per_s"]
    energy_voltage = [M_XE * (v * v - p["ion_inlet_m_per_s"]**2) / (2 * E) for v in speeds]
    checks["ion_energy"] = _check(energy_voltage, [p["voltage_v"] - v for v in phi], voltage_scale)
    checks["nonnegative_ion_speed"] = _metric(max(0.0, -min(speeds)), 0.0)
    if all(p[key] == 0 for key in ("density_bump", "temperature_bump", "nu_variation", "b_peak_t")):
        checks["uniform_potential"] = _check(
            phi, [p["voltage_v"] * (1 - i / n_cells) for i in range(n_cells + 1)], voltage_scale,
        )
        uniform_current = E**2 * p["n0_per_m3"] * p["voltage_v"] / (M_E * p["nu0_per_s"] * p["length_m"])
        checks["uniform_current"] = _check([current], [uniform_current], current_scale)
    elif all(p[key] == 0 for key in ("density_bump", "nu_variation", "b_peak_t")):
        drop = p["voltage_v"] + te[-1] - te[0]
        checks["analytic_pressure_potential"] = _check(
            phi, [p["voltage_v"] - drop * i / n_cells + t - te[0] for i, t in enumerate(te)], voltage_scale,
        )
        exact_current = E**2 * p["n0_per_m3"] * drop / (M_E * p["nu0_per_s"] * p["length_m"])
        checks["analytic_pressure_current"] = _check([current], [exact_current], current_scale)
    return checks


def _refinement_checks(outputs: list[dict]) -> dict[str, dict]:
    currents = [out["electron_current_density_a_per_m2"] for out in outputs]
    dj = [abs(a - b) for a, b in zip(currents, currents[1:])]
    dphi = [
        max(abs(a - b) for a, b in zip(coarse["potential_v"], fine["potential_v"][::2]))
        for coarse, fine in zip(outputs, outputs[1:])
    ]
    # Smooth profiles have second-order differences; 0.4 allows margin around 1/4.
    return {
        "refinement_current": _metric(dj[0] / max(abs(currents[1]), 1.0), TOLERANCE["refinement_current_relative"]),
        "refinement_potential": _metric(dphi[0], TOLERANCE["refinement_potential_v"]),
        "current_contraction": _metric(dj[1] / max(dj[0], 1e-12), TOLERANCE["refinement_contraction"]),
        "potential_contraction": _metric(dphi[1] / max(dphi[0], 1e-12), TOLERANCE["refinement_contraction"]),
    }


def verify(case: dict, value: Any) -> dict[str, Any]:
    try:
        if case["operation"] == "mobility":
            values = _array(value, len(case["b_t"]), "mobility")
            expected = [_mobility(b, case["nu_per_s"]) for b in case["b_t"]]
            checks = {
                "mobility_law": _check(values, expected, min(expected)),
                "unmagnetized_limit": _check(values[:1], [E / (M_E * case["nu_per_s"])], expected[0]),
                "magnetic_evenness": _check([values[4], values[6]], [values[5], values[7]], min(expected)),
                "magnetic_suppression": _metric(0.0 if values[0] > values[1] > values[2] > values[3] > 0 else 1.0, 0.0),
            }
        else:
            if not isinstance(value, list) or len(value) != len(case["parameters"]):
                raise ValueError("Incorrect number of model results")
            checks = {}
            for i, (p, output) in enumerate(zip(case["parameters"], value), start=1):
                checks.update({f"model-{i}/{key}": check for key, check in _model_checks(p, output).items()})
            if case["operation"] == "refinement":
                checks.update(_refinement_checks(value))
            elif case["operation"] == "magnetic_reversal":
                a, b = value
                checks["reversed_potential"] = _check(a["potential_v"], b["potential_v"], case["parameters"][0]["voltage_v"])
                checks["reversed_current"] = _check(
                    [a["electron_current_density_a_per_m2"]], [b["electron_current_density_a_per_m2"]], 1.0,
                )
    except (ValueError, TypeError, OverflowError) as exc:
        return {"status": "invalid_output", "detail": str(exc)[:500], "diagnostics": {}}
    failed = [name for name, check in checks.items() if not check["passed"]]
    return {
        "status": "mismatch" if failed else "passed",
        "detail": "Failed checks: " + ", ".join(failed) if failed else "All physical and numerical checks passed",
        "diagnostics": checks,
    }
