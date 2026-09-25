# Opt-in verification feedback after the 7B development failure

The [preserved episode and compatibility review](../artifacts/ep-agent/7b-development-smoke/README.md)
record a failed repair, not an agent success. Both the 1.5B and 7B episodes failed.
This is a one-episode development comparison, not an estimate of model-size effects.
The 7B model read source and constructed valid versioned edits, but never read
requirements/tests, ran no tests, and removed the function definition on step 5.
The first syntax error was `IndentationError: unexpected indent` at line 3.
The exact five-edit reconstruction is in the archive's `edit-analysis.json`.

## Minimal change

`run_episode(..., verification_feedback=True)` explicitly enables protocol
`epagent.verification-feedback.v3`. The development runner exposes the same
option as `--verification-feedback` and records the full resulting prompt in
its registration. It is off by default and rejected for frozen synthetic recovery
protocols. Historical prompts, parser, tools, versions, edit results, sampling
defaults, training data and scorers are unchanged. The compatibility patch was
committed separately before this instruction/observation change.

The additional instructions ask the agent to inspect requirements and relevant
test source before editing, preserve required APIs, inspect failures, run relevant
tests after changes, and finish with the command, observed result and unresolved
issues. They contain no worked repair or placeholder arguments. These are
instructions, not enforced action ordering or a solution supplied by the runner.

After any action changes Python files, their snapshot bytes are compiled in the
existing constrained Python subprocess. This is bounded by the remaining episode
time, tool timeout and output limit. It neither imports nor executes those files,
writes bytecode, repairs code, nor rolls back a write. Deleted files, timeouts or
unreadable checker output are reported as not checked. Valid syntax says nothing
about API compatibility or correct behavior.

The original tool observation is retained and augmented with `verification`.
An invalid written file explicitly reports `write_status: applied_with_syntax_errors`,
the exception, filename, line and column. The bytes remain changed; an accepted
write is not described as a valid program. The same feedback enters the next
model request and a separate `verification_feedback` trace event. Automatic
checks consume wall time, but do not inflate agent tool-call counts. Any actual
byte change also triggers a reminder to run relevant tests.

At finish, an evidence inventory records agent Python-run steps/statuses and
which occurred after the latest file change. Automatic compilation does not
count as agent-run testing. Runs that themselves write files conservatively do
not qualify as subsequent tests. No subsequent run yields
`claim_support: no_post_change_execution`; otherwise the status remains
`manual_review_required`. A successful process exit or printed PASS is not proof
of relevant tests. Review the recorded commands, outputs and summary together.
Honest unresolved finishes remain possible; this feature does not classify prose
or refuse submission. The independent original-test/physics verifier still runs
only after the backend has closed and supplies no feedback to the agent.

## v2: contract feedback after the second 7B failure

The [second preserved episode](../artifacts/ep-agent/7b-verification-smoke/README.md)
failed differently. The model wrote valid Python, so the syntax path never fired.
Its one edit renamed `cart_total` to `calculate_total` and changed the input
representation, it ran an ad-hoc command against its own replacement, and it
finished claiming success. The protocol identifier moved to `v2` so episodes
before and after this change stay distinguishable.

**Removed definitions.** After an action changes Python files, the top-level
public `def`/`class` names present before it are compared with those present
after. Names that disappeared are reported as `removed_definitions`, with a note
that removal can be intended and that callers may need updating. It never claims
the edit is wrong: renaming back reports the temporary name as removed too.
Nested and method definitions and underscore-prefixed names are out of scope.
When either side does not parse, the comparison is skipped and recorded as
`definitions_not_compared`, leaving the existing syntax feedback to describe it.
Everything is computed from workspace source; no grader expectation is consulted.

**Workspace tests.** Test files are discovered from the original exported
workspace by naming convention only: a path component or filename token in
`test`, `check`, `verify`, `validate`, `validation` or `spec`. No task-specific
filename is built in, and files the agent creates later never qualify. Reads and
executions are tracked from recorded tool actions. Execution is recognized only
by importing the test module or by naming it inside an executing call such as
`exec` or `runpy.run_path`. An arbitrary command that merely prints, including
one that prints a pass marker, is not execution. The finish inventory separates
existence, reads, executions, the observed status of each execution, and whether
the test bytes were still unmodified when it ran.

**Finish semantics.** A warning that arrives only after termination cannot change
anything, so the reminder is nonterminal and bounded. If the feature is enabled,
the workspace ships a discoverable test, no recorded action has run it, no
reminder has been issued yet, at least two turns remain and wall time remains,
then `finish` is not accepted: the observation reports `finished: false` with a
`finish_deferred` block naming the discovered tests and the action to take, the
episode continues, and the agent keeps its remaining budget. Each of those
conditions is required, so at most one reminder is ever issued and the next
`finish` is always accepted whatever the agent did in between. There is no
rejection loop. A task with no discoverable test is never deferred. When the
budget cannot absorb a reminder the finish proceeds and the honest terminal
status stands, with the missing verification recorded rather than success
invented. With the feature disabled, `finish` behaves exactly as before.

