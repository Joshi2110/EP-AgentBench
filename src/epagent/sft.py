"""Small offline preparation / read-only inspection / explicit MLX-LM SFT commands."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

from .mlx_backend import MODEL_ID, REVISION, configure_stop_tokens
from .sft_data import assistant_loss, digest, reviewed_examples, tokenize_example, write_json


def local_model(path):
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    path = Path(path).resolve()
    manifest = json.loads((path / 'epagent-model.json').read_text())
    if manifest['model_id'] != MODEL_ID or manifest['revision'] != REVISION:
        raise ValueError('Use the reviewed pinned local Qwen model')
    for name, expected in manifest['sha256'].items():
        if Path(name).name != name or digest(path / name) != expected:
            raise ValueError('Local model file/hash mismatch: ' + name)
    return manifest


def config_at(path):
    config = json.loads(Path(path).read_text())
    return validate_config(config)


def validate_config(config):
    for name in ['seed', 'iterations', 'batch_size', 'max_seq_length', 'num_layers', 'val_batches']:
        if type(config[name]) is not int:
            raise ValueError('Integer configuration required: ' + name)
    if (config.get('schema') != 'epagent.sft-config.v1' or config['batch_size'] != 1
            or not 1 <= config['iterations'] <= 200 or not 128 <= config['max_seq_length'] <= 2048
            or not 1 <= config['num_layers'] <= 4 or config['lora_parameters']['rank'] not in (4, 8)
            or config['lora_parameters']['keys'] != ['self_attn.q_proj', 'self_attn.v_proj']
            or config['val_batches'] != -1 or not 0 < config['learning_rate'] <= 0.001
            or not config['grad_checkpoint']):
        raise ValueError('Configuration exceeds the reviewed small SFT envelope')
    for key in ['steps_per_report', 'steps_per_eval', 'steps_per_save']:
        if type(config[key]) is not int or config[key] < 1:
            raise ValueError('Reporting/evaluation/save intervals must be positive integers')
    return config


def prepare(trajectories, model_dir, config_file, protocol_file, out):
    from mlx_lm.utils import load_tokenizer
    config = config_at(config_file)
    protocol = json.loads(Path(protocol_file).read_text())
    if (protocol.get('schema') != 'epagent.sft-protocol.v1'
            or protocol['training_iterations'] != config['iterations']
            or protocol['model_id'] != MODEL_ID or protocol['revision'] != REVISION):
        raise ValueError('Training configuration and registered evaluation protocol disagree')
    model = local_model(model_dir)
    examples = reviewed_examples(trajectories)
    eos = json.loads((Path(model_dir) / 'config.json').read_text())['eos_token_id']
    tokenizer = load_tokenizer(Path(model_dir), {'trust_remote_code': False}, eos_token_ids=eos)
    stops = configure_stop_tokens(tokenizer)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    files, counts = {}, {}
    for split, rows in examples.items():
        encoded = [tokenize_example(row, tokenizer, config['max_seq_length']) for row in rows]
        for name, data in [(split + '.jsonl', rows), (split + '.tokens.jsonl', encoded)]:
            path = out / name
            path.write_text(''.join(json.dumps(row) + '\n' for row in data))
            files[name] = digest(path)
        counts[split] = {'episodes': len({r['episode_id'] for r in rows}), 'examples': len(rows),
                         'supervised_tokens': sum(r['supervised_tokens'] for r in encoded),
                         'max_tokens': max(r['length'] for r in encoded)}
    metadata = {'schema': 'epagent.sft-prepared.v1', 'model': model, 'config': config,
        'config_sha256': digest(config_file), 'protocol_sha256': digest(protocol_file),
        'protocol': protocol,
        'converter_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('sft*.py')},
        'review_manifest_sha256': digest(Path(trajectories) / 'reviews.json'),
        'files': files, 'counts': counts, 'stop_token_ids': stops,
        'chat_template_sha256': hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
        'versions': {name: importlib.metadata.version(name) for name in ['mlx-lm', 'mlx', 'transformers']},
        'python': platform.python_version(), 'loss': 'final assistant content and EOS only; half-open token interval',
        'truncation': 'forbidden', 'training_performed': False}
    write_json(out / 'manifest.json', metadata)
    return metadata


def load_prepared(directory):
    directory = Path(directory)
    metadata = json.loads((directory / 'manifest.json').read_text())
    if metadata['schema'] != 'epagent.sft-prepared.v1':
        raise ValueError('Unrecognized prepared dataset')
    validate_config(metadata['config'])
    for name, expected in metadata['files'].items():
        if Path(name).name != name or digest(directory / name) != expected:
            raise ValueError('Prepared dataset hash mismatch')
    sets = {}
    for split in ['train', 'valid']:
        rows = [json.loads(s) for s in (directory / (split + '.tokens.jsonl')).read_text().splitlines()]
        for row in rows:
            if not 0 < row['offset'] < row['length'] == len(row['tokens']) <= metadata['config']['max_seq_length']:
                raise ValueError('Invalid supervision boundary or sequence length')
        sets[split] = [(row['tokens'], row['offset']) for row in rows]
        if not rows:
            raise ValueError('Empty training/validation split')
    return metadata, sets


def adapt(model_dir, config):
    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.tuner.utils import linear_to_lora_layers
    from mlx.utils import tree_flatten
    mx.random.seed(config['seed'])
    model, tokenizer = load(str(model_dir), tokenizer_config={'trust_remote_code': False})
    stops = configure_stop_tokens(tokenizer)
    model.freeze()
    linear_to_lora_layers(model, config['num_layers'], config['lora_parameters'])
    trainable = tree_flatten(model.trainable_parameters())
    if not trainable or any(not name.endswith(('.lora_a', '.lora_b')) for name, _ in trainable):
        raise ValueError('Only LoRA adapter matrices may be trainable')
    mx.eval(model.parameters())
    mx.set_cache_limit(256 * 1024 * 1024)
    return model, {'trainable_parameters': sum(value.size for _, value in trainable),
                   'trainable_names': [name for name, _ in trainable], 'stop_token_ids': stops,
                   'peak_mlx_bytes_before_training': mx.get_peak_memory()}


def train(prepared, model_dir, out):
    """The only weight-updating entry point. Never called by prepare or inspect."""
    import mlx.core as mx
    import mlx.optimizers as optim
    import numpy as np
    import resource
    from mlx_lm.tuner.trainer import TrainingArgs, evaluate, train as mlx_train
    metadata, sets = load_prepared(prepared)
    actual = local_model(model_dir)
    if actual != metadata['model']:
        raise ValueError('Prepared tokenizer/model provenance does not match local model')
    for name, version in metadata['versions'].items():
        if importlib.metadata.version(name) != version:
            raise ValueError('Training library changed since preparation: ' + name)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    config = metadata['config']
    np.random.seed(config['seed'])
    model, adapter_info = adapt(model_dir, config)
    write_json(out / 'adapter_config.json', {'fine_tune_type': 'lora', 'num_layers': config['num_layers'],
                                           'lora_parameters': config['lora_parameters']})
    manifest = {'schema': 'epagent.sft-run.v1', 'status': 'running', 'prepared': metadata,
                'prepared_manifest_sha256': digest(Path(prepared) / 'manifest.json'),
                'adapter': adapter_info, 'updates_requested': config['iterations'],
                'source_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('sft*.py')},
                'host': {'system': platform.system(), 'machine': platform.machine(), 'python': platform.python_version()}}
    write_json(out / 'run.json', manifest)
    started = time.monotonic()
    with (out / 'metrics.jsonl').open('x') as log:
        def record(kind, info):
            log.write(json.dumps({'event': kind, **info}, allow_nan=False) + '\n')
            log.flush()
        class Metrics:
            def on_train_loss_report(self, info):
                record('train_loss', info)
            def on_val_loss_report(self, info):
                record('validation_loss', info)
        args = TrainingArgs(batch_size=1, iters=config['iterations'], val_batches=-1,
            steps_per_report=config['steps_per_report'], steps_per_eval=config['steps_per_eval'],
            steps_per_save=config['steps_per_save'], max_seq_length=config['max_seq_length'],
            adapter_file=out / 'adapters.safetensors', grad_checkpoint=config['grad_checkpoint'],
            clear_cache_threshold=256 * 1024 * 1024)
        try:
            mlx_train(model=model, optimizer=optim.Adam(learning_rate=config['learning_rate']),
                      train_dataset=sets['train'], val_dataset=sets['valid'], args=args,
                      loss=assistant_loss, training_callback=Metrics())
            if not (out / 'adapters.safetensors').is_file():
                raise ValueError('Trainer returned without the final adapter checkpoint')
            final_loss = evaluate(model, sets['valid'], batch_size=1, num_batches=-1,
                                  max_seq_length=config['max_seq_length'], loss=assistant_loss)
            record('final_validation_loss', {'iteration': config['iterations'], 'val_loss': final_loss})
            manifest.update(status='complete', final_validation_loss=final_loss,
                            checkpoint_sha256={p.name: digest(p) for p in out.glob('*.safetensors')})
        except BaseException as exc:
            manifest.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            manifest.update(elapsed_seconds=time.monotonic() - started, peak_mlx_bytes=mx.get_peak_memory(),
                            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            write_json(out / 'run.json', manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare', help='Convert/tokenize reviewed demonstrations; no weight updates')
    prep.add_argument('--trajectories', type=Path, required=True)
    prep.add_argument('--config', type=Path, required=True)
    prep.add_argument('--protocol', type=Path, required=True)
    inspect = commands.add_parser('inspect', help='Load base and initialize LoRA in memory; no training or checkpoint')
    inspect.add_argument('--config', type=Path, required=True)
    training = commands.add_parser('train', help='Explicitly start the reviewed training run')
    training.add_argument('--prepared', type=Path, required=True)
    for command in [prep, inspect, training]:
        command.add_argument('--model-dir', type=Path, required=True)
        command.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = prepare(args.trajectories, args.model_dir, args.config, args.protocol, args.out)
        elif args.command == 'inspect':
            if args.out.exists():
                raise ValueError('Inspection output already exists')
            local_model(args.model_dir)
            _, info = adapt(args.model_dir, config_at(args.config))
            result = {'training_performed': False, 'optimizer_steps': 0, **info}
            write_json(args.out, result)
        else:
            result = train(args.prepared, args.model_dir, args.out)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, ImportError) as exc:
        print(f'epagent-sft: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
