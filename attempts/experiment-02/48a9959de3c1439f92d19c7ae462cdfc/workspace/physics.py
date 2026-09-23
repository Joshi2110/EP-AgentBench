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

    # For a Maxwellian energy density, the required collision average is
    #
    #   <(1-I/e) v(e)> = sqrt(2 e_charge/m_e) *
    #                    2 sqrt(T/pi) exp(-I/T).
    #
    # This follows by integrating the thresholded cross section from I to
    # infinity; the two incomplete exponential moments cancel to T^2 exp(-I/T).
    def maxwellian_average(temperature):
        return (sqrt(2 * ELEMENTARY_CHARGE / ELECTRON_MASS)
                * 2 * sqrt(temperature / pi)
                * exp(-THRESHOLD_EV / temperature))

    calibration_average = maxwellian_average(CALIBRATION_TE_EV)
    sigma0 = CALIBRATION_RATE_M3_PER_S / calibration_average
    average = ((1 - hot_fraction) * maxwellian_average(cold)
               + hot_fraction * maxwellian_average(hot))
    return sigma0 * average
