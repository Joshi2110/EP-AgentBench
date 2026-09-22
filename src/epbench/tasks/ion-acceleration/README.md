# EP-001: Xe+ ion acceleration

Repair `starter.py` so `solve(v_in_m_s, discharge_v)` returns the exit speed
in **m/s**. Keep the signature and return a finite Python `int` or `float`,
not a boolean. The submission must be a single file using the standard library.

Assume steady, one-dimensional, nonrelativistic, collisionless acceleration of
singly charged xenon ions. Conservation of energy gives
`m * (v_out**2 - v_in**2) / 2 = e * discharge_v`.
The parameter `discharge_v` is the accelerating potential drop **experienced by
the ion**, not necessarily the terminal discharge voltage of a real thruster.
Ignore ionization, collisions, divergence, wall interactions, and space charge.

Inputs are finite real numbers: `0 <= v_in_m_s <= 100000` and
`0 <= discharge_v <= 1000` V. Zero drop leaves the speed unchanged; zero entry
speed is allowed. Behavior outside this domain is not graded.
Use the supplied `e = 1.602176634e-19` C and nominal
`m = 2.1801714e-25` kg. The mass is fixed for this task, approximates natural
xenon, and neglects electron mass and isotope variation.

The starter intentionally subtracts the electric work. It usually raises a
square-root domain error and otherwise predicts the wrong speed at nonzero
drop. Repair this energy balance.

Grading uses `math.isclose` with relative tolerance `1e-6` and absolute
tolerance `1e-8` m/s. Each case runs in a fresh process and temporary directory;
only your file is copied. Prints are discarded. Import-time errors, exceptions,
nonfinite/non-scalar returns, and timeouts fail the case. This is a reduced
analytic exercise, not a validated Hall-thruster model.
