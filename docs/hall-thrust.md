# Thrust task maintainer notes

`hall-thrust` tests momentum conservation when mass is added to a flow. It was
built after Experiment 01 returned 20 of 20 successes on `hall-transport`, a
ceiling that resolved nothing. The design rationale is in
[v0.4-design.md](v0.4-design.md).

## The single intentional defect

The starter omits the mass-addition term from the velocity-form momentum update:

```python
u_next = speed[-1] + dx * electric / flux_next              # starter
u_next = speed[-1] + dx * (electric + mass_addition) / flux_next   # reference
```

where `mass_addition = (u_n - u) * S`. Physically, the starter injects newly
created ions already moving at the local ion velocity instead of at the neutral
velocity, so it manufactures momentum. The surplus is exactly
`integral m_Xe (u - u_n) S dx`.

This is an omission, not a wrong expression. There is no incorrect formula on the
page to notice, which is the property `hall-transport` lacked: in that task both
defects were recognisable by reading, and every Experiment 01 attempt diagnosed
them before executing anything.

## Why the two thrust routes detect it

Route A is the net ion momentum flux, which depends on the solved velocity.
Route B integrates the applied force and the injected neutral momentum, which
does not. The verifier reconstructs the field, the source and the neutral speed
itself, so Route B is independent of the submitted velocity. Their difference is
the manufactured momentum.

The specification presents both routes as reported diagnostics, not as a
consistency check. Noticing that they must agree is the investigative step.

## Discrete design

The velocity march specified in the task README is algebraically identical to
marching the conservative pair `n u` and `n u^2`. The reference therefore
satisfies the discrete momentum balance to round-off at every grid: measured
residuals across all cases are between `7e-17` and `3.4e-16`. The defect
violates it by four to thirteen orders of magnitude more, so the discriminating
check carries a `1e-8` tolerance with enormous margin.

The scheme is first order because the electric term uses the upwind density.
Successive grid differences halve, measured contraction `0.495`, so refinement
cases use 160, 320 and 640 cells with a `3e-3` relative bound and a `0.62`
contraction bound. Refinement does not discriminate the defect, since a wrong
model converges too; it checks numerical consistency only.

## Case structure and what each rules out

The 13 cases comprise two sound-speed sweeps, seven model conditions, one
zero-field limit, one no-ionization limit, and two three-grid refinements. They
vary every `Parameters` field.

Two cases deliberately do **not** discriminate, and both are there on purpose.
With no ionization the defect vanishes, because there is no mass to add; a
submission that passes only this case has not fixed the physics. The sound-speed
cases exercise `physics.py`, which carries no defect, so a starter still scores
3 of 13 rather than 0. Case 4 concentrates the source sharply at the inlet,
where the defect is weakest.

Particle conservation is checked and must **not** distinguish the defect, since
the starter's continuity is correct. A test asserts this, so that a future change
which makes continuity fail would be caught as a loss of specificity.

## Adversarial coverage

The verifier tests reject, separately: a hardcoded thrust pair; a wrong solution
that copies one thrust route into the other to fake agreement; a self-consistent
solution of a different problem with the mass-addition term set to zero; a
grid-independent closed-form solution that ignores the source in the momentum
march; a uniformly rescaled density; and malformed output shapes and values.
Each module is also shown to be independently required.

Public evaluation code is withheld at runtime, not secret. Grading is
trusted-local execution and is not sandboxed.
