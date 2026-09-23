# Ionization task: scientific design and authoring review

`hall-ionization` is introduced in v0.5.0. This is a new task, not a revision of
`hall-thrust`. The existing Hall tasks and Pilot 01–03 artifacts are unchanged.
This maintainer document contains the solution derivation and is not exported.
No coding-agent evaluation of this task has been run.

## Why the original proposal was rejected

The historical [v0.4 proposal](v0.4-design.md) put temperature in kelvin inside
`A T^b exp(-I/T)` while keeping the threshold in eV. If that expression and its
units are supplied, the error is visible by dimensional analysis and direct
formula comparison. A fitted prefactor does not change that. Moreover, exact
ion/neutral conservation is compatible with any nonnegative rate coefficient:
conservation alone cannot establish correct kinetics. The original design's
claim that only a temperature sweep could expose this defect was unjustified.

A consistent version of that empirical expression must use dimensionless
`I/T` and either a dimensioned `A` or a dimensionless power `(T/T0)^b`. A single
calibration can identify a scale but cannot identify an arbitrary temperature
law. We instead specify microscopic collision physics and a distribution, which
uniquely determine the rate's shape; one synthetic calibration fixes its scale.

## Governing microscopic model and derivation

The prescribed, isotropic electron energy PDF in eV^-1 is

```text
P_M(epsilon; T) = 2 sqrt(epsilon) exp(-epsilon/T) / (sqrt(pi) T^(3/2))
P = (1-h) P_M(T_c) + h P_M(T_h)
T_c = T/(1-h+h r),  T_h = r T_c
```

The mean energy is `3T/2` for every `h,r`. This PDF integrates to one; it is
not the energy probability function in eV^-3/2. The idealized cross-section is
zero below `I` and `sigma0 (1-I/epsilon)` above it. Electron speed is
`sqrt(2e epsilon/m_e)`. Collision counting therefore gives

```text
K = integral sigma(epsilon) v(epsilon) P(epsilon) d epsilon
K_M(T) = sigma0 sqrt(8e T/(pi m_e)) exp(-I/T)
```

The integral reduces to `integral_I^infinity (epsilon-I) exp(-epsilon/T) d epsilon
= T² exp(-I/T)`. The one calibration `K_M(T0)=K0`, with `T0=20 eV` and
`K0=3e-14 m³/s`, then determines

```text
K_M(T) = K0 sqrt(T/T0) exp(I/T0-I/T)
K(T,h,r) = (1-h) K_M(T_c) + h K_M(T_h)
```

Only this maintainer document and the reference give the evaluated law.
The agent receives the microscopic probability model and synthetic observations.
All exponent arguments are dimensionless; electronvolts are converted to joules
only in the speed. The collision integral has units m² * m/s = m³/s.
The fitted cross-section scale has units m² and is positive and unique.

