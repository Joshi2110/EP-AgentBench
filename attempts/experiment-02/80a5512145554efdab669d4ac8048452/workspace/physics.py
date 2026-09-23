"""Idealized electron-impact ionization with a prescribed energy distribution."""

from math import exp, isfinite, sqrt

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

    # For one Maxwellian, integrating sigma(epsilon) v(epsilon) P_M over
    # epsilon >= THRESHOLD_EV gives a common constant times
    # sqrt(T) * exp(-THRESHOLD_EV / T).  The mixture rate is the fraction-
    # weighted sum of that expression.  Normalize the single cross-section
    # constant with the supplied 20 eV calibration.
    def collision_factor(temperature):
        return sqrt(temperature) * exp(-THRESHOLD_EV / temperature)

    mixture_factor = ((1 - hot_fraction) * collision_factor(cold)
                      + hot_fraction * collision_factor(hot))
    calibration_factor = collision_factor(CALIBRATION_TE_EV)
    return CALIBRATION_RATE_M3_PER_S * mixture_factor / calibration_factor
