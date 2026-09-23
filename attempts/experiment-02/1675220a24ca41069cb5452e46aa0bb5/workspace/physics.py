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

    # For one Maxwellian, integrating P_M*sigma*v from the threshold upward
    # gives sigma0*sqrt(2e/m_e)*(2/sqrt(pi))*sqrt(T)*exp(-I/T).
    # The two-temperature population is a number-weighted mixture of these
    # rates, while the calibration fixes the one common sigma0 normalization.
    speed_scale = sqrt(2 * ELEMENTARY_CHARGE / ELECTRON_MASS)

    def thermal_factor(temperature):
        return (2 / sqrt(3.141592653589793) * sqrt(temperature) *
                exp(-THRESHOLD_EV / temperature))

    calibration_factor = speed_scale * thermal_factor(CALIBRATION_TE_EV)
    sigma0 = CALIBRATION_RATE_M3_PER_S / calibration_factor
    mixture_factor = ((1 - hot_fraction) * thermal_factor(cold) +
                      hot_fraction * thermal_factor(hot))
    return sigma0 * speed_scale * mixture_factor
