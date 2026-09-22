"""EP-001: repair the ion acceleration relation."""

import math

ELEMENTARY_CHARGE = 1.602176634e-19  # C
XENON_ION_MASS = 2.1801714e-25  # kg


def solve(v_in_m_s: float, discharge_v: float) -> float:
    """Return ideal Xe+ exit speed [m/s] for a nonnegative potential drop [V]."""
    # Intentional defect: the electric work has the wrong sign.
    return math.sqrt(v_in_m_s**2 - 2 * ELEMENTARY_CHARGE * discharge_v / XENON_ION_MASS)
