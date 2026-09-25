# One original-base 7B development smoke: unsuccessful repair

Exactly one episode was run with mlx-community/Qwen2.5-Coder-7B-Instruct-4bit,
revision 019cc73c45c770444708a6dd8690c66243cc5c80. No adapter, training, prompt
revision, replacement episode, Hall evaluation, or additional seed was used.

| Measurement | Original 1.5B | Original 7B |
|---|---:|---:|
| Responses | 12 | 12 |
| Schema-valid calls | 1 | 12 |
| Schema-rejected calls | 11 | 0 |
| Execution-rejected calls | 0 | 0 |
| Successful source reads | 0 | 6 |
| Attempted / accepted edits | 0 / 0 | 5 / 5 |
| Accepted replace_lines calls | 0 | 4 |
| Content-changing edits | 0 | 5 |
| Modified files | 0 | 1 (cart.py) |
| Agent Python tests | 0 | 0 |
| Final summaries | 0 | 0 |
| Independent original visible tests | Fail (AssertionError) | Fail (IndentationError) |
| Repair completed | No | No |
| Termination | step_limit | step_limit |
| Runtime | 28.134309 s | 128.015582 s |
| Generated tokens | 515 | 596 |
| Prompt tokens, summed repeated history | 13215 | 13441 |
| Peak MLX allocation | 1664106152 bytes | 5054105664 bytes |
| Peak process RSS | 764133376 bytes | 2070511616 bytes |

The initial task files, complete system/user messages and initial prompt token
IDs are identical. All episode configuration fields match: 12 turns, 300 seconds,
8 seconds per Python tool, 8192 output bytes, 8192 context tokens, 768 maximum new
tokens per turn, temperature 0, seed 0, adapter null. Tool/parser, episode runner,
fixture and development checker hashes remain unchanged. Software versions match:
MLX 0.32.2, MLX-LM 0.31.3, Transformers 5.17.0, NumPy 2.4.6, Python 3.11.15.

## Actual trajectory

Events 64–65 show a schema-correct read_file call and the original source.
Event 142 copies the observed `def cart_total(rows):` header into a legacy edit,
but replaces it with `calculate_total(items)` operating on dictionary inputs,
leaving the old return statement behind. The agent had not read README.md or
checks.py, which specify the actual interface and tests.

Event 179 returns observed version v2. Event 261 uses v2 in replace_lines and
replaces lines 3–4 with only an indented return statement. Event 262 confirms
changed bytes. This removes the function definition. Three subsequent line edits
use newly observed versions v3, v4 and v5; all execute and change bytes, but none
restores the function. The final source observation is event 671.

The final cart.py grew from 131 to 153 bytes and contains an indented top-level
return. Its SHA-256 changed from
a3861d98b29faf7d762241e5c0e059f66f57e3015a31928073006bf74b709fbc to
1fd3db9e0b25a62ccfcdeff5bd95b57501a84f7d4a5bea1e7b382f04c1d3c473.
README.md, checks.py and the unrelated label function are unchanged. The complete
changes.diff and both workspaces are retained.

There are no agent test executions or final summaries to substantiate. Event 673
records the independent post-termination development check: importing cart.py
fails with `IndentationError: unexpected indent` at line 3. This is the existing
original-visible-test checker, not a Hall physics grade. No scientific reward is
assigned. There was no backend or execution-boundary infrastructure failure.

## Preparation and limitations

Ten downloaded files are SHA-256 recorded in the separate model directory's
epagent-model.json. Weight SHA-256:
56a3d94706833f753e6c6b47ea57af8ef638cd8cc1d74eca1142ba640b26060e.
Actual loading verified native mlx_lm.models.qwen2.Model, 28 transformer
layers with native QuantizedLinear projections and 4-bit/group-64 weights. The model config declares endoftext (151643);
the actual tokenizer declares im_end (151645). The unchanged stop-token helper
therefore configures [151643, 151645]. Native template hashes differ only in
fallback system text that is unused because EP-Agent supplies a system message;
no tokenizer transformation or prompt rewrite was required.

Preparation stopped twice before loading for warning pressure. The first
non-generating native load succeeded but caused critical pressure and was
unloaded. After applications were closed, the load-only headroom check passed;
pressure was normal with weights loaded, during the sole episode, and afterward.
All preparation loads generated zero responses and performed zero forward passes.
The backend has an explicit 7 GiB MLX allocation ceiling for this 7B model,
recorded in model-ready metadata. It did not change sampling or context and the
measured episode peak was below that ceiling. Cache precision is unchanged.
The process RSS and MLX allocation measurements overlap and must not be summed.

The compatibility change allowlists this exact model/revision and download size;
it leaves the original 1.5B default and files intact. Fourteen focused offline
checks passed; the installed worker matches the preserved source patch. Source
HEAD remains 967e8517728c68a97487f931a0ec25a4ffece9d8, with the uncommitted
compatibility patch preserved at sft-runs/replace-lines-7b-engineering/compatibility.patch.
No experimental results were committed, pushed or published.

Both episodes failed the repair. In this instance 7B satisfied the tool schema,
used observed versions, reached line editing and changed bytes. It failed to
preserve the required function and never checked its work. This is a one-episode
development comparison between different models and memory environments, not a
controlled estimate of parameter-count effects, broad superiority, scientific
competence or generalization. No further episode is authorized.

Raw evidence: registration.json, result.json and
 episodes/95eb3af15ec44c8caae710da1139383a/ (trajectory.jsonl, report.json,
 conversation.json, initial/, workspace/, changes.diff, control/inference.stderr).
comparison.json contains per-edit arguments, tool observations, byte diffs,
metrics and exact artifact paths. Commands, download metadata, all preflight
results, source patch, software metadata and preservation verification are in
sft-runs/replace-lines-7b-engineering. The experiment-owned model and caffeinate
exited; the pre-existing unrelated caffeinate was left alone.
