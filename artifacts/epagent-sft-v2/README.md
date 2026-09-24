# Focused SFT audit corrections: verification evidence

This is private implementation evidence, not an evaluation campaign. No real
model generated a response; no baseline, adapted-model evaluation, backward
training, or replacement Hall smoke episode ran. Surrogate adapter tensors are
untrained temporary unit-test fixtures, removed with their temporary directories.
No model weights, adapters, credentials or control directories are committed.

## Results

- `full-tests.log`: **159 tests passed, no skips**, 103.056 seconds, source tree.
- `installed-wheel-tests.log`: **159 passed, no skips**, 105.578 seconds, installed
  wheel from outside the checkout with `PYTHONPATH` unset. This includes actual
  local tokenizer/loss checks and native surrogate adapter loading, never a
  backward pass or model generation. Training orchestration is mocked.
- `outside-checkout.json`: 13 exact commands and their outputs: fresh wheel in
  a new venv, CLI help and adapter-arm rejection, installed converter, and all
  three Hall reference grades. Invalid evaluation arms fail before model loading
  or creation of an attempt directory.
- `hall-transport-reference.json`, `hall-thrust-reference.json`, and
  `hall-ionization-reference.json`: **13/13 each**, unchanged independent graders.
- `preparation.json`: actual tokenizer counts, pinned base metadata, source,
  dataset, template and amended-protocol hashes, versions including NumPy,
  and 40/72 = 0.555556 effective training passes. No training occurred.
- `rebuild.json`: all 11 traces and their review manifest rebuild byte-for-byte
  after documented elapsed-time/workspace-path normalization.
- `protection.json`: **2,273 protected files and their file set unchanged**,
  including historical attempts, smoke artifacts, prior SFT data/evidence, all
  Hall code/references, and the separate publication snapshot. Base model hashes
  and the four held-out fixture bytes are unchanged. No trained adapter was saved.

The 13 additional tests comprise four adapter tests and nine runner/scorer tests.
They cover the CLI/config/worker/native-loader chain with distinct surrogate
adapters, base default, changed/incomplete adapter rejection, ready/final metadata,
actual injected tool failure without mutations, setup/model-turn separation,
no-op and byte-changing recovery, read-only non-recovery, repeated rejection,
late recovery, unsupported PASS, honest failure/incomplete reporting, evidence
invalidated by later source mutation, fixed arms, fresh output directories and
preserved infrastructure failure. The existing eight SFT tests now check the
revised counts, truthful finishes, budget counters and immediate iterator seeding.

These are scripted test outcomes, not outcomes for a Qwen baseline or adapted
policy. The four evaluation tasks remain held out from SFT. Mechanical observed
output support is not independent functional verification; the amended protocol
and guide document that limitation.

## Executed commands

From the repository root:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_sft_demos.py \
  --fixtures data/epagent-sft-v2/fixtures.json \
  --out /var/folders/vr/4b0xhmsn53d5d6r3qsg80zc00000gn/T/epagent-sft-amend-ypxp1967/normalized-rebuild

PYTHONPATH=src .venv/bin/python -m epagent.sft prepare \
  --trajectories data/epagent-sft-v2/trajectories \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --config data/epagent-sft-v2/lora-config.json \
  --protocol data/epagent-sft-v2/eval-protocol.json \
  --out sft-runs/reviewed-prepared-v2

.venv/bin/python -m pip install --no-build-isolation --no-deps --force-reinstall .
.venv/bin/python -m pip wheel --no-build-isolation --no-deps \
  --wheel-dir /var/folders/vr/4b0xhmsn53d5d6r3qsg80zc00000gn/T/epagent-sft-amend-ypxp1967/wheels .

EPAGENT_TEST_MLX=1 PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v
```

`installed-wheel.json` records the exact wheel install and outside-checkout
full-suite commands, environment and exit status. `outside-checkout.json` records
all fresh-venv CLI/reference commands. Focused adapter, SFT and runner test files
were also run before the full suites. MLX and confined-tool tests required the
approved local execution boundary; this is not a secure-isolation claim.

The first rebuild exposed a nondeterministic absolute temporary path in the new
ZeroDivisionError traceback. Only temporary path prefixes and elapsed seconds
are normalized by the final builder; exception content and test outcomes are
preserved. A subsequent rebuild matched every committed trace/review byte.

Generated output directories refuse reuse. See [the guide](../../docs/ep-agent-sft.md)
for the proposed baseline → SFT → adapted sequence. Those commands have **not**
been run. The next step is targeted independent review, not model execution.
