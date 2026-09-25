# 7B verification-feedback development episode: a functional-contract failure

One authorized episode, run once, no retries. It records a **failed repair**.
The syntax-error feedback path was **never exercised**, because the model wrote
no invalid Python. Nothing here supports a claim that the feedback helped or
hurt, and one episode cannot separate the feature from ordinary run-to-run
variation.

Implementation commit `48c0c690d5b4e5284243005f3e596437f2134dc4`. Model
`mlx-community/Qwen2.5-Coder-7B-Instruct-4bit`, revision
`019cc73c45c770444708a6dd8690c66243cc5c80`, no adapter, seed 0, temperature 0,
12 turns, 300 seconds, 768 output tokens. Configuration is byte-identical to the
earlier 7B episode in `../7b-development-smoke/`; the only deliberate differences
are the opt-in `--verification-feedback` flag and the instructions it appends.

## What happened

Five schema-valid tool calls, no rejections: list, read `cart.py`, one edit, one
Python run, finish. The edit replaced `def cart_total(rows):` with
`def calculate_total(cart_items):` plus a dictionary-based body. That is valid
Python, so the checker reported `valid` and `write_status: applied`, and said so
in the next model request along with its standing reminder that an applied edit
is not a verified repair. The model then ran its own command importing
`calculate_total` with dictionary inputs, saw `35`, and finished claiming the
test passed. The independent grader failed with
`ImportError: cannot import name 'cart_total'`.

The required name was not merely discoverable. It was the exact string the model
supplied as `old_text` in order to delete it, and the required tuple
destructuring was in the observation it had just read. `README.md` and
`checks.py` were listed at step 1 and never opened.

## Why the agent's test passed and the shipped test failed

The agent imported the name it had just created and passed the representation it
had just invented, so its command exercised the replacement against itself. It
asserted nothing and compared against no specified value. `checks.py` imports
`cart_total` and passes tuples, so it failed at import time before any assertion
ran. Full event-level detail is in `contract-analysis.json`.

## Contents and handling

Registration, result, cleanup, the complete trajectory and conversation, the
original and final workspace, the changes diff, the fixture, the model manifest,
and the implementation files as they stood at the commit. Excluded: model
tensors, the control directory, and machine install logs.

Absolute repository prefixes in metadata and tracebacks become `<REPOSITORY>`.
Model-visible trace events, generated responses, source bytes and the
conversation are byte-identical to the raw records, which remain unchanged under
`attempts/replace-lines-7b-verification-smoke/`. `archive-manifest.json` records
the original-to-archived hash mapping for all 22 files.

Regenerate with:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/archive_7b_verification_smoke.py
```

No inference, training or re-grading was performed to produce this archive.
