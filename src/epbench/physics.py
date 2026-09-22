"""Reduced physical relations for inputs in the documented task domains."""

import math

ELEMENTARY_CHARGE = 1.602176634e-19  # C, exact SI definition
XENON_ION_MASS = 2.1801714e-25  # kg, fixed nominal Xe mass; electron mass neglected


def ion_exit_speed(v_in_m_s: float, discharge_v: float) -> float:
    """Ideal Xe+ speed from kinetic energy gained across a nonnegative drop."""
    return math.sqrt(v_in_m_s**2 + 2 * ELEMENTARY_CHARGE * discharge_v / XENON_ION_MASS)


def ideal_beam_thrust(beam_current_a: float, ion_speed_m_s: float, charge_state: int = 1) -> float:
    """Ideal collimated beam thrust in N: I_b * m_Xe * v / (Z e)."""
    return beam_current_a * XENON_ION_MASS * ion_speed_m_s / (charge_state * ELEMENTARY_CHARGE)


def axial_electric_field(phi_left_v: float, phi_right_v: float, length_m: float) -> float:
    """Signed constant E (V/m), with the positive axis from left to right."""
    return (phi_left_v - phi_right_v) / length_m
