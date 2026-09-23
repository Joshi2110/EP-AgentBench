"""Independent energy quadrature and conservative ionization verification."""

from functools import lru_cache
import math
import random

E = 1.602176634e-19
M_E = 9.1093837139e-31
THRESHOLD_EV = 12.12984
TOLERANCE = {"scaled_residual": 1e-8, "refinement_absolute": 2e-3, "refinement_contraction": 0.35}
DEFAULTS = {
    "length_m": 0.03, "n_cells": 80, "te_ev": 20.0, "temperature_variation": 0.0,
    "hot_fraction": 0.0, "hot_ratio": 4.0, "ion_flux_in_per_m2_s": 5e20,
    "neutral_flux_in_per_m2_s": 1.2e22, "ion_speed_m_per_s": 12000.0,
    "velocity_rise": 0.5, "neutral_speed_m_per_s": 300.0,
}


def cases():
    yield {"operation": "rate", "distributions": [[t, 0, 4] for t in (4, 6, 9, 13, 20, 32, 40)]}
    yield {"operation": "rate", "distributions": [[t, h, 5] for t in (5, 10) for h in (0, 0.08, 0.2, 0.3)]}
    rng = random.Random(503)
    yield {"operation": "rate", "distributions": [
        [rng.uniform(3, 55), rng.uniform(0, 0.3), rng.uniform(1, 6)] for _ in range(12)]}
    conditions = [
        {}, {"te_ev": 8, "n_cells": 41},
        {"te_ev": 13, "neutral_flux_in_per_m2_s": 9e21, "length_m": 0.025, "n_cells": 37},
        {"te_ev": 32, "ion_flux_in_per_m2_s": 8e20, "neutral_speed_m_per_s": 650, "n_cells": 53},
        {"te_ev": 10, "hot_fraction": 0.2, "hot_ratio": 5, "n_cells": 57},
        {"te_ev": 10, "hot_fraction": 0, "hot_ratio": 5, "n_cells": 57},
        {"te_ev": 17, "temperature_variation": 0.4, "hot_fraction": 0.12, "hot_ratio": 3,
         "ion_speed_m_per_s": 19000, "velocity_rise": 1.2, "n_cells": 4},
    ]
    for changes in conditions:
        yield {"operation": "model", "parameters": [DEFAULTS | changes]}
    yield {"operation": "no_seed", "parameters": [DEFAULTS | {"ion_flux_in_per_m2_s": 0.0}]}
    for changes in ({"te_ev": 12, "temperature_variation": 0.4},
                    {"te_ev": 27, "temperature_variation": -0.3, "hot_fraction": 0.23, "hot_ratio": 5}):
        yield {"operation": "refinement", "parameters": [DEFAULTS | changes | {"n_cells": n}
                                                          for n in (40, 80, 160)]}


@lru_cache(maxsize=4096)
def _collision_integral(temperature, panels=2048):
    # Integrate sigma/sigma0 * speed * energy PDF, using z=(energy-I)/T.
    # This is an energy PDF (eV^-1), not an energy probability function (eV^-3/2).
    step = 48.0 / panels
    terms = []
    for j in range(panels + 1):
        energy = THRESHOLD_EV + temperature * j * step
        cross_section = 1 - THRESHOLD_EV / energy
        speed = math.sqrt(2 * E * energy / M_E)
        pdf = 2 * math.sqrt(energy) * math.exp(-energy / temperature) / (math.sqrt(math.pi) * temperature**1.5)
        weight = 1 if j in (0, panels) else 4 if j % 2 else 2
        terms.append(weight * cross_section * speed * pdf * temperature)
    return step * math.fsum(terms) / 3


@lru_cache(maxsize=4096)
def _rate(te, fraction=0.0, ratio=4.0):
    cold = te / (1 - fraction + fraction * ratio)
    integral = (1 - fraction) * _collision_integral(cold) + fraction * _collision_integral(ratio * cold)
    return 3e-14 * integral / _collision_integral(20.0)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Outputs must be finite real numbers, not booleans")
    return float(value)


def _array(out, name, size):
    values = out.get(name)
    if not isinstance(values, list) or len(values) != size:
        raise ValueError(f"Incorrect shape for {name}")
    return [_number(v) for v in values]


def _metric(error, tolerance=1e-8):
    return {"passed": math.isfinite(error) and error <= tolerance,
            "error": error if math.isfinite(error) else None, "tolerance": tolerance}


def _check(actual, expected, scale):
    return _metric(max(abs(a - b) / max(abs(b), scale) for a, b in zip(actual, expected)))


