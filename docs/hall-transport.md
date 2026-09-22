# Hall task maintainer notes

`hall-transport` integrates the adjacent `ep-hall-task-design` prototype. The
prototype is left unchanged. Its equation conventions and face discretization
are retained. The reference uses the integrated current formula; verification
reconstructs prescribed data and checks local balances without importing or
executing the reference implementation.

The two intentional starter defects are:

1. `physics.py` uses `nu² + |omega_ce nu|` instead of `nu² + omega_ce²`.
2. `model.py` subtracts the pressure integral when closing current and adds the
   pressure-gradient term when computing field, reversing both required signs.

The second defect preserves the voltage boundary condition, illustrating why
endpoint checks alone are insufficient. The first still passes the B=0 limit,
magnetic evenness, and monotonic suppression, so the verifier also checks the
quantitative mobility law at weak, transitional, and strong magnetization.
Neither defect is identified in the exported README. Tests also repair each
file separately to demonstrate independent detection of the remaining defect.

The 13 cases comprise three mobility sweeps, seven model conditions, one magnetic
reversal pair, and two three-grid refinement studies. They vary every Parameters
field. Model cases include a zero-current uniform limit, an analytic uniform
field, mixed density/temperature gradients, weak and strong magnetization,
nonmonotone potential, and pressure-driven negative electron current at Vd=0.
There are no experimental data or experimental-validation claims.

The verifier reconstructs n, T, B, nu, pressure, face averages, and mobility from
the specified inputs. It checks every returned array's shape and finite numeric
contents before testing conservation. In particular, face current uses the
verifier's mobility and pressure gradient, not the submitted versions. This
prevents mutually consistent but incorrect diagnostics from defining their own
physics. Only submitted modules run in the child; comparisons and final reports
are computed in the parent process.

Physical residuals use `abs(actual-expected)/max(abs(expected), characteristic)`.
Characteristic scales are L, n0, T0, max(|B_peak|, 1e-12 T), nu0, e*n0*T0 for
pressure, and that pressure divided by L for its gradient. Mobility uses the
minimum independently computed face mobility. Voltage uses max(Vd,T0,1 V), with
T0 interpreted as its numerical eV-to-volt energy-per-charge scale; field uses
that scale divided by L. Current uses the largest of Vd/R, the face pressure
current magnitudes, and 1 A/m². Ion energy is converted to voltage before checking.
These scales prevent division by zero without accepting an arbitrary zero output.
All these residuals must be at most 1e-8.

At B=0 with constant n and nu, the nonuniform-temperature solution has the exact
nodal form `phi(x)=Vd-(Vd+T(L)-T(0))*x/L+T(x)-T(0)`. This supplies an independent
analytic pressure-sign check. Uniform T further reduces to a linear potential
and `j=e²*n*Vd/(m_e*nu*L)`.

Refinement uses 80, 160, and 320 cells and compares all coincident nodes. The
prototype's 0.02 V and 1e-3 relative-current thresholds are retained for the first
refinement. A contraction threshold of 0.4 adds an order check with margin around
the expected second-order ratio 1/4. Every grid must also satisfy the prescribed
discrete equations; a constant or grid-independent wrong profile cannot pass
through convergence alone. The absolute differences have 1e-12 floors for
contraction ratios to avoid division by zero.

The prototype's finite-input and grid validation was tightened equally in starter
and reference. Zero inlet speed is valid when the diagnostic remains real.
Negative ion speed squared still raises ValueError: there is no clipping or
feedback into the electron closure. The Hall nominal xenon mass is exactly the
prototype convention (131.293 u); the original analytic smoke tasks retain their
existing rounded mass and behavior.

The flat four-file export (`README.md`, `physics.py`, `model.py`, `run.py`) supports
`python /any/workspace-name/run.py`. Grading requires a directory and snapshots
only the two required regular, non-symlink modules. Auxiliary files, caches,
reference code, and verifier code are never copied into that working directory.
Reports must be outside the submission workspace, including symlink/hardlink
aliases of its files. The grader is installed separately from the submission.

This separation is a packaging and workflow boundary, **not enforced isolation**.
Trusted submissions still inherit host filesystem, environment, installed-package,
and network access. A subprocess can deliberately access or modify those resources;
there are no filesystem permissions, resource quotas, or anti-cheating guarantees.
Public evaluation code is withheld at runtime, not secret; future agent studies
need separate unseen cases/tasks or a private evaluation split.

`epbench evaluate` adds enforced isolation for the agent, not for grading. The
agent runs under a Codex permission profile whose boundary is re-verified by a
preflight probe on every attempt; grading the workspace it produces is still
trusted-local execution. Keep `--out` outside `/tmp` and `/private/tmp`, which stay
readable under that profile. Verify isolation again after upgrading Codex: the
profile schema is a property of the installed CLI, and the preflight probe is
what actually holds the line.

The reduced electron equations follow the conventions in the University of
Michigan's [HallThruster.jl physics documentation](https://um-pepl.github.io/HallThruster.jl/stable/physics/).
The prescribed profiles and finite-volume exercise are illustrative code, not an
integration of that simulator or a reproduction of its complete plasma model.
