# 3B workflow SFT pivot plan

Prepared configuration, **not an executable experiment registration**. No model
weights downloaded, training, evaluation or new memory probe performed.
The shorter-context 7B preflight was blocked by pressure, not a measured model
OOM. Further 7B memory optimization stops here.

1. Use original `mlx-community/Qwen2.5-Coder-3B-Instruct-4bit`, revision
   `3dd939c621c08e5753d5b89f35a2642cd83b98ca`, in a separate local directory.
   Pin and hash every downloaded model/tokenizer file before any execution.
   The [pinned upstream config](https://huggingface.co/mlx-community/Qwen2.5-Coder-3B-Instruct-4bit/blob/3dd939c621c08e5753d5b89f35a2642cd83b98ca/config.json)
   specifies Qwen2, 36 blocks, width 2048, 16 query heads, 2 KV heads and tied
   embeddings. Compatibility and memory fit still require local verification.
2. Reuse the archived selected messages: 12 training episodes/62 targets and
   2 validation episodes/8 targets. Retokenize using the actual 3B chat template;
   do not reuse 7B token arrays by assumption. Check target equality, all retained
   observations and supervision boundaries. Reject overflow at 1024 tokens;
   do not truncate. Derive stop IDs from the tokenizer, not family assumptions.
3. Use `lora-config.json`: original base, no prior adapter; final four blocks
   **32–35**, Q/V only, rank 8, scale 16, dropout 0; batch 1, checkpointing,
   seed 0, learning rate 1e-4, 1024 ceiling, **124 updates / two complete passes**.
   Expected trainable count: 4 × 8 × ((2048+2048)+(2048+256)) = 204,800.
   Report every 4 updates; validation/checkpoint after 62 and 124, all validation
   targets. Preserve actual model, dataset, software and checkpoint identities.
4. Before execution, add separately reviewed 3B compatibility support: current
   model allowlist does not admit 3B. Preserve the frozen Evaluation 02 runtime
   and hashes; use a separate entry point or snapshot rather than changing its
   registered files. Verify the tokenizer, trainable parameter set, finite tiny
   surrogate gradients and assistant-only loss offline.
5. Request authorization for a separate 3B memory gate: normal system pressure,
   one longest-example forward/backward, 7 GiB ceiling, 6.5 GiB peak acceptance,
   300-second deadline, zero optimizer updates, pressure abort and resource logs.
   Do not assert feasibility from model size alone. Training needs subsequent
   explicit authorization and a frozen 3B registration.

Evaluation 02 remains unchanged and no baseline outputs are collected. This
3B adapter must never be supplied to its registered 7B adapted arm. Any later
base/adapted comparison needs a separately named, frozen 3B protocol. Previously
inspected evaluation cases remain development evidence, not newly held-out data.
