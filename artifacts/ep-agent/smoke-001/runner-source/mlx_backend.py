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


def download(destination):
    """Explicit separate download; refuse more than 2 GB, pin and hash every file."""
    def fetch(url):
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.load(response)
    metadata = fetch(f'https://huggingface.co/api/models/{MODEL_ID}/revision/{REVISION}?blobs=true')
    if metadata['sha'] != REVISION or metadata.get('cardData', {}).get('license') != 'apache-2.0':
        raise ValueError("Unexpected model revision or license")
    members = [s for s in metadata['siblings'] if s['rfilename'] != '.gitattributes']
    total = sum(s['size'] for s in members)
    if total > 2_000_000_000:
        raise ValueError("Model exceeds 2 GB; explicit user approval and a reviewed downloader are required")
    destination.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for member in members:
        name = member['rfilename']
        if Path(name).name != name or not name.endswith(('.json', '.txt', '.md', '.safetensors')):
            raise ValueError("Unexpected model file")
        url = f'https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}'
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
    manifest = {'model_id': MODEL_ID, 'revision': REVISION, 'license': 'apache-2.0',
                'download_bytes': total, 'sha256': hashes}
    (destination / 'epagent-model.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


class BackendError(RuntimeError):
    pass


class ContextLimit(BackendError):
    pass


class MLXBackend:
    def __init__(self, model_dir, config):
        self.model_dir, self.config = Path(model_dir).resolve(), config
        self.process = None
        self.stderr = None
        self.metadata = json.loads((self.model_dir / 'epagent-model.json').read_text())
        self.metadata['backend'] = 'mlx-lm'
        if self.metadata['model_id'] != MODEL_ID or self.metadata['revision'] != REVISION:
            raise ValueError("This v0.1 backend requires the reviewed pinned model")

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
    for name, expected in manifest['sha256'].items():
        digest = hashlib.sha256()
        with (model_dir / name).open('rb') as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError('Model digest mismatch: ' + name)
    mx.random.seed(config['seed'])
    model, tokenizer = load(str(model_dir), tokenizer_config={'trust_remote_code': False})
    mx.set_cache_limit(256 * 1024 * 1024)
    emit('ready', metadata={'mlx_lm_version': importlib.metadata.version('mlx-lm'),
                           'mlx_version': importlib.metadata.version('mlx'),
                           'transformers_version': importlib.metadata.version('transformers'),
                           'chat_template_sha256': hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
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
