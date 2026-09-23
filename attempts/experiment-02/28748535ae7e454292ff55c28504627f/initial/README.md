# Ionization & Neutral Depletion

Repair a reduced Hall-channel ionization model that agrees with a nominal
calibration but does not reproduce the supplied off-nominal observations.
Edit `physics.py` and `continuity.py`, keeping their APIs and prescribed profiles.
Use only the Python standard library. `python run.py` prints controlled sweeps.
All information needed for this task is here; no external data or simulator is
required. Diagnose the model rather than fit a separate coefficient for each case.

## Physical assumptions and collision model

The steady channel has constant area and coordinate `0 <= x <= L`. Singly
charged ions and neutrals travel in the positive direction. Ion speed is
prescribed; neutral speed is constant. Quasineutrality gives `n_e = n_i`.
Electron-impact ionization creates one ion and consumes one neutral. There is no
recombination, wall loss, charge exchange, or external electron seed. Electron
energy evolution, ion momentum, and neutral heating are not solved.

Electron kinetic energy `epsilon` and temperature parameters are in eV.
`e = 1.602176634e-19 C`, `m_e = 9.1093837139e-31 kg`, and the ionization
threshold is `I = 12.12984 eV`. For this task the idealized cross-section is

```text
sigma(epsilon) = 0                              for epsilon < I
sigma(epsilon) = sigma0 * (1 - I/epsilon)         for epsilon >= I
v(epsilon) = sqrt(2 e epsilon / m_e)             [m/s]
```

`sigma0` is one positive constant in m^2. In a short time `dt`, an electron of
energy `epsilon` has ionization probability `n_n sigma(epsilon) v(epsilon) dt`.
Neutral motion is negligible relative to electron speed for collision counting.
The local electron population is specified by this normalized energy probability
density, in eV^-1 (not the energy probability function sometimes used in plasma
software):

```text
P_M(epsilon; T) = 2 sqrt(epsilon) exp(-epsilon/T) / (sqrt(pi) T^(3/2))
P(epsilon) = (1-h) P_M(epsilon; T_c) + h P_M(epsilon; T_h)
T_c = T / (1-h+h r),    T_h = r T_c
```

`h` is the number fraction in the hotter population, and `r` is its temperature
ratio. `T` is the mean-energy temperature: the population's mean kinetic energy
is `3 T / 2`, including when `h` changes. `h=0` or `r=1` gives a single Maxwellian.
These distributions and the cross-section are defined for all nonnegative
energies. Ionization is determined by collision counting for this population.

Determine the single cross-section normalization using the synthetic calibration
`K(20 eV, h=0) = 3.0e-14 m^3/s`, where `K` is the population ionization rate
coefficient. Use that same normalization throughout the task. This calibration,
the microscopic model, and the distribution fully specify the rate; the
additional observations below are checks, not a finite table defining the law.

This is an idealized kinetic model, not a measured xenon cross-section fit or an
experimentally validated thruster simulation. All calibration and response values
below are synthetic.

## Continuity, profiles, and boundary conditions

```text
Gamma_i = n_i u_i                [m^-2 s^-1]
Gamma_n = n_n u_n                [m^-2 s^-1]
d Gamma_i/dx = S
d Gamma_n/dx = -S
S = n_i n_n K                    [m^-3 s^-1]
```

Both inlet fluxes are prescribed. No outlet boundary condition is imposed.
With no seed ions there are no electrons under the quasineutral assumption and
therefore no ionization. Let `s=x/L`. Preserve

```text
T(s) = te_ev * (1 + temperature_variation * sin(2 pi s))
u_i(s) = ion_speed_m_per_s * (1 + velocity_rise * s)
u_n = neutral_speed_m_per_s
```

