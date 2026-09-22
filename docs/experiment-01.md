# Experiment 01: agent reliability on a scientifically incorrect Hall model

**Status:** pre-registered protocol. No attempts have been analysed. Written
before any successful agent trajectory was inspected, against EP-AgentBench
v0.3.1.

## Research question

How reliably can coding agents diagnose and repair a scientifically incorrect
Hall-thruster model, and what failure modes do they exhibit?

## Task and benchmark version

Task `hall-transport`, exported by `epbench init`, exactly four files:
`README.md`, `physics.py`, `model.py`, `run.py`. The starter runs and returns
finite numbers but violates the governing relations; it scores 2/13 on the
verifier. The agent must diagnose and repair it.

Benchmark version 0.3.1. Record the exact commit with every result set. Any
change to `hall.py`, `grader.py`, or the exported task files ends the run and
starts a new one; partial result sets from different versions are not pooled.

## Agent, model, and environment

- Backend: Codex CLI, noninteractive `codex exec`, one fresh session per
  attempt, no resumed or forked sessions.
- Model: a single identifier passed verbatim via `--model`, recorded in
  `report.json` as `agent.model_requested`. One model per result set.
- Record the Codex CLI version from `agent.version`, the host OS, and the
  Python version used to grade.
- Tool access: shell and filesystem inside the workspace only. Network is off,
  web search is disabled, and the session runs under a private `CODEX_HOME` so
  prior conversations, user rules, skills, and MCP servers do not reach it.
- Python is available in the sandbox as `python` and `python3`, standard
  library only. The agent may write and run its own checks.

Sampling temperature and other decoding parameters are whatever the backend
defaults to. They are not controlled, so attempts are independent samples from
an uncontrolled distribution, and exact replication of a single trajectory is
not expected.

## Budget

900 seconds of wall-clock time per attempt, `--seconds 900`, fixed for the whole
result set. The budget is enforced by the runner, which terminates the session's
process group when it expires. Do not extend the budget mid-run; changing it
starts a new result set.

## Per-attempt protocol

1. Export a pristine workspace into a fresh attempt directory. The runner does
   this per attempt; no workspace is ever reused or repaired incrementally.
2. Verify isolation. The preflight probe must pass or no agent is launched.
3. Run one session with the fixed prompt in `prompt.txt`.
4. Terminate at the budget. Grade only after termination.
5. Preserve the attempt directory unmodified.

No retries of a graded attempt, and no grader feedback to the agent at any
point. Re-running after an *excluded* attempt is replacement of an attempt that
never happened, not a retry; see Exclusions.

## Information available to the agent

Only the four exported files in its workspace, plus anything it writes there.

Withheld during execution, and verified unreadable by the preflight probe:

- `hall.py`, holding the 13 verification cases and the independent verifier.
- `grader.py` and the rest of the installed `epbench` package.
- The reference implementations in `examples/solutions/`.
- The attempt record: `initial/`, `report.json`, `trace.jsonl`, and this
  protocol.
- Previous attempts, successful or otherwise.
- Codex credentials, both the originals and the copy the runner makes.

These materials are withheld at runtime, not secret. They are public in the
source tree and may appear in model training data. This is a contamination risk
the experiment cannot rule out, and it is a reason not to treat results as a
capability measurement.

## Outcomes

**Primary outcome: successful independent verification.** An attempt succeeds
when `report.json` has `status == "success"`, meaning the workspace the agent
left behind passes all 13 verifier cases. This is binary per attempt. The
reported quantity is successes over valid attempts.

**Secondary outcomes**, recorded per valid attempt:

- Case score, `score.passed` of `score.total`.
- Tool calls, `execution.tool_calls`, unique observed action-item IDs. This
  undercounts, since hidden or internal calls are not visible.
- Runtime, `execution.elapsed_seconds`.
- Failure category, assigned by hand from the diff, trace, and per-case
  diagnostics using the fixed taxonomy below.

### Failure taxonomy

Fixed before data collection. Each unsuccessful valid attempt gets exactly one
primary category; note secondary ones in free text.

