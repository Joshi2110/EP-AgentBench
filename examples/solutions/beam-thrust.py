ELEMENTARY_CHARGE = 1.602176634e-19  # C
XENON_ION_MASS = 2.1801714e-25  # kg, nominal Xe mass


def solve(beam_current_a: float, ion_speed_m_s: float, charge_state: int = 1) -> float:
    ions_per_second = beam_current_a / (charge_state * ELEMENTARY_CHARGE)
    momentum_per_ion = XENON_ION_MASS * ion_speed_m_s
    return ions_per_second * momentum_per_ion
