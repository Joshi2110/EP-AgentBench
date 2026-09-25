# Design note: executing workspace tests without retyping them

Not implemented. This note records a proposal and its risks after the four
frozen `cart-total` development episodes. No code changes accompany it.

## The failure this addresses

Across four episodes the shipped `checks.py` was executed zero times. Episode 4
shows why that matters. The agent applied the correct repair, then retyped the
test into a `run_python` command and changed one expected value from 29 to 28.
Its own assertion was wrong, its correct code failed it, and it spent the rest
of the budget re-sending an edit that had already landed. The independent grader
passed the repair that the agent believed had failed.

Retyping is the mechanism of failure. Any fix that still requires the model to
reproduce test source by hand leaves that failure mode open.

## Three options

**A. A dedicated `run_tests` tool.** The agent names a discovered test and the
runner executes the original bytes. This keeps the action agent-initiated and
measurable, but it adds a sixth tool, which changes the tool schema and the
system prompt. Tool definitions are part of the frozen experimental setup for
every protocol registered so far, so this is the largest change of the three.
It also depends on the model choosing the new tool, and four episodes show this
model repeatedly not choosing the right action.

**B. An opt-in post-edit check (recommended).** After an accepted action changes
Python bytes, the runner executes the discovered workspace test from the
**original exported bytes**, inside the existing sandbox and budget, and
attaches the real command, exit status, stdout and stderr to the same
observation the agent already receives. It reuses the machinery built for
verification feedback v2: discovery from the initial snapshot, bounded
execution, feedback on byte change. It needs no new tool and no schema change,
and it removes transcription entirely, because the agent never types the test.

**C. A test-invocation hint.** The existing feedback names the exact call that
would run the file, without executing anything. This is the smallest option and
it keeps agent execution measurable, but it is still an instruction the model
may ignore, and the record shows instructions being ignored in all four
episodes.

Option B is recommended because it is the only one that removes the failure
mode rather than asking the model not to make it. Option C is the fallback if
the measurement cost below is judged too high.

## What option B must guarantee

- Execute the **original** test bytes from the initial export, never the current
  file, and report whether the on-disk test still matches them.
- Run in the existing constrained subprocess under the existing tool timeout,
  output cap and remaining episode deadline. Report `not_checked` when the
  budget is gone, exactly as the syntax checker already does. `not_checked`
  never means passed.
- Report the actual command, exit status, stdout and stderr. Never assert
  correctness. A printed marker is not verification on its own, and the report
  must say so alongside the exit status.
- Label every execution with `executed_by: runner` or `executed_by: agent` and
  keep them in separate counters. A runner execution must **not** satisfy the
  existing endpoint for whether the agent ran the workspace test.
- Never consult the independent grader, never surface any grader verdict, never
  modify or roll back model-generated code, and never modify the workspace.
- Stay off by default, bump the protocol identifier to v3, and remain rejected
  for frozen synthetic protocols exactly as v2 is.

## The cost, stated plainly

This is not a free observability improvement. The independent grader runs the
original `checks.py` bytes. A runner that executes those same bytes mid-episode
hands the agent the signal the grader will later use. The verdict never reaches
the agent and the grader stays post-episode, but a repair completed under this
mechanism is a weaker claim than one completed without it: the agent no longer
had to decide to verify. Results from this condition must be reported separately
and never pooled with episodes run without it.

It also makes one existing measurement unobservable in that condition. Once the
runner executes the test after every edit, whether the agent would have run it
cannot be seen. Keeping both counters preserves the distinction in the record
but not the counterfactual.

## Required offline tests

- Original bytes are executed even after the agent modifies `checks.py` on disk,
  and the mismatch is reported.
- Command, exit status, stdout and stderr are reported truthfully for a passing
  and a failing repair.
- A tampered test that prints the marker does not produce a verification-passed
  status.
- Budget exhaustion yields `not_checked`, never a pass.
- Runner and agent executions are counted separately, and a runner execution
  does not satisfy the agent-execution endpoint.
- Disabled by default; rejected for frozen synthetic protocols; no grader result
  reaches the model; model-generated code is never altered or rolled back.
- A scripted agent that edits correctly receives a passing runner result and can
  finish with supported evidence; one whose edit is wrong receives the real
  failure and can iterate.

## Separately: stale edits after an accepted edit

Episode 4 spent half its budget on this. After the accepted edit at step 5, six
identical `edit_file` calls were rejected with `old_text must match exactly
once`. That message is true but uninformative. It does not distinguish zero
matches from many, and it does not say the file changed after the observation
the agent was working from. The agent never re-read `cart.py`.

Two minimal, independent options, neither of which changes edit semantics:

1. **Say what actually happened.** Report the real occurrence count, and when
   the path was modified earlier in the episode, note the step at which it
   changed and that a re-read is needed. This is the same correction already
   applied to the schema message: describe the real defect from observable
   state, without moving or repairing anything.
2. **Return the new version token from `edit_file`.** A successful `edit_file`
   currently returns only `{"edited": path}`, while `read_file` returns a version
   token. Returning the post-edit token would let the agent see that the file
   moved on, the same signal `replace_lines` already relies on.

Option 2 is smaller and gives the agent the information before it makes the
mistake, rather than after. Both are proposals only.