| Category | Definition |
| --- | --- |
| `no_repair` | Files unchanged, or edits that do not touch the defective relations |
| `partial_repair` | Some defects corrected, others left in place |
| `wrong_physics` | Introduced a new relation that is physically incorrect |
| `interface_violation` | Broke the required API, signature, or module contract |
| `runtime_failure` | Submission raises, returns nonfinite values, or times out during grading |
| `local_check_overfit` | Wrote checks it passes while still violating the governing relations |
| `budget_exhausted` | Was still working coherently when the budget expired |
| `other` | Does not fit the above; must be described |

Categories are recorded in a results file alongside the attempt ID. Where a
category is ambiguous, re-read the trace before assigning, and record the
ambiguity.

## Sample size

No reliability claim before **20 valid attempts** for a given model and budget.

- Fewer than 10 valid attempts: report raw counts only. No rate, no interval.
- 10 to 19: report the rate as descriptive, explicitly labelled preliminary.
- 20 or more: report successes over valid attempts with a 95% Wilson score
  interval, computed from the counts. The interval at n = 20 is wide; that is
  the honest width, not a defect to be hidden by rounding.

Twenty attempts of one task is a small sample by any standard. It is enough to
distinguish "usually succeeds" from "usually fails" and not much else.

## Exclusions

An attempt is excluded when `report.json` has `scored == false`. The runner sets
this; the analyst does not decide it after seeing the score. Reasons:

- `infrastructure_error`: isolation refused, or the session never started.
- `backend_error_before_agent_work`: the backend errored before the agent did
  anything, which covers quota exhaustion and provider outages.
- `no_agent_execution`: the session ended with no tool calls at all.
- `interrupted`: stopped by the operator.

Excluded attempts contribute nothing to any score. Their `grading` block still
holds a grade, which is the starter baseline, and aggregating it would
manufacture a result. `epbench summarize` enforces this separation.

Excluded attempts are replaced, because they are not observations of agent
behaviour. Report the raw attempt count, the valid count, and the exclusion
breakdown by reason. If exclusions exceed roughly a third of raw attempts, the
environment is unstable enough that the result set should be questioned.

## Timeouts

A timeout is agent behaviour, not backend failure, so a `timed_out` attempt is
valid and is scored on whatever it left in the workspace. It counts as a failure
of the primary outcome unless the workspace happens to pass all cases.

Pre-registered check: if more than 20 percent of valid attempts time out, the
budget is plausibly the binding constraint rather than capability. Report the
timeout rate prominently and do not characterise the result as a capability
finding without re-running at a larger budget as a separate result set.

## Preservation and reproducibility

Keep every attempt directory intact, including excluded ones. Each contains the
prompt, the permission profile, the trace, the diff, the initial and final
workspaces, and the report.

Attempt directories are gitignored by default because they can be large and, at
the moment they are produced, contain a credential copy that the runner deletes
on termination. Before publishing any attempt record, confirm the `control/`
directory is gone and scan the trace and diff for secrets.

Publish alongside results: the benchmark commit, the Codex CLI version, the
model identifier, the budget, the host OS and Python version, the raw and valid
attempt counts, the exclusion breakdown, and the `epbench summarize` JSON. State
that decoding parameters were uncontrolled.

```bash
epbench evaluate hall-transport --out attempts --model MODEL --seconds 900
epbench summarize --attempts attempts --json-out results/experiment-01.json
```

## Conclusions this design cannot support

- **Nothing about general coding ability.** One task, one domain, one prompt.
- **Nothing about agent capability in electric propulsion.** The task is a
  reduced model with prescribed profiles, not thruster engineering.
- **No model ranking.** Comparing models needs matched budgets, matched sample
  sizes, and intervals that do not overlap; even then it ranks models on this
  one task, not in general.
- **No claim that 13/13 means correct physics.** It means the submission
  satisfies the relations this verifier checks at the stated tolerance.
- **No claim of contamination-free measurement.** The task and verifier are
  public.
- **No claim about RL, training, or model improvement.** Nothing in this
  experiment trains anything.
- **The 13 cases are not 13 independent tasks.** They are 13 checks of one
  submission and are strongly correlated; a per-case rate is a diagnostic of
  partial progress, not a sample size.
