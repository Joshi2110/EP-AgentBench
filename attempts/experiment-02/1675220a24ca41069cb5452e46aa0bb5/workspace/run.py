"""Print controlled temperature and distribution-shape sweeps."""

import json

from continuity import Parameters, solve
from physics import rate_coefficient

if __name__ == "__main__":
    for temperature, fraction in ((5, 0), (10, 0), (20, 0), (30, 0), (5, 0.2), (10, 0.2)):
        p = Parameters(te_ev=temperature, hot_fraction=fraction, hot_ratio=5)
        result = solve(p)
        print(json.dumps({"te_ev": temperature, "hot_fraction": fraction, "hot_ratio": 5,
                          "rate_m3_per_s": rate_coefficient(temperature, fraction, 5),
                          "neutral_conversion": result["neutral_conversion"]}))
