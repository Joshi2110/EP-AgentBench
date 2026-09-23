"""Conservative ion production and neutral depletion for prescribed plasma conditions."""

from dataclasses import dataclass, fields
from math import exp, isfinite, pi, sin

from physics import rate_coefficient


@dataclass(frozen=True)
class Parameters:
    length_m: float = 0.03
    n_cells: int = 80
    te_ev: float = 20.0
    temperature_variation: float = 0.0
    hot_fraction: float = 0.0
    hot_ratio: float = 4.0
    ion_flux_in_per_m2_s: float = 5e20
    neutral_flux_in_per_m2_s: float = 1.2e22
    ion_speed_m_per_s: float = 12000.0
    velocity_rise: float = 0.5
    neutral_speed_m_per_s: float = 300.0


def _validate(p):
    if isinstance(p.n_cells, bool) or not isinstance(p.n_cells, int) or not 4 <= p.n_cells <= 640:
        raise ValueError("n_cells must be an integer from 4 to 640")
    bounds = {
        "length_m": (0.01, 0.04), "te_ev": (4, 40), "temperature_variation": (-0.5, 0.5),
        "hot_fraction": (0, 0.3), "hot_ratio": (1, 6), "ion_flux_in_per_m2_s": (0, 1e21),
        "neutral_flux_in_per_m2_s": (1e21, 1.5e22), "ion_speed_m_per_s": (10000, 30000),
        "velocity_rise": (0, 2), "neutral_speed_m_per_s": (250, 1000),
    }
    for field in fields(p):
        if field.name == "n_cells":
            continue
        v = getattr(p, field.name)
        lo, hi = bounds[field.name]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"{field.name} is outside the documented domain")


def sample_profiles(p):
    _validate(p)
    return {
        "x_m": [p.length_m * i / p.n_cells for i in range(p.n_cells + 1)],
        "ion_speed_m_per_s": [p.ion_speed_m_per_s * (1 + p.velocity_rise * i / p.n_cells)
                             for i in range(p.n_cells + 1)],
        "te_ev": [p.te_ev * (1 + p.temperature_variation * sin(2 * pi * (i + 0.5) / p.n_cells))
                  for i in range(p.n_cells)],
    }


def solve(p: Parameters) -> dict:
    profiles = sample_profiles(p)
    dx = p.length_m / p.n_cells
    total = p.ion_flux_in_per_m2_s + p.neutral_flux_in_per_m2_s
    ions, neutrals = [p.ion_flux_in_per_m2_s], [p.neutral_flux_in_per_m2_s]
    rates, sources = [], []
    for i, temperature in enumerate(profiles["te_ev"]):
        k = rate_coefficient(temperature, p.hot_fraction, p.hot_ratio)
        speed = p.ion_speed_m_per_s * (1 + p.velocity_rise * (i + 0.5) / p.n_cells)
        # In a cell with frozen coefficients, Gi obeys the logistic equation
        # dGi/dx = [k/(ui*un)] Gi (total-Gi).  Evolving its odds exactly
        # preserves both flux conservation and the no-seed solution.
        old_ion = ions[-1]
        old_neutral = neutrals[-1]
        if old_ion == 0.0 or old_neutral == 0.0 or k == 0.0:
            ion, neutral = old_ion, old_neutral
        else:
            odds = old_ion / old_neutral
            growth = exp(dx * total * k / (speed * p.neutral_speed_m_per_s))
            new_odds = odds * growth
            neutral = total / (1 + new_odds)
            ion = total - neutral
        rates.append(k)
        sources.append((ion - old_ion) / dx)
        ions.append(ion)
        neutrals.append(neutral)
    return {
        **profiles,
        "n_i_per_m3": [g / u for g, u in zip(ions, profiles["ion_speed_m_per_s"])],
        "n_n_per_m3": [g / p.neutral_speed_m_per_s for g in neutrals],
        "rate_m3_per_s": rates,
        "source_per_m3_s": sources,
        "neutral_conversion": 1 - neutrals[-1] / neutrals[0],
    }
