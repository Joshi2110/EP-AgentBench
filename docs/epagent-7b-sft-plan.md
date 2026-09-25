# First 7B LoRA SFT: frozen preparation and execution plan

Preparation only. No generation, model forward/backward or optimizer update has
been performed. Training approval and a successful memory check are prerequisites.
The objective is the existing evidence-supported-workflow metric, with functional
repair reported separately. Evaluation 01 measured 3/10 base repairs and 0/10
workflows; feedback v3 measured 1/10 repairs and 0/10 workflows. It is development
evidence, not the held-out comparison for this training run.

## Feasibility and bounded probe

The installed mlx-lm 0.31.3 trainer uses `nn.value_and_grad` on the registered
loss, with `grad_checkpoint(model.layers[0])` wrapping that layer class, then
Adam updates. This was inspected in installed source and the
[pinned upstream trainer](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/tuner/trainer.py).
The existing SFT implementation now accepts either exact model identity from the
inference allowlist, streams model hashing in 1 MiB chunks, and validates actual
trainable names/counts against a model-specific plan. The original loss masking,
trainer and agent remain unchanged. No verification mechanism was added.

The 7B configuration and safetensors **header**, without loading tensors, confirm
28 Qwen2 layers, hidden width 3584, Q output 3584 and V output 512. Rank-eight Q/V
LoRA on the last four layers (24–27) therefore has
`4 × 8 × [(3584 + 3584) + (3584 + 512)] = 360448` trainable parameters.
Four-bit base weights remain frozen. The model manifest, ten file hashes, packed
projection shapes, derived names, template hash and actual-tokenizer counts are
recorded in `data/epagent-sft-7b-v1/`. Native attachment and backward compatibility
remain unverified until the probe; a shared model family is not evidence of that.

Point-in-time memory observation: 16 GiB physical, 8 GiB swap allocated,
6981.69 MiB swap used, 1210.31 MiB swap free, pressure level 2 (warning).
Free/inactive/speculative page counters sum to about 3.68 GiB; this is not a
guarantee of reclaimable headroom. The OS separately reported 47% free by its
pressure-accounting measure. No current headroom clearance is claimed.

The old feasibility document suggested seq ≤1024. Actual full-history targets
reach 1382 tokens; this plan uses 1536 to retain requirements, failed observations
and edit/test/finish history without truncation. The provisional estimate is
**6–7 GiB peak MLX**, not measured. Original weights occupy about 4 GiB; large
vocabulary logits, gradient graphs, activations and cache dominate the rest.
Adam's two float32 states add about 2.75 MiB for these adapters. Estimated total
training time is **45–90 minutes** including validation, extrapolated from the
prior 1.5B run rather than a 7B timing measurement.

Proposed command — **not executed; requires separate authorization**:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_7b_training_memory.py \
  --prepared sft-runs/7b-workflow-prepared-v1 \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out sft-runs/7b-workflow-memory-v1 --confirm-backward
