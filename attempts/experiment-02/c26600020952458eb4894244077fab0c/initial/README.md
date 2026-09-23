# Hall Transport & Potential Closure

Diagnose and repair a reduced axial electron transport model. The code runs, but
its outputs do not consistently satisfy the prescribed physical relations.
Edit `physics.py` and `model.py`, preserving the public interface and prescribed
profiles. Use only the Python standard library. `run.py` is a local example:

```bash
python run.py
```

From any directory, grade the workspace with:

```bash
epbench grade hall-transport --solution /path/to/workspace --json-out /path/to/results/hall.json
```

The JSON report must be outside the submission directory. Grading copies only
`physics.py` and `model.py` into a fresh working directory, imports them as
standalone modules, and calls their APIs. Additional helper files are not part of
this task's submission contract. Both modules must work without `run.py` first
being executed. Print output is discarded. Execution is trusted-local only,
**not a security sandbox**.

## Physical model

The coordinate x points from anode (0) to channel exit (L). Set `phi(0)=Vd`,
`phi(L)=0`, and `E=-d(phi)/dx`. Density, electron temperature, radial magnetic
field, and effective electron collision frequency are prescribed. There is no
ion-current term in the potential closure. The ion speed is a **passive energy
diagnostic**; do not feed it back into electron current or infer an ion density
from it.

Use the provided constants: `e=1.602176634e-19` C,
`m_e=9.1093837139e-31` kg, and `m_Xe=131.293 * 1.66053906892e-27` kg.
The nominal xenon mass neglects electron mass and isotope variation.
Electron temperature is in eV; all other quantities use SI units.

```text
p_e = n_e e T_e                         [Pa, with T_e in eV]
omega_ce = e B_r / m_e                  [s^-1]
mu_perp = e nu_e / (m_e (nu_e² + omega_ce²))  [m²/(V s)]
j_e = e n_e mu_perp E + mu_perp dp_e/dx  [A/m²]
E = j_e/(e n_e mu_perp) - (dp_e/dx)/(e n_e)
j_e = (Vd + integral (dp_e/dx)/(e n_e) dx)
      / integral 1/(e n_e mu_perp) dx
v_i² = v_in² + 2e (Vd - phi)/m_Xe       [m²/s²]
```

`j_e` is spatially constant **conventional electron current**, opposite to
negative-charge particle flow. Its sign is determined by the closure; a pressure
gradient may drive negative current, even at nonnegative applied voltage.
Potential need not be monotone and E need not be positive. Do not clamp these
quantities. Ion speed is the nonnegative square root; raise `ValueError` if its
squared value is negative anywhere. Such a profile has no real ion diagnostic
under these assumptions, rather than requiring a modified potential closure.

This is not a self-consistent or experimentally validated thruster simulation.
It omits ionization, electron energy evolution, sheaths, ion momentum sources,
and density evolution. The reduced electron momentum convention is described in
[HallThruster.jl's physics documentation](https://um-pepl.github.io/HallThruster.jl/stable/physics/).
No external simulator is required.

## API and prescribed profiles

`physics.cross_field_mobility(b_tesla, nu_per_s)` returns a scalar mobility.
The magnetic field may have either sign or be zero; frequency must be positive.

`model.Parameters` retains these fields and defaults:

| Field | Default | Unit |
| --- | ---: | --- |
| `voltage_v` | 300 | V |
| `length_m` | 0.038 | m |
| `n0_per_m3` | 2e18 | m^-3 |
| `te0_ev` | 20 | eV |
| `b_peak_t` | 0.02 | T |
| `nu0_per_s` | 2e7 | s^-1 |
| `ion_inlet_m_per_s` | 5000 | m/s |
| `n_cells` | 80 | integer |
| `density_bump` | 0.25 | dimensionless |
| `temperature_bump` | 0.20 | dimensionless |
| `nu_variation` | 0.10 | dimensionless |

All numeric inputs must be finite; booleans are not physical numbers. Length,
base density, temperature, and collision frequency are positive. Voltage and
inlet speed are nonnegative. Each variation has absolute value below one, and
`n_cells` is an integer at least four. Reject invalid parameters with `ValueError`.
Evaluation uses moderate scales: 0–600 V, 0.02–0.07 m, 8e17–7e18 m^-3,
8–50 eV, profile |B| up to 0.045 T, 2e7–1e9 s^-1 base frequency,
0–20000 m/s inlet speed, and 4–320 cells. Not every combination has a real ion
diagnostic. Graded model cases do; explicit rejection of invalid configurations
is tested separately. Standalone mobility checks also cover weak, transitional,
and strong magnetization and zero field at other finite B and nu values.

For `s=x/L`, `sample_profiles(p)` must preserve:

```text
x_i = L i/N                         i=0,...,N
n(s) = n0 (1 + density_bump sin(pi s))
T(s) = T0 (1 + temperature_bump sin(pi s + 0.2))
B(s) = b_peak (0.12 + 0.88 exp(-((s - 0.76)/0.24)²))
nu(s) = nu0 (1 + nu_variation cos(pi s))
```

`model.solve(p)` returns a dictionary with these entries:

| Keys | Shape |
| --- | --- |
| `x_m`, `n_per_m3`, `te_ev`, `b_t`, `nu_per_s` | N+1 node values each |
| `pressure_pa`, `potential_v`, `ion_speed_m_per_s` | N+1 node values each |
| `mu_face_m2_per_vs`, `pressure_gradient_pa_per_m`, `electric_field_v_per_m` | N face values each |
| `electron_current_density_a_per_m2` | scalar |

Arrays contain finite Python numbers, not booleans. Return every diagnostic;
consistent-looking potential alone is insufficient.

## Discrete contract and verification

Use uniform spacing `dx=L/N`, node pressures `p_i=e n_i T_i`, and arithmetic
face averages of n, B, and nu. Evaluate mobility **at those averaged inputs**;
do not average node mobilities. Use face pressure differences
`g_i=(p_(i+1)-p_i)/dx`. Both integrals in the current expression are face sums
multiplied by dx, and integrate potential using `phi_(i+1)=phi_i-E_i dx`.
Comparisons enforce this discrete equation, not exact continuum agreement on
coarse grids.

Verification covers the zero-field mobility limit, magnetic sign symmetry and
suppression, prescribed profiles, face/current and voltage closure, boundary
values, field gradient, ion energy, analytic limits, and grid refinement over
multiple conditions. Physical checks allow a maximum scaled residual of `1e-8`,
using prescribed characteristic scales to handle zeros. For the smooth refinement
cases, the 80-to-160-cell current change must be at most `1e-3` relative and the
maximum matched-node potential change at most `0.02` V. Refining again to 320
cells must reduce both changes by a factor at most `0.4` (second-order behavior).
Refinement agreement does not excuse failure of discrete physical constraints.

A task passes only if every evaluation case passes. Reports contain per-case
physical/numerical diagnostics; the fraction of cases passed is not agent pass@k.
Evaluation cases and references are withheld from this exported workspace at
runtime, but are publicly inspectable in the project repository.
