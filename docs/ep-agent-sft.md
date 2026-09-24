# EP-Agent: first SFT pipeline, prepared but not trained

This milestone implements reviewed trajectory conversion, real-template
assistant-only supervision, and a small local MLX-LM LoRA training entry point.
No optimizer update, policy generation, baseline evaluation, or SFT training run
was performed. The existing agent loop, prompt, tools, Hall tasks, graders,
references, Experiment 02, and publication snapshot are unchanged.

## Data and role preservation

The [demonstration set](../data/epagent-sft-v1/README.md) contains six training and
two validation workspaces, yielding 57 and 19 assistant-turn examples. They are
new inspectable synthetic fixtures, authored with assistant help and checked
by executing the tools. They are not harvested proprietary-model successes.
Human/Claude Code review is pending; this delivery requests that review before
training. Four additional workspace families are reserved for behavioral probes.

The existing trajectory format already separates `model_request.messages`,
`assistant`, `tool_call`, and `tool_result`. Tool observations are **user-role
messages** in EP-Agent's actual conversation format. The converter preserves
those roles and contents verbatim; it does not convert an observation into an
assistant response. For each explicitly selected assistant step it exports:

```json
{
  "schema": "epagent.sft-example.v1",
  "episode_id": "bound-count",
  "family": "bounds",
  "step": 8,
  "source_trace_sha256": "...",
  "messages": ["the exact context messages, then one assistant target"],
  "message_kinds": ["system_instruction", "user_instruction", "assistant_history", "tool_observation", "assistant_tool_call"]
}
```

The example above shows structure, not an executable row; generated JSONL has
full role/content objects and an aligned kind for every message. A terminal
`finish` call has kind `assistant_finish` and remains an assistant target. There
is no separate free-form final response in the current five-tool protocol.
Terminal grader feedback is never converted into context or targets.

Each row ends at one selected assistant message. All earlier instructions,
assistant actions, and tool observations form its **masked context**. An earlier
assistant turn can be supervised in its own row, not again as part of later
prefixes. Four intentionally failed edit calls are never selected, but their
errors and subsequent recovery are retained. Origin, review selection, hashes,
message-history consistency, and whole-family splits are validated. Phase 1
rejects Hall episodes and external-provider trajectories altogether.

## Actual tokenizer and loss masking

Preparation uses the supplied Qwen chat template through the installed real
MLX-LM tokenizer. It tokenizes the context with `add_generation_prompt=True`
and the full conversation with `False`, then verifies that the former is an
exact token prefix of the latter. A mismatch fails preparation. The target is
the final assistant's content plus its actual end token, 151645 (`<|im_end|>`).
The template newline after that token is excluded. Inference stopping remains
the previously verified union `[151643, 151645]`.

For a token sequence of length `L` and assistant offset `o`, shifted prediction
positions `j` contribute exactly when `o <= j < L`. This includes the first
assistant token and end-of-turn token and excludes every prompt/observation and
padding target. Oversize examples are rejected, never silently truncated. The
real prepared examples are at most 1,425 tokens, below the 2,048 cap.

