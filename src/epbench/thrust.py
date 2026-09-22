"""Withheld-at-runtime cases and independent ion-momentum verification."""

from __future__ import annotations

import math
from typing import Any, Iterator

E = 1.602176634e-19
M_XE = 131.293 * 1.66053906892e-27
TOLERANCE = {"scaled_residual": 1e-8, "refinement_relative": 3e-3, "refinement_contraction": 0.62}
DEFAULTS = {
    "length_m": 0.025, "n_cells": 80, "e_peak_v_per_m": 30000.0,
    "field_center": 0.70, "field_width": 0.25, "s0_per_m3_s": 4e23,
    "source_center": 0.15, "source_width": 0.25, "n_inlet_per_m3": 5e17,
    "te_ev": 5.0, "u_neutral_m_per_s": 300.0,
}


def cases() -> Iterator[dict[str, Any]]:
    yield {"operation": "bohm", "te_ev": [0.5, 2.0, 5.0, 20.0, 60.0]}
    yield {"operation": "bohm", "te_ev": [1.0, 4.0, 16.0, 64.0]}
    conditions = [
        {},
        dict(source_width=0.03, source_center=0.04, n_cells=41),
        dict(source_width=2.0, s0_per_m3_s=9e23, n_cells=57),
        dict(e_peak_v_per_m=90000.0, te_ev=25.0, n_inlet_per_m3=2e18, n_cells=23),
        dict(u_neutral_m_per_s=0.0, s0_per_m3_s=7e23, source_width=1.0, n_cells=64),
        dict(u_neutral_m_per_s=2500.0, te_ev=1.5, length_m=0.06, field_center=0.4, n_cells=97),
        dict(s0_per_m3_s=1e24, source_center=0.5, source_width=0.12,
             e_peak_v_per_m=12000.0, n_inlet_per_m3=9e16, n_cells=4),
    ]
    for changes in conditions:
        yield {"operation": "model", "parameters": [DEFAULTS | changes]}
    # No field: ion momentum flux may change only through the neutral momentum injected.
    yield {"operation": "zero_field",
           "parameters": [DEFAULTS | dict(e_peak_v_per_m=0.0, s0_per_m3_s=6e23,
                                          source_width=1.5, u_neutral_m_per_s=0.0, n_cells=60)]}
    # No ionization: particle flux is constant and the task reduces to electrostatic acceleration.
    yield {"operation": "no_source",
           "parameters": [DEFAULTS | dict(s0_per_m3_s=0.0, n_cells=72)]}
    for changes in ({}, dict(source_width=1.2, e_peak_v_per_m=45000.0, u_neutral_m_per_s=150.0)):
        yield {"operation": "refinement",
               "parameters": [DEFAULTS | changes | {"n_cells": n} for n in (160, 320, 640)]}


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


def _metric(error: float, tolerance: float) -> dict:
    return {
        "passed": math.isfinite(error) and error <= tolerance,
        "error": error if math.isfinite(error) else None,
        "tolerance": tolerance,
    }


def _check(actual: list[float], expected: list[float], scale: float,
           tolerance: float = TOLERANCE["scaled_residual"]) -> dict:
    error = max(abs(a - b) / max(abs(b), scale) for a, b in zip(actual, expected))
    return _metric(error, tolerance)


def _prescribed(p: dict) -> dict[str, list[float]]:
    # Rebuild the prescribed field and source from the case, never from submitted output.
    n_cells, dx = p["n_cells"], p["length_m"] / p["n_cells"]
    centres = [(i + 0.5) / n_cells for i in range(n_cells)]
    return {
        "x_m": [i * dx for i in range(n_cells + 1)],
        "e_field_v_per_m": [p["e_peak_v_per_m"] * math.exp(-((s - p["field_center"]) / p["field_width"]) ** 2)
                            for s in centres],
        "source_per_m3_s": [p["s0_per_m3_s"] * math.exp(-((s - p["source_center"]) / p["source_width"]) ** 2)
                            for s in centres],
    }


