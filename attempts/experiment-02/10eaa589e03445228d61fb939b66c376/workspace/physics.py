"""Idealized electron-impact ionization with a prescribed energy distribution."""

from math import exp, isfinite, pi, sqrt

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

    # Integrating sigma(epsilon) v(epsilon) against the stated probability
    # density gives, for one Maxwellian component,
    #
    #   sigma0 * 2 sqrt(2 e / m_e) / sqrt(pi)
    #       * sqrt(T) * exp(-I / T).
    # The threshold integral is particularly simple because the factor
    # (epsilon - I) cancels the otherwise incomplete-gamma expression.
    def component_factor(temperature):
        return sqrt(temperature) * exp(-THRESHOLD_EV / temperature)

    kinetic_prefactor = (2.0 * sqrt(2.0 * ELEMENTARY_CHARGE / ELECTRON_MASS)
                         / sqrt(pi))
    sigma0 = CALIBRATION_RATE_M3_PER_S / (
        kinetic_prefactor * component_factor(CALIBRATION_TE_EV))
    mixture_factor = ((1.0 - hot_fraction) * component_factor(cold)
                      + hot_fraction * component_factor(hot))
    return sigma0 * kinetic_prefactor * mixture_factor
