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
`epagent.verification-feedback.v1`. The development runner exposes the same
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
