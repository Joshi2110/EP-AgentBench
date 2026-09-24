# EP-Agent SFT: amended protocol and integration, not trained

The focused corrections to the SFT audit at `2a3b6c65f4987e2032d9d58a45702d1033ed4897`
are ready for targeted independent review. No baseline or adapted-model evaluation,
backward training, or new real-model episode has been run. The second authorized
Hall smoke episode already occurred: 12 accepted calls, two reads, ten rejected
edits, no source changes, reward zero, and unchanged-starter 3/13. It was not repeated.

The audited assistant-only loss and LoRA design are unchanged. Hall tasks,
verifiers, references, historical experiments, original smoke artifacts, the
publication snapshot, and the original SFT v1 data/evidence remain unchanged.

## Revised demonstrations and provenance

[Dataset v2](../data/epagent-sft-v2/README.md) contains 11 newly authored/scripted
synthetic episodes: eight training and three validation workspaces. They yield
**72 training examples / 1,980 supervised tokens** and **28 validation examples /
822 supervised tokens**, using the actual local Qwen tokenizer. Longest sequences
are 1,430 and 1,447 tokens. No sequence is truncated.

Eight episodes retain successful edits, relevant checks, recovery, and supported
finish claims. Three add accurate failure endings: a failed check with no repair,
a rejected edit left unresolved, and an accepted partial repair whose rerun still
fails. The five rejected edit actions are context only, never positive targets.
The four evaluation fixtures retain their original bytes and remain excluded
from both training and validation.

Actual scripted episode lengths are 7, 9, or 11 turns; declared budgets vary from
10 to 15. Each observation uses `steps_remaining = budget - executed_turns`, as
in the runtime. Finish targets have **3, 4, 5, or 6** turns remaining; values
4–6 also occur before non-finish actions. Completion is no longer perfectly
identified by `steps_remaining == 1`. This small, patterned corpus does not
establish statistical independence between all contextual features and actions.

Fixtures, traces, review selections and hashes are inspectable. Tool outputs are
executed, not invented. The builder removes elapsed time and normalizes temporary
workspace prefixes in stdout/stderr to `<workspace>/`; it preserves exception
types, messages, source lines, test outcomes and all other observation content.
Independent human review remains pending. No proprietary-model trajectories,
Hall solutions or reserved verifier cases were imported. The prior dataset and
its evidence remain under `data/epagent-sft-v1` and `artifacts/epagent-sft-v1`;
use their original commit to reproduce the original builder.

## Roles, tokenization, and the audited loss

One JSONL row contains an episode/step identifier, source trace hash, exact
conversation prefix, one selected assistant target, and aligned `message_kinds`.
System/user instructions, prior assistant actions, tool observations, tool calls,
and terminal `finish` calls remain distinguishable. EP-Agent's observations are
user-role JSON envelopes; they are not relabelled as assistant messages.

Preparation uses the actual chat template, verifies that the generation prefix
is an exact prefix of the full tokenization, and supervises only final assistant
content plus EOS 151645. The inference stop union remains `[151643, 151645]`.
For target token position `j`, assistant offset `o`, and sequence length `L`, the
unchanged loss uses `o <= j < L`. Instructions, observations, earlier assistant
history, padding and the post-EOS template newline contribute no loss.

## Adapter selection and reproducibility

`epagent run ... --adapter-dir DIR` and `epagent synthetic ... --adapter-dir DIR`
pass selection through CLI, `Config`, the worker, `MLXBackend`, and
`mlx_lm.load(adapter_path=...)`. Omitting the flag selects the base model.

Both `model_ready` and the final report identify the base model/revision and
record `adapter.requested`, `adapter.loaded`, canonical path, configuration,
configuration/weight SHA-256 hashes, and a content-derived adapter ID. An adapter
requested but failing to load remains distinguishable from a base episode.
Selection hashes are checked across worker loading; all configured LoRA matrices
must be present and match the selected file. This also catches silently ignored
or incomplete weight files under MLX-LM's `strict=False` adapter loader. A suite
rejects changed model/adapter selection between cases.

Tests use an untrained one-layer, eight-hidden-unit surrogate and two distinct
constant adapter files through the real MLX-LM loading path. They perform **no
forward pass, response generation, or optimizer update**. This verifies loading
and provenance, not learned behavior of the real Qwen model.

Training remains the existing pinned Qwen 1.5B 4-bit base, rank-8 query/value
LoRA on the last four layers, 155,648 trainable parameters, batch size one,
2,048-token cap, Adam learning rate 0.0001 and 40 updates. The NumPy iterator RNG
is now seeded immediately before entering the native trainer, after model and
optimizer construction. A regression consumes RNG during mocked loading and
checks the first draw at trainer entry. MLX initialization still receives its seed.

