# Thrust task maintainer notes — v0.4.1

This document contains the derivation and intentional defect. It is not exported
to the agent workspace. The historical proposal is in [v0.4-design.md](v0.4-design.md).

## What changed and what this measures

Pilot 02 ran five attempts on v0.4.0; all passed, and all diagnosed the defect
before observing numerical thrust values. The exported README gave away the
repair in two places: the Physical model section supplied the nonconservative
velocity equation, and the Discrete scheme section supplied the correct velocity
update. The following prose also directed the reader to that velocity form.
Those disclosures measured comparison with a supplied formula, not the intended
investigation. The other exported files (`physics.py`, `momentum.py`, `run.py`)
and the fixed runner prompt contain no correct velocity-update formula.

v0.4.1 removes those two formulas and the directional prose. It retains the
conservative momentum and continuity equations, birth velocity, constants,
units, prescribed profiles, inlet conditions, thrust definitions, API, and
precise quadrature. Constant area and the absence of an exit boundary condition
are explicit. The statement that neutrals must be slower is removed: the allowed
inputs include faster neutrals. Starter code, reference code, verification cases,
tolerances, adversarial tests, and the agent prompt are unchanged.

The revised task measures whether an agent can translate conservative balances
into a consistent numerical march and diagnose a violation of momentum
conservation. Constructing local residuals, comparing thrust routes, and testing
limits are useful evidence of scientific reasoning. They are not required steps:
a competent agent can still derive the correction from the equations by reading.
We do not claim this specification forces simulation-based discovery or that it
is more discriminating; no agent evaluation of v0.4.1 has been run.

## Continuous derivation and well-posedness

Write `n` for ion number density, `u` for ion velocity, `S` for the prescribed
ionization source, and `a = e/m_Xe`. For steady, constant-area, pressureless flow,
with ions born at the neutral velocity `u_n`,

```text
(n u)'   = S
(n u²)'  = a n E + u_n S
(n u²)'  = u (n u)' + n u u' = u S + n u u'
n u u'   = a n E + (u_n - u) S
```

The term `(u_n - u) S` follows from continuity, not an additional force in the
conservative equation. It dilutes ion velocity for slower incoming particles and
can increase it for faster ones. Omitting it treats created particles as already
moving at the local ion velocity. Adding it to the conservative equation would
double-count the effect.

`S` has units m^-3 s^-1; `n u u'`, `a n E`, and `u_n S` each have units
m^-2 s^-2. Multiplication by ion mass gives force density in N/m^3. The inlet
speed is `sqrt(e T_e/m_Xe)` with `T_e` in eV. Both inlet density and temperature
are strictly positive; field, source, and birth velocity are nonnegative.

Set particle flux `F = n u` and momentum flux divided by mass `M = n u²`.
The initial-value problem becomes `F' = S` and `M' = a E F²/M + u_n S`.
The prescribed smooth profiles and positive inlet values give a unique positive
solution on the finite channel: `F` is known by integration and `M` cannot
decrease toward zero. The right-hand side is locally Lipschitz for `M > 0` and
bounded there on a finite interval. Recover `u = M/F` and `n = F²/M`.
There is no independent exit condition to impose. This argument concerns the
mathematical model; arbitrarily extreme finite inputs can still overflow floats.

## Discrete consistency

The specification requires cell-centre `E_i, S_i` and left-node density in the
electric force. Integrating each conservative balance with that quadrature gives

```text
F_next = F_i + dx S_i
M_next = M_i + dx (a n_i E_i + u_n S_i)
u_next = M_next / F_next
n_next = F_next / u_next
```

Since `M_i = F_i u_i`, algebra gives the reference's existing update:

```text
u_next = u_i + dx [a n_i E_i + (u_n - u_i) S_i] / F_next
```

The updated denominator is essential for exact discrete conservation; directly
applying forward Euler to the continuous velocity equation with denominator
`F_i` would not satisfy this contract. Both fluxes remain positive, so the
discrete solution is also uniquely determined. Either internal representation is
accepted. A test constructs the conservative march from the exported starter,
without copying the reference velocity update, and requires 13/13.

