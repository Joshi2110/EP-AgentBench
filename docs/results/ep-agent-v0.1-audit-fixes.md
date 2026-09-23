# Focused corrections after the EP-Agent v0.1 audit

Base audited commit: `360f1914ddb7dda54fd4a6fa600d7ada7a5ce025`.
These changes repair the tool protocol and preserve evidence. No model episode,
model inference, training, or new scientific evaluation was performed. Hall task
files, verifiers, references, Experiment 02, and the publication snapshot were
not changed.

## Corrections

`parse_call` now accepts bare JSON or a single complete Markdown block with an
optional lowercase `json` label. Opening and closing fences must occupy their
own lines; surrounding whitespace is allowed. It unwraps that one envelope and
parses its entire contents. There is no regex extraction or search for a JSON
substring. Outside text, multiple/incomplete blocks, other fence labels,
malformed JSON, duplicate keys, non-finite constants, and invalid tool schemas
are rejected. Paths and tool execution retain the original confinement checks.

Parser feedback now distinguishes `invalid_wrapper`, `json_syntax`,
`invalid_tool`, `missing_arguments`, and `schema_violation`. Each message gives
the actual problem and a short reminder of the accepted format. Syntax messages
include line/column; missing-argument messages name required fields. Feedback
contains no grader or reference data. Tool execution errors remain separate.

The system prompt lists tool names, field names, and semantics, without sample
replacement strings or toy diagnostic code. It tells the policy to copy
`old_text` from a file it has observed and to choose actions from observations.
It includes no Hall-specific correction or solution. No worked example is
needed for this minimal schema. This removes known copying triggers; it does
not establish that a future model will follow the prompt.

## Replay: syntax is separate from schema and execution

The original strings contain both Markdown fences and trailing chat-control
tokens from the old stopping bug. The parser correctly rejects those trailing
tokens as outside text. The offline audit uses the **real tokenizer** to decode
the recorded token prefix before the first configured stop ID, then tests the
fence-aware parser. It does not edit the raw strings, regenerate responses, or
execute proposed tools.

| Input/processing | Valid JSON after stated processing | Valid tool schema |
| --- | ---: | ---: |
| Original recorded response, without changes | 0/12 | 0/12 |
| Corrected stop rule only; fences still passed to plain JSON parser | 0/12 | 0/12 |
| Corrected stop rule plus permitted fence unwrapping | 12/12 | 12/12 |

All 12 resulting JSON objects pass the tool schema. That is not evidence that
their arguments are scientifically useful or that the tools would succeed:

- Turns **3, 5, 7, 9, 11** copy `old_text: "exact existing text"` and
  `new_text: "replacement"`. Schema-valid strings do not supply a valid edit.
- Turns **4, 6, 8, 10, 12** copy `code: "print(2 + 2)"`. This is a toy calculation,
  not a Hall diagnostic.
- Turns **1 and 2** propose listing files and reading `README.md`.

Per-turn texts, acceptance fields, copied arguments, tokenizer evidence, and
original measurements are in
[replay-tokenizer.json](../../artifacts/ep-agent/audit-v0.1-fixes/replay-tokenizer.json).
The replay script explicitly reports unavailable tokenizer evidence as
unverified; it does not substitute mock values.

## Real tokenizer verification

Local model: `mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit`, revision
`b3252a2f97102b1fb1571fec2c9b27219a8536be`.
The offline check verified the downloaded tokenizer/configuration file hashes,
loaded the real MLX-LM tokenizer, encoded its EOS token, and rendered a two-message
chat using the actual template. No weights were loaded and no tokens generated.

- Model configuration EOS: **151643**, `<|endoftext|>`.
- Tokenizer EOS / rendered assistant end-of-turn: **151645**, `<|im_end|>`.
- Actual rendered assistant suffix: `<|im_end|>\n`.
- Configured termination IDs: **[151643, 151645]**.
- Chat template SHA-256:
  `89d726e7795b101935db5c909c75a7d403a47deedad53a64947e9b079ba94def`.

The existing stop-token union is correct against this tokenizer; no further
stopping-rule change was necessary. Future `model_ready` events and final
`model.stop_token_ids` record the configured IDs. A protocol regression checks
that readiness metadata reaches the trace callback and backend metadata. That
mock event test is distinct from the executed real-tokenizer check above.

## Evidence preservation

The [private artifact policy](../../artifacts/ep-agent/README.md) allowlists a
byte-identical archive of the original report, trace, conversation, diff,
initial/final task files, and historical runner source. No control directory,
model download, credential, authentication file, or unrelated machine state is
included. The raw local attempt also remains unchanged. SHA-256 checks cover
all 19 payload files; no sanitization was needed or performed.

The original result remains **12 responses, zero accepted tool calls, zero
edits, reward zero, starter diagnostic 3/13**. Tests compare the report with its
terminal trace event and verify unchanged initial/final file hashes. Neither
this replay nor fake-model success is attributed to the original policy.

## Verification and reproduction

All **138 tests passed** in the checkout (87.142 seconds), and all **138 passed**
again from outside the checkout against the installed wheel (86.290 seconds).
The focused EP-Agent suite passed **23 tests**. Nine explicit outside-checkout
CLI checks passed, including the installed fenced parser and all three Hall
reference grades at 13/13. Wheel inspection confirmed that evidence archives,
attempts, tests, and reference solutions were excluded. A preservation audit
matched all 1,683 protected file hashes and all 19 original episode payloads;
the local real-episode count remains one.

The focused suite covers valid bare/fenced calls, every prohibited wrapper,
schema bypasses, actionable feedback, prompt regression, immutable evidence,
replay counts, unavailable-tokenizer reporting, and stop-ID recording. The fake
model completes read/edit/run/finish/grade/save with a 13/13 repaired fixture.
Assertions show that file listings, read contents, and Python observations
reach the next model request. A recovery test passes syntax feedback to the
next turn, accepts a fenced read, rejects a fenced path escape, and leaves an
unchanged submission at reward zero / starter 3/13. Existing backend-failure,
timeout, confinement, and reward-attribution regressions remain in place.

Commands for independent re-audit:

```bash
.venv/bin/python -m pip install --no-build-isolation --no-deps --force-reinstall .
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python scripts/audit_epagent.py \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out /tmp/epagent-audit.json
```

The second command requires permission to launch the existing macOS development
profile for live confinement checks. It does not launch a real coding agent.
The third command requires the pinned tokenizer files and MLX-LM; it neither
downloads files nor performs inference. Omit `--model-dir` to verify archive/raw
counts while explicitly reporting the tokenizer as unverified (exit 2).

Validation logs and exact outside-checkout CLI invocations are committed under
[the audit evidence directory](../../artifacts/ep-agent/audit-v0.1-fixes/).
Execution remains constrained macOS development mode, not production-grade
isolation. Actual scientific repair by the corrected real policy remains
unverified; parser acceptance is not a repair result. No SFT/RL was started.
