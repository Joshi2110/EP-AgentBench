# SFT v3 preparation — no training or model evaluation performed

This proposal tests whether more varied, explicitly supervised recovery continuations improve tool behavior. SFT v2 had 0/4 recovery in both arms; its adapted model never attempted an edit. See the preserved [v2 diagnosis](../../artifacts/ep-agent/sft-v2/README.md).

No agent, tool schema, trainer/loss implementation, physics task, grader or reference solution changed. `scripts/build_sft_v3.py` executes inspectable, project-authored action plans in [fixtures.json](fixtures.json), using the existing real tools. These are scripted demonstrations, not model successes. No provider trajectories or Hall material are used as targets. Internal checks and content review are complete; independent maintainer review remains pending.

## Data and supervision

| Split | Episodes | Selected assistant targets | Assistant tokens | Maximum templated length |
| --- | ---: | ---: | ---: | ---: |
| Train | 12 | 69 | 2,531 | 1,587 |
| Validation | 4 | 21 | 752 | 1,292 |
| Development | 4 previously observed v2 cases | Never trained | — | — |
| Held-out | 4 newly authored v3 cases | Never trained | — | — |

Training targets: **19 reads, 19 runs, 14 edits, 12 finishes, 5 listings**. Read targets fall from 50% to 27.5%; accepted edit targets rise from 8.3% to 20.3%. No row is duplicated for balancing. Repetitive setup inspections are context-only; failed edits are also context-only. Every selected recovery action receives the real preceding error/source observation in its full conversation. Actual action order is retained; excluded steps are not collapsed. System/user/assistant/tool-observation distinctions and the audited final-assistant-only mask are unchanged.

The 16 episodes use distinct functions, source paths and requirements. Seven plan styles range from 5 to 11 actual turns: direct repair, discovery, exact-match recovery, diagnostic-first recovery, a second rejected correction, partial repair followed by failed-test inspection and another repair, and honest incomplete termination. Failures include whitespace, quotes, a missing comment, a newline mismatch and an ambiguous repeated span. Some positive edits replace one observed line, others a larger contextual block. Two training episodes and one validation episode recover after a second exact-match failure. Two training episodes make a useful partial edit, observe a remaining test failure, then correct it. One episode per split finishes honestly with a still-failing test.

Every positive edit uses a nonempty uniquely matching span from a real source read and changes bytes. Every accepted edit is followed by a relevant test. Success finishes cite actual `PASS <id>` output; incomplete finishes cite actual failure. Assertions in the builder check observations and final file contents. Full review records and selected/context-only step IDs are in `trajectories/reviews.json`; action sequences and target counts are in `trajectories/coverage.json`.

## Frozen proposal and exposure budget

[training-freeze.json](training-freeze.json) pins the data, implementation and configuration **before** the new held-out cases were authored. [eval-protocol.json](eval-protocol.json) links that hash and records the later authoring time. This is a reviewable local ordering record, not an external timestamp attestation. If review changes training choices after inspecting held-out outcomes, those cases become development data and new held-out cases are required.

Propose **two complete passes over 69 examples = 138 updates**, batch size one, seed zero, initialized from the original pinned Qwen2.5-Coder-1.5B 4-bit base. The native sampler visits every row once per permutation; two passes expose each selected continuation twice (5,062 supervised tokens in total). Keep learning rate 1e-4, rank 8, scale 16, Q/V LoRA on layers 24–27, gradient checkpointing and the 2,048-token cap. No truncation occurred. No checkpoint selection by validation or evaluation outcome: use update 138.

Save/evaluation interval is 69. **Native MLX-LM validation runs before the numbered update**, so scheduled observations correspond to completed updates 0, 68 and 137, plus the existing explicit final validation at 138. Checkpoints save after updates 69 and 138. The freeze's shorthand “pass boundaries” refers to this configured interval; do not mislabel actual completed updates. Training reports remain every five updates, with the trainer's final partial interval.

Planning estimate only: v2 used 251 seconds and 3.06 GB peak MLX allocation for 40 updates. Scaling to 138 updates suggests roughly 15 minutes; allow 10–25 minutes and approximately 3–5 GB MLX allocation because sequence lengths and validation workload differ. These are not measured v3 training results; unified-memory usage and RSS are distinct measurements. Sixteen GB memory is not a guarantee against other local workloads.

## Separation and future evaluation

Split by whole workspace/family, not individual turns. The old `data/epagent-sft-v2/eval-fixtures.json` cases are development cases only; they were not copied into any demonstration. New held-out families and file contents are disjoint from train, validation and development. They were authored after the training configuration was frozen, and have no model outputs. Authorship and static/tool-fixture checks necessarily expose them to the benchmark author; they are not secret from source readers. Training preparation reads only demonstrations and protocol metadata, never held-out source files. Do not use held-out model feedback for tuning.

Keep the existing v2-format runner and automatic A/B/C definitions, seed 0, temperature 0, 12 turns/300 seconds and four-turn primary window. The protocol identifier is `tool-recovery-v3`; the schema remains compatible with the unchanged runner. New held-out setup failures vary exact-match failure types. As in v2, injected new_text is a no-op: accepted recovery B is separate from byte change C. Neither alone demonstrates correct code or scientific repair. Check repetition, tests, finishes and unclassified summary wording separately. Future paired base/adapted runs require authorization, one attempt per case per arm, no replacements and no outcome-driven configuration changes. No development runs are scheduled by this proposal.

Keep all Hall tasks as a separate, independently authorized downstream assessment. Four synthetic cases cannot establish statistical significance or scientific generalization. Changing both data and exposure budget prevents a causal attribution of any future difference. Short functions, exact-match edit mechanics, author-chosen plans and a common three-turn remaining-budget finish cue remain overfitting risks; this is a small reviewable pilot, not broad training coverage.

## Smallest implementation and review path

1. Review explicit action plans and retained histories; reproduce scripted observations with `scripts/build_sft_v3.py` into a **new** output directory.
2. Reuse the audited converter and actual pinned tokenizer. Preparation completed locally at `sft-runs/reviewed-prepared-v3`; [preparation-manifest.json](preparation-manifest.json) records all hashes, versions and the template identity.
3. Obtain independent review and separate execution authorization. No trainer, backend, scoring or reward changes are needed.

Preparation command executed (no weight updates):

```bash
PYTHONPATH=src .venv/bin/python -m epagent.sft prepare \
  --trajectories data/epagent-sft-v3/trajectories \
  --config data/epagent-sft-v3/lora-config.json \
  --protocol data/epagent-sft-v3/eval-protocol.json \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out sft-runs/reviewed-prepared-v3
```

Future training command, **not executed or authorized**:

```bash
PYTHONPATH=src .venv/bin/python -m epagent.sft train \
  --prepared sft-runs/reviewed-prepared-v3 \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out sft-runs/tool-use-lora-v3
```

Preserve the original base and v2 adapter. The output directory must be new; do not resume into or overwrite v2 artifacts.
