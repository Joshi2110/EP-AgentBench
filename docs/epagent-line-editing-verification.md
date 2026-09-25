# Pre-inference engineering verification

The sanitized edit-history diagnostic was committed separately as `fe0d813`.
Its 55 original inventory entries verified; the archive contains 58 evidence and
historical runtime files plus its manifest and explanatory README. Outcome remains
0/8 exact targets with the documented format-example/history confound.

Before the development model episode:

- All 188 automated tests passed in 108.190 seconds with real tokenizer checks
  enabled. No real-model generation or weight updates were performed by the suite.
- Seven new engineering test methods cover newline/byte preservation, stale
  versions, confinement, ranges, schema, byte limits, no-op rejection, two full
  scripted repairs with failed-edit recovery, and tampered-test rejection.
- The nine diagnostic/archive checks also pass as part of the full suite.
- A wheel built without dependency downloads, installed into a fresh temporary
  virtual environment, and passed `epagent --help`, `epbench list`, and an
  installed-package CRLF/versioned edit check outside the checkout.
- A prior 2904-file inventory verified all original experiment artifacts, base
  weights, adapters, physics sources, references and publication snapshot intact.
  Seven changed entries are the authorized agent/docs/test sources and generated
  package metadata. All 55 diagnostic raw inventory entries remain identical.

The initial full-suite invocation found two legacy corpus-discovery errors:
Experiment 02 tests globbed every `attempts/*/*/trace.jsonl`, including a different
diagnostic format. Discovery now targets `attempts/experiment-*/*/trace.jsonl`.
The actual scorer and experiment records were not changed. Historical SFT checks
verify their original archived tools hash and replay their recorded system prompt.
The initial sandboxed scripted invocation failed preflight before any agent ran;
the same offline checks passed with macOS sandbox-exec permitted.

Commands executed (package checks use a fresh temporary directory):

```bash
.venv/bin/python scripts/archive_edit_history.py
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_edit_history*.py' -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_replace_lines.py -v
PYTHONPATH=src PATH="$PWD/.venv/bin:$PATH" EPAGENT_TEST_MLX=1 .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip wheel --no-deps --no-build-isolation . --wheel-dir /tmp/epagent-line-wheel
```

Exact outside-checkout subprocess commands, stdout and stderr are retained locally
in `sft-runs/replace-lines-engineering/outside-checkout-final.json`. Full initial
and final suite logs, packaging logs and preservation verification are in the
same ignored directory. These engineering checks do not predict model success.
The single real episode, its model identity and its outcome will be recorded
separately under `attempts/replace-lines-base-smoke`; it has not been used to
tune this implementation or its prompt.
