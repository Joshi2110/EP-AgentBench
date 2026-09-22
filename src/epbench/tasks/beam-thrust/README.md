# EP-002: Thrust from xenon ion beam current

Repair `starter.py` so `solve(beam_current_a, ion_speed_m_s, charge_state=1)`
returns ideal axial thrust magnitude in **newtons**. Keep the signature and
return a finite Python `int` or `float`, not a boolean. The submission must be a
single file using the standard library.

Assume a steady, monoenergetic, perfectly collimated beam containing one xenon
charge state. The current is **ion beam current**, not total discharge current
or electron current. Each ion carries charge `Z * e`, so the ion rate is
`I_b / (Z * e)` and the axial momentum per ion is `m * v`.
Their product is the outgoing momentum flux, identified here with thrust.
Neglect incoming axial momentum, neutral thrust, divergence, and pressure forces.
The force on the thruster points opposite the beam; return its nonnegative
magnitude. Mixed charge populations are outside this model.

Inputs are finite real numbers: `0 <= beam_current_a <= 10` A and
`0 <= ion_speed_m_s <= 100000` m/s; `charge_state` is integer 1 or 2 and may
be omitted (default 1). Zero current or speed must give zero thrust.
Zero speed at nonzero current is tested only as an algebraic limit.
Behavior outside this domain is not graded.
Use `e = 1.602176634e-19` C and nominal `m = 2.1801714e-25` kg for both
charge states, neglecting electron mass and isotope variation.

The starter intentionally ignores charge state. It passes singly charged cases
but overestimates nonzero doubly charged beam thrust by a factor of two.

Grading uses `math.isclose` with relative tolerance `1e-6` and absolute
tolerance `1e-12` N. Each case runs in a fresh process and temporary directory;
only your file is copied. Prints are discarded. Import-time errors, exceptions,
nonfinite/non-scalar returns, and timeouts fail the case. This is an ideal beam
relation, not a complete thruster performance model.
