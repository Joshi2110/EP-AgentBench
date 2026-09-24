# Frozen SFT v3 experiment

Commit: `cd900043565a13fa10409ab755f6e1e1ca461f74`. Primary recovery: **base 0/4, v3 0/4**.

Registered scores were recomputed from the complete traces with the unchanged scorer and matched every original report. Setup interventions are excluded from model action counts.

| Fixture | Arm | Primary | A | B | C | Rejected edits / repeated injected | Relevant tests | Finish classifications | Calls | Seconds |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | ---: | ---: |
| exclusive-members | base | no | yes | no | no | 6 / 6 | 0 | none | 12 | 29.432 |
| exclusive-members | adapted | no | yes | no | no | 6 / 6 | 0 | none | 12 | 31.576 |
| version-numbers | base | no | yes | no | no | 6 / 6 | 0 | none | 12 | 33.370 |
| version-numbers | adapted | no | yes | no | no | 6 / 6 | 0 | none | 12 | 27.453 |
| record-priority | base | no | yes | no | no | 6 / 6 | 0 | none | 12 | 38.718 |
| record-priority | adapted | no | yes | no | no | 6 / 6 | 0 | none | 12 | 30.989 |
| true-streak | base | no | no | no | no | 12 / 12 | 0 | none | 12 | 36.047 |
| true-streak | adapted | no | yes | no | no | 6 / 6 | 0 | none | 12 | 35.187 |

A: source reinspection after injected error. B: accepted edit using uniquely matching observed text. C: qualifying source-byte change. Primary requires B within four model-generated turns. Final workspace changes and event IDs are in result.json.

## Training measurements

Completed 138 updates / 138 row exposures / 2.0 passes; 5062 supervised assistant tokens. Mean per-example train loss: 0.152354027.
Command wall time 419.058 s; trainer/validation time 415.067 s; peak MLX 3173620874 bytes; peak process RSS 1833533440 bytes. Memory measures are distinct, not additive.

| Completed updates | Training interval mean | Validation loss |
| ---: | ---: | ---: |
| 0 | — | 0.37003418803215027 |
| 5 | 0.767885160446167 | — |
| 10 | 0.5457186222076416 | — |
| 15 | 0.16408265829086305 | — |
| 20 | 0.2717587947845459 | — |
| 25 | 0.31143667697906496 | — |
| 30 | 0.23730020523071288 | — |
| 35 | 0.17955904006958007 | — |
| 40 | 0.15763449668884277 | — |
| 45 | 0.1290869116783142 | — |
| 50 | 0.12001408338546753 | — |
| 55 | 0.0602752685546875 | — |
| 60 | 0.07772846817970276 | — |
| 65 | 0.13861805200576782 | — |
| 68 | — | 0.08661115914583206 |
| 70 | 0.09775983095169068 | — |
| 75 | 0.18493324518203735 | — |
| 80 | 0.12439998388290405 | — |
| 85 | 0.2611932516098022 | — |
| 90 | 0.02151448130607605 | — |
| 95 | 0.07902719378471375 | — |
| 100 | 0.031103023886680604 | — |
| 105 | 0.03176595866680145 | — |
| 110 | 0.0361248254776001 | — |
| 115 | 0.027053672075271606 | — |
| 120 | 0.04092769920825958 | — |
| 125 | 0.010734477639198303 | — |
| 130 | 0.01841738075017929 | — |
| 135 | 0.024377158284187316 | — |
| 137 | — | 0.04922730475664139 |
| 138 | 0.09090088804562886 | 0.048685792833566666 |

Native validation labels are completed updates 0, 68 and 137; final explicit validation is after 138. Training means cover five updates except the final three-update interval. No loss-based stopping or checkpoint selection.

## Final summaries

No finish calls or final summaries were emitted.
No summaries were classified as unclassified.

## Reproducibility

Model: mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit, revision b3252a2f97102b1fb1571fec2c9b27219a8536be. Stop IDs [151643, 151645]. Python 3.11.15; mlx-lm 0.31.3; mlx 0.32.2; transformers 5.17.0; numpy 2.4.6.

Final adapter SHA-256: `4f0f3dde55d6486313f860eaf1f6fcdb2d1f1373b481553e8302cacdb6bc42ff`.

Exact stage commands (each launched once through the preserved run_stage.py wrapper):

