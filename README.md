# EP-AgentBench

EP-AgentBench provides a reduced **Hall Transport & Potential Closure** coding
task and three analytic electric propulsion smoke tests. It exports repair
workspaces and grades submitted Python against deterministic physical and
numerical checks. Version 0.3 adds `epbench evaluate`, a single-attempt
end-to-end run of a Codex coding agent against the Hall task. There is no RL
training and there are no experimental-validation results.

The Hall task asks an agent to repair electron transport and potential closure
for prescribed plasma profiles. It is a reduced model, not a comprehensive
Hall-thruster benchmark or a self-consistent thruster simulation.

## Installation and quick start

Use Python 3.10–3.14 on macOS or Linux. Runtime and tests use only the Python
standard library. From the repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
epbench list
epbench init hall-transport --out ./my-hall-task
python ./my-hall-task/run.py
epbench grade hall-transport --solution ./my-hall-task --json-out results/hall.json
```

The starter executes but intentionally fails grading (exit `1`). Edit
`my-hall-task/physics.py` and `model.py` using the workspace README, then grade
again. The example command alone does not verify correctness. Initialization
accepts a new or empty directory and refuses to overwrite files.

The installed CLI works from any directory; relative paths are interpreted from
your current directory. `python -m epbench.cli` is also supported. To check the
reference and run all tests from the checkout:

```bash
epbench grade hall-transport --solution examples/solutions/hall-transport --json-out results/hall-reference.json
python -m unittest discover -s tests -v
```

## Tasks

| Task | Submission | Purpose |
| --- | --- | --- |
| `hall-transport` | Directory with `physics.py` and `model.py` | Coupled cross-field electron transport and potential closure |
| `ion-acceleration` | Python file | Xe+ kinetic-energy balance |
| `beam-thrust` | Python file | Ideal beam thrust from current and charge state |
| `axial-field` | Python file | Signed field from a linear potential |

The original analytic tasks remain smoke tests with unchanged grading cases:

```bash
epbench init ion-acceleration --out ./my-first-task
epbench grade ion-acceleration --solution ./my-first-task/starter.py
epbench grade ion-acceleration --solution examples/solutions/ion-acceleration.py
```

Each task README specifies equations, units, domains, and the interface.
The Hall model uses `p_e=e*n_e*T_e` with temperature in eV, conventional electron
current `j_e=e*n_e*mu*E+mu*dp_e/dx`, and `E=-d(phi)/dx`. The integrated voltage
condition closes a spatially constant current with no ion-current term. Mobility
uses `e*nu/[m_e*(nu²+omega_ce²)]`, evaluated at arithmetic face averages. The ion
energy calculation is a passive diagnostic, not feedback into the closure.

These reduced electron equations follow the conventions in
[HallThruster.jl's physics documentation](https://um-pepl.github.io/HallThruster.jl/stable/physics/).
Density, temperature, collision frequency, and magnetic field are prescribed;
ionization, sheaths, electron energy evolution, ion momentum sources, and
self-consistent density evolution are excluded. No external simulator is used.
See the [task specification](src/epbench/tasks/hall-transport/README.md) and
[maintainer notes](docs/hall-transport.md) for the discrete contract, verification,
prototype integration decisions, and intentional defects.

The Hall task uses the prototype's nominal xenon mass `131.293 u`. The analytic
smoke tasks retain their rounded nominal mass `2.1801714e-25` kg. Both neglect
electron mass and isotope variation; these are task conventions, not
isotope-resolved predictions. The elementary charge is the exact
[NIST value](https://physics.nist.gov/cuu/Constants/Value/e.html).

## Execution and reporting

Hall export contains exactly `README.md`, `physics.py`, `model.py`, and `run.py`.
Grading accepts a directory and snapshots only the two required regular,
non-symlink modules. Additional helper modules are outside this task's contract.
Analytic tasks export `README.md` and `starter.py`, and accept a single file
returning a finite Python `int` or `float` (not a boolean).

Each evaluation case runs in a fresh Python subprocess (`-I -B`) and temporary
working directory. Hall model cases call `solve(Parameters(...))`; mobility cases
call `cross_field_mobility` directly. A refinement or symmetry case makes multiple
calls in the same fresh process. Submission stdout/stderr are discarded;
exceptions produce short diagnostics. The worker receives inputs for that case,
not expected answers. Verification and final report construction run in the
parent process, without importing submitted code.

The timeout defaults to five seconds per case (`--timeout` changes it). Errors,
invalid/missing outputs, nonfinite numbers, and timeouts fail the affected case;
remaining cases still run. On macOS/Linux ordinary descendants in the worker's
process group are terminated when the case ends. Hall worker results are capped
at 2 MB when read; scalar results at 4096 bytes. These are protocol limits, not
resource quotas.

Grading prints JSON to stdout and a summary to stderr. `--json-out` saves identical
JSON, creating parent directories and replacing an existing report. Reports must
be outside Hall workspaces and cannot alias submission files. Exit codes:

- `0`: all cases passed, or successful `list`/`init`.
- `1`: at least one grading case failed.
- `2`: command, file, configuration, or report-writing error.
- `130`: user interruption.

Schema version 1 retains task/package version, status, passed/total counts,
`success_rate`, timeout, tolerances, cases, and an execution warning. Hall cases
add `kind` and named `diagnostics` containing `passed`, `error`, and `tolerance`.
An error may be null for an overflowing diagnostic; such a check fails.
Hall's scalar `relative_error` is null; its diagnostics carry the useful metrics.
Case statuses remain `passed`, `mismatch`, `runtime_error`, `invalid_output`, or
`timeout`. Case inputs and expected arrays are omitted from reports. The score
is the fraction of cases passed, not agent pass@k; task success requires all cases.

Hall physical residuals must be at most `1e-8` after characteristic scaling.
The 13 cases cover analytic limits, pressure/current closure, field and energy
consistency, magnetic sign/magnitude, varied operating conditions, and three-grid
refinement. The verifier reconstructs prescribed profiles and transport
coefficients independently of submitted diagnostics. Its tests reject each
injected defect separately, hardcoded output, and mutually consistent wrong
profiles. Analytic tolerances remain `1e-6` relative with absolute tolerances
`1e-8` m/s, `1e-12` N, and `1e-8` V/m respectively.

Configuration/file errors during grading emit an error JSON object to stdout;
no report file is saved for them. Argument errors use argparse's stderr output.

## Agent evaluation

`epbench evaluate` runs one Hall attempt end to end and grades only what the
agent leaves behind:

```bash
epbench evaluate hall-transport --out attempts --model MODEL --seconds 900
```

Each attempt exports a pristine workspace, starts a fresh noninteractive Codex
session with a private `CODEX_HOME`, stops the agent at the wall-clock budget,
and then grades. There are no retries, no resumed sessions, and no grader
feedback to the agent. Every attempt writes `report.json`, `trace.jsonl`,
`prompt.txt`, `backend-config.toml`, `changes.patch`, `initial/`, and
`workspace/` under `--out/<attempt_id>/`. Exit code `0` means the attempt both
completed and passed all cases.

Attempt status is one of `success`, `grading_failed`, `agent_failed`,
`timed_out`, `interrupted`, `grading_error`, or `infrastructure_error`. Token
counts, costs, and determinism are not inferred. Credentials found in Codex auth
are redacted from the trace, diff, and report.

### What counts as a score

Only attempts where the agent actually worked belong in model aggregates. Each
report carries `scored`, `exclusion_reason`, and `score`. An attempt is excluded
when isolation was refused or no session started (`no_attempt`), when the run was
interrupted (`interrupted`), when the backend errored before the agent did any
work (`backend_error_before_agent_work`, which covers quota exhaustion and
provider outages), or when the session ended with no tool calls at all
(`no_agent_execution`). Excluded attempts set `score` to null.

A budget overrun is agent behaviour, not backend failure, so a `timed_out`
attempt still scores. Excluded attempts keep `execution.backend_error` and the
full `grading` block for debugging; that grade is the starter baseline, not a
benchmark result, and must not be aggregated. Aggregate on `score`, never on
`grading`.

### Isolation

The agent runs under a Codex permission profile that grants read access to a
minimal system set plus the interpreter, and write access only to its workspace.
Before any agent starts, a preflight probe runs inside that same profile and
must prove, in order, that the workspace is writable, that `epbench` is not
importable, that the withheld Hall cases, the grader, and the attempt record are
unreadable, and that the network is unreachable. If any check fails, the attempt
is recorded as `infrastructure_error` and **no agent is launched**. Isolation is
never silently downgraded.

This boundary is real and verified per attempt, but it is a local CLI policy,
not a comprehensive security boundary, and it is only as strong as the installed
Codex build. `--out` must not point inside `/tmp` or `/private/tmp`, which stay readable
under the minimal profile; the preflight probe refuses such an attempt. The
session's `TMPDIR` is remapped into the workspace and is not readable, but do
not rely on that: on Linux the default temporary directory is `/tmp`. The withheld cases are withheld at runtime, not secret; they
remain readable in the public source tree.

Codex must be installed and logged in. It is found via `EPBENCH_CODEX`, then
`PATH`, then the ChatGPT app bundle.

## Architecture and boundaries

```text
src/epbench/
  __init__.py       Version, task catalog, export allowlists
  cli.py            List, initialize, grade, evaluate
  evaluation.py     One attempt: isolate, run, preserve, then grade
  codex_backend.py  Codex CLI launch and isolation preflight
  grader.py         File/workspace execution and common reports
  _worker.py        Submission APIs and JSON result protocol
  hall.py           Independent Hall cases and physical/numerical checks
  physics.py        Analytic smoke-test relations
  tasks/<task>/     Agent-visible files only
examples/solutions/ Public reference implementations
tests/             CLI, execution, physics, and defect-detection tests
docs/              Hall maintainer notes
.github/workflows/  macOS/Linux editable and wheel installation checks
```

The wheel includes public task files and evaluators; it excludes references and
tests. The source distribution includes references, tests, and maintainer notes.
CI is configured for Python 3.10–3.14 on macOS/Linux and tests wheel installations
from outside the checkout. No simulator or general plugin framework is required.

Evaluation code and references are **withheld from the agent workspace at
runtime**, not secret: they are inspectable in the public source tree. Give an
agent only the exported workspace. Future publishable agent studies need unseen
tasks/cases or a private evaluation split.

`epbench grade` is **trusted-local only, not sandboxed**, including when it
grades a workspace an agent produced. Submitted Python can access
host files, installed packages (including the grader), inherited environment
variables, and the network. Keeping evaluator files and reports outside the
workspace prevents accidental inclusion; it does not prevent malicious access
or modification. Memory/disk usage is not limited. Real filesystem/network
isolation and resource limits are required before running untrusted agents.

## License

The existing [MIT license](LICENSE) and copyright notice are retained.