The starter instead uses `u_next = u_i + dx a n_i E_i / F_next`. Its exact cell
momentum residual is `dx (u_i - u_n) S_i`. Consequently the thrust-route gap is
`m_Xe sum_i dx (u_i - u_n) S_i`, evaluated on the defective state. This is a
surplus when the local ions are faster, not necessarily for all allowed inputs.
Continuity remains correct. The zero-field, stationary-neutral limit exposes the
error particularly clearly: momentum flux must stay constant as particle flux
grows and velocity decreases.

The scheme is first order because electric force uses left-node density.
Refinement cases use 160, 320, and 640 cells, a `3e-3` relative difference bound,
and a `0.62` contraction bound. Physical residuals have tolerance `1e-8`.
Refinement alone cannot distinguish a converged solution of the wrong equations.

## What independence of the thrust routes means

Route A is the boundary difference `m_Xe (M_exit - M_inlet)`. Route B sums
`dx (e n_i E_i + m_Xe u_n S_i)` across cells. The discrete conservative momentum
balance telescopes, so these agree to round-off for a correct march.

They use different calculations, but share the solved state: Route B depends on
submitted density, and density is coupled to velocity through continuity. It is
incorrect to call Route B independent of the submitted velocity or state. Route
agreement is also the integrated local balance, not an independent physical law;
local residuals catch cancelling errors that the global check alone could miss.

The verifier is independent of the reference solver and submitted thrust
diagnostics: it reconstructs field/source profiles from case parameters, uses the
prescribed neutral velocity, computes both routes from submitted density and
velocity, and checks local continuity, momentum, inlet data, and profile fidelity.
Copying a reported thrust into the other reported thrust cannot fool these checks.

## Cases, adversarial checks, and export review

The unchanged 13 cases comprise two sound-speed sweeps, seven model conditions,
one zero-field limit, one no-ionization limit, and two three-grid refinements.
The reference passes all 13. The starter passes only the two sound-speed sweeps
and no-source limit: 3/13. Its failures include local momentum balance and global
thrust agreement, not continuity. Strong mass loading, coarse grids, zero field,
and faster-neutral conditions prevent a nominal-profile correction from sufficing.

Existing adversarial tests reject hardcoded thrusts, copied thrust diagnostics,
the wrong birth-velocity assumption, grid-independent wrong profiles, rescaled
density, malformed outputs, and broken required modules. These tests remain.
Added checks reject the superficially plausible old-flux-denominator update and
verify the starter's residual identity, including the sign change at faster
neutral velocity.

Export tests inspect the four actual exported files and runner prompt for known
expanded-equation/update disclosures, and check that the conservative equations
and quadrature remain. This is a regression guard, not a proof that all semantic
answer leakage is detectable automatically. Manual review remains necessary.
Public reference code, tests, and these notes are withheld at runtime, not secret;
prior exposure remains a contamination risk. Grading executes trusted local Python
and is not a security sandbox.

## Revision validation

On macOS with Python 3.11.15, `python -m unittest discover -s tests -v` passed
all 78 tests, including the existing live CLI permission probes (no model
sessions). An editable installation and a separate wheel installation succeeded.
Outside the repository, the wheel's `epbench init hall-thrust` exported exactly
the four intended files, byte-identical to the revised task resources. Its
`epbench grade hall-thrust` returned 13/13 for the reference and 3/13 for that
export; the starter failed momentum balance, thrust agreement, and the
zero-field momentum invariant, with no continuity failures. The four added tests
cover the known disclosures, a derived conservative repair, the incorrect
old-flux denominator, and the starter's signed momentum-residual identity.

## Provenance

The original implementation remains at commit
`a3d97fb` (task addition) and commit `00deeee77289b35a21e284bd8229ccf34560c350`
(v0.4.0 with the generalized runner). The local tag `hall-thrust-v0.4.0` points
to the latter. Pilot 02's five attempt directories under `attempts/pilot-02/`
retain their original initial exports, traces, final workspaces, diffs, and v0.4.0
reports. Their contents were hashed before and after this revision to check they
were not changed. No prior pilot report is rewritten or regraded.

v0.4.1 is a different agent-information condition despite using the same solver
and verifier. Do not pool its results with Pilot 02 or interpret equal case scores
as measurements under identical tasks. A new pilot would be required before any
claim about difficulty or an Experiment 02 protocol. None is run by this revision.
