# Third 7B development episode: a rejected-envelope loop, no edit applied

One authorized episode, run once, no retries. It records a **failed repair**.
The workspace came back byte-identical to its initial state, and none of the
verification-feedback v2 mechanisms were exercised, because the episode failed
upstream of all of them.

Implementation commit `cf421bbc294b3b50b7b42d72a3b3c3c6d52ab54d`. Model
`mlx-community/Qwen2.5-Coder-7B-Instruct-4bit`, revision
`019cc73c45c770444708a6dd8690c66243cc5c80`, no adapter, seed 0, temperature 0,
12 turns, 300 seconds, 768 output tokens, `--verification-feedback` enabled at
protocol `epagent.verification-feedback.v2`. Fixture bytes are identical to the
two earlier 7B episodes in `../7b-development-smoke/` and `../7b-verification-smoke/`.

## What happened

Nine accepted calls and three rejections across twelve turns, ending on the step
limit with no `finish`. The agent listed files, read `cart.py`, and read
`checks.py`, the first time any 7B episode has opened the shipped test. It then
attempted `edit_file` and was rejected, after which it repeated a three-step
cycle of list, read, rejected edit twice more.

All three rejected responses were byte-identical. They named the right tool and
carried correct parameter values, but placed `path`, `old_text` and `new_text`
at the top level instead of inside the required `arguments` object. Only the
envelope shape was wrong. The rejection text the agent received was a fixed
string that named `list_files` whatever tool had been attempted and never said
to nest the parameters under `arguments`. In all three cases the next recorded
action was `list_files`. That is a co-occurrence in the record, not a claim
about what the model intended.

## The offline counterfactual, which is not a repair

`envelope-analysis.json` records that the rejected call's own `old_text` and
`new_text`, placed in a valid envelope and applied to a fresh copy of the
original fixture **outside the episode**, make `checks.py` print
`PASS cart-total`. That is an offline property of the generated text.

**The agent did not repair this task.** It never applied an edit, never executed
`checks.py`, left the workspace unchanged, and the independent grader failed with
the original `AssertionError`. The counterfactual must not be reported as an
agent-completed repair or counted in any success rate.

## Contents and handling

Registration, result, cleanup, the complete trajectory and conversation, the
original and final workspace, the changes diff, the fixture, the model manifest,
and the implementation files as they stood at the commit. Excluded: model
tensors, the control directory, and machine install logs.

Absolute repository prefixes in metadata and tracebacks become `<REPOSITORY>`.
Model-visible trace events, generated responses, source bytes and the
conversation are byte-identical to the raw records, which remain unchanged under
`attempts/replace-lines-7b-contract-smoke/`. `archive-manifest.json` records the
original-to-archived hash mapping for all 22 files.

Regenerate with:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/archive_7b_contract_smoke.py
```

No inference, training or re-grading was performed to produce this archive.
