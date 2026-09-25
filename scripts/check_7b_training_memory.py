"""Authorization-only, bounded real LoRA forward/backward probe. Zero updates."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from epagent.sft import adapt, load_prepared, local_model
from epagent.sft_data import assistant_loss, digest, write_json

LIMIT = 7 * 1024**3
ACCEPT_PEAK = 6.5 * 1024**3
TIMEOUT = 300


def pressure():
    return int(subprocess.check_output(
        ['/usr/sbin/sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], text=True))


def backward_probe(prepared, model_dir, out):
    """Real training loss, batching, checkpointing and adapter gradients; no optimizer exists."""
    import importlib.metadata
    import resource
    import mlx.core as mx
    import mlx.nn as nn
    from mlx.utils import tree_flatten
    from mlx_lm.tuner.trainer import grad_checkpoint, iterate_batches
    metadata, sets = load_prepared(prepared)
    if local_model(model_dir) != metadata['model']:
        raise ValueError('Model differs from prepared identity')
    for name, version in metadata['versions'].items():
        if importlib.metadata.version(name) != version:
            raise ValueError('Software differs from prepared identity: ' + name)
    mx.set_memory_limit(LIMIT)
    model, info = adapt(model_dir, metadata['config'])
    grad_checkpoint(model.layers[0])
    model.train()
    longest = max(sets['train'] + sets['valid'], key=lambda row: len(row[0]))
    batch = next(iterate_batches([longest], 1, metadata['config']['max_seq_length']))
    before = {name: mx.array(value) for name, value in tree_flatten(model.trainable_parameters())}
    mx.eval(before)
    value_and_grad = nn.value_and_grad(model, assistant_loss)
    step = mx.compile(lambda: value_and_grad(model, *batch),
                      inputs=[model.state, mx.random.state], outputs=[mx.random.state])
    started = time.monotonic()
    (loss, tokens), gradients = step()
    mx.eval(loss, tokens, gradients)
    flat = tree_flatten(gradients)
    finite = bool(mx.isfinite(loss).item()) and all(bool(mx.all(mx.isfinite(v)).item()) for _, v in flat)
    unchanged = all(bool(mx.array_equal(before[n], v).item()) for n, v in
                    tree_flatten(model.trainable_parameters()))
    peak = mx.get_peak_memory()
    result = {'kind': 'real longest-example forward/backward; zero optimizer updates',
              'optimizer_updates': 0, 'parameters_unchanged': unchanged, 'finite_loss_and_gradients': finite,
              'loss': loss.item() if bool(mx.isfinite(loss).item()) else None,
              'supervised_tokens': tokens.item(), 'batch_shape': list(batch[0].shape),
              'peak_mlx_bytes': peak, 'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'forward_backward_seconds': time.monotonic() - started, 'adapter': info,
              'model': metadata['model'], 'prepared_manifest_sha256': digest(Path(prepared) / 'manifest.json'),
              'software': metadata['versions'], 'passed': finite and unchanged and peak <= ACCEPT_PEAK,
              'limitation': 'One backward pass without Adam/update buffers or a sustained training loop. '
                            'This is a memory gate, not a completed training feasibility measurement.'}
    write_json(out / 'probe.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'model-dir', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--confirm-backward', action='store_true', help='Requires separate explicit authorization')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.confirm_backward:
        parser.error('Backward execution requires --confirm-backward and explicit user authorization')
    if args.worker:
        backward_probe(args.prepared, args.model_dir, args.out)
        return 0
    args.out.mkdir(parents=True, exist_ok=False)
    initial = pressure()
    record = {'status': 'blocked', 'initial_pressure': initial, 'optimizer_updates': 0,
              'memory_limit_bytes': LIMIT, 'accept_peak_bytes': ACCEPT_PEAK, 'timeout_seconds': TIMEOUT}
    write_json(args.out / 'supervisor.json', record)
    if initial != 1:
        raise SystemExit('Memory pressure is not normal; no model loaded or backward pass executed')
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--worker']
    process = inhibitor = None
    start = time.monotonic()
    try:
        with (args.out / 'stdout.log').open('x') as stdout, (args.out / 'stderr.log').open('x') as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
            inhibitor = subprocess.Popen(['/usr/bin/caffeinate', '-i', '-w', str(process.pid)])
            record['status'] = 'running'
            while process.poll() is None:
                if time.monotonic() - start > TIMEOUT or pressure() != 1:
                    record['status'] = 'aborted_time_or_pressure'
                    os.killpg(process.pid, signal.SIGKILL)
                    break
                time.sleep(1)
            record['returncode'] = process.wait()
            if record['status'] == 'running':
                result = json.loads((args.out / 'probe.json').read_text()) if record['returncode'] == 0 else {}
                record['status'] = 'passed' if result.get('passed') else 'failed'
    except BaseException as exc:
        record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        if inhibitor is not None:
            inhibitor.terminate(); inhibitor.wait(timeout=10)
        record['elapsed_seconds'] = time.monotonic() - start
        record['child_exited'] = process is None or process.poll() is not None
        write_json(args.out / 'supervisor.json', record)
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
