# Fourth cart-total episode: a grader-passing repair the agent never recognized

One authorized episode, run once, no retries. **The independent grader passed
for the first time in four episodes.** The agent did not verify that itself.

Read the outcome precisely: the agent-produced repair passed the independent
grader, but the agent never executed the shipped `checks.py`, never recognized
its own success, and never completed the workflow. The episode ended on the step
limit with no summary. This is a functional success by the grader only, not an
agent-verified repair, and it should never be reported as a completed agent
workflow.

Implementation commit `4252ebf9b3c9da0470a2507a2e5735593af7f5f8`. Model
`mlx-community/Qwen2.5-Coder-7B-Instruct-4bit`, revision
`019cc73c45c770444708a6dd8690c66243cc5c80`, no adapter, seed 0, temperature 0,
12 turns, 300 seconds, verification feedback v2. Fixture bytes identical to the
three earlier 7B episodes.

## What happened

Twelve turns: list, read `cart.py`, read `checks.py`, one rejected envelope, the
corrected edit, one Python run, then six stale edits until the step limit.

At step 4 the agent placed `path`, `old_text` and `new_text` at the top level
and was rejected. The corrected message named `edit_file`, listed the misplaced
keys and showed the placeholder shape, and did not mention `list_files`. At step
5 the agent nested the same values under `arguments` and the edit was accepted,
changing `cart.py` to the correct `price * quantity` form while preserving both
public definitions and the tuple representation. Syntax feedback reported valid.

At step 6 the agent retyped `checks.py` into a `run_python` command instead of
executing the file, and changed one expected value from 29 to 28. The specified
total for `[(7, 3), (2, 4)]` is 29, so its own assertion was wrong and its
correct code failed it. The only execution in the episode therefore reported
failure for a repair that was already right.

At steps 7 through 12 the agent re-sent the identical accepted edit six times.
Each was schema-valid and rejected with `old_text must match exactly once`,
because step 5 had already replaced that text and it now occurs zero times. The
workspace was never re-read after the edit landed.

## Mechanism coverage

Syntax feedback fired. Removed-definition feedback did not, correctly, because
the edit preserved both definitions. Finish deferral did not, because `finish`
was never requested. No existing mechanism covers an agent that edits correctly,
tests against a faulty transcription of the shipped test, and never finishes.

## Contents and handling

Registration, result, cleanup, the complete trajectory and conversation, the
original and final workspace, the changes diff, the fixture, the model manifest,
and the implementation files as they stood at the commit. Excluded: model
tensors, the control directory, and machine install logs.

Absolute repository prefixes in metadata and tracebacks become `<REPOSITORY>`.
Model-visible trace events, generated responses, source bytes and the
conversation are byte-identical to the raw records, which remain unchanged under
`attempts/replace-lines-7b-envelope-smoke/`. `archive-manifest.json` records the
original-to-archived hash mapping for all 23 files.

Regenerate with:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/archive_7b_envelope_smoke.py
```

No inference, training or re-grading was performed to produce this archive.
