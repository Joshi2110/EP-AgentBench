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

    # For a Maxwellian energy density, the collision integral is analytic:
    # integral[(1-I/e) v(e) P_M(e; T) de]
    # = 2 sqrt(2 e_charge / m_e) sqrt(T) exp(-I/T) / sqrt(pi).
    def collision_integral(temperature_ev):
        return (2.0 * sqrt(2.0 * ELEMENTARY_CHARGE / ELECTRON_MASS)
                * sqrt(temperature_ev) * exp(-THRESHOLD_EV / temperature_ev)
                / sqrt(3.141592653589793))

    normalization = CALIBRATION_RATE_M3_PER_S / collision_integral(CALIBRATION_TE_EV)
    average = ((1.0 - hot_fraction) * collision_integral(cold)
               + hot_fraction * collision_integral(hot))
    return normalization * average