The threshold `I=12.12984 eV` is a rounded xenon ionization energy from
[NIST](https://physics.nist.gov/PhysRefData/Handbook/Tables/xenontable1.htm).
The cross-section shape and calibration are **synthetic**, not measured xenon
collision data. The averaging construction agrees with the collision-rate
convention in the [CRANE documentation](https://crane-plasma-chemistry.readthedocs.io/en/latest/rates/RateCoeff_Maxwellian.html);
that source writes an energy probability function rather than our energy PDF.
Neither citation supplies experimental validation of this benchmark.

## Exact defect and nominal masking

The starter replaces the energy distribution by one representative electron at
its mean energy. It evaluates the cross-section and speed there, then fits the
normalization at 20 eV:

```text
q(T) = max(1-I/(1.5T), 0) sqrt(2e (1.5T)/m_e)
K_bad(T,h,r) = K0 q(T)/q(T0)
```

This is one closure defect with a compensating nominal calibration, not a unit
mistake. It is dimensionally valid. It ignores the noncommutation of collision
counting and energy averaging and cannot distinguish distributions with equal
mean energy. Its fitted normalization is a plausible area, so dimensions alone
do not expose it. Below `T=2I/3` it wrongly predicts zero ionization, even though
the true distribution still has electrons above threshold.

For the nominal uniform 20 eV Maxwellian, both codes have exactly the same rate
and, using the same conservative transport, the same complete solution at every
grid. Calibration is not merely matching a plotted endpoint. At 30 eV the rate
also happens to be within 0.2%, showing why one extra warm condition is weak
evidence. Broader controls are necessary to distinguish plausible explanations.

## Transport and well-posedness

Assume steady constant-area flow, prescribed positive ion/neutral velocities,
quasineutrality `n_e=n_i`, one ion produced per neutral lost, and no other sources
or sinks. With particle fluxes `Gamma_i=n_i u_i`, `Gamma_n=n_n u_n`,

```text
Gamma_i' = S,  Gamma_n' = -S,  S=n_i n_n K
J = Gamma_i + Gamma_n = constant
y = Gamma_i/J
(log(y/(1-y)))' = J K/(u_i u_n)        for nonzero seed flux
```

Both inlet fluxes are supplied. The prescribed smooth temperature and velocity
profiles determine coefficients everywhere; no outlet condition is required.
For positive neutral flux and nonnegative seed ions this initial-value problem
has a unique bounded solution. If the seed is zero, quasineutrality implies no
electrons and `y=0` identically. Otherwise `0<y<1`, with increasing ion flux.
This is a seeded reduced model, not a model of plasma ignition.

For a cell with midpoint coefficients, the log-odds increment is
`dx J K/(u_i u_n)`. The reference accumulates this quantity from the inlet and
recovers both fluxes with a logistic expression. The cell-averaged source is
`(Gamma_i,next-Gamma_i)/dx`; it equals the integral of the kinetic source for
that frozen-coefficient solution. Using midpoint *densities* to define that
source instead would be a different scheme. Nodal densities use prescribed
nodal velocities. Nonuniform coefficients converge at second order; constant
coefficients give the exact continuum solution at any grid spacing.

## Numerical evidence and identifiable controls

These are synthetic predictions using the default transport parameters (`r=5`).
Conversion is the fraction of incoming neutrals consumed, not an ion number
fraction in the plasma.

| T [eV] | h | Reference K [m³/s] | Starter K [m³/s] | Reference conversion | Starter conversion |
| --- | --- | --- | --- | --- | --- |
| 5 | 0 | 2.4316601e-15 | 0 | 0.00903853 | 0 |
| 10 | 0 | 1.1566717e-14 | 6.8141850e-15 | 0.06214720 | 0.03018858 |
| 20 | 0 | 3.0000000e-14 | 3.0000000e-14 | 0.31704677 | 0.31704677 |
| 30 | 0 | 4.4974422e-14 | 4.5055623e-14 | 0.63588416 | 0.63750699 |
| 5 | 0.2 | 4.0371188e-15 | 0 | 0.01599537 | 0 |
| 10 | 0.2 | 1.0993389e-14 | 6.8141850e-15 | 0.05770751 | 0.03018858 |

Temperature sweeps change the threshold-tail population and give rate ratios
independent of the cross-section scale. A constant rescaling cannot simultaneously
repair those ratios and retain the nominal anchor. At fixed mean temperature,
changing `h,r` changes higher moments of the distribution without a temperature
or transit-time change. A temperature-only rate table cannot reproduce this.
The effect can have either sign: adding a hot component increases the rate at
5 eV but decreases it at 10 eV under this fixed-mean constraint. A blanket
"hotter tail always increases ionization" correction is also insufficient.

Changing inlet flux, channel length, or prescribed velocities at fixed electron
distribution changes depletion without changing the microscopic rate. These
controls distinguish a kinetic closure error from a density normalization,
residence-time error, or a change confined to the reported conversion. Spatial
temperature variation tests whether the local law is used throughout the domain.
The observations alone would not uniquely identify an arbitrary function; the
microscopic assumptions, distribution, and calibration supply that uniqueness.

## Independent verification and authoring sequence

The reference and verifier were constructed and passed all 13 cases before the
starter was created. The reference uses the analytic rate above. The verifier
never imports either solution: it numerically integrates cross-section times
speed times energy PDF using composite Simpson quadrature on
`z=(epsilon-I)/T`, from 0 to 48 with 2048 panels. The omitted tail is negligible
at the stated tolerances. A 4096-panel test independently checks each raw
Maxwellian integral against its analytic value to relative error below `1e-9`;
the 2048-panel result is below `1e-8`. Calibration cancels the common quadrature
bias, but the raw-integral test ensures that cancellation is not the sole
accuracy argument.

The verifier reconstructs prescribed profiles and rates, checks inlet and total
fluxes, both species' source balances, independently reconstructs each cell's
kinetic response, and recomputes conversion from the returned neutral density.
It does not trust submitted rates or source diagnostics. There are 3 rate sweeps
(including off-table, reproducibly generated distributions), 7 operating-condition
cases, a zero-seed limit, and 2 three-grid refinement cases: 13 total.
The reference scores 13/13; the starter scores 2/13 (nominal and zero seed).
Starter failures are kinetic, not violations of particle conservation.

Adversarial checks reject nominal hardcoding, linear interpolation of the public
temperature table, single-condition coefficient refitting, correct diagnostics
attached to wrong transport, rescaled densities, changed profiles, and malformed
values. These are concrete regression adversaries, not proof that every possible
lookup table or malicious submission can be rejected by a public finite test set.
A separate correction derived from the exported microscopic model, using
midpoint energy quadrature instead of the closed form, must also score 13/13.

## Answer-disclosure audit and limitations

The exported README contains no evaluated rate law, correct replacement for
`rate_coefficient`, or instruction naming the starter's mean-energy closure as
the bug. The probability-density and cross-section expressions describe different
physical objects from that function; deriving or numerically constructing the
rate requires combining them and calibrating the result. `continuity.py` is
correct and common to starter/reference; `run.py` prints controlled observations
without supplying expected answers. The public table is synthetic evidence,
not a complete solution. Export tests check file boundaries, observation fidelity,
and known closed-form disclosures. Manual review covers the semantics.

An experienced reader can still recognize the single-energy approximation and
derive the integral analytically. This is acceptable; we do not claim experiments
are compulsory or diagnosis must follow a simulation. The numerical controls
are informative because they distinguish scale, distribution-shape, and transport
explanations. Difficulty remains unmeasured. The idealized cross-section, fixed
energy distributions, prescribed speeds, quasineutrality, and absent energy/
momentum feedback limit physical realism. No measurements validate this model.
Cases, reference code, and maintainer derivations are public and may contaminate
future models; they are withheld only at runtime. Grading remains trusted local
execution, not secure sandboxing.

## Recommended next pilot (not executed)

Freeze this commit, task export, prompt, backend version, model identifier, and
budget before collecting a small pilot. Preserve every attempt, including failed
or excluded ones; use the existing isolation preflight and grade only after the
session ends. Do not give agents maintainer notes or previous trajectories.

Report raw counts separately from prior pilots. Annotate when each diagnosis
first appears, what evidence was available then, competing explanations tested,
which controlled changes were attempted, and whether closing verification claims
are supported by recorded outputs. Distinguish analytical derivation from direct
formula comparison and from numerical investigation; an early valid analytical
solution is not a design failure by itself. Inspect a small pilot before defining
Experiment 02. No agent evaluations or experiment runs are part of this change.
