# EP-AgentBench

Coding agents can produce scientific software that runs, returns plausible
numbers, and passes shallow tests while silently violating the physics it is
supposed to model. A sign error in a gradient, a collision term dropped from a
mobility expression, or a boundary condition applied at the wrong face all
produce output that looks like a reasonable plasma simulation. Comparing against
a stored expected value does not catch this, because the stored value was
produced by the same broken assumptions.

EP-AgentBench is a small benchmark for that failure mode, built around electric
propulsion models. It provides executable scientific debugging tasks, an
independent verifier that checks physical relations rather than remembered
outputs, and a reproducible runner that executes one isolated coding-agent
attempt and grades only what the agent leaves behind.

**No agent results are reported yet.** The runner and its isolation are
implemented and tested; the first evaluation is specified in
[docs/experiment-01.md](docs/experiment-01.md) and has not yet produced a valid
attempt.

## What is actually here

**Executable tasks.** Each task exports a small workspace containing a
specification and code that runs but is wrong. The agent's job is diagnosis and
repair, not writing code from scratch.

**An independent verifier.** For the Hall task, grading does not compare against
a saved answer. It reconstructs the prescribed plasma profiles and transport
coefficients itself, then checks that the submitted model satisfies the
governing relations: current continuity, the integrated voltage condition, the
pressure and mobility closures, sign and scaling behaviour under changed
magnetic field, and convergence under grid refinement. A submission that invents
self-consistent but wrong profiles fails, and the verifier's own tests confirm
it rejects each injected defect separately.

**A reproducible agent runner.** `epbench evaluate` starts one noninteractive
Codex session against a pristine export, under a filesystem and network boundary
that is re-verified before every launch, and preserves the trace, the final
workspace, a diff, and a machine-readable report.

### Three things that are easy to confuse

| Artifact | What it is | Expected result |
| --- | --- | --- |
| Reference implementation | A correct solution in `examples/solutions/` | 13/13 cases |
| Starter | The exported task, deliberately defective | 2/13 cases |
| Agent evaluation | One real agent attempt, graded after it terminates | Unknown; that is the experiment |

The starter's 2/13 is the floor, not a baseline score for any model. Reporting
it as an agent result would be wrong.

## Scope

Three analytic smoke tests and one reduced Hall-thruster modelling task. The
smoke tests exist to check the harness end to end; they are single-formula
problems and are not interesting as agent evaluations. The Hall task is the
substantive one.

This is a reduced model, not a thruster simulator. Density, temperature,
collision frequency, and magnetic field are prescribed. Ionization, sheaths,
electron energy evolution, ion momentum sources, and self-consistent density
evolution are excluded. No external simulator is used, and nothing here is
validated against experimental data.

There is no RL training, no reward model, and no demonstrated model improvement.

## Installation and quick start

Python 3.10–3.14 on macOS or Linux. Runtime and tests use only the standard
library; there are no dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

