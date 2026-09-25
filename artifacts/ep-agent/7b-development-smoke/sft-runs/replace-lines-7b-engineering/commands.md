# Authorized preparation and single-episode commands

Public metadata was fetched with Python urllib from:
https://huggingface.co/api/models/mlx-community/Qwen2.5-Coder-7B-Instruct-4bit/revision/main?blobs=true
The returned full revision was pinned before any file download.

Download (caffeinate attached to the downloader process):

```python
from pathlib import Path
from epagent.mlx_backend import download, MODEL_7B
download(Path('.epagent-models/qwen2.5-coder-7b-4bit'), model_id=MODEL_7B)
```

Offline tests and installed worker:

```bash
PYTHONPATH=src EPAGENT_TEST_MLX=1 .venv/bin/python -m unittest discover -s tests -p test_adapters.py -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_replace_lines.py -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_model_selection.py -v
.venv/bin/python -m pip wheel --no-deps --no-build-isolation . --wheel-dir /tmp/epagent-7b-wheel
.venv/bin/python -m pip install --no-deps --force-reinstall /tmp/epagent-7b-wheel/ep_agentbench-0.5.0-py3-none-any.whl
```

Load-only validation (zero forward passes, zero generated responses):

```bash
PYTHONPATH=src HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python sft-runs/replace-lines-7b-engineering/check_compatibility.py
```

The authorized single episode, only after preparation passes:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_development_smoke.py --fixture data/epagent-development/cart-total.json --model-dir .epagent-models/qwen2.5-coder-7b-4bit --out attempts/replace-lines-7b-smoke
```

The unchanged runner refuses to reuse its output directory and attaches caffeinate.
No retry, prompt adjustment, tool-argument transformation, training, adapter, or
Hall evaluation is authorized. Source HEAD remains 967e851; the compatibility
patch and source hashes are preserved separately before inference.
