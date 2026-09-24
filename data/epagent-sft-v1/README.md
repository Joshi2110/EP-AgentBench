# EP-Agent SFT demonstration set v1

Eight new, scripted synthetic Python workspaces; **not model rollouts**. The
fixtures and tool actions were authored with Codex assistance for this task,
then inspected and executed through the actual EP-Agent tools. No successful
proprietary-model trajectories were imported. No Hall task, reference solution,
reserved verifier case, or previous policy trajectory supplies a target.
Independent maintainer review is still pending; execution checks are not a claim
of human review. The project's license covers these newly authored files; no
rights over third-party trajectories are inferred.

`fixtures.json` is the compact review surface: initial files, visible checks,
intended replacement, and recovery flag. `trajectories/*.jsonl` records actual
tool observations in the existing episode event format. Timing values alone
are omitted from synthetic Python observations to make rebuilds reproducible.
The review manifest pins each trace's SHA-256 and lists exactly which assistant
turns may be supervised. Unsupported origins and unreviewed/changed traces are
rejected, even if they claim a successful grade.

| Workspace | Split | Error / behavior | Failed-edit recovery |
| --- | --- | --- | --- |
| bound-count | Train | Clamp bounds reversed | Yes |
| suffix-token | Train | First rather than final colon segment | No |
| ordered-unique | Train | Sorting destroys first-occurrence order | Yes |
| batch-count | Train | Floor rather than ceiling batch count | No |
| enabled-flag | Train | Nonempty text mistaken for true | Yes |
| pair-changes | Train | Unique values mistaken for adjacent transitions | No |
| midpoint-order | Validation | Unsorted/even-length median | Yes |
| longest-label | Validation | Lexical rather than length comparison | No |

All eight demonstrate listing before choosing files, reading tests and source,
running a failing check, inspecting the failed check's source, editing from
observed text, rerunning a relevant check, and finishing with an observed PASS
claim. Four add an intentional whitespace mismatch, the real
`old_text must match exactly once` error, a fresh source read, and a successful
exact replacement. Those four failed edit actions are **excluded as targets**;
they remain visible, masked history for the recovery examples.

There are **57 train examples from six workspaces** and **19 validation examples
from two workspaces**. A whole workspace/family belongs to one split; turns from
a single demonstration cannot straddle splits. At the real Qwen tokenizer these
contain 1,624 and 554 supervised tokens respectively, with maximum total lengths
1,408 and 1,425. Repeated prefixes are context, not extra independent examples.

The four additional `eval-fixtures.json` workspaces contain no target repairs:
rotation, prefix removal, positive-only aggregation, and missing-key fallback.
They are reserved from training and validation preparation. Their prescribed
failed-edit setup and metrics are fixed in `eval-protocol.json`. They are small
public-in-this-private-repository probes, not secret or representative evidence
of general coding ability. Shared Python primitives and tool patterns remain
across splits, so this is not a clean statistical test of broad generalization.

Rebuild into a new directory without any model inference:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_sft_demos.py \
  --fixtures data/epagent-sft-v1/fixtures.json --out /tmp/epagent-demos-rebuilt
```

The builder executes only these synthetic files under the existing constrained
macOS tool profile. Compare its trace/review hashes with this directory before
accepting a changed dataset. Do not add external provider outputs by simply
changing the origin label: a future import policy needs an explicit rights check,
quality review, and a new dataset version.
