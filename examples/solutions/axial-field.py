def solve(phi_left_v: float, phi_right_v: float, length_m: float) -> float:
    potential_gradient = (phi_right_v - phi_left_v) / length_m
    return -potential_gradient
