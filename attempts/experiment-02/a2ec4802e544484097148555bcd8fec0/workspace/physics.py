"""Physical constants and the reduced cross-field mobility closure."""

from math import isfinite

ELEMENTARY_CHARGE = 1.602176634e-19  # C
ELECTRON_MASS = 9.1093837139e-31  # kg
ATOMIC_MASS_UNIT = 1.66053906892e-27  # kg
XENON_ION_MASS = 131.293 * ATOMIC_MASS_UNIT  # nominal Xe+ mass, kg


def cross_field_mobility(b_tesla: float, nu_per_s: float) -> float:
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
        for v in (b_tesla, nu_per_s)
    ) or nu_per_s <= 0:
        raise ValueError("Field must be finite and collision frequency finite and positive")
    omega_ce = ELEMENTARY_CHARGE * b_tesla / ELECTRON_MASS
    return ELEMENTARY_CHARGE * nu_per_s / (
        ELECTRON_MASS * (nu_per_s**2 + omega_ce**2)
    )