The effective sample-equivalent passes are **40 × 1 / 72 = 0.555556**. This is
reported in preparation and run manifests; duration was not increased. Native
validation can consume RNG too, so reproducibility also requires the recorded
library versions and validation schedule. Adapter-weight checkpoints, losses,
hashes and failure reports follow the audited pipeline. Checkpoints do not
include optimizer state for exact interrupted-run resumption.

## Protocol amendment: tool-recovery-v2

The [protocol](../data/epagent-sft-v2/eval-protocol.json) was amended on
**2026-09-23**, before any outcomes were collected. It records its predecessor's
hash and the reason: injected `new_text` is intentionally equal to current file
bytes, so an accepted recovery edit can be a no-op. Requiring byte changes would
conflate tool recovery and repair.

Each fresh workspace receives its task instruction and two explicitly labelled
setup interventions: a real source read, then the registered rejected edit and
actual error observation. The runner checks that setup leaves bytes unchanged.
Neither setup turn counts as model-generated; the model then has 12 turns and
300 seconds including model loading, with the same generation/tool limits in
both arms. Initial/final workspaces, diff, conversation, responses, observations,
usage, status and reports are preserved by the existing loop. There are no retries.

The scorer distinguishes:

- **A — Reinspection:** a successful, untruncated model-generated source read
  after the injected failure. The setup read does not count.
- **B — Accepted correction:** after A, an accepted edit to that source with
  nonempty `old_text` appearing exactly once in the observed content.
- **C — Byte change:** a qualifying B edit actually changes source bytes.
  C can be false when B is true; final workspace differences are also reported.

**Primary endpoint: B within four model-generated turns, divided by all four
registered cases.** Reading alone fails. A later B is recorded but misses the
primary window. Event IDs identify the first A/B/C. This is an observable
copy/match criterion, not proof of the model's internal reasoning.

Secondary reporting includes schema acceptance, repeated identical rejected
edits, recognized checks after edits, finish evidence, and infrastructure/backend
failures/timeouts. The mechanical claim rubric recognizes literal fixture-test
`runpy.run_path` calls through AST inspection. A supported PASS requires the
registered marker from a completed recognized run, unchanged test bytes, and no
subsequent source/test mutation. Failed checks/edits can support honest failure
reports; incomplete or unrecognized prose is classified separately.

This narrow rubric does not understand all valid Python invocation styles or
all natural language. Agent-controlled output can be misleading, so observed
PASS support is **not independent functional verification**. Raw evidence remains
available for manual review. Synthetic episodes receive no Hall reward and never
call the Hall graders. Independent Hall physics success remains separate.

## Proposed commands: do not execute model runs before approval

The reviewed preparation already exists at `sft-runs/reviewed-prepared-v2`.
For reproduction, select a new output directory:

```bash
PYTHONPATH=src .venv/bin/python -m epagent.sft prepare \
  --trajectories data/epagent-sft-v2/trajectories \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --config data/epagent-sft-v2/lora-config.json \
  --protocol data/epagent-sft-v2/eval-protocol.json \
  --out sft-runs/reviewed-prepared-v2
```

After targeted review and explicit authorization, the proposed order is baseline,
SFT, then the adapted arm. **None of these three commands has been executed.**

```bash
.venv/bin/epagent synthetic --arm base \
  --fixtures data/epagent-sft-v2/eval-fixtures.json \
  --protocol data/epagent-sft-v2/eval-protocol.json \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out attempts/tool-recovery-v2-base

PYTHONPATH=src .venv/bin/python -m epagent.sft train \
  --prepared sft-runs/reviewed-prepared-v2 \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out sft-runs/tool-use-lora-v2

.venv/bin/epagent synthetic --arm adapted \
  --fixtures data/epagent-sft-v2/eval-fixtures.json \
  --protocol data/epagent-sft-v2/eval-protocol.json \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --adapter-dir sft-runs/tool-use-lora-v2 \
  --out attempts/tool-recovery-v2-adapted
```

Inspect `suite.json` and each case's linked report/trajectory. Exit zero means
all cases were mechanically scorable, not that recovery or repair succeeded.
A suite output directory must be new. Failed/partial attempts are retained and
remain in the four-case denominator. Operator review enforces baseline-before-
training; the CLI does not implement an authorization gate or campaign scheduler.

## Verification and limits

See [the verification record](../artifacts/epagent-sft-v2/README.md) for actual
commands, test logs, native surrogate checks, installed-wheel checks, reference
grades, dataset hashes and preservation checks. All runner trajectories used
for infrastructure tests are scripted, never real-model baseline evidence.
The full real-model backward path remains unexecuted.

The earlier planning estimates remain unmeasured: roughly 3–8 GB and 2–20 minutes
for 40 updates plus validation. The earlier 872 MB initialization measurement
was not training memory. No memory cap or successful training result is claimed.
A corpus with 1,980 training tokens and 155,648 trainable parameters has severe
overfitting risk. Repeated prefixes are not independent tasks; four held-out
probes cannot establish generalization. The inspectable cases are not secret.
The local process/confinement boundary is not a secure isolation guarantee.
