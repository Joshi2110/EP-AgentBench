# Ion Momentum & Thrust Closure

Diagnose and repair a reduced quasi-one-dimensional ion momentum model. The code
runs and returns finite, plausible numbers, but its outputs do not consistently
satisfy the prescribed physical relations. Edit `physics.py` and `momentum.py`,
preserving the public interface and prescribed profiles. Use only the Python
standard library. `run.py` is a local example:

```bash
python run.py
```

From any directory, grade the workspace with:

```bash
epbench grade hall-thrust --solution /path/to/workspace --json-out /path/to/results/thrust.json
```

The JSON report must be outside the submission directory. Grading copies only
`physics.py` and `momentum.py` into a fresh working directory, imports them as
standalone modules, and calls their APIs. Additional helper files are not part of
this task's submission contract. Both modules must work without `run.py` first
being executed. Print output is discarded. Execution is trusted-local only,
**not a security sandbox**.

## Physical model

The coordinate `x` runs from the acceleration-region inlet at `x=0` to the
channel exit at `x=L`. The flow is steady and the channel area is constant.
Singly charged xenon ions flow in the `+x` direction.

Ions are created from neutrals drifting at a prescribed constant axial speed
`u_n`. Each new ion enters the ion fluid with this birth velocity. No ordering
between neutral and ion speeds is imposed. The prescribed source `S(x)` gives
the number of ions created per unit volume per unit time, in m^-3 s^-1.

The electric field `E(x)` and the source `S(x)` are **prescribed**. Ion density
and ion velocity are solved. Ion pressure, collisions between ions, and any
back-reaction on the field are neglected.

Use the provided constants: `e = 1.602176634e-19` C and
`m_Xe = 131.293 * 1.66053906892e-27` kg. Electron temperature is in eV; all
other quantities use SI units.

```text
d(n_i u_i)/dx   = S                                  particle conservation
d(n_i u_i^2)/dx = (e n_i / m_Xe) E + u_n S            conservative momentum balance
u_i(0) = sqrt(e T_e / m_Xe)                           inlet at the ion sound speed
n_i(0) = n_inlet
```

Here `n_i` is ion number density in m^-3, `u_i` and `u_n` are velocities in m/s,
and `E` is axial electric field in V/m. The momentum balance above is divided by
the ion mass; multiplying it by `m_Xe` gives force per volume in N/m^3.
Both inlet values are prescribed. This is an initial-value problem in `x`;
there is no additional exit boundary condition.

Two thrust diagnostics are reported, both per unit channel area, in N/m²:

```text
thrust_momentum = m_Xe [n_i u_i^2]_(x=L) - m_Xe [n_i u_i^2]_(x=0)
thrust_force    = integral_0^L ( e n_i E + m_Xe u_n S ) dx
```

Ion velocity must remain positive everywhere; raise `ValueError` if it does not.
This is a reduced model, not a self-consistent or experimentally validated
thruster simulation. It omits electron dynamics, ionization chemistry, sheaths,
neutral depletion, and radial losses.

## API and prescribed profiles

`physics.bohm_speed(te_ev)` returns the inlet ion sound speed in m/s and raises
`ValueError` for a nonpositive or nonfinite temperature.

`momentum.Parameters` is a frozen dataclass with these fields and defaults:

| Field | Default | Meaning |
| --- | --- | --- |
| `length_m` | `0.025` | Channel length `L` |
| `n_cells` | `80` | Number of cells, integer at least 4 |
| `e_peak_v_per_m` | `30000.0` | Peak electric field |
| `field_center` | `0.70` | Field peak position, as a fraction of `L` |
| `field_width` | `0.25` | Field Gaussian width, as a fraction of `L` |
| `s0_per_m3_s` | `4e23` | Peak ionization source |
| `source_center` | `0.15` | Source peak position, as a fraction of `L` |
| `source_width` | `0.25` | Source Gaussian width, as a fraction of `L` |
| `n_inlet_per_m3` | `5e17` | Inlet ion density |
| `te_ev` | `5.0` | Electron temperature setting the inlet speed |
| `u_neutral_m_per_s` | `300.0` | Neutral drift speed `u_n` |

With `s = x/L`, the prescribed profiles at cell centres `s_i = (i + 1/2)/N` are

```text
E(s)  = e_peak_v_per_m * exp(-((s - field_center)  / field_width)^2)
S(s)  = s0_per_m3_s    * exp(-((s - source_center) / source_width)^2)
```

`momentum.sample_profiles(p)` returns `x_m` at the `N+1` nodes and
`e_field_v_per_m` and `source_per_m3_s` at the `N` cell centres.

Reject invalid parameters with `ValueError`: `n_cells` must be an integer of at
least four; every other field must be a finite real number; length, inlet
density, and temperature must be positive; both widths must be positive; and
field, source, and neutral speed must be nonnegative.

## Discrete scheme

The channel is divided into `N` cells of width `dx = L/N`. State is stored at the
`N+1` nodes; `E` and `S` are evaluated once per cell at its centre. Apply each
conservative balance above to the interval between nodes `i` and `i+1`: the
outgoing minus incoming flux equals the cell-integrated right-hand side.
Approximate each right-hand-side integral by `dx` times its cell value, using
the **upwind density** at node `i` in the electric force and the prescribed
cell-centre field and source. Use this same quadrature for the force thrust.

The returned density and velocity must satisfy both cell balances with that
quadrature. You may choose the variables used internally to march the solution.
The contract is the discrete conservative balance, not an exact continuum
profile on a coarse grid.

`momentum.solve(p)` returns a dictionary containing `x_m`, `e_field_v_per_m`,
`source_per_m3_s`, the node arrays `n_per_m3` and `u_i_m_per_s`, and the scalars
`thrust_momentum_n_per_m2` and `thrust_force_n_per_m2`.

Verification covers the sound-speed law and its scaling, the prescribed profiles,
particle and momentum conservation cell by cell, the reported thrust
diagnostics, inlet boundary values, positivity, analytic limits with no field and
with no ionization, and grid refinement over several operating conditions. The
scheme is first order, so refinement checks allow the expected first-order
contraction. Physical checks allow a maximum scaled residual of `1e-8`.

A task passes only if every evaluation case passes. Reports contain per-case
physical and numerical diagnostics; the fraction of cases passed is not agent
pass@k.

Evaluation cases and reference implementations are withheld from this exported
workspace at runtime, but are publicly inspectable in the project repository.
