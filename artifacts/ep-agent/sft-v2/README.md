# SFT v2: preserved negative result

**SFT v2 did not improve recovery: base 0/4, adapted 0/4. The adapted model avoided editing altogether.** Lower validation loss (0.351335 → 0.191719) is not evidence of improved interactive behavior. Exactly 40 updates completed. No code changed, tests ran, or final summaries appeared in either arm.

The [original frozen report](sft-runs/controlled-v2-experiment/report.md), [machine-readable result](sft-runs/controlled-v2-experiment/result.json), [training measurements](sft-runs/tool-use-lora-v2/metrics.jsonl), and [new evidence diagnosis](diagnosis.json) serve different purposes. The original report has not been rewritten; its statement that artifacts were uncommitted describes the time of that analysis. This archive was subsequently authorized.

## Intentional private artifact policy

This directory belongs to the private research repository, not the separate publication snapshot or Python package. The explicit allowlist is implemented in `scripts/archive_sft_v2.py`: both suite reports; each attempt's complete trajectory, conversation, report, diff, initial workspace and final workspace; the frozen analysis/result; execution command records; software/model/dataset metadata; training metrics and configuration; cleanup/preservation attestations.

All 132 files in the original raw inventory were verified before and after archiving. All model files and three adapter checkpoints were hash-verified separately. The 97 archived files and their original/archived SHA-256 pairs are in [archive-manifest.json](archive-manifest.json). Only the absolute repository prefix was replaced with `<REPOSITORY>`. No token IDs, prompts, assistant responses, tool observations, event ordering, measured results or numeric metadata changed. Original raw bytes remain in ignored `attempts/` and `sft-runs/` directories. Initial/final source and empty diffs are byte-identical.

Excluded: all safetensors/weights, tokenizer payloads, credentials/authentication files, temporary control directories/canaries, environment dumps and unrelated machine state. Absolute private paths are rejected by the archiver. This is a curated allowlist, not a recursive dump of the experiment directory. Preserve raw artifacts and adapters in private local storage/backups independently of Git; a Git clone alone does not recover the trained adapter.

## Adapter retention and loading

The actual adapter remains at `sft-runs/tool-use-lora-v2/`, alongside its training report and both intermediate/final numbered checkpoints. Keep `adapters.safetensors` and `adapter_config.json` together. Hashes:

| File | SHA-256 |
| --- | --- |
| adapters.safetensors (also 0000040_adapters.safetensors) | cbec8646e75885f48b30a06be8a5d65475fd13d838daeaab673e38fbd99086f7 |
| 0000020_adapters.safetensors | 03296c3a66c1917343e941425639024ccac3a2fb06460119abe9dcd5dbc5f657 |
| adapter_config.json | 134bdad3e25e685963ee6bf1a660228981515b53d6bcf7d54efbdea7947de12e |

Recorded adapter identity: `25e1b0e9a96408fc8091f417c727f96adddce2119148dffe02432ca8307735ac`. It loaded in all four adapted attempts; none of the base attempts loaded an adapter. Base revision, model hashes and exact software versions are in the archived `run.json` and `preflight.json`.

For a future **separately authorized** load, use MLX-LM 0.31.3 with the pinned local base model:

```python
from mlx_lm import load
model, tokenizer = load(
    '.epagent-models/qwen2.5-coder-1.5b-4bit',
    adapter_path='sft-runs/tool-use-lora-v2',
    tokenizer_config={'trust_remote_code': False},
)
```

Verify the file hashes above before loading. This loading example was not executed during v3 preparation. Do not merge this adapter into the base or initialize v3 from it.

## Evidence diagnosis

| Selected training target | Examples | Assistant tokens |
| --- | ---: | ---: |
| list_files | 8 | 104 |
| read_file | 36 | 701 |
| edit_file | 6 | 408 |
| run_python | 14 | 516 |
| finish | 8 | 251 |

The 72 training examples have 1,980 assistant tokens. Validation has 28 examples: 13 reads, 3 edits, 6 runs, 3 listings and 3 finishes (822 tokens). Each row retains its entire dialogue prefix, but only its final assistant content and EOS receive loss. The native training objective averages supervised-token loss within each sampled example: target counts and token counts are both relevant and are not interchangeable.

Training contains 10 adjacent read→edit transitions, including four rejected context-only edits and six accepted edits. Only three accepted edits immediately follow a **source** read; the other three follow a repeated test-file read, with exact source present earlier in context. All six positive edits use exact previously observed source. There are three successful error→source-read→accepted-edit recoveries, one unresolved error→read→finish, and 16 read→read transitions. Excluded failed calls remain in history; transition counts do not collapse across them.

Base trajectories contain 24 source-read→edit transitions, all rejected. Each old_text repeats the injected two-space indentation despite the actual four-space source being available untruncated, both at setup and immediately before each edit. All 24 edits are syntactically valid JSON and schema-valid. Every base fixture repeats its identical error six times; its six source observations are identical.

Adapted trajectories contain no read→edit transition: all 48 actions are reads, with 44 adjacent read→read transitions and identical source observations within each fixture. Across both arms, all 96 responses are valid JSON and schema-valid. Format/schema failure does not explain this outcome.

Forty batch-size-one updates over 72 examples equal 0.556 passes; no complete pass occurred. The recorded run processed 1,127 assistant targets at the token level, but did not log example IDs per update. We cannot say which specific recovery examples were sampled. The data's narrow skeleton, inspection-heavy target distribution and limited exposure are plausible contributing factors, **not established causes**. Teacher-forced validation improvement does not demonstrate closed-loop recovery. More training could also reinforce an undesirable policy.

The v3 plan changes data and exposure together. It is a focused next pilot, not a causal ablation of these explanations. The four observed v2 cases are now development-only.
