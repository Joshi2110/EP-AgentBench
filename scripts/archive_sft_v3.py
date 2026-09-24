"""Curate the completed v3 evidence; preserve raw bytes locally and exclude weights."""
import argparse
import json
from pathlib import Path
import re

from archive_sft_v2 import sha, read, save


def archive(root, out):
    control = root / 'sft-runs/controlled-v3-experiment'
    inventory = read(control / 'artifact-sha256.json')
    for name, item in inventory['files'].items():
        assert sha(root / name) == item['sha256'], name
    training = root / 'sft-runs/tool-use-lora-v3'
    run = read(training / 'run.json')
    assert run['status'] == 'complete' and run['updates_requested'] == 138
    for name, expected in run['checkpoint_sha256'].items():
        assert sha(training / name) == expected
    for name, expected in run['prepared']['model']['sha256'].items():
        assert sha(root / '.epagent-models/qwen2.5-coder-1.5b-4bit' / name) == expected
    originals = []
    for arm in ['base', 'adapted']:
        folder = root / f'attempts/tool-recovery-v3-{arm}'
        suite = read(folder / 'suite.json')
        assert suite['scorable_cases'] == 4 and suite['primary_successes'] == 0
        originals.append(folder / 'suite.json')
        for case in suite['cases']:
            report = Path(case['report'])
            r = read(report)
            assert r['initial_sha256'] == r['final_sha256'] and not r['modified_files']
            assert r['model']['adapter']['loaded'] == (arm == 'adapted')
            if arm == 'adapted':
                for name, expected in r['model']['adapter']['sha256'].items():
                    assert sha(training / name) == expected
            originals.extend(report.parent / name for name in ['report.json', 'trajectory.jsonl', 'conversation.json', 'changes.diff'])
            for sub in ['initial', 'workspace']:
                originals.extend(p for p in (report.parent / sub).rglob('*') if p.is_file())
    originals.extend(control / name for name in [
        'result.json', 'report.md', 'analysis.json', 'trajectory-review.json', 'preflight.json',
        'base-execution.json', 'train-execution.json', 'adapted-execution.json',
        'train-verification.json', 'comparability-verification.json', 'cleanup.json',
        'preservation-verification.json', 'verification-notes.json', 'artifact-sha256.json',
        'run_stage.py', 'base.stdout.log', 'base.stderr.log', 'train.stdout.log',
        'train.stderr.log', 'adapted.stdout.log', 'adapted.stderr.log'])
    originals.extend(training / name for name in ['run.json', 'metrics.jsonl', 'adapter_config.json'])
    originals.append(root / 'sft-runs/reviewed-prepared-v3/manifest.json')
    out.mkdir(parents=True, exist_ok=False)
    mapping = {}
    for source in originals:
        name = source.relative_to(root).as_posix()
        raw = source.read_bytes().decode('utf-8')
        clean = raw.replace(str(root), '<REPOSITORY>')
        removed = []
        if source == control / 'preflight.json':
            value = json.loads(clean)
            value.pop('prior_processes')
            removed = ['prior_processes (unrelated process state)']
            clean = json.dumps(value, indent=2) + '\n'
        assert not re.search(r'/(?:Users|home|private/var|var/folders|opt/homebrew)/', clean), name
        if source.name == 'trajectory.jsonl':
            before = [json.loads(s) for s in raw.splitlines()]
            after = [json.loads(s) for s in clean.splitlines()]
            assert len(before) == len(after)
            for a, b in zip(before, after):
                if a['event'] in ['model_request', 'model_start', 'model_chunk', 'assistant', 'tool_call', 'tool_result', 'setup_tool_call', 'setup_tool_result']:
                    assert a == b, (name, a['event'])
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(clean.encode('utf-8'))
        mapping[name] = {'raw_sha256': sha(source), 'archived_sha256': sha(target),
                         'repository_prefix_replacements': raw.count(str(root)), 'removed_fields': removed}
    save(out / 'archive-manifest.json', {'schema': 'epagent.private-archive.v1',
        'source_commit': 'cd900043565a13fa10409ab755f6e1e1ca461f74',
        'verified_raw_inventory_files': len(inventory['files']),
        'raw_inventory_sha256': sha(control / 'artifact-sha256.json'),
        'normalization': 'Repository prefix becomes <REPOSITORY>; omit unrelated prior_processes in preflight only. Raw bytes remain local.',
        'model_visible_event_content_unchanged': True, 'frozen_scores_unchanged': True,
        'files': mapping, 'excluded_weights': run['checkpoint_sha256']})
    for name, item in inventory['files'].items():
        assert sha(root / name) == item['sha256'], name
    print(json.dumps({'archived_files': len(mapping), 'verified_raw_files': len(inventory['files'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    archive(Path(__file__).resolve().parents[1], args.out)