def _model_checks(p: dict, output: Any) -> dict[str, dict]:
    if not isinstance(output, dict):
        raise ValueError("solve must return a dictionary")
    n_cells = p["n_cells"]
    dx = p["length_m"] / n_cells
    given = _prescribed(p)
    density = _array(output.get("n_per_m3"), n_cells + 1, "n_per_m3")
    speed = _array(output.get("u_i_m_per_s"), n_cells + 1, "u_i_m_per_s")
    momentum_thrust = _number(output.get("thrust_momentum_n_per_m2"), "thrust_momentum_n_per_m2")
    force_thrust = _number(output.get("thrust_force_n_per_m2"), "thrust_force_n_per_m2")
    field, source = given["e_field_v_per_m"], given["source_per_m3_s"]

    inlet_speed = math.sqrt(E * p["te_ev"] / M_XE)
    scales = {"x_m": p["length_m"], "e_field_v_per_m": max(p["e_peak_v_per_m"], 1.0),
              "source_per_m3_s": max(p["s0_per_m3_s"], 1.0)}
    checks = {key: _check(_array(output.get(key), len(given[key]), key), given[key], scales[key])
              for key in given}

    flux = [n * u for n, u in zip(density, speed)]
    momentum_flux = [n * u * u for n, u in zip(density, speed)]
    flux_scale = max(max(map(abs, flux)), 1.0)
    momentum_scale = max(max(map(abs, momentum_flux)), 1.0)
    speed_scale = max(inlet_speed, max(map(abs, speed)), 1.0)

    checks["inlet_density"] = _check([density[0]], [p["n_inlet_per_m3"]], p["n_inlet_per_m3"])
    checks["inlet_speed"] = _check([speed[0]], [inlet_speed], speed_scale)
    checks["positive_state"] = _metric(0.0 if min(density) > 0 and min(speed) > 0 else 1.0, 0.0)
    checks["continuity"] = _check(
        [b - a for a, b in zip(flux, flux[1:])], [dx * s for s in source], flux_scale,
    )
    # The discriminating relation: creating an ion costs the momentum to accelerate it.
    checks["momentum_balance"] = _check(
        [b - a for a, b in zip(momentum_flux, momentum_flux[1:])],
        [dx * ((E / M_XE) * n * e + p["u_neutral_m_per_s"] * s)
         for n, e, s in zip(density, field, source)],
        momentum_scale,
    )
    route_momentum = M_XE * (momentum_flux[-1] - momentum_flux[0])
    route_force = math.fsum(
        dx * (E * n * e + M_XE * p["u_neutral_m_per_s"] * s) for n, e, s in zip(density, field, source)
    )
    thrust_scale = max(abs(route_momentum), abs(route_force), M_XE * momentum_scale, 1e-6)
    checks["thrust_routes_agree"] = _check([route_momentum], [route_force], thrust_scale)
    checks["reported_momentum_thrust"] = _check([momentum_thrust], [route_momentum], thrust_scale)
    checks["reported_force_thrust"] = _check([force_thrust], [route_force], thrust_scale)
    return checks


def _limit_checks(operation: str, p: dict, output: dict) -> dict[str, dict]:
    density = output["n_per_m3"]
    speed = output["u_i_m_per_s"]
    flux = [n * u for n, u in zip(density, speed)]
    momentum_flux = [n * u * u for n, u in zip(density, speed)]
    if operation == "no_source":
        # Without ionization the particle flux is an exact discrete invariant.
        return {"constant_particle_flux": _check(flux, [flux[0]] * len(flux), max(abs(flux[0]), 1.0))}
    # Without a field and with motionless neutrals the ion momentum flux is invariant.
    return {"constant_momentum_flux": _check(
        momentum_flux, [momentum_flux[0]] * len(momentum_flux), max(abs(momentum_flux[0]), 1.0))}


def _refinement_checks(outputs: list[dict]) -> dict[str, dict]:
    exits = [out["u_i_m_per_s"][-1] for out in outputs]
    thrusts = [out["thrust_force_n_per_m2"] for out in outputs]
    du = [abs(a - b) for a, b in zip(exits, exits[1:])]
    dt = [abs(a - b) for a, b in zip(thrusts, thrusts[1:])]
    # The upwind march is first order, so successive differences halve.
    return {
        "refinement_speed": _metric(du[0] / max(abs(exits[1]), 1.0), TOLERANCE["refinement_relative"]),
        "refinement_thrust": _metric(dt[0] / max(abs(thrusts[1]), 1e-6), TOLERANCE["refinement_relative"]),
        "speed_contraction": _metric(du[1] / max(du[0], 1e-12), TOLERANCE["refinement_contraction"]),
        "thrust_contraction": _metric(dt[1] / max(dt[0], 1e-12), TOLERANCE["refinement_contraction"]),
    }


def verify(case: dict, value: Any) -> dict[str, Any]:
    try:
        if case["operation"] == "bohm":
            values = _array(value, len(case["te_ev"]), "bohm_speed")
            expected = [math.sqrt(E * t / M_XE) for t in case["te_ev"]]
            ratios = [values[i + 1] / values[i] for i in range(len(values) - 1)]
            roots = [math.sqrt(case["te_ev"][i + 1] / case["te_ev"][i]) for i in range(len(values) - 1)]
            checks = {
                "sound_speed_law": _check(values, expected, min(expected)),
                "square_root_scaling": _check(ratios, roots, 1.0),
                "monotonic_in_temperature": _metric(
                    0.0 if all(b > a > 0 for a, b in zip(values, values[1:])) else 1.0, 0.0),
            }
        else:
            if not isinstance(value, list) or len(value) != len(case["parameters"]):
                raise ValueError("Incorrect number of model results")
            checks = {}
            for i, (p, output) in enumerate(zip(case["parameters"], value), start=1):
                checks.update({f"model-{i}/{key}": c for key, c in _model_checks(p, output).items()})
            if case["operation"] in ("zero_field", "no_source"):
                checks.update(_limit_checks(case["operation"], case["parameters"][0], value[0]))
            elif case["operation"] == "refinement":
                checks.update(_refinement_checks(value))
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
        return {"status": "invalid_output", "detail": str(exc)[:500], "diagnostics": {}}
    failed = [name for name, check in checks.items() if not check["passed"]]
    return {
        "status": "mismatch" if failed else "passed",
        "detail": "Failed checks: " + ", ".join(failed) if failed else "All physical and numerical checks passed",
        "diagnostics": checks,
    }