```

It refuses non-normal initial memory pressure before loading, attaches caffeinate,
and runs one actual longest-example loss and adapter-gradient computation using
the native batching/checkpointing and existing assistant-only loss. It forces MLX
evaluation of all gradients, checks finiteness and unchanged trainable values,
and has **no optimizer**. It records actual batch shape, loss, tokens, runtime,
MLX peak/RSS, parameter names and hashes. The 7 GiB MLX allocation ceiling,
300-second supervisor deadline and abort on elevated pressure bound the probe.
Acceptance also requires peak ≤6.5 GiB. Any failure blocks training; no automatic
shorter-sequence retry or configuration change. This does not measure sustained
training, allocator fragmentation or optimizer-update peak memory. A passed probe
is a necessary gate, not a guarantee that 124 updates will finish.

## Frozen training and data

Fourteen inspectable real-tool demonstrations: 12 train / two validation,
62 / eight assistant targets, 1948 / 247 supervised tokens. Complete histories,
assistant-only EOS-inclusive masks, no truncation, no synthetic observations.
The data README records tool counts, transition counts, patterns and deliberate
context-only failures. Twelve train finishes comprise eleven observed passes and
one honest unresolved failure. Validation is family-disjoint, small and fixed.
All earlier SFT and Evaluation 01 cases are excluded from Evaluation 02.

| Setting | Frozen value |
|---|---|
| Model | mlx-community/Qwen2.5-Coder-7B-Instruct-4bit |
| Revision | 019cc73c45c770444708a6dd8690c66243cc5c80 |
| Starting adapter | None; original base |
| Updates / exposure | 124 / two full passes over 62 targets |
| Batch / sequence cap | 1 / 1536 tokens |
| LoRA | Q/V on layers 24–27; rank 8, scale 16, dropout 0 |
| Optimizer | Adam, learning rate 1e-4; no schedule change |
| Seed / checkpointing | 0 / enabled |
| Validation / save | All eight validation examples at start/pass boundaries; save each 62 updates |
| Loss reports | Every four updates, plus validation/final validation |
| Final adapter | sft-runs/7b-workflow-lora-v1/adapters.safetensors |
| Adapter configuration | Same directory, adapter_config.json |

Use the **final** 124-update adapter, not a validation-selected checkpoint.
Native checkpoints and losses remain saved even on failure; do not restart with
new hyperparameters. `run.json`, `metrics.jsonl` and checkpoint hashes establish
actual completion. The initial adapters are newly initialized in memory; neither
1.5B adapter is loaded. The final adapter identity cannot be known before training:
record SHA-256 of its config and weights then verify actual load in the adapted arm.

Reproducible preparation command (already executed; choose a fresh output if replaying):

```bash
PYTHONPATH=src .venv/bin/python -m epagent.sft prepare \
  --trajectories data/epagent-sft-7b-v1/trajectories \
  --config data/epagent-sft-7b-v1/lora-config.json \
  --protocol data/epagent-sft-7b-v1/training-protocol.json \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out sft-runs/7b-workflow-prepared-v1
```

## Exact later sequence, not yet executed

After review, normal memory pressure and a passed authorized memory probe, install
the reviewed package into `.venv` (`.venv/bin/python -m pip install --no-deps
--no-build-isolation .`) so the offline inference child imports the reviewed code.
Then run, in order, only when separately authorized:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_evaluation_02.py \
  --arm base --fixtures data/epagent-evaluation-02/fixtures.json \
  --protocol data/epagent-evaluation-02/protocol.json \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out attempts/evaluation-02-base

caffeinate -i .venv/bin/python -m epagent.sft train \
  --prepared sft-runs/7b-workflow-prepared-v1 \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out sft-runs/7b-workflow-lora-v1 > sft-runs/7b-workflow-lora-v1.log 2>&1

PYTHONPATH=src .venv/bin/python scripts/run_evaluation_02.py \
  --arm adapted --fixtures data/epagent-evaluation-02/fixtures.json \
  --protocol data/epagent-evaluation-02/protocol.json \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --adapter-dir sft-runs/7b-workflow-lora-v1 \
  --out attempts/evaluation-02-adapted
```

Preserve all ten baseline records before updates. Only successful training permits
the adapted arm. Keep original model/adapter directories unchanged. The evaluation
runner records commands/software, attaches caffeinate and refuses overwriting;
training records losses/checkpoints/versions, preserves stdout/stderr in a separate
log, and uses the frozen prepared identity. Do not overwrite an existing log.
Both evaluation arms have feedback off and identical task/generation conditions.
The existing primary metric and separate hidden functional endpoint are unchanged.

## Limits and review decisions

Training memory is the genuine unresolved feasibility gate. Do not authorize a
run on the strength of a load-only check; the recorded pressure is already elevated.
The bounded probe itself still requires explicit permission. The dataset and
sequence cap should be reviewed together rather than silently truncating history
to fit a memory estimate. Do not alter the frozen budget after baseline or losses.

Only 1948 unique supervised training tokens invite memorization. Setup README/test
reads are present but not positive targets, so initial discovery could remain weak.
The tiny validation split and demonstrations of behavior the base rarely performs
may fail to transfer. The registered automatic finish metric records execution
evidence, not semantic truth of every summary; manual finish review stays separate.
Hidden tests are runtime-withheld, not secret, and finite tests do not prove full
correctness. Ten deterministic cases support paired descriptive results only.

`data/epagent-sft-7b-v1/verification.json` records actual preparation/test/package
commands and outcomes. No inference, backward test or training result is claimed.
