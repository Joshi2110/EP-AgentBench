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
channel exit at `x=L`. Singly charged xenon ions flow in the `+x` direction.

Ions are **created from neutrals**. The neutral gas drifts at a constant speed
`u_n`, much slower than the ions. An ion created at position `x` therefore enters
the ion fluid carrying the neutral velocity, not the local ion velocity. The
prescribed ionization source `S(x)` gives the number of ions created per unit
volume per unit time.

The electric field `E(x)` and the source `S(x)` are **prescribed**. Ion density
and ion velocity are solved. Ion pressure, collisions between ions, and any
back-reaction on the field are neglected.

Use the provided constants: `e = 1.602176634e-19` C and
`m_Xe = 131.293 * 1.66053906892e-27` kg. Electron temperature is in eV; all
other quantities use SI units.

```text
d(n_i u_i)/dx   = S                                   particle conservation
d(n_i u_i^2)/dx = (e n_i / m_Xe) E + u_n S            momentum conservation
n_i u_i du_i/dx = (e n_i / m_Xe) E + (u_n - u_i) S    equivalent velocity form
u_i(0) = sqrt(e T_e / m_Xe)                           inlet at the ion sound speed
n_i(0) = n_inlet
```

The two momentum forms are equivalent given particle conservation. The velocity
form is the one this solver marches.

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
`N+1` nodes; `E` and `S` are evaluated once per cell at its centre. Marching from
node `i` to node `i+1` uses the cell-`i` values and the **upwind** density and
velocity, that is the values at node `i`:

```text
flux_next   = n_i u_i + dx S_i
u_(i+1)     = u_i + dx * [ (e/m_Xe) n_i E_i + (u_n - u_i) S_i ] / flux_next
n_(i+1)     = flux_next / u_(i+1)
```

Both integrals in the thrust diagnostics use the same upwind convention, that is
`sum over cells of dx * (e n_i E_i + m_Xe u_n S_i)`.

`momentum.solve(p)` returns a dictionary containing `x_m`, `e_field_v_per_m`,
`source_per_m3_s`, the node arrays `n_per_m3` and `u_i_m_per_s`, and the scalars
`thrust_momentum_n_per_m2` and `thrust_force_n_per_m2`.

Verification covers the sound-speed law and its scaling, the prescribed profiles,
particle and momentum conservation cell by cell, the reported thrust
diagnostics, inlet boundary values, positivity, analytic limits with no field and
with no ionization, and grid refinement over several operating conditions. The
scheme above is first order, so refinement checks allow the expected first-order
contraction. Physical checks allow a maximum scaled residual of `1e-8`.

A task passes only if every evaluation case passes. Reports contain per-case
physical and numerical diagnostics; the fraction of cases passed is not agent
pass@k.
