# First SFT pipeline: verification evidence, no training

This directory intentionally preserves small private review artifacts for the
SFT implementation. It contains configuration/provenance hashes, test logs,
and read-only compatibility results, **not** model weights, adapters, model
rollouts, credentials, or a training loss curve. Existing real-model episode
artifacts and the separate publication snapshot remain unchanged.

Results:

- `full-tests.log`: 146 automated tests, no skips, including eight new SFT
  tests. Real tokenizer and numerical masked-loss checks ran. Optimization,
  checkpoint writing, and training callbacks in orchestration tests are
  mocked; their dummy loss/checkpoint values are not model measurements.
- `compatibility.json`: actual local model loaded; rank-8 query/value LoRA in
  the last four layers initialized in memory. 155,648 trainable parameters,
  stop IDs `[151643, 151645]`, peak initialization allocation 872,180,852 bytes.
  Zero optimizer steps or generated responses; no checkpoint saved.
- `preparation.json`: real-tokenizer preparation, model/config/protocol/source
  hashes, versions, counts, and dataset hashes. It matches the local
  `sft-runs/reviewed-prepared/manifest.json`.
- `rebuild.json`: all eight scripted traces and their review manifest rebuilt
  byte-for-byte through the real tools. No model supplied their actions.
- `outside-checkout.json`: exact commands and outputs for fresh-wheel CLI and
  converter checks plus installed-package real-tokenizer preparation. All
  prepared files were byte-identical. Hall starter grading is a packaging
  diagnostic (3/13), not an agent result. An initial manual use of `--dest`
  instead of the existing `--out` option failed cleanly; it was corrected
  without changing product code.
- `install.log`, `wheel.log`: noneditable installation and wheel build.
- `protection.json`: 1,710 protected files and all model manifest hashes
  checked unchanged. No SFT checkpoints exist in the output directory.

## Commands actually executed

From the repository root, using the existing local Python 3.11 environment:

```bash
PYTHONPATH=src .venv/bin/python scripts/build_sft_demos.py \
  --fixtures data/epagent-sft-v1/fixtures.json \
  --out /var/folders/vr/4b0xhmsn53d5d6r3qsg80zc00000gn/T/epagent-sft-review-2clyl9ki/rebuilt-demos

PYTHONPATH=src .venv/bin/python -m epagent.sft inspect \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --config data/epagent-sft-v1/lora-config.json \
  --out artifacts/epagent-sft-v1/compatibility.json

PYTHONPATH=src .venv/bin/python -m epagent.sft prepare \
  --trajectories data/epagent-sft-v1/trajectories \
  --model-dir .epagent-models/qwen2.5-coder-1.5b-4bit \
  --config data/epagent-sft-v1/lora-config.json \
  --protocol data/epagent-sft-v1/eval-protocol.json \
  --out sft-runs/reviewed-prepared

.venv/bin/python -m pip install --no-build-isolation --no-deps --force-reinstall .
.venv/bin/python -m pip wheel --no-build-isolation --no-deps \
  --wheel-dir /var/folders/vr/4b0xhmsn53d5d6r3qsg80zc00000gn/T/epagent-sft-review-2clyl9ki/wheels .

EPAGENT_TEST_MLX=1 PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src \
  .venv/bin/python -m unittest discover -s tests -v
```

The tool preflights and MLX checks ran outside the outer development sandbox
where macOS confinement/Metal initialization required it. The existing tool
confinement remains a local defense, not a claim of secure isolation.
Generated directories reject reuse; select new output paths when reproducing.
Temporary wheel environments are disposable; all persistent evidence is here.

## Limits of this verification

The complete model backward pass and optimizer update are intentionally
unexecuted. No training or baseline evaluation has started. The held-out
evaluation protocol is defined, but a synthetic-task evaluation runner has not
been added. Human review and baseline collection precede any authorized
training run. Memory/runtime estimates in the guide are planning estimates.
No scientific-repair or generalization claim follows from these tests.
