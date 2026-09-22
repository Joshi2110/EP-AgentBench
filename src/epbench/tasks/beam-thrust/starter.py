"""EP-002: repair thrust from beam current."""

ELEMENTARY_CHARGE = 1.602176634e-19  # C
XENON_ION_MASS = 2.1801714e-25  # kg


def solve(beam_current_a: float, ion_speed_m_s: float, charge_state: int = 1) -> float:
    """Return ideal collimated xenon beam thrust [N]."""
    # Intentional defect: charge_state is ignored.
    return beam_current_a * XENON_ION_MASS * ion_speed_m_s / ELEMENTARY_CHARGE