[MLX-LM's official LoRA guide](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)
documents Qwen2/QLoRA and final-message prompt masking. Inspection of installed
MLX-LM **0.31.3** showed that its default loss uses `position <= length`, while
its batch iterator adds padding beyond the real sequence. That can supervise
the first padding target. EP-Agent supplies a small custom half-open masked loss
to the native trainer and evaluator; it does not fork or modify MLX-LM. Tests
change prompt and padding logits and confirm that loss stays identical, then
change the first assistant/EOS logits and confirm that loss changes.

## Training implementation and fixed configuration

The model is the existing local
`mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit`, revision
`b3252a2f97102b1fb1571fec2c9b27219a8536be`. Files are hash-verified before use;
loading is local/offline and remote tokenizer code is disabled. The existing
[Apple Silicon dependency constraints](../requirements/epagent-macos-py311.txt)
apply; no new framework or system dependency is needed.

[The registered configuration](../data/epagent-sft-v1/lora-config.json) uses:

- Frozen 4-bit base weights; LoRA on `self_attn.q_proj` and `self_attn.v_proj` in
  the last four blocks (24–27).
- Rank 8, **MLX scale 16 directly** (not an assertion that another library's
  `alpha` convention is identical), dropout 0, gradient checkpointing enabled.
- Batch size 1, sequence cap 2,048, Adam learning rate 0.0001, seed 0.
- 40 updates, train-loss reports every 5, validation and saves every 20;
  full validation set each time. No automatic restart or resume.

Read-only inspection of the actual quantized model successfully attached those
layers in memory: **155,648 trainable parameters**, all adapter matrices. No
optimizer was constructed by that inspection and no checkpoint was written.
Initialization allocated a measured peak **872,180,852 MLX bytes**; this is not
a measurement of training memory. Model weights on disk remain unchanged.

The implementation reuses `mlx_lm.tuner.trainer.train/evaluate`, native LoRA
conversion, and native checkpoint saving. It freezes all base weights and
checks that only `lora_a`/`lora_b` remain trainable. MLX and NumPy seeds are fixed;
versions, model/dataset/template/config/protocol hashes, and source hashes are
recorded. Bitwise equality across hardware/library versions is not promised.

Output includes compatible `adapter_config.json`, final `adapters.safetensors`,
numbered checkpoints at updates 20 and 40, `metrics.jsonl`, and `run.json` with
status, timing, memory, and checkpoint hashes. Failed/interrupted training keeps
its report and existing checkpoints. These are **adapter-weight checkpoints**,
not saved optimizer state; exact interrupted-run resumption is not implemented.
The trainer reports validation before update 1 and at its configured boundaries;
a final evaluation explicitly runs after update 40. The final checkpoint is
preselected, not chosen by held-out probe performance. Train loss averages
per-example means at batch size 1; validation aggregates supervised-token loss.

## Commands: preparation is safe to run now; training is not yet authorized

Install the optional dependencies in the existing private venv if needed:

```bash
.venv/bin/python -m pip install -c requirements/epagent-macos-py311.txt '.[agent]'
```

Prepare into a **new** directory (the reviewed local preparation already exists
at `sft-runs/reviewed-prepared`):

```bash
PYTHONPATH=src .venv/bin/python -m epagent.sft prepare \
  --trajectories data/epagent-sft-v1/trajectories \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --config data/epagent-sft-v1/lora-config.json \
  --protocol data/epagent-sft-v1/eval-protocol.json \
  --out sft-runs/reviewed-prepared
```

The exact proposed **training command, not executed**, is:

```bash
PYTHONPATH=src .venv/bin/python -m epagent.sft train \
  --prepared sft-runs/reviewed-prepared \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out sft-runs/tool-use-lora-v1
```

Run that only after independent review, user authorization, and the registered
base-model evaluation. The CLI's explicit `train` subcommand performs updates;
it does not itself enforce a human-approval or baseline-collection gate.
Prepared files and all training outputs are Git-ignored. The committed
[preparation/compatibility evidence](../artifacts/epagent-sft-v1/) contains no
trained weights or fabricated loss history.

**Planning estimate, not a training benchmark:** allow roughly **3–8 GB** of
training working memory and **2–20 minutes** for this 40-update run plus full
validation on the M4. The bound is deliberately broad: activation/logit memory,
compilation, checkpointing, and competing unified-memory use are unmeasured.
The 0.872 GB initialization measurement is a lower bound, not an assurance that
training fits. There is no hard memory cap. The first authorized training run
must report actual loss, memory, runtime, and any failure without retries.

## Registered baseline evaluation

The [protocol](../data/epagent-sft-v1/eval-protocol.json) and
[four held-out fixtures](../data/epagent-sft-v1/eval-fixtures.json) are fixed
before any weight update. First evaluate the unadapted base, then the final
40-update adapter, one attempt per case per arm, seed 0, temperature 0, and the
unchanged EP-Agent inference/tool budgets. No selection on these results.

Each fresh workspace starts with a real source-read observation and a supplied
exact-match edit failure. These are explicitly labelled setup interventions,
not actions attributed to the model. The model then has 12 turns. The primary
metric is recovery within four model turns: a successful source edit using
nonempty `old_text` copied from a prior real source observation and producing a
file change. A reread is welcome but is not required if the observed file is
unchanged. This avoids penalizing a valid immediate correction.

Report the primary result out of all four registered cases, plus schema
acceptance, repeated failed edits, reads before edits, relevant test execution,
test outcomes, and supported finishing claims. Visible tests must remain
unchanged. Report infrastructure failures and timeouts separately, preserve all
attempts, and do not silently replace or remove them from the registered count.
A tool-operation success is separate from functional correctness.

This milestone **defines the protocol and checks its setup, but does not collect
baseline/model results or add a synthetic-task evaluation runner**. The baseline
must be collected under a separately authorized execution step before training.
The existing Hall tasks remain a separately authorized downstream check; no
Hall score is evidence of generalization from these tool-use demonstrations.

## Verification and limitations

```bash
EPAGENT_TEST_MLX=1 PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v
```

MLX-enabled tests use the actual local tokenizer and numerical loss, but all
optimizer/trainer calls in orchestration tests are mocked. Standard CI can run
without MLX and skips those explicitly labelled checks. No test performs a
training update. Tests cover split integrity, trace provenance, exclusion of
failed-edit targets, role preservation, exact EOS/prefix masking, padding
boundaries, config constraints, prepared-data tampering, checkpoint wiring,
and all four frozen failure setups. The full model backward/optimizer path
remains unexecuted until the first authorized training run.

The completed local verification passed **146 tests with no skips** (the prior
138 plus eight SFT tests), including the real-tokenizer and numerical masking
checks. A fresh wheel passed outside-checkout CLI checks; preparation through
the installed MLX environment produced byte-identical data and metadata.
All eight scripted demonstrations rebuilt byte-for-byte. See the
[verification record](../artifacts/epagent-sft-v1/README.md) for commands,
logs, compatibility results, and protected-artifact checks.

Only **1,624 supervised training tokens** support 155,648 adapter parameters.
Overfitting and weak coverage are major risks; 76 prefix examples are not 76
independent tasks. The validation families differ, but the tool grammar and
simple Python idioms overlap heavily. Runtime use of tools with synthetic
recovery prompts may not transfer to long autonomous investigations. Cases are
inspectable source, not secret; no assertion about base-model pretraining
contamination is possible. A smaller validation loss alone will not establish
recovery, truthful diagnostics, scientific reasoning, or generalization. No
training or evaluation result is claimed in this implementation milestone.
The 40-update run samples less than one full pass through the 57 training rows;
it is a small first training check, with no promised behavioral improvement.
