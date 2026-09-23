# Experiment 02: structured verification in scientific coding agents

Collected 2026-09-22/23. Design and pre-registration:
[experiment-02.md](../experiment-02.md). Schedule:
[experiment-02-schedule.json](../experiment-02-schedule.json).

## Research question

Does structured verification change how reliably scientific coding agents
substantiate their conclusions, and does it affect task performance or execution
cost?

## Conclusion, stated narrowly

**Structured verification improved evidence observability and final-claim
substantiation, at an execution cost. It did not demonstrate improved underlying
scientific reasoning, and task success remained at ceiling in both conditions.**

## Configuration

| Item | Value |
| --- | --- |
| Benchmark | EP-AgentBench v0.5.0 |
| Tasks | `hall-transport`, `hall-thrust`, `hall-ionization` |
| Requested model | `gpt-5.6-luna`; `model_observed` null for all 60 |
| Budget | 900 s per attempt |
| Design | 3 tasks x 2 conditions x 10 valid attempts = 60 |
| Schedule | seed 20260922, committed before collection |

Conditions differ only in the prompt. Condition A renders byte-identically to the
prompt used in Experiment 01 and Pilots 02 to 04. Condition B appends three
sentences asking that each check run as its own command and print
`EPBENCH_CHECK <name> PASS|FAIL`, and that the final message report only checks
that printed such a line. Task, grader, verifier, backend, isolation, tool access
and budget are identical.

## Integrity of the collected set

Sixty records against sixty scheduled slots; every task-by-condition cell has
exactly 10; zero duplicate attempt identifiers; zero exclusions; every slot
filled on its first attempt, so the randomised order was followed exactly with no
replacements. Exactly six distinct prompt hashes, one per task and condition.
All records carry the same model, budget and benchmark version.

## Measurement definitions and their version

The primary outcome is computed by `src/epbench/trace_audit.py`, frozen at commit
`56433c3` (22:44:47) and unchanged through collection, which began at 22:49:59
and ended at 02:55. The analysis in this report uses that frozen parser.

**One correction was made during preflight, before any attempt existed.** The
first implementation credited only the structured `EPBENCH_CHECK` form. Validated
against the 41 previously archived attempts, it scored manually-supported and
manually-overstated runs identically at 0.000, and it was reachable only in
condition B, which would have made the primary outcome a compliance measure and
manufactured an effect. The definition now credits a printed check outcome in any
wording, alongside single-program exit attribution, with structured verdicts
counted separately. After the correction the parser tracks the manual construct
monotonically on the archive: supported 1.000, partially supported 0.333,
overstated 0.083. No collected data was affected, because none existed.

A command is attributable when it printed its own result, or when it invoked
exactly one program so the exit status belongs to the check. Heredoc bodies,
quoting and top-level separators are parsed; unbalanced quoting, unterminated
heredocs and nested shells are reported as ambiguous rather than guessed. A run
that attempted no checks yields an undefined rate, never a perfect one.

## Results

Proportions use Wilson 95% intervals; means use bootstrap 95% intervals from
20,000 resamples.

### 1. Evidence-attributable check rate (primary)

| Condition | n | Mean | 95% CI | Median | Range |
| --- | --- | --- | --- | --- | --- |
| Baseline | 30 | 0.402 | [0.272, 0.535] | 0.367 | 0.00 to 1.00 |
| Structured | 30 | **1.000** | [1.000, 1.000] | 1.000 | 1.00 to 1.00 |

Difference **+0.598** [0.463, 0.729]. The structured interval is degenerate
because every attempt attained 1.000; that is a real ceiling, not a computed
precision claim.

| Task | Baseline | Structured |
| --- | --- | --- |
| `hall-transport` | 0.457 [0.280, 0.633] | 1.000 |
| `hall-thrust` | 0.475 [0.200, 0.750] | 1.000 |
| `hall-ionization` | 0.273 [0.090, 0.483] | 1.000 |

### 2. Attempted checks and verdict emission

| Condition | Attempted total | Mean per attempt | Verdict-emitting attempts | Verdict lines |
| --- | --- | --- | --- | --- |
| Baseline | 73 | 2.43 [2.03, 2.83] | 0/30 [0.00, 0.11] | 0 |
| Structured | 260 | 8.67 [7.97, 9.40] | 30/30 [0.89, 1.00] | 256 |

Attribution route, in commands:

| Condition | Verdict | Printed | Single program | Masked | Ambiguous |
| --- | --- | --- | --- | --- | --- |
| Baseline | 0 | 25 | 1 | 47 | 0 |
| Structured | 256 | 0 | 4 | 0 | 0 |

Compliance was complete: every structured attempt emitted verdicts. Baseline
reached 0.402 entirely through the format-agnostic route, which is why the
preflight correction mattered.

### 3. Verification integrity of the final response

Coded by the Amendment 1 rules, applied identically to both conditions.

| Condition | Supported | 95% CI | Partially | Overstated | Not assessable |
| --- | --- | --- | --- | --- | --- |
| Baseline | 6/30 | [0.10, 0.37] | 9 | **15** | 0 |
| Structured | 24/30 | [0.63, 0.90] | 6 | **0** | 0 |

### 4. Independent task success

| Condition | 13/13 | Rate | 95% CI |
| --- | --- | --- | --- |
| Baseline | 30/30 | 1.000 | [0.886, 1.000] |
| Structured | 30/30 | 1.000 | [0.886, 1.000] |

**Ceiling in both arms.** Success could not increase, so this outcome functions
only as a guardrail: the intervention did not harm performance. The lower bound
of 0.886 is the honest limit of what 30 attempts can exclude.

### 5. Runtime and tool calls

| Condition | Runtime mean | 95% CI | Median | Range | Tools mean | 95% CI | Range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 112.9 s | [102.2, 124.7] | 107.4 | 68 to 210 | 7.47 | [6.87, 8.13] | 5 to 12 |
| Structured | 134.6 s | [125.4, 144.2] | 132.6 | 85 to 200 | 15.33 | [14.23, 16.50] | 10 to 23 |

Runtime **+21.8 s** [6.7, 36.3]. Tool calls **+7.87** [6.57, 9.20]. No attempt
approached the 900 s budget.

### 6. Exclusions, missing data, limitations

Zero exclusions of 60 raw attempts. No attempt skipped checks, so no rate was
undefined. No command was ambiguous, so no attribution was guessed.

**Model identification.** All 60 requested `gpt-5.6-luna` and recorded
`model_observed` as null, because the backend exposes no served-model field.
Results are conditional on the backend having honoured the request, which this
design cannot verify. Read the model name as requested, not confirmed.

## What this does and does not establish

It establishes that a three-sentence procedural instruction moved evidence
attributability from 0.402 to 1.000, eliminated all 15 overstated final
responses, raised attempted checks from 73 to 260, and cost about 22 seconds and
eight tool calls per attempt.

It does not establish that the model reasoned better, checked more carefully, or
understood more physics. Task success was identical and at ceiling, so no
performance improvement is claimed or claimable. Whether the 187 additional
checks were good checks is a separate question this design cannot answer.
Improved trace readability is not improved reasoning.

It cannot rank models, since one requested model was used and the served model is
unverifiable. It does not generalise beyond these three tasks, this budget and
this backend.

## Reproducing

Raw records for all 60 attempts are preserved under `attempts/experiment-02/`,
including the prompt, backend permission profile, trace, diff, and the initial
and final workspaces. Per-attempt derived rows are in
`docs/results/experiment-02-rows.json`.

```bash
python -c "from epbench.trace_audit import audit; print(audit('attempts/experiment-02/<id>/trace.jsonl'))"
```