Use a uniform grid, `dx=L/N`. Sample temperature at cell centres and ion speed
at nodes. For transport within each cell, freeze temperature and ion speed at
that cell's centre and use the exact solution of the resulting two coupled
continuity equations. `h` and `r` are constant along the channel. Recover nodal
densities from fluxes using the prescribed nodal velocities. This defines a
unique discrete contract; arbitrary Euler steps are not interchangeable with it.
`source_per_m3_s` is the cell-averaged production in that frozen-coefficient
solution, not the source evaluated at an arithmetic average of nodal densities.
Nonuniform profiles are approximated to second order by the midpoint sampling.

## Public synthetic observations

All rows use `Parameters` defaults except the displayed `T`, `h`, and `r=5`.
Rounded values should agree within `1e-6` relative. Neutral conversion is the
fraction of inlet neutral flux ionized by the outlet.

| T [eV] | h | K [m^3/s] | Neutral conversion |
| --- | --- | --- | --- |
| 5 | 0 | 2.43166012013e-15 | 0.00903852546628 |
| 10 | 0 | 1.15667174803e-14 | 0.0621472018139 |
| 20 | 0 | 3.00000000000e-14 | 0.317046765466 |
| 30 | 0 | 4.49744223394e-14 | 0.635884155347 |
| 5 | 0.2 | 4.03711880795e-15 | 0.0159953745817 |
| 10 | 0.2 | 1.09933891446e-14 | 0.0577075079759 |

Changing temperature, the distribution shape at fixed mean energy, inlet fluxes,
or transit time gives different controlled comparisons. Particle conservation
alone does not establish that the collision model is correct.

## API, units, and validity domain

`physics.rate_coefficient(te_ev, hot_fraction=0.0, hot_ratio=4.0)` returns a finite
rate in m^3/s. Its domain is `2 <= te_ev <= 60`, `0 <= hot_fraction <= 0.3`, and
`1 <= hot_ratio <= 6`. Component temperatures follow the distribution definitions.
`continuity.Parameters` retains the following fields; all bounds are inclusive:

| Field | Default | Domain and units |
| --- | --- | --- |
| length_m | 0.03 | 0.01–0.04 m |
| n_cells | 80 | integer 4–640 |
| te_ev | 20 | 4–40 eV |
| temperature_variation | 0 | -0.5–0.5, dimensionless |
| hot_fraction | 0 | 0–0.3, number fraction |
| hot_ratio | 4 | 1–6, dimensionless |
| ion_flux_in_per_m2_s | 5e20 | 0–1e21 m^-2 s^-1 |
| neutral_flux_in_per_m2_s | 1.2e22 | 1e21–1.5e22 m^-2 s^-1 |
| ion_speed_m_per_s | 12000 | 10000–30000 m/s |
| velocity_rise | 0.5 | 0–2, dimensionless |
| neutral_speed_m_per_s | 300 | 250–1000 m/s |

Reject booleans, nonfinite numbers, and values outside these domains with
`ValueError`. `sample_profiles(p)` returns the three prescribed arrays below.
`solve(p)` returns a dictionary with:

- `x_m`, `ion_speed_m_per_s`, `n_i_per_m3`, `n_n_per_m3`: N+1 node values.
- `te_ev`, `rate_m3_per_s`, `source_per_m3_s`: N cell values.
- `neutral_conversion`: scalar, `1 - Gamma_n(L)/Gamma_n(0)`.

Return finite Python numbers, with nonnegative ion density/source and positive
neutral density. Verification checks the microscopic collision model, profiles,
inlet fluxes, particle conservation, source consistency and conversion under
varied conditions. Physical checks allow scaled residuals of `1e-8`. On 40/80/160
cell smooth-profile checks, matched-node changes in ion fraction must be below
`2e-3` and shrink by a factor no greater than `0.35` at the next refinement.

Grading imports only `physics.py` and `continuity.py` as standalone modules;
helper files and changes to `run.py` or this README do not define the solution.
From outside the agent session:

```bash
epbench grade hall-ionization --solution /path/to/workspace --json-out /path/to/report.json
```

Keep the report outside the workspace. Grading executes trusted local Python,
not secure sandboxing. Cases and reference code are withheld from the agent
workspace at runtime, but are public in the repository, not secret.
