# EP-Agent v0.1: one local-model smoke episode

The local MLX policy ran and its final workspace reached the independent grader,
but it did not successfully use a tool. This is a failed interaction smoke test,
not a demonstrated scientific repair. There was exactly one real episode, with
no retry. Fake-model tests separately verified the complete repair workflow.

## Observed result

| Field | Observed value |
| --- | --- |
| Episode | `cc94d8972f2641ebb4f971d91fa21d57` |
| Task / benchmark | `hall-thrust` / EP-AgentBench 0.5.0 |
| Baseline private commit | `cc64669` |
| Start / end UTC | 2026-09-23 19:10:02.087782 / 19:10:21.263180 |
| Backend | MLX-LM 0.31.3, MLX 0.32.2, Transformers 5.17.0 |
| Model | `mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit` |
| Model revision | `b3252a2f97102b1fb1571fec2c9b27219a8536be` |
| Termination | `unfinished`, `step_limit`; CLI exit 1 |
| Responses / accepted tool calls | 12 / 0 |
| Final raw verifier score | 3/13; binary terminal reward 0 |
| Files modified | None; initial and final hashes match |
| Agent / grading / total wall time | 18.532 / 0.608 / 19.175 seconds |
| Prompt / generated tokens | 9,116 / 402; prompt total includes repeated history |
| Peak MLX allocated memory | 1,649,016,392 bytes (1.65 GB decimal) |
| Peak process RSS | 926,826,496 bytes (0.927 GB decimal) |

MLX and RSS are different, overlapping measurements; do not add them. These
measurements include model loading and all 12 completed generations. Token
log-probabilities were available from the backend but not saved by this adapter;
there is no inferred log-probability or cost figure.

The policy's first response proposed `list_files` inside a Markdown JSON fence.
The next proposed reading `README.md`, also fenced. Both were rejected by the
strict JSON-only protocol. Subsequent responses repeated illustrative
`edit_file`/`run_python` calls from the system prompt, including placeholder text
and `print(2 + 2)`, rather than recovering from the recorded parse errors. No
workspace file was read by the policy, no generated Python executed, and no
scientific diagnostic was observed. All 12 responses were malformed for this
protocol; there were no accepted `finish` calls.

The three passing cases were the untouched starter's two Bohm-speed cases and
its source-free limit. **The 3/13 raw grade is a starter diagnostic, not evidence
that the policy solved three scientific cases.** No defect was corrected. The
momentum-source defect remains. There was no observed attempt to access reserved
materials, bypass the grader, or hardcode expected results; no proposed call
passed parsing.

## Integration issue discovered and corrected after the episode

The pinned conversion's `config.json` declares end token 151643
(`<|endoftext|>`), while its chat tokenizer declares token 151645 (`<|im_end|>`).
MLX-LM used the model-config stop set, so responses included literal chat
terminators, and sometimes the beginning of another turn, before stopping at
151643. The trace records those actual token IDs and text.

The final implementation adds the tokenizer's chat end token to the stop set,
retaining both IDs. The regression test checks this union, and an offline check
against the downloaded tokenizer confirmed `[151643]` becomes
`[151643, 151645]`. This check did not load a policy generation or run a second
episode. The original model files, report, trace, and submitted workspace were
not rewritten. `runner-source/` in the attempt directory preserves the exact
pre-fix agent source, matching the source hashes in that report.

The fenced output was independently invalid even before the extra chat
terminator, so the stop-token mismatch does not explain away all failures. The
observed result combines a model/protocol failure with a now-corrected integration
limitation. It cannot establish the model's scientific capability. Successful
real tool use under the corrected backend remains unverified; a further smoke
episode would need separate authorization. No prompt/parser changes were made
to turn this failed episode into a success.

## Reproduction and evidence

The exact real-episode command was:

```bash
.venv/bin/epagent run hall-thrust \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out attempts/ep-agent --steps 12 --seconds 300 --tool-seconds 8 \
  --context-tokens 8192 --max-tokens 768 --temperature 0 --seed 0
```