def _model_checks(p, out):
    if not isinstance(out, dict):
        raise ValueError("solve must return a dictionary")
    n, dx = p["n_cells"], p["length_m"] / p["n_cells"]
    x = [i * dx for i in range(n + 1)]
    speed = [p["ion_speed_m_per_s"] * (1 + p["velocity_rise"] * i / n) for i in range(n + 1)]
    te = [p["te_ev"] * (1 + p["temperature_variation"] * math.sin(2 * math.pi * (i + 0.5) / n)) for i in range(n)]
    ni, nn = _array(out, "n_i_per_m3", n + 1), _array(out, "n_n_per_m3", n + 1)
    k = [_rate(t, p["hot_fraction"], p["hot_ratio"]) for t in te]
    reported_k = _array(out, "rate_m3_per_s", n)
    source = _array(out, "source_per_m3_s", n)
    checks = {
        "x_m": _check(_array(out, "x_m", n + 1), x, p["length_m"]),
        "ion_speed": _check(_array(out, "ion_speed_m_per_s", n + 1), speed, max(speed)),
        "temperature": _check(_array(out, "te_ev", n), te, max(te)),
        "rate_law": _check(reported_k, k, max(k)),
        "physical_state": _metric(0 if min(ni) >= 0 and min(nn) > 0 and min(source) >= 0 else 1, 0),
    }
    gi = [a * b for a, b in zip(ni, speed)]
    gn = [a * p["neutral_speed_m_per_s"] for a in nn]
    total = p["ion_flux_in_per_m2_s"] + p["neutral_flux_in_per_m2_s"]
    checks["inlet_fluxes"] = _check([gi[0], gn[0]], [p["ion_flux_in_per_m2_s"], p["neutral_flux_in_per_m2_s"]], total)
    checks["particle_conservation"] = _check([a + b for a, b in zip(gi, gn)], [total] * (n + 1), total)
    production = [dx * s for s in source]
    checks["ion_source"] = _check([b - a for a, b in zip(gi, gi[1:])], production, total)
    checks["neutral_sink"] = _check([a - b for a, b in zip(gn, gn[1:])], production, total)
    # Reconstruct each physical cell response independently of reported rates/sources.
    expected = []
    for i, rate in enumerate(k):
        alpha = total * rate * dx / ((speed[i] + speed[i + 1]) / 2 * p["neutral_speed_m_per_s"])
        fraction = gi[i] / total
        if not 0 <= fraction < 1:
            raise ValueError("Ion fraction must be in [0,1)")
        response = fraction / (fraction + (1 - fraction) * math.exp(-alpha))
        expected.append(total * (response - fraction))
    checks["kinetic_source"] = _check(production, expected, total)
    conversion = 1 - gn[-1] / p["neutral_flux_in_per_m2_s"]
    checks["reported_conversion"] = _check([_number(out.get("neutral_conversion"))], [conversion], 1.0)
    return checks


def verify(case, value):
    try:
        if case["operation"] == "rate":
            values = _array({"rate": value}, "rate", len(case["distributions"]))
            expected = [_rate(*d) for d in case["distributions"]]
            # Per-distribution scaling prevents large rates from masking cold-tail errors.
            checks = {f"distribution-{i}": _check([a], [b], b)
                      for i, (a, b) in enumerate(zip(values, expected))}
        else:
            if not isinstance(value, list) or len(value) != len(case["parameters"]):
                raise ValueError("Incorrect number of model results")
            checks = {}
            for i, (p, out) in enumerate(zip(case["parameters"], value)):
                checks.update({f"model-{i}/{k}": v for k, v in _model_checks(p, out).items()})
            if case["operation"] == "refinement":
                fractions = [[ni * u / (p["ion_flux_in_per_m2_s"] + p["neutral_flux_in_per_m2_s"])
                              for ni, u in zip(out["n_i_per_m3"], out["ion_speed_m_per_s"])]
                             for p, out in zip(case["parameters"], value)]
                differences = [max(abs(a - b) for a, b in zip(coarse, fine[::2]))
                               for coarse, fine in zip(fractions, fractions[1:])]
                checks["refinement_fraction"] = _metric(differences[0], TOLERANCE["refinement_absolute"])
                checks["contraction"] = _metric(differences[1] / max(differences[0], 1e-14), TOLERANCE["refinement_contraction"])
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
        return {"status": "invalid_output", "detail": str(exc)[:500], "diagnostics": {}}
    failed = [name for name, c in checks.items() if not c["passed"]]
    return {"status": "mismatch" if failed else "passed", "diagnostics": checks,
            "detail": "Failed checks: " + ", ".join(failed) if failed else "All physical and numerical checks passed"}