```bash
.venv/bin/epagent synthetic --arm base --fixtures data/epagent-sft-v3/eval-fixtures.json --protocol data/epagent-sft-v3/eval-protocol.json --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --out attempts/tool-recovery-v3-base
PYTHONPATH=src .venv/bin/python -m epagent.sft train --prepared sft-runs/reviewed-prepared-v3 --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --out sft-runs/tool-use-lora-v3
.venv/bin/epagent synthetic --arm adapted --fixtures data/epagent-sft-v3/eval-fixtures.json --protocol data/epagent-sft-v3/eval-protocol.json --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --adapter-dir sft-runs/tool-use-lora-v3 --out attempts/tool-recovery-v3-adapted
```

Each long-running child had `/usr/bin/caffeinate -i -s -w CHILD_PID`; exact PIDs, timestamps, exit codes and log paths are retained.

V3 was designed after observing the v2 failure. Training configuration/data were frozen before the new v3 held-out fixtures were authored. No held-out model outcomes informed that configuration.

- Data and exposure changed together; no causal attribution to either alone.
- Different held-out fixtures across v2/v3; score changes are not a controlled same-task estimate of improvement.
- Four deterministic cases per arm; no significance or broad generalization claim.
- B permits accepted no-op edits; C measures bytes separately. Neither proves scientific repair.
- Synthetic checks are visible and their output agent-controlled; no independent functional or Hall validation is claimed.

## Behavioral evidence and v2 comparison

Recovery remains 0/4 in both arms. V3 makes 24 edit attempts, all repeats of injected rejected edits; none succeeds. The first three complete action sequences are identical across arms. On true-streak the base repeats 12 rejected edits without reinspection; v3 alternates six source reads with six identical rejected edits. Neither arm modifies files, runs Python/tests or finishes.

V2 adapted made 48 reads and zero edits on its earlier four cases. V3 adapted makes 24 reads and 24 rejected edits on new cases. V3 changed both training data and exposure budget, and uses different held-out fixtures; this is descriptive behavior evidence, not a causal attribution to either change or a matched v2-v3 score comparison.

For adapted exclusive-members, event 32 reads the source; event 33 returns four-space indentation. Event 105 submits old_text with two-space indentation, exactly repeating the injected rejected edit. Event 106 returns `old_text must match exactly once`. This six-cycle repetition occurs despite untruncated source observations.

For adapted true-streak, source read events 33/34 expose two occurrences of `    return 0\n`; edit event 100 still uses that ambiguous span. Observation event 101 returns the same exact-match error. The base makes twelve rejected edits and never performs post-failure source reinspection. Full event records and final response wording are in trajectory-review.json.

All eight final assistant responses inspected: tool calls only. No finish calls, final summaries or unclassified summaries. None counted as substantiated claims.

## Integrity, warnings and cleanup

All eight episodes were valid/scored and terminated at `step_limit` (12 schema-valid tool calls each). No retry, numerical training failure, nonfinite loss, episode infrastructure failure or training warning was observed. Training stderr contains progress bars. The initial postprocessing helper expected a hash field in model_ready that only exists in the final report; the helper was corrected and verification passed. No registered code, configuration or outputs were changed, and no stage reran.

Baseline/adapted configurations differ only in adapter_dir, initial workspace hashes match, and first model-input token IDs match per fixture. Both final reports and actual model_ready events verify the original model ID/revision and requested/loaded adapter states. Final adapter hashes match training output.

All 2656 protected pre-existing files remain byte-identical, including v1/v2 artifacts, model weights, adapters, task/grader code and the public snapshot. Baseline, adapted and v3 checkpoint hashes were rechecked. Git remains at the reviewed commit with a clean worktree; no results were committed, pushed or published.

Cleanup verified that all experiment-owned wrapper, model/collector, trainer and caffeinate processes exited. No unrelated process was terminated.

Stage execution records preserve exact UTC timestamps. Training ended before the conversation resumed for adapted evaluation; that idle gap was not training runtime or an interrupted training operation. Reported command wall times exclude the between-stage gap.

## Preserved locations

- Base suite and four raw attempt directories: `attempts/tool-recovery-v3-base/`
- Adapted suite and four raw attempt directories: `attempts/tool-recovery-v3-adapted/`
- Adapter/checkpoints/configuration/run/metrics: `sft-runs/tool-use-lora-v3/`
- Paired JSON result, analysis, full command logs, trace review, verification and inventory: `sft-runs/controlled-v3-experiment/`
- Frozen prepared data: `sft-runs/reviewed-prepared-v3/`

result.json lists absolute paths for every report, trace, initial/final workspace, conversation and diff. artifact-sha256.json inventories every retained experiment artifact except itself.
