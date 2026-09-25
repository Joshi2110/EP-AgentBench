"""Pinned local MLX inference; no hosted model, shell agent, or hidden repair logic."""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import urllib.request

from .execution import stop

MODEL_ID = 'mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit'
REVISION = 'b3252a2f97102b1fb1571fec2c9b27219a8536be'
MODEL_7B = 'mlx-community/Qwen2.5-Coder-7B-Instruct-4bit'
REVISION_7B = '019cc73c45c770444708a6dd8690c66243cc5c80'
PINNED_MODELS = {MODEL_ID: (REVISION, 2_000_000_000), MODEL_7B: (REVISION_7B, 5_000_000_000)}


def download(destination, *, model_id=MODEL_ID):
    """Explicit separate download of an allowlisted revision; hash every file."""
    if model_id not in PINNED_MODELS:
        raise ValueError('Download requires a reviewed pinned model')
    revision, byte_limit = PINNED_MODELS[model_id]
    def fetch(url):
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.load(response)
    metadata = fetch(f'https://huggingface.co/api/models/{model_id}/revision/{revision}?blobs=true')
    if metadata['sha'] != revision or metadata.get('cardData', {}).get('license') != 'apache-2.0':
        raise ValueError("Unexpected model revision or license")
    members = [s for s in metadata['siblings'] if s['rfilename'] != '.gitattributes']
    total = sum(s['size'] for s in members)
    if total > byte_limit:
        raise ValueError("Model exceeds its reviewed download size limit")
    destination.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for member in members:
        name = member['rfilename']
        if Path(name).name != name or not name.endswith(('.json', '.txt', '.md', '.safetensors')):
            raise ValueError("Unexpected model file")
        url = f'https://huggingface.co/{model_id}/resolve/{revision}/{name}'
        temporary = destination / (name + '.partial')
        digest, count = hashlib.sha256(), 0
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open('xb') as target:
            while block := source.read(1024 * 1024):
                count += len(block)
                if count > member['size']:
                    raise ValueError("Download exceeds declared file size")
                target.write(block)
                digest.update(block)
        expected = member.get('lfs', {}).get('sha256')
        if count != member['size'] or (expected and digest.hexdigest() != expected):
            raise ValueError("Model file integrity check failed")
        temporary.rename(destination / name)
        hashes[name] = digest.hexdigest()
        print(f'Downloaded {name}: {count} bytes', flush=True)
    manifest = {'model_id': model_id, 'revision': revision, 'license': 'apache-2.0',
                'download_bytes': total, 'sha256': hashes}
    (destination / 'epagent-model.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


class BackendError(RuntimeError):
    pass


class ContextLimit(BackendError):
    pass


def configure_stop_tokens(tokenizer):
    # This conversion's model config ends on <|endoftext|>, while its chat
    # tokenizer ends a turn on <|im_end|>. Honor both without editing model files.
    if not tokenizer.eos_token:
        raise ValueError('The chat tokenizer must define an end-of-turn token')
    tokenizer.add_eos_token(tokenizer.eos_token)
    return sorted(tokenizer.eos_token_ids)


def adapter_manifest(directory, loaded=False):
    """Fingerprint precisely the two files MLX-LM loads, not incidental checkpoints."""
    if directory is None:
        return {'requested': False, 'loaded': False, 'path': None, 'id': None, 'config': None, 'sha256': {}}
    path = Path(directory).resolve()
    hashes = {}
    for name in ['adapter_config.json', 'adapters.safetensors']:
        member = path / name
        if member.is_symlink() or not member.is_file():
            raise ValueError('Adapter requires regular config and weight files')
        hashes[name] = hashlib.sha256(member.read_bytes()).hexdigest()
    config = json.loads((path / 'adapter_config.json').read_text())
    if config.get('fine_tune_type') != 'lora':
        raise ValueError('Only LoRA adapters are supported')
    ident = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {'requested': True, 'loaded': loaded, 'path': str(path), 'id': ident,
            'config': config, 'sha256': hashes}


def verify_loaded_adapter(model, adapter):
    # MLX-LM loads adapters with strict=False. Reject silently ignored/incomplete
    # weight files before reporting success or generating any response.
    if not adapter['requested']:
        return
    import mlx.core as mx
    from mlx.utils import tree_flatten
    weights = mx.load(str(Path(adapter['path']) / 'adapters.safetensors'))
    actual = {n: v for n, v in tree_flatten(model.parameters()) if n.endswith(('.lora_a', '.lora_b'))}
    if not actual or set(weights) != set(actual):
        raise ValueError('Adapter weights must cover exactly the configured LoRA matrices')
    if any(v.shape != actual[n].shape or not mx.array_equal(v, actual[n]).item() for n, v in weights.items()):
        raise ValueError('Loaded adapter matrices do not match the selected weights')


class MLXBackend:
    def __init__(self, model_dir, config):
        self.model_dir, self.config = Path(model_dir).resolve(), dict(config)
        self.process = None
        self.stderr = None
        self.metadata = json.loads((self.model_dir / 'epagent-model.json').read_text())
        self.metadata['backend'] = 'mlx-lm'
        selected = PINNED_MODELS.get(self.metadata['model_id'])
        if selected is None or self.metadata['revision'] != selected[0]:
            raise ValueError("This backend requires a reviewed pinned model revision")
        self.metadata['adapter'] = adapter_manifest(config.get('adapter_dir'))
        self.config['adapter_dir'] = self.metadata['adapter']['path']
        self.config['adapter_expected'] = self.metadata['adapter']

    def start(self, control):
        self.stderr = (control / 'inference.stderr').open('wb')
        # Local loading only. No authentication variables or private conversation
        # are passed into inference. The worker receives exactly the recorded messages.
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(control), 'TMPDIR': str(control),
               'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false',
               'LANG': 'en_US.UTF-8'}
        self.process = subprocess.Popen([sys.executable, '-m', 'epagent.mlx_backend', str(self.model_dir),
                                        json.dumps(self.config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=self.stderr, env=env, start_new_session=True)
        self.buffer = bytearray()

    def generate(self, messages, seconds, emit):
        try:
            return self._generate(messages, seconds, emit)
        except TimeoutError:
            raise
        except (OSError, ValueError) as exc:
            raise BackendError(f'Inference protocol failed: {type(exc).__name__}: {exc}') from exc

    def _generate(self, messages, seconds, emit):
        self.process.stdin.write((json.dumps({'messages': messages}) + '\n').encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + seconds
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while True:
                while b'\n' in self.buffer:
                    line, _, rest = self.buffer.partition(b'\n')
                    self.buffer = bytearray(rest)
                    event = json.loads(line)
                    emit('model_' + event['event'], event)
                    if event['event'] == 'ready':
                        self.metadata.update(event['metadata'])
                    elif event['event'] == 'context_limit':
                        raise ContextLimit('Model context budget reached; history was not silently truncated')
                    elif event['event'] == 'error':
                        raise BackendError(event['message'])
                    elif event['event'] == 'done':
                        return event
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError('Episode wall-time budget reached during inference')
                if selector.select(min(left, 0.1)):
                    chunk = os.read(self.process.stdout.fileno(), 65536)
                    if not chunk:
                        raise BackendError('Local inference process exited; see inference.stderr')
                    self.buffer.extend(chunk)
                    if len(self.buffer) > 2_000_000:
                        raise BackendError('Inference event exceeds size limit')

    def close(self):
        if self.process is not None:
            stop(self.process)
            self.process.stdin.close()
            self.process.stdout.close()
        if self.stderr is not None:
            self.stderr.close()


def worker(model_dir, config):
    import resource
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    def emit(event, **data):
        print(json.dumps({'event': event, **data}, allow_nan=False), flush=True)

    model_dir = Path(model_dir)
    manifest = json.loads((model_dir / 'epagent-model.json').read_text())
    # Resource guard for the authorized 16 GB development machine. This does not
    # alter sampling, context, cache precision, or any historical 1.5B run.
    memory_limit = 7 * 1024**3 if manifest['model_id'] == MODEL_7B else None
    if memory_limit is not None:
        mx.set_memory_limit(memory_limit)
    for name, expected in manifest['sha256'].items():
        digest = hashlib.sha256()
        with (model_dir / name).open('rb') as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError('Model digest mismatch: ' + name)
    mx.random.seed(config['seed'])
    adapter = adapter_manifest(config.get('adapter_dir'))
    if adapter != config.get('adapter_expected', adapter):
        raise ValueError('Adapter changed between episode selection and worker loading')
    model, tokenizer = load(str(model_dir), tokenizer_config={'trust_remote_code': False},
                            adapter_path=adapter['path'])
    verify_loaded_adapter(model, adapter)
    if adapter_manifest(config.get('adapter_dir')) != adapter:
        raise ValueError('Adapter changed during loading')
    adapter['loaded'] = adapter['requested']
    stop_token_ids = configure_stop_tokens(tokenizer)
    mx.set_cache_limit(256 * 1024 * 1024)
    emit('ready', metadata={'model_id': manifest['model_id'], 'revision': manifest['revision'],
                           'adapter': adapter, 'mlx_lm_version': importlib.metadata.version('mlx-lm'),
                           'mlx_version': importlib.metadata.version('mlx'),
                           'transformers_version': importlib.metadata.version('transformers'),
                           'chat_template_sha256': hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
                           'stop_token_ids': stop_token_ids,
                           **({'mlx_memory_limit_bytes': memory_limit} if memory_limit is not None else {}),
                           'inference': 'local MLX; offline; no proprietary model'})
    for line in sys.stdin:
        request = json.loads(line)
        tokens = tokenizer.apply_chat_template(request['messages'], tokenize=True, add_generation_prompt=True)
        if len(tokens) + config['max_tokens'] > config['context_tokens']:
            emit('context_limit', prompt_tokens=len(tokens))
            continue
        started = time.monotonic()
        emit('start', prompt_token_ids=tokens, prompt_tokens=len(tokens))
        parts, ids, exposes_logprobs = [], [], False
        for response in stream_generate(model, tokenizer, prompt=tokens, max_tokens=config['max_tokens'],
                                        sampler=make_sampler(temp=config['temperature'])):
            parts.append(response.text)
            ids.append(int(response.token))
            exposes_logprobs |= hasattr(response, 'logprobs')
            emit('chunk', text=response.text, token_id=int(response.token))
        emit('done', text=''.join(parts), generated_token_ids=ids,
             prompt_tokens=len(tokens), generation_tokens=len(ids),
             finish_reason=response.finish_reason, elapsed_seconds=time.monotonic() - started,
             peak_mlx_bytes=mx.get_peak_memory(), peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
             token_logprobs=None, backend_exposes_logprobs=exposes_logprobs,
             logprobs_recorded=False, logprobs_note='Adapter does not record log-probabilities; none inferred.')


if __name__ == '__main__':
    try:
        worker(sys.argv[1], json.loads(sys.argv[2]))
    except Exception as exc:
        print(json.dumps({'event': 'error', 'message': f'{type(exc).__name__}: {exc}'[:1000]}), flush=True)
        raise
