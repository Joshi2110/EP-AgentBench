# First controlled SFT experiment: frozen analysis

Code: `b5d99aec17362cc1ab4b459454efac90b3800488`. Primary recovery: **base 0/4, adapted 0/4**. All eight attempts were valid/scored, and all ended at the 12-turn limit. No infrastructure failures or retries occurred.

A = post-failure source reinspection; B = accepted corrected edit using observed source; C = qualifying source-byte change. Each arm used the same four frozen cases, seed 0, temperature 0, tools and limits. Setup turns are excluded.

| Fixture | Arm | Primary | A | B | C | Repeated rejected edit | Schema-valid tool calls | Episode seconds |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| rotate-ticket | base | No | Yes | No | No | 6 | 12 | 29.711 |
| rotate-ticket | adapted | No | Yes | No | No | 0 | 12 | 22.783 |
| strip-badge | base | No | Yes | No | No | 6 | 12 | 30.580 |
| strip-badge | adapted | No | Yes | No | No | 0 | 12 | 22.902 |
| positive-total | base | No | Yes | No | No | 6 | 12 | 25.235 |
| positive-total | adapted | No | Yes | No | No | 0 | 12 | 22.227 |
| mapping-fallback | base | No | Yes | No | No | 6 | 12 | 29.601 |
| mapping-fallback | adapted | No | Yes | No | No | 0 | 12 | 23.432 |

Lower validation loss did not produce successful held-out tool recovery. The base policy alternated six source reads with six repeated injected rejected edits per case. The adapted policy made twelve source reads per case and attempted no edits. Zero rejected edits therefore reflects edit avoidance, not successful repair.

Both arms made 48 schema-valid calls. Base: 24 reads and 24 rejected edits. Adapted: 48 reads and no edit attempts. No model changed any file or ran Python/tests. There were no accepted no-op edits either. No Hall evaluation was performed.

## Final-summary review

All eight last assistant messages are tool calls, not summaries. No finish calls or unclassified finish summaries were emitted. See trajectory-review.json for exact last-response wording.

No absence of a summary is counted as an honest failure claim. The registered automatic scorer was not changed.

## Actual training measurements

Exactly **40 updates**, batch size 1, Adam LR 1e-4, rank 8, MLX scale 16, query/value LoRA in layers 24–27, seed 0, gradient checkpointing enabled. **155,648 trainable parameters**, 1,127 supervised token targets processed, **40/72 = 0.555556** sample-equivalent passes.

Training command wall time: **251.145 s**. Trainer/validation interval: **246.850 s**, excluding initial loading/provenance checks. Peak MLX allocation: **3,061,407,218 bytes**. Peak process RSS: **1,816,543,232 bytes**. These are separate memory measurements, not additive.

| Completed updates | Training loss (preceding five updates) | Validation loss |
| ---: | ---: | ---: |
| 0 | — | 0.35133481 |
| 5 | 0.36641586 | — |
| 10 | 0.53087344 | — |
| 15 | 0.13991944 | — |
| 19 | — | 0.26560044 |
| 20 | 0.46514654 | — |
| 25 | 0.10714437 | — |
| 30 | 0.05559247 | — |
| 35 | 0.13166040 | — |
| 39 | — | 0.19627519 |
| 40 | 0.20578134 | 0.19171867 |

Mean of all 40 per-example training losses: **0.25031673**. Train reporting averages example means; validation aggregates supervised tokens. Native validation occurs before updates 20 and 40, hence the 19/39 labels. Final validation is after update 40. No checkpoint selection or update-count change was made.

## Model, adapter and artifacts

Base model: `mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit`, revision `b3252a2f97102b1fb1571fec2c9b27219a8536be`. All base records verified `adapter.loaded=false`; all adapted `model_ready` and final records verified `adapter.loaded=true`, matching the final training adapter/configuration hashes.

Final adapter SHA-256: `cbec8646e75885f48b30a06be8a5d65475fd13d838daeaab673e38fbd99086f7`.

Protocol SHA-256: `32da3a32b46c3df1ae117c0f59f40f1a32a7abb8f0029a1a334d30bb8a77e8dd`. Fixture SHA-256: `e15e687806b96b7b2d6d0b6a6f907867bf529af41b598a7228de52262d4a2147`.

Software: Python 3.11.15; mlx-lm 0.31.3; mlx 0.32.2; transformers 5.17.0; numpy 2.4.6.

All raw traces, workspaces, diffs, conversations, logs, checkpoints and reports are retained. `artifact-sha256.json` inventories their bytes. `result.json` contains exact per-case paths, model/dataset metadata, event IDs, measurements and stage argv.

- Base suite: `attempts/tool-recovery-v2-base/suite.json`
- Adapted suite: `attempts/tool-recovery-v2-adapted/suite.json`
- Training: `sft-runs/tool-use-lora-v2/run.json` and `metrics.jsonl`
- Adapter: `sft-runs/tool-use-lora-v2/adapters.safetensors` (20/40-update checkpoints also retained)
- This analysis/evidence: `sft-runs/controlled-v2-experiment/`

## Exact execution commands

Each stage was launched once by `.venv/bin/python sft-runs/controlled-v2-experiment/run_stage.py STAGE`. The wrapper invoked the following argv from the repository root and attached `/usr/bin/caffeinate -i -s -w CHILD_PID`. Exact PID/timestamp/exit records are in each `*-execution.json`.

```bash
.venv/bin/epagent synthetic --arm base --fixtures data/epagent-sft-v2/eval-fixtures.json --protocol data/epagent-sft-v2/eval-protocol.json --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --out attempts/tool-recovery-v2-base
PYTHONPATH=src .venv/bin/python -m epagent.sft train --prepared sft-runs/reviewed-prepared-v2 --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --out sft-runs/tool-use-lora-v2
.venv/bin/epagent synthetic --arm adapted --fixtures data/epagent-sft-v2/eval-fixtures.json --protocol data/epagent-sft-v2/eval-protocol.json --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --adapter-dir sft-runs/tool-use-lora-v2 --out attempts/tool-recovery-v2-adapted
```

Stage command wall times: base 115.865 s; train 251.145 s; adapted 91.486 s.

Base generated 2,016 tokens from 48,090 cumulative prompt tokens; adapted generated 924 from 43,800. Prompt counts include repeated history. The shorter adapted responses and absence of edit attempts accompany its shorter runtime; this is not successful task completion.

## Preservation and limitations

All 2,321 previously fingerprinted files and the base-model weights are unchanged, including prior episodes and the public snapshot. Baseline records were hash-checked after training and adapted collection. Git remains at the audited commit with a clean working tree; results are ignored local artifacts, not committed, pushed or published.

Owned wrapper/collection/training/caffeinate PIDs and EP-Agent model workers are gone. The pre-existing unrelated caffeinate PID 84856 was left untouched. Read-only process verification was temporarily delayed by approval-service quota exhaustion and completed after continuation.

This is one small, controlled tool-behavior experiment. Falling teacher-forced validation loss did not translate into recovery under the registered interactive protocol. Four fixtures do not support statistical significance or broad coding/scientific generalization. No extra evaluation or training run was launched.