The workspace is never modified by any of this, no code is repaired or rolled
back, and the independent grader is unchanged and still runs only after the
backend closes.

## v3: runner-executed workspace tests

Across four frozen `cart-total` episodes the shipped test was executed zero
times. In the fourth the agent retyped it into a Python command, changed one
expected value, and its correct repair failed its own incorrect assertion.
Retyping is the failure, so v3 removes the need to retype.

When an accepted action changes Python bytes and the original workspace ships a
discoverable test, the runner executes **the original test bytes** against the
current source, in the existing bounded subprocess, and attaches the result to
the same observation. The preserved bytes are used even when the agent has since
edited the test on disk, and the difference is reported rather than corrected.
Nothing is written to the workspace and no code is repaired or rolled back.

Each result carries the test path, the execution method, a hash of the executed
bytes, whether the on-disk file still matches them, the exit status, the process
return code and bounded stdout and stderr, and whether execution completed or
timed out. When the remaining budget is gone the entry reads `not_checked` with
no status, return code or output: a passing result is never assumed.

Every execution records who started it. Runner-initiated runs are listed in
`runner_executed` and `runner_executions` and are **never** credited to the
agent-initiated endpoint, so `executed` and `claim_support` keep their v2
meaning and the finish reminder still fires when the agent has not run the test
itself, however many times the runner has.

The independent grader is untouched and still runs only after the backend
closes, and no grader verdict or metadata reaches the model. There is an
important consequence to state plainly: where a discovered workspace test is the
same file the grader executes, as on `cart-total`, this feedback exposes the
functional evaluation signal during the episode. Episodes run with it must be
analyzed separately and never pooled with episodes run without it. Exit status
zero, a printed marker and verified correctness remain three different things.

The protocol identifier moved to v3. The feature stays off by default and
rejected for frozen synthetic protocols, and the agent prompt, editing tools,
grader, training pipeline and reward function are unchanged.

## Offline acceptance

`tests/test_verification_feedback.py` uses scripted decisions only. It covers:

- An actual syntax-breaking write, delivery of its error to the next turn,
  source reinspection, correction, relevant test and supported finish. All
  unrelated source bytes remain intact.
- Valid syntax with incorrect behavior and a fabricated printed PASS: the
  independent original tests still fail after the backend closes.
- An unresolved finish without testing, stale execution evidence, and a Python
  action that writes invalid source. Edits remain freely possible.
- Compile-only behavior despite workspace import shadows and executable source
  side effects, deleted/empty/null-byte files, time/output limits, and unchanged
  default prompts and observations.
- Removed-definition reporting for function removal, rename, class removal,
  unrelated edits, private names and unparseable source, plus delivery of the
  removal to the next model request and a scripted restoration afterwards.
- Runner-executed workspace tests for a correct and an incorrect edit, delivery
  to the next model request, preserved bytes running after the agent rewrites
  the test on disk, honest `not_checked` and `timed_out` reporting, runner and
  agent executions staying distinguishable, and absence when disabled.
- Convention-based test discovery, rejection of ad-hoc commands as execution,
  agent-created files failing to qualify, one bounded nonterminal reminder, an
  immediately accepted second finish, and no reminder when turns run out.

The full suite and packaging commands/results are recorded in
[verification-feedback-checks.json](../artifacts/ep-agent/verification-feedback-v1/verification-feedback-checks.json),
alongside the test, wheel and install logs. These are engineering tests, not ML results.
No real-model inference or training was run for this change.

## Proposed single next episode — not yet authorized or run

Use the same `cart-total` source, original pinned 7B weights, no adapter, seed 0,
temperature 0, 12 turns, 300 seconds, 768 output tokens and existing tool definitions.
Enable only the documented verification mode, in a fresh output directory:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_development_smoke.py \
  --fixture data/epagent-development/cart-total.json \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out attempts/replace-lines-7b-verification-smoke \
  --verification-feedback
```

Before any separately authorized run, recheck memory headroom and output-directory
freshness. The runner attaches caffeinate and performs the existing execution
preflight. Run exactly once, preserving failures. Inspect requirements/test reads,
all byte changes, syntax feedback received, actual relevant test results, final
claim evidence and the independent check. Extra feedback consumes context/time
and changes the interaction protocol; success would establish only this development
repair, not a controlled model-size effect or scientific generalization.
