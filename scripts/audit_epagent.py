"""Offline evidence replay and real-tokenizer audit; never loads model weights or generates."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

from epagent.mlx_backend import MODEL_ID, REVISION, configure_stop_tokens
from epagent.tools import decode_call, parse_call

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'artifacts' / 'ep-agent' / 'smoke-001'


def accepts(function, text):
    try:
        function(text)
        return True
    except (ValueError, TypeError):
        return False


def audit(model_dir):
    manifest = json.loads((ARCHIVE / 'manifest.json').read_text())
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == digest, name
    report = json.loads((ARCHIVE / 'report.json').read_text())
    events = [json.loads(line) for line in (ARCHIVE / 'trajectory.jsonl').read_text().splitlines()]
    responses = [e['data'] for e in events if e['event'] == 'assistant']
    assert len(responses) == report['usage']['completed_generations'] == 12
    assert report['tool_calls'] == report['reward'] == 0 and report['modified_files'] == []
    assert report['grading']['passed'] == 3 and report['grading']['total'] == 13
    assert report['initial_sha256'] == report['final_sha256']
    result = {'schema': 'epagent.audit.v1', 'episode_id': report['episode_id'],
              'inference_performed': False, 'tools_executed': False,
              'archive_hashes_verified': True, 'original_measurements_unchanged': True,
              'original_responses': len(responses), 'original_tool_calls': 0,
              'original_file_edits': 0, 'original_reward': 0, 'original_starter_score': '3/13',
              'raw_json_valid': sum(accepts(json.loads, r['text']) for r in responses),
              'raw_envelope_json_valid': sum(accepts(decode_call, r['text']) for r in responses),
              'raw_tool_schema_valid': sum(accepts(parse_call, r['text']) for r in responses)}
    if model_dir is None or not (model_dir / 'epagent-model.json').is_file():
        return {**result, 'tokenizer_status': 'unverified: pinned local tokenizer unavailable',
                'replay': None}

    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    try:
        from mlx_lm.utils import load_tokenizer
    except ImportError:
        return {**result, 'tokenizer_status': 'unverified: local MLX-LM tokenizer dependencies unavailable',
                'replay': None}
    model_manifest = json.loads((model_dir / 'epagent-model.json').read_text())
    assert model_manifest['model_id'] == MODEL_ID and model_manifest['revision'] == REVISION
    # Verify the actual tokenizer/config files, not a stand-in with assumed IDs.
    checked = {name: digest for name, digest in model_manifest['sha256'].items()
               if name.endswith(('.json', '.txt'))}
    for name, digest in checked.items():
        assert hashlib.sha256((model_dir / name).read_bytes()).hexdigest() == digest, name
    config_eos = json.loads((model_dir / 'config.json').read_text())['eos_token_id']
    tokenizer = load_tokenizer(model_dir, {'trust_remote_code': False}, eos_token_ids=config_eos)
    before = sorted(tokenizer.eos_token_ids)
    token_ids = tokenizer.encode(tokenizer.eos_token, add_special_tokens=False)
    assert token_ids == [tokenizer.eos_token_id]
    rendered = tokenizer.apply_chat_template([
        {'role': 'user', 'content': 'audit-user'},
        {'role': 'assistant', 'content': 'audit-assistant'}],
        tokenize=False, add_generation_prompt=False)
    suffix = rendered.split('audit-assistant', 1)[1]
    assert suffix.strip() == tokenizer.eos_token, 'Chat template termination disagrees with tokenizer EOS'
    configured = configure_stop_tokens(tokenizer)
    assert tokenizer.eos_token_id in configured and set(before) <= set(configured)
    result.update(tokenizer_status='verified against local pinned tokenizer', tokenizer={
        'model_id': MODEL_ID, 'revision': REVISION, 'checked_file_sha256': checked,
        'mlx_lm_version': importlib.metadata.version('mlx-lm'),
        'transformers_version': importlib.metadata.version('transformers'),
        'config_eos_token_id': config_eos, 'tokenizer_eos_token': tokenizer.eos_token,
        'tokenizer_eos_token_id': tokenizer.eos_token_id, 'encoded_eos_token_ids': token_ids,
        'initial_stop_token_ids': before, 'configured_stop_token_ids': configured,
        'chat_template_sha256': hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
        'rendered_chat': rendered, 'assistant_suffix': suffix})
    replay = []
    for response in responses:
        ids = response['generated_token_ids']
        end = next(i for i, token in enumerate(ids) if token in configured)
        # A counterfactual replay of recorded tokens under the corrected stopping
        # rule. No regeneration, arbitrary text extraction, or tool execution.
        stopped = tokenizer.decode(ids[:end])
        row = {'step': response['step'], 'stopped_text': stopped,
               'termination_token_id': ids[end], 'stopped_bare_json_valid': accepts(json.loads, stopped),
               'stopped_envelope_json_valid': accepts(decode_call, stopped),
               'stopped_tool_schema_valid': accepts(parse_call, stopped), 'copied_arguments': {}}
        if row['stopped_tool_schema_valid']:
            name, args = parse_call(stopped)
            row['tool'] = name
            row['copied_arguments'] = {k: v for k, v in args.items() if (k, v) in {
                ('old_text', 'exact existing text'), ('new_text', 'replacement'), ('code', 'print(2 + 2)')}}
        replay.append(row)
    result['replay'] = replay
    result['replay_totals'] = {key: sum(r[key] for r in replay) for key in (
        'stopped_bare_json_valid', 'stopped_envelope_json_valid', 'stopped_tool_schema_valid')}
    result['interpretation'] = 'Parser replay only; no accepted calls or scientific repairs are added to the original episode.'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.model_dir)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('replay', 'tokenizer')}, indent=2))
    raise SystemExit(0 if result['replay'] is not None else 2)
