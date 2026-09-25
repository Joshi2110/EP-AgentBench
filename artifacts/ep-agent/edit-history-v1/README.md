# Edit-history diagnostic: preserved negative result

All eight responses failed exact target equality (0/8). Four calls passed the
schema; three executed and changed bytes, but none produced the prescribed file.
This is a tool-use diagnostic, not scientific repair evidence.

History-present prompts also contained a concrete object-shaped tool-call example;
history-absent prompts did not. The experiment did **not** isolate the causal
effect of misleading history. Formatting assistance and misleading content were
bundled. No causal interface ranking follows from these eight responses.

The archive contains the registered schedule, prompts, complete responses and
traces, tool results, final source bytes, analysis, commands, software metadata,
and historical runtime source. `archive-manifest.json` records both raw and
archived SHA-256 hashes. Only repository path prefixes in metadata are sanitized.
Prompts, generated responses and workspace bytes are unchanged. The original raw
files remain at `attempts/edit-history-v1` and `sft-runs/edit-history-v1-control`.
The private machine-path preservation inventory is excluded.

The frozen v3 adapter remains locally at `sft-runs/tool-use-lora-v3`; its final
weight SHA-256 is
`4f0f3dde55d6486313f860eaf1f6fcdb2d1f1373b481553e8302cacdb6bc42ff`.
No weights are committed. Model and adapter identities are recorded in the
manifest and model-ready trace events. No rerun or rescore was performed to
create this archive. The historical diagnostic tool is not the production tool.
