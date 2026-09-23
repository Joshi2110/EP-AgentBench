# Private EP-Agent evidence policy

This directory is an intentional, reviewable exception to the default policy
of leaving attempt collections untracked. It belongs only to the private
research repository. Do not copy it into the sanitized publication snapshot or
include it in a package/wheel.

`smoke-001/` archives the first real episode
`cc94d8972f2641ebb4f971d91fa21d57`. The allowlist is: the real report, full JSONL
trajectory, policy conversation, cumulative diff, initial/final exported task
files, and the exact runner source used for that episode. `manifest.json` lists
every payload file and its SHA-256. These are byte-identical copies, **not
sanitized or regenerated results**. Absolute local artifact paths remain in the
original report for provenance; use this archive's relative layout for review.
The original raw directory remains locally under `attempts/ep-agent/`.

The original outcome remains 12 responses, zero accepted tools, zero edits,
reward zero, and an untouched-starter diagnostic of 3/13. Parsing replays are
separate counterfactual analyses, never replacements for the measured outcome.
The archived prompt and parser are historical; do not update them when changing
the current implementation.

Excluded: model weights/tokenizer downloads, credentials, authentication files,
all `control/` directories, caches, environment dumps, and unrelated machine
state. The payload was reviewed for these exclusions before committing. New
archives require their own explicit allowlist and content review; this policy
does not automatically permit committing all future attempts.

`audit-v0.1-fixes/` contains the separately labelled offline replay/tokenizer
result and focused verification logs. These analyses must not be merged into or
used to rewrite the original report. Reproduce the audit without inference:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_epagent.py \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --out /tmp/epagent-audit.json
```

If the real local tokenizer is unavailable, the script reports it as unverified
and exits 2. It does not download anything or substitute mock-tokenizer evidence.
