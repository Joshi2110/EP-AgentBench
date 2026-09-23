"""Print a representative model result."""

import json

from model import Parameters, solve


def main() -> None:
    p = Parameters()
    result = solve(p)
    print(json.dumps({
        "electron_current_density_a_per_m2": result["electron_current_density_a_per_m2"],
        "exit_potential_v": result["potential_v"][-1],
        "exit_ion_speed_m_per_s": result["ion_speed_m_per_s"][-1],
    }, indent=2))


if __name__ == "__main__":
    main()