epbench list
epbench init hall-transport --out ./my-hall-task
python ./my-hall-task/run.py
epbench grade hall-transport --solution ./my-hall-task --json-out results/hall.json
```

The starter runs but fails grading with exit code `1`, which is the point. Edit
`physics.py` and `model.py` in the workspace, then grade again. Confirm the
reference passes and run the tests:

```bash
epbench grade hall-transport --solution examples/solutions/hall-transport
python -m unittest discover -s tests -v
```

The installed CLI works from any directory. `python -m epbench.cli` also works.

## Tasks

| Task | Submission | Purpose |
| --- | --- | --- |
| `hall-transport` | Directory with `physics.py` and `model.py` | Coupled cross-field electron transport and potential closure |
| `ion-acceleration` | Python file | Xe+ kinetic-energy balance |
| `beam-thrust` | Python file | Ideal beam thrust from current and charge state |
| `axial-field` | Python file | Signed field from a linear potential |

Each task README gives equations, units, domains, and the interface. The Hall
model uses `p_e = e*n_e*T_e` with temperature in eV, conventional electron
current `j_e = e*n_e*mu*E + mu*dp_e/dx`, and `E = -d(phi)/dx`. The integrated
voltage condition closes a spatially constant current with no ion-current term.
Mobility is `e*nu/[m_e*(nu^2 + omega_ce^2)]`, evaluated at arithmetic face
averages. The ion energy calculation is a passive diagnostic and does not feed
back into the closure.

These reduced electron equations follow the conventions in
[HallThruster.jl's physics documentation](https://um-pepl.github.io/HallThruster.jl/stable/physics/).
The Hall task uses that prototype's nominal xenon mass of `131.293 u`; the
analytic tasks keep a rounded `2.1801714e-25` kg. Both neglect electron mass and
isotope variation. The elementary charge is the exact
[NIST value](https://physics.nist.gov/cuu/Constants/Value/e.html).

See the [task specification](src/epbench/tasks/hall-transport/README.md) and the
[maintainer notes](docs/hall-transport.md) for the discrete contract, the
verification strategy, and the intentional defects.

## Running one agent evaluation

Codex must be installed and logged in. The runner finds it via `EPBENCH_CODEX`,
then `PATH`, then the ChatGPT app bundle.

```bash
epbench evaluate hall-transport --out attempts --model MODEL --seconds 900
```

One attempt, no retries, no resumed sessions, and no grader feedback to the
agent. Grading happens only after the agent has terminated. Each attempt writes
a directory under `--out/<attempt_id>/`:

| File | Contents |
| --- | --- |
| `report.json` | Machine-readable result, status, score, and limitations |
| `trace.jsonl` | Timestamped backend events, one JSON object per line |
| `prompt.txt` | The exact prompt the agent received |
| `backend-config.toml` | The permission profile the agent ran under |
| `changes.patch` | Unified diff from the pristine export |
| `initial/`, `workspace/` | The export before and after the attempt |

Choose `--out` outside `/tmp` and `/private/tmp`; see [Isolation](#isolation).

### Inspecting an attempt

```bash
jq '{status, scored, exclusion_reason, score, execution}' attempts/*/report.json
jq -r 'select(.event.type=="item.completed") | .event.item.type' attempts/*/trace.jsonl | sort | uniq -c
git diff --no-index attempts/*/initial attempts/*/workspace
```

`jq` is a convenience, not a dependency. Attempt status is one of `success`,
`grading_failed`, `agent_failed`, `timed_out`, `interrupted`, `grading_error`,
or `infrastructure_error`.

### What counts as a score

Only attempts where the agent actually did work belong in model aggregates. Each
report carries `scored`, `exclusion_reason`, and `score`. An attempt is excluded
when isolation was refused or the session never started
(`infrastructure_error`), when it was interrupted (`interrupted`), when the
backend errored before the agent did any work
(`backend_error_before_agent_work`, which covers quota exhaustion and provider
outages), or when the session ended with no tool calls at all
(`no_agent_execution`). Excluded attempts set `score` to null.

A budget overrun is agent behaviour, not backend failure, so a `timed_out`
attempt still scores. Excluded attempts keep `execution.backend_error` and the
full `grading` block for debugging. That grade is the starter baseline, not a
benchmark result. **Aggregate on `score`, never on `grading`.**

### Aggregating attempts

```bash
epbench summarize --attempts attempts --json-out results/summary.json
```

This separates raw attempt counts from valid ones, breaks exclusions down by
reason, reports task success over valid attempts only, and counts unsuccessful
valid attempts rather than dropping them. With no valid attempts it says so
instead of producing a number. The per-attempt table it emits keeps every
attempt visible, including excluded ones.

Case scores are 13 checks of a single task. They are not 13 independent
scientific tasks and should not be treated as a 13-item test set.

## Isolation

The agent runs under a Codex permission profile granting read access to a
minimal system set plus the interpreter, and write access only to its own
workspace. Before any agent starts, a preflight probe runs inside that same
profile and must prove that the workspace is writable, that `epbench` is not
importable, that the withheld Hall cases, the grader, and the attempt record are
unreadable, that the copied and original Codex credentials are unreachable as
both files and directories, and that the network is down. If any check fails the
attempt is recorded as `infrastructure_error` and **no agent is launched**.
Isolation is never silently downgraded.

The session uses a private `CODEX_HOME`, so prior conversations, user rules,
and MCP servers do not reach the agent. The control directory holding copied
credentials is deleted once the agent terminates. Credentials found in Codex
auth are redacted from the trace, diff, and report.

`--out` must not point inside `/tmp` or `/private/tmp`, which stay readable
under the minimal profile; the preflight probe refuses such an attempt. The
session's `TMPDIR` is remapped into the workspace and is not readable, but do
not rely on that, since Linux defaults its temporary directory to `/tmp`.

## Grading and reports

Hall export contains exactly `README.md`, `physics.py`, `model.py`, and
`run.py`. Grading accepts a directory and snapshots only the two required
regular, non-symlink modules. Analytic tasks export `README.md` and
`starter.py`, and accept a single file returning a finite `int` or `float`.

Each case runs in a fresh Python subprocess (`-I -B`) and temporary directory.
Hall model cases call `solve(Parameters(...))`; mobility cases call
`cross_field_mobility` directly. Submission stdout and stderr are discarded.
The worker receives the inputs for that case, never the expected answer.
Verification and report construction happen in the parent process without
importing submitted code.

The per-case timeout defaults to five seconds (`--timeout`). Errors, invalid or
missing output, nonfinite numbers, and timeouts fail that case; the rest still
run. Hall worker results are capped at 2 MB, scalar results at 4096 bytes; these
are protocol limits, not resource quotas.

Hall physical residuals must be at most `1e-8` after characteristic scaling. The
13 cases cover analytic limits, pressure and current closure, field and energy
consistency, magnetic sign and magnitude, varied operating conditions, and
three-grid refinement. Analytic tolerances are `1e-6` relative with absolute
tolerances of `1e-8` m/s, `1e-12` N, and `1e-8` V/m.

Grading prints JSON to stdout and a summary to stderr. `--json-out` saves the
same JSON and must be outside the workspace. Exit codes:

- `0`: all cases passed, or a successful `list`, `init`, or `summarize`.
- `1`: at least one grading case failed, or an attempt did not fully succeed.
- `2`: command, file, configuration, or report-writing error.
- `130`: interrupted.

Reports are schema version 1 and carry the package version, status, passed and
total counts, `success_rate`, timeout, tolerances, and per-case results. Hall
cases add `kind` and named `diagnostics`. Case inputs and expected arrays are
omitted. The score is the fraction of cases passed; task success requires all of
them.

## Limitations

**Security.** The agent boundary is a local CLI permission policy, not a
comprehensive security boundary, and it is only as strong as the installed Codex
build. Re-verify it after upgrading Codex. Separately, `epbench grade` is
trusted-local execution and is **not** sandboxed, including when grading a
workspace an agent produced: submitted Python can reach host files, installed
packages, environment variables, and the network. Do not grade untrusted code on
a machine you care about.

**Scientific.** One reduced model of one device, with prescribed profiles and no
experimental validation. Passing 13/13 means the submission satisfies the
governing relations this verifier checks at the stated tolerance. It does not
mean the code is a correct Hall thruster model.

**Methodological.** The tasks and verifier are public and therefore visible to
anything trained on public code; they are withheld from the agent at runtime,
not secret. Results from a single task and a handful of attempts support no
claim about general agent capability. Token counts, costs, and determinism are
not measured. Ranking models on this benchmark would require unseen tasks or a
private split that does not yet exist.

## Repository layout

```text
src/epbench/
  __init__.py       Version, task catalog, export allowlists
  cli.py            list, init, grade, evaluate, summarize
  evaluation.py     One attempt: isolate, run, preserve, then grade
  codex_backend.py  Codex CLI launch and isolation preflight
  summary.py        Aggregation that never scores an excluded attempt
  grader.py         Execution and report construction
  _worker.py        Submission APIs and JSON result protocol
  hall.py           Independent Hall cases and physical checks
  physics.py        Analytic smoke-test relations
  tasks/<task>/     Agent-visible files only
examples/solutions/ Public reference implementations
tests/              Grading, CLI, physics, agent-runner, and live isolation tests
docs/               Maintainer notes and the experiment protocol
```

The wheel ships public task files and evaluators, excluding references and
tests. CI is configured for Python 3.10–3.14 on macOS and Linux and exercises
wheel installation from outside the checkout.

## License

[MIT](LICENSE).
