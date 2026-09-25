# Practical line editing and development smoke tests

`replace_lines` is an additional production tool. Historical `edit_file` exact
replacement semantics and stored episodes are unchanged. New ordinary episodes
use a workspace tool session. The stateless legacy execution API retains its
original read observations for historical demonstration replay. Stored recovery
interventions and scores are unchanged. The diagnostic-only `edit_lines` remains historical.

The model must emit exactly one JSON object with exactly two keys: `tool`, a
string naming an available tool, and `arguments`, a JSON **object**, never an
array or string. Bare JSON or a single complete optional `json` code fence is
accepted. There may be no explanatory text, extra keys or additional blocks.
For `replace_lines`, the `arguments` object's exact required fields are:

| Field | JSON type | Meaning |
|---|---|---|
| path | string | Relative path inside the workspace |
| version | string | Token from the most recent complete `read_file` of this file |
| start_line | integer | First line to replace, 1-based and inclusive |
| end_line | integer | Last line to replace, inclusive |
| new_text | string | Complete replacement code for these lines, including indentation |

Booleans and numeric strings are not integers. The system prompt describes the
envelope and fields without placeholder arguments or copyable completed edits.

A complete UTF-8 read returns `content`, `truncated: false`, `version` and
`line_count`. A truncated read supplies no usable version. Versions are scoped to
one session and one canonical path, bound to a SHA-256 of the observed bytes.
Any changed bytes invalidate the version. A successful edit consumes the version;
read again before a further edit. Legacy edits or Python writes also invalidate
it when the new tool next checks the current bytes.

Ranges must satisfy `1 <= start_line <= end_line <= line_count`. Empty replacement
deletes the selected lines. Replacement and resulting file are each limited to
256000 UTF-8 bytes. Absolute paths, traversal, symlinks and hardlinks are rejected
using the existing workspace checks. Empty files have no replaceable range;
legacy `edit_file` still supports file creation.

Lines are separated by LF, CRLF or CR. Every byte outside the range is retained.
Replacement newlines are normalized to the file's existing uniform convention
(LF if none exists). A nonempty replacement retains whether the selected block
ended in a newline: one terminating delimiter is appended or removed as needed.
Internal blank lines are retained. Empty deletion adds nothing. Mixed newline
conventions are rejected rather than silently changing the file. No-op edits are
rejected with a request to choose a content-changing replacement or finish
honestly. Success reports `changed: true` and byte counts; rejected edits in the
episode trace report the actual `changed` value as well as the error.

The tool executes in the trusted local controller. It does not claim secure
isolation against concurrent hostile filesystem modification. Python execution
continues to use the existing macOS constrained runner and its mandatory
preflight; no security restrictions or physics verifiers have been relaxed.

Two scripted acceptance cases exercise actual Python repairs: quantity-aware
cart totals and sorted unique codes. Each script reads, receives an invalid-range
error, submits a corrected content-changing edit, runs the real visible tests,
and finishes with the observed result. Assertions require exact preservation of
all unrelated source and files. These deterministic scripts are engineering
tests, not learned-model results. Historical SFT replay tests now use their
recorded prompt and archived tools hash instead of today's protocol.

One authorized base-model development episode uses `cart-total`. It is a visible
development case, not held-out research evidence. Registration occurs before
generation and records the source, prompt, software, pinned original model,
adapter absence, and default 12-turn/300-second/768-token budget with seed 0 and
temperature 0. The runner refuses an existing output directory, never retries,
and attaches caffeinate. It saves the initial/final workspaces, full trajectory,
conversation, byte diff and report. After model shutdown it executes the original
visible tests independently, then records the agent's own Python results and
final summary for manual substantiation review. No physics reward is assigned.

Authorized command (do not rerun without approval):

```bash
PYTHONPATH=src .venv/bin/python scripts/run_development_smoke.py \
  --fixture data/epagent-development/cart-total.json \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out attempts/replace-lines-base-smoke
```
