import math

ELEMENTARY_CHARGE = 1.602176634e-19  # C
XENON_ION_MASS = 2.1801714e-25  # kg, nominal Xe mass


def solve(v_in_m_s: float, discharge_v: float) -> float:
    energy_gain_j = ELEMENTARY_CHARGE * discharge_v
    return math.hypot(v_in_m_s, math.sqrt(energy_gain_j / (0.5 * XENON_ION_MASS)))
