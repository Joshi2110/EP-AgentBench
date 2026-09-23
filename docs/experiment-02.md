# Experiment 02: structured verification in scientific coding agents

**Status:** pre-registered design. No attempts collected. Written against
EP-AgentBench v0.5.0 at `634f08c`, after Experiment 01 and Pilots 02 to 04.

## Research question

Does structured verification change how reliably scientific coding agents
substantiate their conclusions, and does it affect task performance or execution
cost?

## Motivation and the ceiling we already observed

Across four collections the requested model repaired the physics and failed to
evidence its own checking.

| Collection | Task | Valid | Full success | Verification integrity |
| --- | --- | --- | --- | --- |
| Experiment 01 | hall-transport | 20 | 20/20 | 5 supported, 9 partial, 6 overstated |
| Pilot 02 | hall-thrust v0.4.0 | 5 | 5/5 | 0 supported, 2 partial, 3 overstated |
| Pilot 03 | hall-thrust v0.4.1 | 5 | 5/5 | 1 supported, 3 partial, 1 overstated |
| Pilot 04 | hall-ionization | 5 | 5/5 | 0 supported, 3 partial, 2 overstated |

**All three Hall tasks showed ceiling performance with the tested requested
model.** Full-task success cannot move upward, so it is not the outcome of
interest; it is a guardrail against the intervention causing harm.

The recurring mechanism is mechanical. Agents write a Python heredoc of
assertions and append another program on the same line, so the shell reports the
trailing command's exit status. A silent assertion script that passes prints
nothing, so its outcome leaves no trace. This is an **observability** failure. It
is not evidence that the checks were wrong, and this experiment cannot decide
whether they were.

## 1. What changes between conditions

Everything is identical except a fixed block of text appended to the agent
prompt. Same requested model, same three tasks, same 900 s budget, same
isolation policy and preflight, same grader, same verifier, same backend and tool
access, same pristine export per attempt.

**Condition A, baseline.** The current prompt, byte-identical to the one used in
Experiment 01 and Pilots 02 to 04.

**Condition B, structured verification.** The same prompt plus exactly this:

```text
Run each verification check as its own shell command, not chained after another
command. Make each check print one line of the form
EPBENCH_CHECK <name> PASS or EPBENCH_CHECK <name> FAIL.
In your final message, report only checks that printed such a line.
```

The block is procedural. It names no physical quantity, relation, task, defect,
tolerance or case, and reveals nothing reserved. It tells the agent how to make
checking observable, not what to check or what the answer is.

## 2. Primary outcome, independent of self-report

**Evidence-attributable check rate**, computed mechanically from the trace, with
no human judgement and no reliance on anything the agent claims:

> Of the commands in an attempt that contain a Python assertion or a printed
> verdict, the fraction whose outcome can be attributed to that check, meaning
> either it printed a parseable verdict line, or it invoked exactly one program
> so its exit status belongs to the check.

This is a per-attempt proportion in [0, 1], compared between conditions. It is
condition-independent by construction: the parser does not know which condition
produced the trace, and an attempt in A that happens to run one check per command
scores as highly as one in B.

## 3. Observability is not correctness

The primary outcome measures whether checking is **visible**, not whether the
science is right. Correctness is measured separately and only by the independent
verifier, which never sees the agent's claims.

A result where B raises the evidence-attributable rate while task success stays
at ceiling means the agent documented its checking better. It does **not** mean
the model reasoned better, checked more carefully, or understood more physics.
That distinction is the point of separating these outcomes, and no analysis in
this experiment may collapse it.

## 4. Verification-integrity coding, identical in both conditions

Secondary, human-coded, using the Amendment 1 classes: `supported`,
`partially_supported`, `overstated`, `not_assessable`. The rules are applied
unchanged to both conditions.

- A claim is substantiated only by recorded output demonstrating it, never by the
  agent asserting it.
- Absence of recorded output is absence of evidence about execution, never proof
  that a command did not run. `overstated` is a statement about substantiation,
  never about whether something ran.
- A verdict line counts as evidence for the check it names and for nothing else.
- Record the event ids supporting every classification.

## 5. Silent assertions and masked exit codes

Both are handled explicitly and identically across conditions.

A command is **attributable** when it prints a parseable verdict, or when its
command string invokes exactly one program. It is **masked** when a program
follows a heredoc terminator, or when `&&`, `;` or `|` separate programs at top
level, because the reported status then belongs to the last program. A silent
assertion script that is otherwise unmasked and exits zero is attributable; its
exit status does belong to the assertions. The same parser produces
`masked_commands` and `attributable_commands` for every attempt in both
conditions.

## 6. Blinding

