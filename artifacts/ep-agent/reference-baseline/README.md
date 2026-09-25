# Reference baseline for the learning phase

The pinned `mlx-community/Qwen2.5-Coder-7B-Instruct-4bit`, revision
`019cc73c45c770444708a6dd8690c66243cc5c80`, **no adapter**, **verification
feedback disabled**, seed 0, temperature 0, 12 turns, 300 seconds, 768 output
tokens, 8192 context, with the existing six tools including `replace_lines`.
Implementation commit `9c58aff8`.

This is the configuration any learning result must be compared against.
`baseline.json` records it with the hashes of the eight files that define it.

## Measured performance, Evaluation 01

| Measure | Value |
| --- | --- |
| Independent functional repair | 3/10 |
| Evidence-supported finish | 0/10 |
| Fixtures with agent-initiated testing | 1/10 |
| Visible test passed | 4/10 |
| Finish called | 10/10 |
| Reached step limit | 0/10 |
| Schema rejections / tool failures | 0 / 0 |
| Wall time, ten episodes | 12.3 min |
| Peak MLX / RSS | 4.76 / 1.35 GB |

The repaired fixtures were `matrix-transpose`, `histogram-buckets` and
`retry-backoff`.

Two numbers matter most for what comes next. Functional repair sits at 3/10,
which with ten samples has almost no power to detect a change. Evidence-supported
finish sits at **0/10**, a clean floor: the agent never once ran the shipped test
after its last edit and then finished citing the result.

## What is preserved, not replaced

Verification feedback v3 stays implemented in `src/epagent/verification.py` and
its negative evaluation stays in `../evaluation-01/`. Neither is deleted,
rewritten or rescored. The feature is disabled in this reference configuration
because it measured worse, not because it was removed.

Evaluation 01's outcomes have now been observed. Its ten fixtures are
development and validation data from here on and must never be presented as
fresh held-out evidence again.

Any learning result must report functional repair and tool-compliance measures
separately. They are not one score.
