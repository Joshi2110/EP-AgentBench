"""Physical constants and the ion sound-speed inlet closure."""

from math import isfinite, sqrt

ELEMENTARY_CHARGE = 1.602176634e-19  # C
ATOMIC_MASS_UNIT = 1.66053906892e-27  # kg
XENON_ION_MASS = 131.293 * ATOMIC_MASS_UNIT  # nominal Xe+ mass, kg


def bohm_speed(te_ev: float) -> float:
    """Return ``sqrt(e * T_e / m_Xe)`` for ``T_e`` in eV."""
    if isinstance(te_ev, bool) or not isinstance(te_ev, (int, float)) or not isfinite(te_ev) or te_ev <= 0:
        raise ValueError("Electron temperature must be a finite positive number of eV")
    return sqrt(ELEMENTARY_CHARGE * te_ev / XENON_ION_MASS)
