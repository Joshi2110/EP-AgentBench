# Evaluation 01: a negative result for verification feedback v3

Twenty episodes, ten fixtures, two arms, one attempt each, no retries and no
infrastructure failures.

**Baseline 3/10. Verification feedback v3 1/10.**

Verification feedback v3 did not improve independent functional repair. It
scored lower. Nothing in this archive should describe it as an improvement.

Neither arm produced a single evidence-supported autonomous workflow.

## Primary and paired outcomes

The baseline repaired `matrix-transpose`, `histogram-buckets` and
`retry-backoff`. The verification arm repaired only `matrix-transpose`. Two
fixtures regressed, one was solved in both arms, seven in neither, and none
improved. Full per-fixture detail is in `results.json`.

| Total | Baseline | Verification |
| --- | --- | --- |
| Independent repair | 3/10 | 1/10 |
| Source changed | 10/10 | 7/10 |
| Final syntax valid | 10/10 | 10/10 |
| Agent-initiated test runs | 3, in 1 fixture | 9, in 4 fixtures |
| Runner-initiated test runs | 0 | 51 |
| Visible test passed | 4/10 | 2/10 |
| Finish called | 10/10 | 0/10 |
| Evidence-supported finish | 0/10 | 0/10 |
| Reached step limit | 0/10 | 10/10 |
| Schema rejections / tool failures | 0 / 0 | 0 / 16 |
| Wall time | 12.3 min | 42.2 min |
| Prompt / generation tokens | 61,258 / 3,874 | 274,282 / 8,478 |
| Peak MLX / RSS | 4.76 / 1.35 GB | 4.92 / 1.61 GB |

## What the records show, and what they do not

Every verification episode ran out its twelve turns without calling finish,
while every baseline episode finished. Prompt context grew from a mean of 689
tokens on the first turn to 4,048 on the last in the verification arm, against
490 rising to 1,227 in the baseline. No episode hit the context limit, so the
budget was exhausted by turn count, not truncation.

That is an observation about budget, not a demonstrated cause. Ten synthetic
fixtures at temperature zero with one attempt each give no uncertainty estimate
and support no significance or generalization claim.

The feature did raise agent-initiated testing from one fixture to four, which
was its stated motivation. It also stopped every episode from finishing.

## Three distinctions kept strict

A repair that passes the hidden test but never finishes is **functionally
successful, not a complete agent workflow**. All three baseline successes are of
that kind: none ran the workspace test after its last change.

A **runner-executed test is not agent-initiated testing**, and the 51 runner
executions are excluded from that counter.

A **visible-test pass is not a hidden-test pass**. In the baseline four fixtures
passed the visible test while three passed the hidden one.

## Provenance

The agent architecture, tools, feedback mechanisms and graders were developed
across four prior `cart-total` episodes, archived separately. Those are
development evidence and form no part of this campaign. The overall architecture
is not independently pre-registered.

## Contents and handling

Both registrations and cleanups, both suite results, all twenty episodes with
trajectory, conversation, report, changes diff, initial and final workspace, plus
the frozen fixtures, protocol, validation record and the implementation files as
they stood at commit `9c58aff8`. Excluded: model tensors and control directories.

Every occurrence of the repository root becomes `<REPOSITORY>`, verified per file
to be the only difference and exactly reversible. Unlike the earlier archives,
some model-visible events here did contain the path, because agent `run_python`
tracebacks name the absolute workspace file; `tool_result`, the `model_request`
history repeating it, and `verification_feedback` output were normalized too, and
`archive-manifest.json` records the affected counts. Workspace and initial source
bytes contain no machine path and are byte-identical. Raw originals under
`attempts/` are unchanged.

Regenerate with:

```bash
PYTHONPATH=src:scripts .venv/bin/python scripts/archive_evaluation_01.py
```

No inference, training or re-grading was performed to produce this archive.
