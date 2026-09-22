# Experiment 01: agent reliability on a scientifically incorrect Hall model

Completed 2026-09-22. Protocol and analysis plan: [experiment-01.md](../experiment-01.md).

## Research question

How reliably can coding agents diagnose and repair a scientifically incorrect
Hall-thruster model, and what failure modes do they exhibit?

## What the task actually is

No plasma-physics background is needed to read this.

A Hall thruster accelerates ions to produce spacecraft thrust. The task models a
one-dimensional slice of its channel. Four quantities are **prescribed** along
the channel and are not solved for: plasma density, electron temperature,
magnetic field, and collision frequency. Given those, the code must solve for the
electric field and the electric potential such that two conditions hold at once:
a single electron current flows uniformly along the channel, and the field
integrates to the applied voltage across it.

Concretely it is a small boundary-value problem with about 120 lines of standard
library Python and no dependencies. The agent receives four files: a
specification `README.md`, the two modules it must repair, `physics.py` and
`model.py`, and a runnable example `run.py`. It receives nothing else.

The supplied code runs and returns finite, plausible-looking numbers. It is
wrong. Two defects were injected deliberately:

**Defect A, in the mobility formula.** Cross-field mobility describes how easily
electrons drift across a magnetic field. The correct denominator is
`ν² + ω_ce²`, where `ν` is the collision frequency and `ω_ce` the cyclotron
frequency. The starter uses `ν² + |ω_ce·ν|`. This is not obviously wrong: it
still gives the correct answer when the magnetic field is zero, it is still even
in the field's sign, and mobility still falls monotonically as the field rises.
It is wrong only in magnitude at intermediate magnetization.

**Defect B, in the pressure-gradient sign.** The electron pressure gradient
enters the current closure and the field reconstruction with the wrong sign in
both places. This defect deliberately **preserves the voltage boundary
condition**, so the potential still starts at the applied voltage and ends at
zero. Checking the endpoints does not reveal it.

Grading does not compare against a stored answer. An independent verifier
reconstructs the prescribed profiles and transport coefficients itself and checks
that the submission satisfies the governing relations.

## Frozen setup

| Item | Value |
| --- | --- |
| Benchmark | EP-AgentBench v0.3.1, commit `4193f2d` |
| Task | `hall-transport` |
| Backend | Codex CLI 0.154.0-alpha.6.2, `codex exec`, one fresh session per attempt |
| Wall-clock budget | 900 s per attempt |
| Tool access | Shell and filesystem inside the workspace; no network; web search disabled |
| Collection window | 2026-09-22 20:27 to 21:10 UTC |

Every attempt began from a pristine export, was graded only after the agent
terminated, and received no grader feedback. No attempt was retried. The
verifier's cases, the grader, the reference implementation, the repository, and
all previous attempts were verified unreadable from inside the sandbox before
each launch.

### Requested model versus served model

Attempts requested `gpt-5.6-luna`. The backend exposes no served-model field, so
every record carries `model_observed: null`. These results are conditional on the
backend having honoured the requested identifier, which this design cannot
verify. Read the model name as *requested*, not *confirmed*.

## Results

### Attempt counts

| | |
| --- | --- |
| Raw attempts | 20 |
| Valid scored attempts | 20 |
| Excluded attempts | 0 |

No quota failures, infrastructure errors, timeouts, or interruptions occurred, so
no attempt needed replacement.

### Primary outcome

**20 of 20 valid attempts achieved full task success**, passing all 13 verifier
cases.

The 13 cases are **not 13 independent tasks**. They are correlated checks of one
submission, and they resolve two coupled scientific decisions. Measured directly
by grading partial repairs:

| Repaired | Score |
| --- | --- |
| Neither defect | 2/13 |
| Defect A only | 5/13 |
| Defect B only | 3/13 |
| Both | 13/13 |

Repairing one defect alone yields 3 to 5 of 13, because the surviving defect
corrupts the shared model cases. Success is close to a two-bit outcome. A
per-case rate is a diagnostic of partial progress, never a sample size.

### Per-defect repair

Coded from each attempt's patch, not inferred from the score.

| Defect | Repaired |
| --- | --- |
| A, mobility denominator | 20/20 |
| B, current-closure sign | 20/20 |
| B, field-reconstruction sign | 20/20 |

