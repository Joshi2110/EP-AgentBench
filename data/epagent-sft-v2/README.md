# EP-Agent tool-use demonstrations v2

Amended after the independent audit of `2a3b6c6`. Version 1 remains unchanged.
These are project-authored scripted synthetic workspaces with executed tool
observations, not model rollouts or imported provider trajectories. New files
follow the project license; no third-party trajectory rights are assumed.
Independent maintainer review is pending; execution checks are not human review.

| Episode | Split | Outcome |
| --- | --- | --- |
| bound-count | Train | Supported success; exact-match recovery |
| suffix-token | Train | Supported success |
| ordered-unique | Train | Supported success; exact-match recovery |
| batch-count | Train | Supported success |
| enabled-flag | Train | Supported success; exact-match recovery |
| pair-changes | Train | Supported success |
| average-empty | Train | Failed check reported; no edit |
| join-separator | Train | Failed edit reported as unresolved after reread |
| midpoint-order | Validation | Supported success; exact-match recovery |
| longest-label | Validation | Supported success |
| inclusive-total | Validation | Partial edit; rerun fails; honest incomplete finish |

Totals: **11 episodes / 100 assistant targets**. Training: **8 episodes, 72
examples, 1,980 supervised tokens**. Validation: **3 episodes, 28 examples, 822
tokens**. Five rejected edits remain masked context, not targets. Eight episodes
end successfully and three unsuccessfully. Source/test inspection, listing,
observed old_text, diagnostics, recovery and supported claims remain represented.

Budgets are explicit (10–15 turns), episodes use 7/9/11 turns, and observations
count down from the actual budget, not the scripted endpoint. Finish targets
occur with 3–6 turns remaining. Counters 4–6 also precede other actions, removing
the previous perfect `steps_remaining == 1` shortcut. This is still a small,
patterned set, not proof that no other shortcut exists.

`fixtures.json` is the compact manual review surface. `trajectories/` preserves
role-separated events and actual observations. For reproducibility, elapsed
seconds are omitted and temporary workspace prefixes in stdout/stderr become
`<workspace>/`; exception details, code lines and outcomes remain unchanged.
`reviews.json` pins fixture/trace hashes, split, outcome and explicit selected
assistant steps. The unchanged converter validates history/provenance and
preserves observations as masked context. No Hall references or verifier cases
supply targets.

The four original evaluation cases are byte-identical to v1 and are excluded
from preparation. The amended `tool-recovery-v2` protocol separates reinspection,
accepted corrected edits, and byte changes. A no-op can be valid tool recovery.
No base/adapted outcomes have been collected. Scripted runner tests are not
model evaluations and do not supply repairs for these four cases.

Rebuild into a new directory, with no model involved:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_sft_demos.py \
  --fixtures data/epagent-sft-v2/fixtures.json --out /tmp/epagent-demos-v2-rebuilt
```

Compare trace/review hashes before accepting changes. Whole task families are
separated across training, validation and evaluation; tool grammar and Python
primitives naturally overlap. Do not reinterpret loss or four-case recovery as
scientific generalization. See [the guide](../../docs/ep-agent-sft.md) for the
unchanged training configuration, amended protocol, commands and limitations.
