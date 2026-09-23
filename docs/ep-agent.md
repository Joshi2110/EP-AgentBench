# EP-Agent v0.1

EP-Agent is a local open-weight coding policy connected to five workspace tools
and the existing EP-AgentBench terminal verifier. It adds the `epagent` command;
`epbench`, its task exports, graders, and existing evaluation protocols are
unchanged. There is no SFT or RL implementation in this version.

## Install and run

The tested inference host is Apple M4, 16 GB unified memory, macOS, Python 3.11.
Use a virtual environment, not a system Python installation:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install '.[agent]'
.venv/bin/epagent download --out .epagent-models/qwen2.5-coder-1.5b-4bit
.venv/bin/epagent run hall-thrust \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out attempts/ep-agent \
  --steps 12 --seconds 300 --tool-seconds 8 \
  --context-tokens 8192 --max-tokens 768 --temperature 0 --seed 0
```

For the exact tested Python dependency versions, install with
`--constraint requirements/epagent-macos-py311.txt`. This is a platform-specific
constraints file, not a hash-locked cross-platform environment. The package's
base install does not require MLX. Downloading is an explicit separate command;
`run` loads local files with offline settings. The downloader refuses a model
larger than 2 GB. A partial download is retained on failure, not silently retried.
Use a new destination if deliberately restarting a failed download.

Each `run` starts exactly one fresh UUID directory. Exit status is 0 for a
finished, scored episode (even if reward is zero), 1 for unfinished/unscored
execution, and 2 for invalid configuration. There is no retry or campaign mode.
The same interface accepts `hall-transport` and `hall-ionization`. Each task's
instance ID includes the exact export hash; these are the existing fixed task
instances, not newly generated scientific problems.

The final command prints the JSON report, including absolute artifact paths.
Inspect the files named by `paths.report`, `paths.trace`, `paths.conversation`,
`paths.patch`, and `paths.workspace`. For example:

```bash
.venv/bin/python -m json.tool attempts/ep-agent/EPISODE_ID/report.json
cat attempts/ep-agent/EPISODE_ID/changes.diff
```

Model files and new attempt collections are ignored by Git. The first failed
episode also has a byte-identical, allowlisted archive in the private repository
under [artifacts/ep-agent](../artifacts/ep-agent/README.md). Its raw local directory
remains unchanged. The archive policy excludes weights, credentials, control
directories, and unrelated machine state; it is not permission to commit all
future attempts. The terminal report is not a substitute for the trajectory and
final files.

## Model and decision provenance

The reviewed model is
[`mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit`](https://huggingface.co/mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit),
revision `b3252a2f97102b1fb1571fec2c9b27219a8536be` (Apache-2.0), converted from
[Qwen2.5-Coder-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct).
Its weights occupy 868,628,559 bytes; the complete downloaded files occupy
880,170,581 bytes. It is a 1.54B-parameter Qwen2 model quantized to four bits,
with group size 64. The downloaded manifest records SHA-256 for every file and
the immutable repository revision; the inference worker verifies those hashes
before loading.

The conversion's model config and chat tokenizer specify different stop tokens.
The backend honors their union, including the tokenizer's end-of-turn token.
This was corrected after the first smoke episode; its original trace is preserved.

[MLX-LM](https://github.com/ml-explore/mlx-lm) runs the policy on Apple Silicon
and has a [LoRA training interface](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)
for a subsequent milestone. This implementation uses its tokenizer's supplied
chat template and `stream_generate`, with remote tokenizer code disabled. The
chat-template hash, library versions, prompt token IDs, generated token IDs,
generated text, sampling configuration, and code hashes are recorded. No
proprietary model or agent CLI is involved in these decisions. The surrounding
environment parses JSON and executes tools; it contains no scientific repair
policy. The deterministic fake model exists only in tests and is clearly
identified in its reports.

## Episode contract and limits

The system prompt describes the scientific coding role and exactly five tools:

| Tool | Arguments | Effect |
| --- | --- | --- |
| `list_files` | none | List task-workspace files |
| `read_file` | `path` | Read a relative UTF-8 file, with output truncation |
| `edit_file` | `path`, `old_text`, `new_text` | Replace exactly one match; empty old text creates a file |
| `run_python` | `code` | Execute standard-library Python and local task modules |
| `finish` | `summary` | End the policy loop and submit the current workspace |

The policy emits one JSON object, `{"tool": ..., "arguments": {...}}`, per
turn. Bare JSON and one complete Markdown code fence (unlabelled or labelled
`json`, with opening/closing fences on their own lines) are accepted. Surrounding
whitespace is allowed. Explanatory text outside the fence, multiple/incomplete
blocks, invalid JSON, duplicate keys, and invalid tool schemas are rejected.
Unwrapping a fence never bypasses tool or workspace validation. Syntax, wrapper,
tool-name, missing-argument, and schema errors have separate feedback categories,
with an explanation of the problem and the accepted format. The prompt lists
field names and semantics without copyable placeholder arguments or toy code.

Tool results become user messages. Malformed calls, unavailable files,
Python errors, and Python timeouts are observations, not hidden retries. They
consume turns. The JSON protocol has no schema-constrained decoder, arbitrary
JSON extraction, or automatic repair of malformed JSON.

Defaults: 12 turns, 300 seconds for model startup and the agent loop, 8 seconds
per Python tool, 8,192 output bytes, 8,192 context tokens, 768 generated tokens
per turn, greedy decoding, seed 0. Token context includes the system prompt,
conversation, chat-template overhead, and the reserved generation budget. The
runner stops rather than silently truncating history. Grading is a separate
terminal phase with the existing five-second limit per case. Preflight/export
also occur outside the policy time budget. Processes are killed and reaped when
their budget expires. A host crash or SIGKILL can leave the initial report marked
`running`; the flushed JSONL prefix remains available and must not be treated as
a completed result.

Additional fixed development limits: Python input 32,768 bytes; workspace 128
entries, 256,000 bytes per file and 2,000,000 bytes total; Python file creation
2,000,000 bytes per file, 64 open descriptors, 20 CPU seconds. Parent wall-time
and output limits are normally tighter. Workspace limits are checked between
tools, not enforced as an aggregate filesystem quota during Python execution.
There is no dependable per-process memory limit in this implementation; hostile
code could exhaust host resources before a wall-time check.

## Execution boundary

This is **constrained macOS development execution, not production-grade secure
isolation**. It requires `/usr/bin/sandbox-exec` and fails closed if its preflight
fails. There is no unrestricted fallback and no Linux execution implementation.
The Python profile starts from deny-all. It allows the workspace, interpreter
and system runtime reads; workspace writes; runtime execution; file metadata;
and system-information reads. Network access, process forking, private file
contents, and private directory enumeration are denied. Paths used by file
tools must be relative and cannot traverse symlinks or hardlinks. Python tools
run with `-I -S -B`, a clean environment, and no credentials, shell, or imported
benchmark package. The verified local Python prefix must not itself contain
private research or credentials because runtime-prefix reads are allowed.

The preflight checks workspace operations, private canary and verifier read
denial, absent `epbench` imports, network denial, and fork denial. Automated tests
also check external writes, private directory enumeration, process launch,
symlinks, output limits, and timeouts. Root directory names, file metadata, OS
runtime files, and system information remain observable. Seatbelt is an
OS-specific, deprecated development interface. It is not a container, VM, or a
claim of resistance to kernel/interpreter vulnerabilities.

The trusted inference process needs MLX/Metal and loads the reviewed model and
EP-Agent implementation outside this Python profile. It only receives recorded
messages and emits text/token events. It does not execute that text. All actions
chosen by the model go through the constrained tools. The parent runner,
installed dependencies, OS, tokenizer template, and model files are trusted.
The clean inference environment excludes host authentication variables; the
runner never records host environment values or credentials. Backend stderr is
preserved privately for debugging. No authentication files are copied.

Submitted Python is also restricted during grading. The adapter scopes the
existing grader's subprocess launcher, copies only its generic submission worker
into a temporary case directory, and applies the same development profile.
Cases and physical checks stay in the parent process and are unchanged. It
rejects a link/special-file `result.json` before the existing parent reader can
follow it. The adapter is synchronous and temporarily substitutes a module
launcher; concurrent grading in the same Python process is unsupported.

The policy process is stopped before grading. It never receives verifier
feedback. Cases remain public source material withheld at runtime; neither
this boundary nor the report establishes that pretraining did not contain them.

## Trajectory and reward schema

Every JSONL event and final report uses `schema: "epagent.episode.v1"`. The trace
has an episode ID, increasing sequence number, UTC timestamp, event name, and
data. Events preserve:

- Initial task/model/configuration and the execution preflight.
- Complete messages for each `model_request`, including the system prompt.
- Backend readiness, actual input token IDs, streaming output tokens/text, and
  completed assistant messages. Partial output survives inference timeouts.
- Parsed tool calls and arguments, observations/errors, and per-tool file diffs,
  including edits made through Python.
- Agent termination followed by terminal reward/grading and the final report.

`conversation.json` is the policy conversation only. `initial/` and `workspace/`
store initial/final files; `changes.diff` is the cumulative text patch, with
initial/final hashes in the report. Raw final files are authoritative for binary
content. The report separates agent `status`/`termination_reason` from
`evaluation_status` (`scored`, `not_scored`, or `grading_failure`). A backend
failure before any completed model response has null reward and is not scored
as an untouched-starter model result. A partially completed/unfinished episode
with a model response can be graded; its termination remains explicit and it
must not be pooled with finished episodes without a stated analysis rule.

Reward is exactly 1 when all verifier cases pass, otherwise 0. A failure to
execute the verifier itself yields null reward and a grading error. Case scores
and diagnostic checks are retained for analysis; correlated cases are not
independent rewards or independent training examples. This physics-only reward
does not certify truthful diagnostic claims, successful use of `finish`, or
general scientific competence.

Token totals cover completed generations and count repeated prompt history on
each request. Streaming records allow partial generations to be analyzed
separately. The adapter records whether MLX exposes token log-probabilities, but
does not currently save them; values are explicitly null and are never inferred.
There is no cost estimate. Peak MLX allocated bytes and process maximum resident
set bytes are measured separately on macOS and must not be added together as if
they were disjoint memory. Both are cumulative high-water marks. Wall-clock
agent, grader, and total durations are recorded independently.

## Tests and next training step

The [first real smoke result](results/ep-agent-v0.1-smoke.md) is preserved as a
failed interaction: 12 malformed responses, zero accepted tools, unchanged
starter. It does not establish successful real-model scientific repair.
The [focused audit corrections](results/ep-agent-v0.1-audit-fixes.md) separately
document fence parsing, prompt changes, the real-tokenizer check, and replay
results. The replay does not change the first episode's outcome.

```bash
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v
```

The EP-Agent tests use only a deterministic fake model. They cover a real
read/edit/run/finish/grade/save sequence, a pristine second export, terminal-only
feedback, malformed actions, missing files, Python failures and timeouts,
backend failures, context exhaustion, unfinished episodes, path attacks, grading
failures, and all three reference solutions. macOS execution tests are skipped
on unsupported platforms; they should run on the intended development host.
The pre-existing live Codex *sandbox* checks may run if configured; they do not
launch a Codex evaluation or request model inference.

The smallest subsequent SFT step is an offline converter from reviewed
`model_request`/assistant pairs to MLX-LM chat examples, with a validation check
that template tokenization matches recorded prompt IDs. First review labels and
split by task family; do not train on verifier feedback or count a single smoke
trajectory as evidence of generalization. A tiny LoRA overfit check can later
validate the training plumbing. No training is part of v0.1, and the three Hall
tasks are insufficient for a credible held-out generalization claim.
