# EP-003: Axial electric field

Repair `starter.py` so `solve(phi_left_v, phi_right_v, length_m)` returns the
**signed** axial electric field in **V/m**. Keep the signature and return a
finite Python `int` or `float`, not a boolean. The submission must be a single
file using the standard library.

Assume a linear electrostatic potential between endpoints separated by
`length_m`. The positive axis points from left to right and `E_x = -d(phi)/dx`.
The field is constant in this idealization. Equal potentials give zero field;
rising potential gives a negative field. Adding the same offset to both
potentials must leave the field unchanged. This endpoint relation does not
reconstruct a spatially varying Hall-thruster field.

Inputs are finite real numbers: both potentials lie in `[-1000, 1000]` V and
`0.001 <= length_m <= 1` m. Negative and equal potentials are allowed.
Behavior outside this domain (including zero or negative length) is not graded.

The starter intentionally returns the potential gradient with the wrong sign.
It passes equal-potential cases and fails every nonzero-field case.

Grading uses `math.isclose` with relative tolerance `1e-6` and absolute
tolerance `1e-8` V/m. Each case runs in a fresh process and temporary directory;
only your file is copied. Prints are discarded. Import-time errors, exceptions,
nonfinite/non-scalar returns, and timeouts fail the case.
