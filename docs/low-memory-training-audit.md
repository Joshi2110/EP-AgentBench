# Experimental short-context preparation

This is an offline audit and a proposed probe, not a training run or a revision
of registered Evaluation 02. Its original dataset, protocol, runtime and
prepared artifacts remain unchanged. No new evaluation outputs were collected.

## Backward graph

The installed MLX 0.32.2 `nn.value_and_grad` differentiates
`model.trainable_parameters()`. The existing `adapt()` freezes the base and
exposes only Q/V LoRA matrices in blocks 24–27: 360,448 trainable parameters.
For integer inputs x, write h = F_frozen(x), logits = G_phi(h). Since h has no
dependence on phi, dh/dphi = 0. The requested gradient is the partial derivative
of the upper network with respect to its adapters. The lower 24 blocks are
already forward-only in this differentiation. Frozen operations *above* the
first adapter still participate in backward; freezing their weights does not
remove the required activation derivatives.

An explicit `stop_gradient(h)` is therefore redundant here. We did not add a
production mode or change inference. This conclusion would need revisiting if
adapters moved lower, embeddings became trainable, or input gradients were
requested. See the [MLX differentiation API](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.nn.value_and_grad.html)
and [stop-gradient semantics](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.stop_gradient.html).

The deterministic test uses a tiny randomly initialized, 4-bit Qwen2 with Q/V
LoRA in its final two blocks, both with and without native checkpointing. A
custom VJP witness at the frozen-prefix boundary is not invoked by adapter
differentiation; a positive control explicitly differentiating that boundary
does invoke it. Explicit detachment yields exactly equal logits, masked forward
loss and adapter gradients. All adapter gradients are finite, at least one is
nonzero, and no lower-layer parameters occur in the gradient tree. This tests
the relevant implementation, not the actual 7B allocation footprint.

## Context selection

`scripts/prepare_short_context.py` creates a separate inspectable derivative.
Every example records original indices, removed indices and retention reasons.
It preserves the original system prompt, task/budget instruction, target and
immediately preceding action/observation. It additionally keeps:

- The latest README observation (requirements/API).
- For edits: latest source/version, shipped test contract and latest failure.
- For test execution or finish: the latest applied edit and its observation.
- For finish: the latest actual test result.

Older listings, superseded reads, earlier edits and earlier test results outside
those dependencies are removed as complete action/observation pairs. No target
or retained tool observation is rewritten, shortened or summarized. Original
full trajectories remain available. Tokenization raises on overflow; it never
truncates. Tests check exact source/version grounding, immediate observation
retention, whole-message equality and identical supervised token sequences
using the actual local tokenizer. These are explicit dependency checks for
these demonstrations, not a proof that the selector generalizes to arbitrary
conversations. Selected examples should receive review before training.

| Split | Targets | Supervised tokens, unchanged | Full → selected maximum | Full → selected total tokens | Removed messages |
|---|---:|---:|---:|---:|---:|
| Train, 12 episodes | 62 | 1,948 | 1,382 → 1,010 | 60,613 → 47,573 | 274 |
| Validation, 2 episodes | 8 | 247 | 1,127 → 874 | 6,976 → 6,026 | 22 |

Train context volume drops 21.5%; the longest row drops 26.9%. The assistant
action distribution, split and 124-update/two-pass configuration are preserved;
only the derivative sequence ceiling changes from 1,536 to 1,024. This derivative
is **not eligible as the frozen Evaluation 02 training artifact**.

Reproduce preparation (output must not exist):

```bash
PYTHONPATH=src .venv/bin/python scripts/prepare_short_context.py \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out sft-runs/7b-short-context-v1
```

The generated manifest records model file hashes, selector/review hashes,
software versions, chat-template hash and all derivative file hashes.

## Memory conclusion and proposed probe

No memory saving is claimed from detachment. Native batch padding reduces the
longest probe batch from 1,409 to 1,024 positions, approximately 27% fewer
sequence-dependent elements; attention matrices, if materialized, would shrink
about 47%. This is not a 27–47% reduction in total peak memory. Roughly 4 GiB of
quantized weights remains resident, and temporary dequantization, kernels,
allocator behavior and macOS pressure remain important. The vocabulary logits
alone shed roughly 111–223 MiB per materialized tensor depending on dtype.
Actual peak allocation, RSS and backward runtime remain unmeasured. The previous
probe was interrupted by memory pressure without a completed backward result.

One shorter-context 7B probe is worth proposing, conditional on normal pressure
and sufficient system headroom. It is not authorized or executed by this work.
Use the existing guarded script, unchanged rank/scale, last-four-block Q/V LoRA,
batch 1, checkpointing, seed, 7 GiB ceiling and 300-second deadline:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_7b_training_memory.py \
  --prepared sft-runs/7b-short-context-v1 \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out sft-runs/7b-short-context-memory-v1 \
  --confirm-backward
```

No optimizer update. Preserve the script's pressure abort and acceptance checks.
If unsafe or unsuccessful, stop 7B fitting; do not lower parameters and retry.
A 3B fallback would require a separate pinned model identity, architecture and
tokenizer compatibility check, retokenization of this same derivative, and its
own registration/probe before training. No 3B weights were downloaded and no
claim of 3B feasibility is made here; the current evidence does not yet establish
that the shorter 7B configuration is clearly unsafe.

## Offline verification

```bash
PYTHONPATH=src PATH="$PWD/.venv/bin:$PATH" EPAGENT_TEST_MLX=1 \
  .venv/bin/python -m unittest discover -s tests -v
```

Also validate the derivative with `epagent.sft.load_prepared` and the original
Evaluation 02 with `epagent.assessment02.registered(..., 'base')`. These are
read-only checks, not evaluations. Public presentation is prepared separately
in `docs/public-readme-draft.md`; the publication snapshot is unchanged.

Executed on 2026-10-05: **261 tests passed in 131.241 seconds**, including
all three new context/gradient tests. Derivative validation and frozen
Evaluation 02 registration checks passed. Test log:
`/tmp/epagent-low-memory-tests.log` (temporary local log).
Software: Python 3.11.15, MLX 0.32.2, MLX-LM 0.31.3,
Transformers 5.17.0, NumPy 2.4.6. No optimizer or real-model generation ran.
