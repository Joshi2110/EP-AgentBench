"""Local example: solve the default case and print a short summary."""

import json

from momentum import Parameters, solve

if __name__ == "__main__":
    result = solve(Parameters())
    print(json.dumps({
        "exit_speed_m_per_s": result["u_i_m_per_s"][-1],
        "exit_density_per_m3": result["n_per_m3"][-1],
        "thrust_momentum_n_per_m2": result["thrust_momentum_n_per_m2"],
        "thrust_force_n_per_m2": result["thrust_force_n_per_m2"],
    }, indent=2))
