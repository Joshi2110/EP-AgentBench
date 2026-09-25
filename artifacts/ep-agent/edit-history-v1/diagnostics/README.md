# Edit-interface/history diagnostic v1

This standalone harness uses the existing MLX worker, strict exact-edit parser/tool and execution preflight. The production agent and original tools are unchanged. `line_edit` exists only in `diagnostics/edit_history.py`; it checks workspace paths, the server-held hash for observation version `v1`, integer inclusive line bounds, and replacement/result byte limits. It offers no Python execution tool to the model. This is trusted local diagnostic execution, not a new secure isolation claim.

Two new files (levels.py and markers.py) were authored specifically for this diagnostic; no previous held-out fixture or Hall reference was reused. Both tasks require preserving the whole file and appending one `# diagnostic note` line ending in LF. The full expected outputs are recorded outside the prompts in `data/epagent-edit-history-v1/manifest.json`.

The manifest freezes all eight task × interface × history cells, exact prompts, actual historical failure observations, source/target hashes, model/adapter identities, software versions, generation settings, implementation hashes and measurement definitions. It was written before any generation. History is the same labeled user-quoted failed legacy exact-edit call in A and B, followed by the current source. Each real cell used a fresh model worker and workspace and exactly one response. No recovery feedback or replacement attempt was allowed.

Offline command executed before inference:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_edit_history_diagnostic.py -v
```

All eight tests passed, covering confinement including links, stale versions, bounds and byte limits, JSON/schema rejection, no-op/wrong-location failures, exact target success, schedule/prompt pairing and fake-backend one-response behavior. Fake responses are tests, not experiment evidence.

Registration command executed:

```bash
PYTHONPATH=src .venv/bin/python diagnostics/edit_history.py freeze --manifest-dir data/epagent-edit-history-v1 --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit --adapter-dir sft-runs/tool-use-lora-v3
```

Exactly one collection was then executed, with caffeinate attached, using the command preserved in `sft-runs/edit-history-v1-control/execution.json`. Existing registration/output directories cannot be overwritten. No more inference is authorized by this documentation.

Raw evidence is retained at `attempts/edit-history-v1/` (one prompt, trace, report, stderr and final workspace per cell). Frozen analysis, commands, process cleanup, prior-artifact verification and a SHA-256 inventory are at `sft-runs/edit-history-v1-control/`. These ignored local directories can contain machine paths and are not automatically suitable for Git. No weights were copied or committed.

Observed primary: 0/8 exact targets. History-present: 4/4 schema-valid; history-absent: 0/4. Three accepted edits changed bytes but failed the target. None repeated the entire historical call, though the repeated-span A/present cell retained the ambiguous old_text. The compact schema descriptions did not explicitly name the object type for arguments; historical evidence supplied an object-shaped call. That bundles format-example exposure with misleading history and limits interpretation. B's schema was also new to the model. These eight responses do not establish scientific competence, broad interface superiority, or a causal explanation of SFT v3 failures.
