# Preserved 7B development result and compatibility review

Both the original 1.5B and 7B development episodes failed repair. This is a
**one-episode development comparison, not an estimate of model-size effects**.
The 7B episode made 12 schema-valid calls, six reads and five content-changing
edits (four `replace_lines`). It ran no tests and produced no final summary.
The independent original-visible-test check ended with `IndentationError`.

The allowlisted archive preserves both complete trajectories, conversations,
initial/final source bytes, diffs, reports, configuration, comparison, resource
measurements, model revision and file hashes, and historical runtime source.
`archive-manifest.json` records original and archived hashes. Only repository
prefixes in metadata and the terminal traceback become `<REPOSITORY>`; all
model-visible events, responses and source bytes are identical. Originals remain
under `attempts/replace-lines-{base,7b}-smoke` and the engineering control directory.
Weights, credentials and machine path inventories are excluded. The actual 7B
weights remain locally under `.epagent-models/qwen2.5-coder-7b-4bit`; its manifest
records revision `019cc73c45c770444708a6dd8690c66243cc5c80` and every file hash.
Loading uses that directory without an adapter. Do not rerun without authorization.

## Compatibility patch review

Previously `MLXBackend` accepted only the pinned 1.5B identity; the download
function also had a 2 GB limit. The preserved patch allows the exact pinned 7B
identity and a model-specific 5 GB download limit (actual download 4.296 GB).
The 1.5B default, revision and 2 GB limit are unchanged. Both downloads retain
size/hash checks and refuse existing destinations. Unknown identities/revisions
are rejected. No tokenizer rewrite was required: the existing helper derives
both actual EOS tokens, 151643 and 151645. Native templates differ only in unused
fallback system text; the actual initial prompt tokens were equal.

For 7B only, the worker sets a 7 GiB MLX allocation ceiling and reports it in
model-ready metadata. This can make an oversized allocation fail earlier; it
does not alter sampling, context, cache precision, parser behavior or tool calls.
The actual episode peak was 5.054 GB. Preparation loads exposed insufficient
memory and were stopped without generation; application cleanup preceded the
single episode. All such failures and the successful headroom check are retained.

The compatibility commit contains no prompt, tool-definition, agent-policy,
reward or physics changes. Relevant selection, adapter/surrogate-loading and
scripted-edit checks are rerun before committing. Verification guardrails belong
to a separate later commit, never to this historical compatibility patch.

## Per-edit reconstruction

`edit-analysis.json` gives every exact observed source, observation event,
requested operation, generated replacement, preserved/removed numbered lines,
resulting source and compilation result. It reproduces every recorded diff and
final byte hash without executing the source or rerunning the grader.

| Step / call event | Operation | Required API and syntax consequence | Direction |
|---|---|---|---|
| 3 / 142 | Replace observed `def cart_total(rows):` with `def calculate_total(items):` and dictionary-based multiplication | Removes required API and changes input contract; old return remains unreachable. Syntax valid. | Adds multiplication but moves away from the required interface. |
| 5 / 261 | Replace lines 3–4 with only the indented dictionary-based return | Deletes `calculate_total` definition. **First syntax failure: unexpected indent at line 3.** | Makes the entire module unimportable. |
| 7 / 396 | Replace docstring/blank lines 1–2 with a new docstring and another indented return | Duplicates the invalid body; still no function definition. | No repair progress. |
| 9 / 515 | Replace duplicate indented returns at lines 3–4 with one | Removes duplication; syntax remains invalid. | No progress toward an importable required API. |
| 11 / 634 | Replace remaining new/old returns at lines 3–4 with one | Removes old expression; still an indented top-level return. | No valid repair. |

Every edit preserves all bytes outside its requested span. The legacy edit
changes only a header span; the line edits replace complete specified lines.
The unrelated `label()` function is preserved, but cannot be imported from an
invalid module. Accepted writes establish neither syntactic nor semantic success.

Event 29 lists `README.md`, `cart.py` and `checks.py`. The system explicitly asks
the model to read README.md; it never does. Tests were plainly listed and README
instructed running them, but the system did not explicitly request inspecting tests
before editing. These materials were accessible and discoverable. The observed
omission does not establish intent, or prove that a stronger instruction would
have changed the outcome.