Working directory: `/Users/josh/Desktop/EP-Bench/ep-agentbench`.
All artifact paths below are relative to that checkout:

- Report: `attempts/ep-agent/cc94d8972f2641ebb4f971d91fa21d57/report.json`
- Trace: `attempts/ep-agent/cc94d8972f2641ebb4f971d91fa21d57/trajectory.jsonl`
- Conversation: `attempts/ep-agent/cc94d8972f2641ebb4f971d91fa21d57/conversation.json`
- Final files: `attempts/ep-agent/cc94d8972f2641ebb4f971d91fa21d57/workspace/`
- Initial files, empty `changes.diff`, backend stderr, and original runner source
  are alongside them. Backend stderr is empty.

SHA-256 of `report.json`:
`836c8db143fec2a05f55c1252543b8bfb8af229520c65d1c8996963efd1ab132`.
SHA-256 of `trajectory.jsonl`:
`a67fe423864d7f86c6136eac38446ce98689ef73941b464056e7168ad84427d9`.
These local artifacts are intentionally Git-ignored, not published.

Decision provenance is the pinned/hashes-verified local weights, model readiness
metadata, exact prompt token IDs, streamed output token IDs, and corresponding
assistant text in the trace. The inference worker used local `mlx_lm` with
offline settings and no authentication environment. There was no Codex/Claude
agent backend or supplied scientific patch. The accepted tool count of zero
must remain visible alongside this provenance: local generation was demonstrated;
a real-model-authored repair was not.

## Verification and next step

See [the implementation guide](../ep-agent.md) for installation, environment
limits, schema, reward semantics, and test commands. The final automated suite
and packaging checks are recorded in the companion local validation artifacts.
The fake model repairs Hall thrust and obtains 13/13; all three unchanged Hall
references also obtain 13/13 through the restricted grading adapter. These are
test fixtures, not additional model evaluations.

Final verification: **129 tests passed**, including 14 EP-Agent tests, in 52.632
seconds. Eight outside-checkout CLI checks passed against the rebuilt wheel:
agent version/help, benchmark list/export, a missing-model error, and all three
Hall reference grades. Wheel inspection confirmed that agent source matched the
checkout and that no attempts, tests, or reference solutions were bundled.
An earlier full-suite invocation failed 13 CLI setup checks because `.venv/bin`
was absent from `PATH`; correcting the invocation resolved those failures.

The principal executed installation and verification commands were:

```bash
.venv/bin/python -m pip install 'mlx-lm==0.31.3' wheel
.venv/bin/python -m pip install --no-build-isolation --no-deps --force-reinstall .
.venv/bin/epagent download --out .epagent-models/qwen2.5-coder-1.5b-4bit
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip wheel --no-build-isolation --no-deps \
  --wheel-dir /private/tmp/epagent-validation-pxsuneht/wheels .
/private/tmp/epagent-validation-pxsuneht/installed/bin/python -m pip install \
  --no-deps --force-reinstall \
  /private/tmp/epagent-validation-pxsuneht/wheels/ep_agentbench-0.5.0-py3-none-any.whl
```

`attempts/ep-agent-validation/` preserves test/install logs, the exact eight CLI
commands and outputs in `outside-checks-final.json`, the offline tokenizer
check, and the preservation audit. Across 2,180 pre-recorded file hashes, all
protected source and research artifacts matched. The only differing file was
the public snapshot's ignored Finder `.DS_Store` metadata; this implementation
did not edit or restore it. The public Git working tree remained clean. Existing
graders, reference implementations, and Experiment 02 records were unchanged.

Before collecting training data, authorize a separate smoke test of the corrected
chat stopping behavior and assess whether the small model can follow the strict
tool protocol. The smallest SFT preparation is then a converter plus a handful
of reviewed, correctly formatted tool-use examples and a task-family holdout
plan. This failed trajectory is useful as a negative/protocol-error example;
it must not be labeled as a successful repair. No SFT or RL has been run.