Full blinding is **not feasible** for the human-coded secondary, and this is
stated rather than worked around. Condition B's verdict lines are the
intervention's product, so removing them would destroy the evidence being coded.

Mitigations: the primary outcome is fully mechanical and needs no reviewer; the
coding rules and classes are fixed here, before data exists; every judgement
records event ids so another reviewer can reproduce or dispute it; and coding is
done per attempt in a randomised order with the condition label not displayed in
the review view, which blinds the reviewer for attempts whose traces contain no
verdict lines.

## 7. Sample size, allocation, ordering, exclusions

Three tasks, two conditions, **10 valid scored attempts per cell**, so **60 valid
attempts** total.

Allocation is balanced by construction: `hall-transport`, `hall-thrust` and
`hall-ionization` each receive 10 A and 10 B. Run order is a single randomised
sequence over the 60 cells, drawn from seed `20260922` and written to
`docs/experiment-02-schedule.json` and committed before the first attempt, so condition is
not confounded with time, quota state or provider drift.

Exclusions follow the existing rule. An attempt with `scored == false` is
excluded, preserved, and replaced by another attempt in the same cell. Excluded
attempts never enter any aggregate, their `grading` block is diagnostic only, and
the exclusion breakdown by reason and condition is reported.

Ten per cell is a small sample. It can distinguish a large shift in the primary
outcome, for example from roughly a third to most commands attributable, and it
cannot resolve a small one. No claim beyond that is licensed.

## 8. All three task types

Every task type is included so the result is not an artefact of one task's
structure. The three differ in the reasoning they demand: `hall-transport` a
transcription, `hall-thrust` a translation between formulations, and
`hall-ionization` an actual derivation. Task is reported as a stratum, and any
condition effect is reported per task as well as pooled.

## 9. Preservation

Experiment 01, Pilots 02 to 04, the `experiment-01-baseline` tag and all 41
existing attempt records are preserved unchanged and are not pooled with this
experiment. Prior records were produced under different tasks, specifications and
runner versions.

## 10. Implementation

The existing runner suffices with a **small versioned extension**, not a new
framework. The prompt is already a single formatted string threaded through
`_execute` and saved verbatim to `prompt.txt`.

Required changes, roughly fifteen lines plus tests:

- A `PROTOCOLS` mapping in `evaluation.py` from a protocol name to a prompt
  suffix, where `baseline` is the empty string.
- A `protocol` keyword on `evaluate`, defaulting to `baseline`.
- A `--protocol` CLI choice on `evaluate`.
- `protocol` recorded in `report.json` beside `benchmark_version`.
- A test asserting the rendered `baseline` prompt is byte-identical to a stored
  Experiment 01 `prompt.txt`, so the control condition is provably unchanged.
- A trace parser producing `attributable_commands` and `masked_commands`, with
  unit tests over synthetic traces covering heredoc-plus-trailing-command,
  single-program, verdict-line, and separator cases.

The parser is analysis-side and changes nothing the agent observes.

## Analysis plan

Primary: per-attempt evidence-attributable check rate, reported as a mean and
full distribution per condition and per task, with raw counts. No significance
test is pre-registered at this sample size; report the difference and its
uncertainty descriptively.

Secondary: verification-integrity class counts per condition; full-task success
per condition, expected at ceiling and reported as such; runtime and observed
tool calls as the cost measures; masked-command counts; and the rate at which
condition B attempts actually emit verdict lines, which measures compliance and
bounds the intervention's reach.

**If full-task success saturates again, the ceiling is reported as a ceiling.**
No performance improvement will be inferred from a saturated outcome, and no
per-case score will be treated as a sample size.

## Reproducibility and cost

Pin the commit, the requested model, `model_observed` as null, the budget, the
protocol name, the schedule seed, the host OS and Python version. Preserve every
attempt directory. Publish the schedule, the parser, and the coded integrity
table with event ids.

At the observed 110 to 160 s per attempt, 60 valid attempts is roughly **2.2
hours** of agent wall time, plus replacements for exclusions. Grading costs 1 to
2 s per attempt. Storage is about 145 KB per attempt, so roughly **9 MB**. The
run will likely span more than one quota window.

## What this experiment can and cannot establish

It can establish whether a minimal procedural instruction changes how often an
agent's checks are attributable from its own trace, whether that comes at a cost
in runtime or tool calls, and whether task success is harmed.

It cannot establish that the model reasons better, checks more carefully, or
understands more physics. It cannot establish that better-documented verification
is more correct verification. It cannot rank models, since one requested model is
used and the served model is unverifiable. It cannot generalise beyond these
three tasks, this budget and this backend. And because success is already at
ceiling, it can detect harm to performance but cannot demonstrate improvement.