19 of 20 final solutions are byte-identical to the reference implementation. The
exception adds a two-line comment deriving the closure and is otherwise
identical. Because the starter is the reference with defects injected, identity
is the expected endpoint of a correct minimal repair rather than evidence of
memorisation.

### Runtime and tool calls

| Metric | Min | Median | Mean | Max |
| --- | --- | --- | --- | --- |
| Runtime, s | 77 | 88.3 | 124.2 | 386 |
| Observed tool calls | 5 | 6 | 6.0 | 11 |

Total agent time was 2,483 s. The longest attempt used 43% of its budget, so the
budget never bound. Tool calls count unique observed action-item identifiers and
undercount hidden or internal calls.

### Failure taxonomy

Empty. No attempt failed, so no failure category was assigned.

## Verification integrity

Every attempt repaired the physics correctly, so the score separates nothing.
The attempts do differ in whether their closing claims are backed by their own
recorded execution evidence. That is analysed separately.

| Class | Definition | Count |
| --- | --- | --- |
| `supported` | Every material claim is substantiated by recorded execution evidence | 5 |
| `partially_supported` | Some checks demonstrated; others unconfirmed and not asserted as definite passes | 9 |
| `overstated` | An unqualified "X passed" assertion is contradicted by, or has no, recorded evidence | 6 |
| `not_assessable` | No verification claims, or no usable evidence | 0 |

`overstated` is a statement about **substantiation, not truth**. It does not mean
a check failed or that the agent lied. The claims may well be correct; the
record simply cannot show it.

### The command-composition and output-observability issue

The classification above is driven by a single reproducible mechanism rather than
by differences in rigour.

Agents habitually chain commands, writing a Python heredoc full of assertions and
then appending another command on the same line, most often `python3 run.py`,
`python3 -m py_compile`, or `git diff`. The shell reports the exit status of the
**last** command in the sequence. When the assertion script also prints nothing
on success, which is the natural style for a script of bare `assert` statements,
the attempt ends with a confident summary whose only mechanical trace is an exit
code belonging to a different command.

A related artifact: `git diff` returns exit 1 in the workspace because no
repository is reachable, so it falls back to comparing two paths. Four attempts
end on that exit 1, which reads as a failure and is not one.

The consequence for evaluation design is that **an exit code cannot be attributed
to a specific check unless the check is run as its own command or prints its own
result.** This affects what a trace can prove, not whether the code is correct. A
minimal remedy is proposed in the [v0.4 design](../v0.4-design.md).

### Relationship between repair and supported verification

All 20 attempts fall in the success row, so the cross-tabulation of outcome
against integrity class is degenerate. Correct repair and substantiated
verification are unrelated **in this dataset** because the outcome has no
variance. This is a property of the sample, not a measured independence.

## Limitations

**One task.** A single reduced model of one device, with prescribed profiles and
no experimental validation. Nothing here measures general coding ability.

**One requested model, unconfirmed.** No comparison between models was made, and
no model ranking is supported. The served model is unverifiable.

**Ceiling effect.** A 20 of 20 result cannot distinguish agents, estimate
difficulty, or detect a capability difference. It shows only that this task did
not constrain this backend under these conditions. The pre-registered sample size
was met, but a ceiling leaves nothing for that sample to resolve. No confidence
interval, significance test, or comparison is reported, because none would be
meaningful here.

**Passing is not physical correctness.** 13/13 means the submission satisfies the
relations this verifier checks at the stated tolerance. It does not establish
that the code is a correct Hall-thruster model, and it does not show that the
backend understands electric propulsion.

**Contamination is not excluded.** The task, verifier, and reference are public
and may appear in training data. They are withheld from the agent at runtime,
not secret.

**Token counts, costs, and determinism were not measured.**

## Pilot attempt

Attempt `10c0975f60f84a70b8cc8fc37d96e8f4`, collected before the analysis
amendment, is a **pilot and is excluded from every number above**. It is retained
separately as the worked example that motivated the verification-integrity
analysis. It contributes to no rate, count, or aggregate.

## Artifacts

Attempt records and the aggregate summary are produced locally and excluded from
version control, because each record is large and, at the moment it is written,
contains a copy of backend credentials that the runner deletes on termination.
Regenerate the aggregate with:

```bash
epbench summarize --attempts attempts/experiment-01 --json-out results/experiment-01.json
```
