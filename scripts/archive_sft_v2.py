"""Verify and archive the completed v2 experiment. Never runs a model or changes raw evidence."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from epagent.tools import parse_call


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def transitions(calls):
    return dict(Counter(a['tool'] + ' -> ' + b['tool'] for a, b in zip(calls, calls[1:])))


def diagnosis(root):
    result = {'training': {}, 'arms': {}, 'transition_definition':
              'Adjacent actual assistant actions; excluded failed demonstration edits remain in the sequence.'}
    prepared = root / 'sft-runs/reviewed-prepared-v2'
    reviews = read(root / 'data/epagent-sft-v2/trajectories/reviews.json')['episodes']
    for split in ['train', 'valid']:
        rows = lines(prepared / (split + '.jsonl'))
        tokens = lines(prepared / (split + '.tokens.jsonl'))
        counts, weighted, edges = Counter(), Counter(), Counter()
        for row, token in zip(rows, tokens):
            assert (row['episode_id'], row['step']) == (token['episode_id'], token['step'])
            tool, _ = parse_call(row['messages'][-1]['content'])
            counts[tool] += 1
            weighted[tool] += token['supervised_tokens']
        source_edits = recoveries = failed = 0
        for review in reviews:
            if review['split'] != split:
                continue
            events = lines(root / 'data/epagent-sft-v2/trajectories' / review['trace'])
            calls = [e['data'] for e in events if e['event'] == 'tool_call']
            obs = {e['data']['step']: e['data']['observation'] for e in events if e['event'] == 'tool_result'}
            edges.update(transitions(calls))
            for i, call in enumerate(calls):
                if call['tool'] != 'edit_file':
                    continue
                failed += 'error' in obs[call['step']]
                if i and calls[i-1]['tool'] == 'read_file':
                    prior = calls[i-1]
                    text = obs[prior['step']].get('content', '')
                    if (call['arguments']['path'] == prior['arguments']['path']
                            and text.count(call['arguments']['old_text']) == 1
                            and 'error' not in obs[call['step']]):
                        source_edits += 1
                        recoveries += i >= 2 and 'error' in obs[calls[i-2]['step']]
        result['training'][split] = {'examples': len(rows), 'targets_by_tool': dict(counts),
            'supervised_tokens_by_tool': dict(weighted), 'actual_transitions': dict(edges),
            'source_read_then_exact_accepted_edit': source_edits,
            'failed_edit_then_read_then_accepted_edit': recoveries, 'excluded_failed_edits': failed}
    for arm in ['base', 'adapted']:
        suite = read(root / f'attempts/tool-recovery-v2-{arm}/suite.json')
        cases = []
        for case in suite['cases']:
            events = lines(Path(case['report']).with_name('trajectory.jsonl'))
            calls = [e['data'] for e in events if e['event'] == 'tool_call']
            observations = {e['data']['step']: e['data']['observation'] for e in events if e['event'] == 'tool_result'}
            responses = [e['data']['text'] for e in events if e['event'] == 'assistant']
            syntax = schema = 0
            for text in responses:
                try:
                    json.loads(text)
                    syntax += 1
                except ValueError:
                    pass
                try:
                    parse_call(text)
                    schema += 1
                except ValueError:
                    pass
            reads = [observations[c['step']] for c in calls if c['tool'] == 'read_file']
            edits = [c for c in calls if c['tool'] == 'edit_file']
            cases.append({'case': case['case_id'], 'counts': dict(Counter(c['tool'] for c in calls)),
                'transitions': transitions(calls), 'valid_json': syntax, 'schema_valid': schema,
                'reads_identical_and_untruncated': all(o == reads[0] and not o['truncated'] for o in reads),
                'repeated_reads_after_first': len(reads) - 1,
                'edit_old_text_matches_observed_source': [reads[0]['content'].count(c['arguments']['old_text']) for c in edits],
                'repeats_injected_edit': case['behavior']['repeated_injected_rejected_edits']})
        result['arms'][arm] = cases
    result['budget'] = {'updates': 40, 'train_examples': 72, 'completed_passes': 0,
                        'effective_passes': 40 / 72, 'observed_supervised_tokens': 1127,
                        'limitation': 'Per-update example IDs were not recorded. No claim about which specific recovery targets were sampled.'}
    return result


def archive(root, out):
    control = root / 'sft-runs/controlled-v2-experiment'
    inventory = read(control / 'artifact-sha256.json')
    for name, item in inventory['files'].items():
        assert sha(root / name) == item['sha256'], name
    run = read(root / 'sft-runs/tool-use-lora-v2/run.json')
    assert run['status'] == 'complete' and run['updates_requested'] == 40
    for name, expected in run['checkpoint_sha256'].items():
        assert sha(root / 'sft-runs/tool-use-lora-v2' / name) == expected
    for name, expected in run['prepared']['model']['sha256'].items():
        assert sha(root / '.epagent-models/qwen2.5-coder-1.5b-4bit' / name) == expected
    for name, expected in run['prepared']['files'].items():
        assert sha(root / 'sft-runs/reviewed-prepared-v2' / name) == expected
    originals = []
    for arm in ['base', 'adapted']:
        folder = root / f'attempts/tool-recovery-v2-{arm}'
        originals.append(folder / 'suite.json')
        suite = read(folder / 'suite.json')
        assert suite['scorable_cases'] == 4 and suite['primary_successes'] == 0
        for case in suite['cases']:
            report = Path(case['report'])
            r = read(report)
            assert not r['modified_files'] and r['termination_reason'] == 'step_limit'
            assert r['model']['adapter']['loaded'] == (arm == 'adapted')
            assert r['model']['stop_token_ids'] == [151643, 151645]
            if arm == 'adapted':
                for name, expected in r['model']['adapter']['sha256'].items():
                    assert sha(root / 'sft-runs/tool-use-lora-v2' / name) == expected
            originals.extend(report.parent / name for name in ['report.json', 'trajectory.jsonl', 'conversation.json', 'changes.diff'])
            for sub in ['initial', 'workspace']:
                originals.extend(p for p in (report.parent / sub).rglob('*') if p.is_file())
    originals.extend(control / name for name in [
        'result.json', 'report.md', 'analysis.json', 'trajectory-review.json', 'preflight.json',
        'base-execution.json', 'train-execution.json', 'adapted-execution.json',
        'training-verification.json', 'cleanup.json', 'preservation-verification.json'])
    originals.extend(root / 'sft-runs/tool-use-lora-v2' / name for name in ['run.json', 'metrics.jsonl', 'adapter_config.json'])
    originals.append(root / 'sft-runs/reviewed-prepared-v2/manifest.json')
    out.mkdir(parents=True, exist_ok=False)
    mapping = {}
    for source in originals:
        name = source.relative_to(root).as_posix()
        raw = source.read_text()
        clean = raw.replace(str(root), '<REPOSITORY>')
        # Only metadata paths are normalized. Fail closed on any unreviewed private path.
        assert not re.search(r'/(?:Users|private/var|var/folders|home)/', clean), name
        if source.suffix == '.jsonl' and source.name == 'trajectory.jsonl':
            before, after = [json.loads(s) for s in raw.splitlines()], [json.loads(s) for s in clean.splitlines()]
            for a, b in zip(before, after):
                if a['event'] in ['model_request', 'model_start', 'model_chunk', 'assistant', 'tool_call', 'tool_result', 'setup_tool_call', 'setup_tool_result']:
                    assert a == b, (name, a['event'])
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(clean)
        mapping[name] = {'raw_sha256': sha(source), 'archived_sha256': sha(target),
                         'repository_prefix_replacements': raw.count(str(root))}
    save(out / 'diagnosis.json', diagnosis(root))
    save(out / 'archive-manifest.json', {'schema': 'epagent.private-archive.v1',
        'source_commit': 'b5d99aec17362cc1ab4b459454efac90b3800488',
        'verified_raw_inventory_files': len(inventory['files']),
        'raw_inventory_sha256': sha(control / 'artifact-sha256.json'),
        'normalization': 'Replace repository absolute prefix with <REPOSITORY>; no other changes. Raw artifacts retained locally.',
        'model_visible_events_byte_content_unchanged': True,
        'files': mapping, 'excluded_weights': run['checkpoint_sha256']})
    # Recheck originals after writing; archive creation must never mutate them.
    for name, item in inventory['files'].items():
        assert sha(root / name) == item['sha256'], name
    print(json.dumps({'archived_files': len(mapping), 'verified_raw_files': len(inventory['files'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    archive(Path(__file__).resolve().parents[1], args.out)
