"""EP-003: repair the signed axial electric field."""


def solve(phi_left_v: float, phi_right_v: float, length_m: float) -> float:
    """Return signed E_x [V/m] from a linear potential profile."""
    # Intentional defect: this is the gradient, not its negative.
    return (phi_right_v - phi_left_v) / length_m
