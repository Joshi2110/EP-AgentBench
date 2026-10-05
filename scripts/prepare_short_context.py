"""Select whole recorded messages; never rewrite a target or observation. No model."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path

from epagent.sft import local_model
from epagent.sft_data import digest, reviewed_examples, tokenize_example, write_json


def minimize(row):
    original = row['messages']
    target = json.loads(original[-1]['content'])
    pairs = []
    for i in range(2, len(original) - 1, 2):
        action = json.loads(original[i]['content'])
        observation = json.loads(original[i + 1]['content'])['tool_result']
        pairs.append((i, action, observation))
    reasons = {0: ['system/tool schema'], 1: ['original task instruction and budget'],
               len(original) - 1: ['unaltered supervised target']}
    def keep(pair, reason):
        if pair:
            for i in (pair[0], pair[0] + 1):
                reasons.setdefault(i, []).append(reason)
    def last(predicate):
        return next((p for p in reversed(pairs) if predicate(p)), None)
    if pairs:
        keep(pairs[-1], 'immediately preceding action and observation')
    keep(last(lambda p: p[1]['tool'] == 'read_file' and p[1]['arguments']['path'] == 'README.md'),
         'task requirements and API contract')
    name = target['tool']
    if name in ('edit_file', 'replace_lines'):
        path = target['arguments']['path']
        keep(last(lambda p: p[1]['tool'] == 'read_file' and p[1]['arguments']['path'] == path),
             'latest exact source and version')
        keep(last(lambda p: p[1]['tool'] == 'read_file' and p[1]['arguments']['path'] == 'checks.py'),
             'shipped test contract')
        keep(last(lambda p: p[2].get('error') or p[2].get('status') == 'python_error'),
             'latest observed failure motivating correction')
    if name in ('run_python', 'finish'):
        keep(last(lambda p: p[1]['tool'] in ('edit_file', 'replace_lines') and not p[2].get('error')),
             'last applied edit and its actual observation')
    if name == 'finish':
        keep(last(lambda p: p[1]['tool'] == 'run_python'), 'observed test result supporting finish')
    kept = sorted(reasons)
    result = deepcopy(row)
    result['messages'] = [deepcopy(original[i]) for i in kept]
    result['message_kinds'] = [row['message_kinds'][i] for i in kept]
    result['context_selection'] = {
        'original_message_count': len(original), 'kept_indices': kept,
        'kept_reasons': {str(i): reasons[i] for i in kept},
        'removed_indices': [i for i in range(len(original)) if i not in reasons],
        'rule': 'Remove older history outside explicit target dependencies; retain whole action/observation pairs'}
    return result


def prepare(out, model_dir, max_length=1024):
    from mlx_lm.utils import load_tokenizer
    from epagent.mlx_backend import configure_stop_tokens
    root = Path(__file__).resolve().parents[1]
    source = root / 'data/epagent-sft-7b-v1'
    model = local_model(model_dir)
    tokenizer = load_tokenizer(Path(model_dir), {'trust_remote_code': False}, eos_token_ids=151643)
    stops = configure_stop_tokens(tokenizer)
    examples = reviewed_examples(source / 'trajectories')
    config = json.loads((source / 'lora-config.json').read_text())
    config['max_seq_length'] = max_length
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    files, counts = {}, {}
    for split, rows in examples.items():
        small = [minimize(r) for r in rows]
        encoded = [tokenize_example(r, tokenizer, max_length) for r in small]
        full = [tokenize_example(r, tokenizer, 8192) for r in rows]
        for a, b in zip(full, encoded):
            assert a['tokens'][a['offset']:] == b['tokens'][b['offset']:]
        for name, data in [(split + '.jsonl', small), (split + '.tokens.jsonl', encoded)]:
            path = out / name
            path.write_text(''.join(json.dumps(r) + '\n' for r in data))
            files[name] = digest(path)
        counts[split] = {'episodes': len({r['episode_id'] for r in rows}), 'examples': len(rows),
            'supervised_tokens': sum(r['supervised_tokens'] for r in encoded),
            'max_tokens': max(r['length'] for r in encoded), 'original_max_tokens': max(r['length'] for r in full),
            'total_tokens': sum(r['length'] for r in encoded), 'original_total_tokens': sum(r['length'] for r in full),
            'removed_messages': sum(len(r['context_selection']['removed_indices']) for r in small),
            'targets_by_tool': dict(Counter(json.loads(r['messages'][-1]['content'])['tool'] for r in small))}
    manifest = {'schema': 'epagent.sft-prepared.v1', 'model': model, 'config': config, 'files': files,
        'counts': counts, 'stop_token_ids': stops, 'effective_training_passes': 2,
        'versions': {n: importlib.metadata.version(n) for n in ['mlx', 'mlx-lm', 'transformers', 'numpy']},
        'chat_template_sha256': hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
        'source_review_sha256': digest(source / 'trajectories/reviews.json'),
        'selector_sha256': digest(Path(__file__)), 'training_performed': False,
        'purpose': 'Experimental context ablation; not the registered Evaluation 02 preparation',
        'truncation': 'forbidden; whole-message selection only; targets and retained observations byte-identical'}
    write_json(out / 'manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--max-length', type=int, default=1024)
    args = p.parse_args()
    print(json.dumps(prepare(args.out, args.model_dir, args.max_length)['counts']))
