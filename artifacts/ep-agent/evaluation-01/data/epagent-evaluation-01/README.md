# EP-Agent Evaluation 01: ten fixtures, two arms, frozen

A fixed assessment of the pinned 7B base agent. Ten synthetic Python repair
fixtures, each run once per arm. **Nothing has been generated yet.**

This is an engineering assessment, not a benchmark result. Twenty episodes at
temperature zero give no uncertainty estimate and support no significance or
generalization claim.

## Honest framing of what is and is not pre-registered

The ten fixtures, the hidden tests and `protocol.json` are frozen before any
model generation, and their hashes are recorded. But this campaign follows four
rounds of development on the `cart-total` fixture, and the agent architecture,
tools, feedback mechanisms and graders were all shaped by those rounds. **The
overall architecture is not independently pre-registered and must not be
described as such.**

## Fixtures

Ten distinct problem families, none reused from `cart-total`, from
`sorted-unique`, or from any SFT v1, v2 or v3 training, validation or held-out
family. Each fixture places its defective source inside its own package
directory alongside an unrelated module that must be preserved.

| Fixture | Family | Source |
| --- | --- | --- |
| interval-merge | interval-merging | `ranges/merge.py` |
| roman-numeral | roman-numeral-encoding | `numerals/convert.py` |
| bracket-balance | bracket-matching | `syntax/brackets.py` |
| run-length | run-length-encoding | `codecs_local/rle.py` |
| caesar-shift | alphabet-rotation | `cipher/shift.py` |
| matrix-transpose | grid-transposition | `grids/matrix.py` |
| banker-rounding | half-even-rounding | `money/rounding.py` |
| path-normalize | path-normalisation | `fsutil/paths.py` |
| histogram-buckets | half-open-bucketing | `stats/buckets.py` |
| retry-backoff | capped-exponential-backoff | `net/backoff.py` |

## Visible and independent tests are deliberately different

Each fixture ships a small `checks.py` the agent can read and run, and a
**strictly larger hidden test** that never enters the workspace. Every hidden
test adds at least three assertions the visible test does not contain, covering
edges such as wraparound, exact bucket boundaries, cap saturation, subtractive
numerals and unresolvable parent segments.

Passing the visible test therefore does not imply functional success. This also
removes the overlap that weakened the `cart-total` work: the runner-executed
workspace test is no longer the grader's test, so verification feedback can help
the agent without handing it the evaluation signal.

The hidden tests and the reference repairs live only in `fixtures.json`, which
the agent's sandbox cannot read. `validation.json` records that probe.

## Offline validation

`validation.json` records, for all ten fixtures, that the starter fails both the
visible and the hidden tests with a real `AssertionError`, that the reference
repair passes both, that the visible and hidden tests differ, that no hidden
assertion or reference line appears in any exported file, and that a direct read
of `fixtures.json` from inside the sandbox is refused.

Rebuild and revalidate with:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_evaluation_01.py \
  --out data/epagent-evaluation-01
```

## Running an arm

One attempt per fixture per arm, seed 0, temperature 0, 12 turns, 300 seconds.
The only intended difference is the feedback condition. Do not repair a fixture,
change the prompt, or rerun an episode after observing any model output.

```bash
PYTHONPATH=src .venv/bin/python scripts/run_evaluation_01.py --arm baseline \
  --fixtures data/epagent-evaluation-01/fixtures.json \
  --protocol data/epagent-evaluation-01/protocol.json \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out attempts/evaluation-01-baseline

PYTHONPATH=src .venv/bin/python scripts/run_evaluation_01.py --arm verification \
  --fixtures data/epagent-evaluation-01/fixtures.json \
  --protocol data/epagent-evaluation-01/protocol.json \
  --model-dir .epagent-models/qwen2.5-coder-7b-4bit \
  --out attempts/evaluation-01-verification
```

## Metrics

Primary is independent functional repair success out of ten per arm, judged by
the hidden test after the backend closes. Secondary measures are recorded per
fixture: source changed, unrelated files preserved, final syntax, agent-initiated
test executions and observed passes, runner-initiated test executions, the
visible test outcome, finish called, evidence-supported finish, schema and tool
errors, steps, runtime and tokens.

Agent-initiated and runner-initiated executions are counted separately and never
summed. A passing runner observation is not an agent-initiated test.
