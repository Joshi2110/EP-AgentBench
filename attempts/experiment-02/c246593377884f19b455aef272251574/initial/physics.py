"""Idealized electron-impact ionization with a prescribed energy distribution."""

from math import isfinite, sqrt

ELEMENTARY_CHARGE = 1.602176634e-19
ELECTRON_MASS = 9.1093837139e-31
THRESHOLD_EV = 12.12984
CALIBRATION_TE_EV = 20.0
CALIBRATION_RATE_M3_PER_S = 3.0e-14


def rate_coefficient(te_ev: float, hot_fraction: float = 0.0, hot_ratio: float = 4.0) -> float:
    """Return the ionization coefficient in m^3/s."""
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
           for v in (te_ev, hot_fraction, hot_ratio)):
        raise ValueError("Distribution parameters must be finite real numbers")
    if not 2 <= te_ev <= 60 or not 0 <= hot_fraction <= 0.3 or not 1 <= hot_ratio <= 6:
        raise ValueError("Distribution parameters are outside the documented domain")
    cold = te_ev / (1 + hot_fraction * (hot_ratio - 1))
    hot = hot_ratio * cold

    def collision_proxy(energy_ev):
        cross_section_shape = max(1 - THRESHOLD_EV / energy_ev, 0.0)
        speed = sqrt(2 * ELEMENTARY_CHARGE * energy_ev / ELECTRON_MASS)
        return cross_section_shape * speed

    representative_energy = 1.5 * ((1 - hot_fraction) * cold + hot_fraction * hot)
    normalization = CALIBRATION_RATE_M3_PER_S / collision_proxy(1.5 * CALIBRATION_TE_EV)
    return normalization * collision_proxy(representative_energy)
