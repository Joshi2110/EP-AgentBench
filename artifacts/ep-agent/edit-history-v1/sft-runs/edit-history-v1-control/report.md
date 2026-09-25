# Eight-response edit-interface/history diagnostic

**Primary: 0/8 exact targets.** Exactly eight real-model responses, no recovery turn or replacement attempt.

| Task | Interface | History | Schema | Executed | Changed | Target | Tokens | Wall seconds |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| level-note | A | absent | no | no | no | no | 47 | 2.939 |
| level-note | A | present | yes | yes | yes | no | 59 | 2.466 |
| level-note | B | absent | no | no | no | no | 29 | 2.083 |
| level-note | B | present | yes | yes | yes | no | 48 | 2.406 |
| flag-note | A | absent | no | no | no | no | 27 | 2.119 |
| flag-note | A | present | yes | no | no | no | 52 | 2.440 |
| flag-note | B | absent | no | no | no | no | 30 | 2.135 |
| flag-note | B | present | yes | yes | yes | no | 48 | 2.432 |

Executed means tool execution accepted, not just schema acceptance. Wall seconds include preflight, loading, generation, editing and worker cleanup.

No exact targets. Present-history calls all pass schema; absent-history calls all fail schema. History supplies an object-shaped legacy call as well as misleading edit contents, so format demonstration and misleading content are bundled. Exact copying succeeds in one A/present cell, but LF is missing. B/present constructs valid version/ranges but deletes source. No full-call repetition; A/present repeated-span case reuses the ambiguous old_text with altered new_text.

## Individual responses and actual results

### level-note-A-absent

Invalid JSON and invented replace tool.

```json
{"tool": "replace", "arguments": ["levels.py", "def offset_level(n):\n    return n + 3\n", "def offset_level(n):\n    return n + 3\n# diagnostic note"}
```

Tool result: `{"error": "schema_rejection", "detail": "Invalid JSON at line 1, column 151: Expecting ',' delimiter. Return one JSON object with exactly tool and arguments, bare or inside one complete ```json or unlabelled ``` fence, with no outside text."}`

Exact final source (JSON string makes trailing newlines explicit):

```json
"def offset_level(n):\n    return n + 3\n"
```

### level-note-A-present

Correct source retained and comment appended, but required final LF missing.

```json
{"tool": "edit_file", "arguments": {"path": "levels.py", "old_text": "def offset_level(n):\n    return n + 3\n", "new_text": "def offset_level(n):\n    return n + 3\n# diagnostic note"}}
```

Tool result: `{"edited": "levels.py"}`

Exact final source (JSON string makes trailing newlines explicit):

```json
"def offset_level(n):\n    return n + 3\n# diagnostic note"
```

### level-note-B-absent

Positional arguments array instead of required object.

```json
{"tool": "edit_lines", "arguments": ["levels.py", "v1", 1, 2, "# diagnostic note"]}
```

Tool result: `{"error": "schema_rejection", "detail": "edit_lines requires exactly path, version, start_line, end_line, new_text"}`

Exact final source (JSON string makes trailing newlines explicit):

```json
"def offset_level(n):\n    return n + 3\n"
```

### level-note-B-present

Whole source replaced with comment only; original source deleted.

```json
{"tool": "edit_lines", "arguments": {"path": "levels.py", "version": "v1", "start_line": 1, "end_line": 2, "new_text": "# diagnostic note\n"}}
```

Tool result: `{"edited": "levels.py"}`

Exact final source (JSON string makes trailing newlines explicit):

```json
"# diagnostic note\n"
```

### flag-note-A-absent

Invented replace tool / invalid arguments layout.

```json
{"tool": "replace", "arguments": "markers.py", "old_text": "", "new_text": "# diagnostic note"}
```

Tool result: `{"error": "schema_rejection", "detail": "Unknown or non-string tool name. Allowed tools: list_files, read_file, edit_file, run_python, finish. Return one JSON object with exactly tool and arguments, bare or inside one complete ```json or unlabelled ``` fence, with no outside text."}`

Exact final source (JSON string makes trailing newlines explicit):

```json
"def start_flag():\n    return False\n\ndef end_flag():\n    return False\n"
```

### flag-note-A-present

Ambiguous old_text occurs twice; execution rejected.

```json
{"tool": "edit_file", "arguments": {"path": "markers.py", "old_text": "    return False\n", "new_text": "# diagnostic note\n    return False\n\ndef end_flag():\n    return False\n"}}
```

Tool result: `{"error": "ValueError", "detail": "old_text must match exactly once"}`

Exact final source (JSON string makes trailing newlines explicit):

```json
"def start_flag():\n    return False\n\ndef end_flag():\n    return False\n"
```

### flag-note-B-absent

Positional arguments array instead of required object.

```json
{"tool": "edit_lines", "arguments": ["markers.py", "v1", 1, 5, "# diagnostic note"]}
```

Tool result: `{"error": "schema_rejection", "detail": "edit_lines requires exactly path, version, start_line, end_line, new_text"}`

Exact final source (JSON string makes trailing newlines explicit):

```json
"def start_flag():\n    return False\n\ndef end_flag():\n    return False\n"
```

### flag-note-B-present

Whole source replaced with comment only; original source deleted.

```json
{"tool": "edit_lines", "arguments": {"path": "markers.py", "version": "v1", "start_line": 1, "end_line": 5, "new_text": "# diagnostic note\n"}}
```

Tool result: `{"edited": "markers.py"}`

Exact final source (JSON string makes trailing newlines explicit):

```json
"# diagnostic note\n"
```

## Interpretation limits

- Two inspected tasks; one deterministic response per cell; no statistical or scientific-generalization claim.
- The compact system prompt names arguments fields but does not explicitly say that arguments must be an object. Strict validators require it. History supplies such an example; schema failures limit interface-friction conclusions.
- History is labeled user-quoted legacy evidence, not an assistant-history replay of SFT v3. Lack of repetition here does not negate earlier observations.
- B has an unfamiliar schema; representation, prompt and familiarity effects are inseparable in this small interface contrast.
- No hidden-output hints were supplied: full expected files stayed in the frozen registration, outside prompts. The harmless comment itself is prescribed by the task.
- Trusted local harness with existing preflight and path confinement; no new production security claim.

All eight workers loaded the frozen v3 adapter with the recorded configuration/weight hashes; stop IDs were [151643, 151645]. All ended generation with stop, well below the 768-token budget. Total generated tokens: 340.

Executed collection command (once, with attached caffeinate):

```bash
PYTHONPATH=src .venv/bin/python diagnostics/edit_history.py run --manifest-dir data/epagent-edit-history-v1 --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --adapter-dir sft-runs/tool-use-lora-v3 --out attempts/edit-history-v1
```

Registration SHA-256: `e85e2b18ad4f9d631b366adf2340907fdebfc76ca59e156e1e479fb34fe83c5d`. Eight focused offline tests passed before generation. All 2904 protected pre-existing files remain unchanged. All experiment-owned processes exited. No weights, historical datasets, physics tools or scorers were changed, and no frozen experiment was rescored.
