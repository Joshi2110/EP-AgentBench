"""Archive the completed diagnostic without rerunning or rescoring it."""
import json
from pathlib import Path
import re

from archive_sft_v2 import read, save, sha


def archive(root):
    control = root / 'sft-runs/edit-history-v1-control'
    inventory = read(control / 'artifact-sha256.json')
    for name, item in inventory['files'].items():
        assert sha(root / name) == item['sha256'], name
    out = root / 'artifacts/ep-agent/edit-history-v1'
    out.mkdir(parents=True, exist_ok=False)
    names = [n for n in inventory['files'] if not n.endswith('/protected-before.json')]
    names += ['sft-runs/edit-history-v1-control/artifact-sha256.json',
              'src/epagent/tools.py', 'src/epagent/episode.py', 'src/epagent/mlx_backend.py']
    mapping = {}
    for name in names:
        source = root / name
        raw = source.read_bytes().decode('utf-8')
        clean = raw.replace(str(root), '<REPOSITORY>')
        assert not re.search(r'/(?:Users|home|private/var|var/folders)/', clean), name
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(clean.encode('utf-8'))
        mapping[name] = {'raw_sha256': sha(source), 'archived_sha256': sha(target),
                         'repository_prefix_replacements': raw.count(str(root))}
        # No generated text, prompt or workspace byte is normalized.
        if source.name == 'prompt.json' or 'workspace' in source.parts:
            assert raw == clean, name
        if source.name == 'trace.jsonl':
            for before, after in zip(raw.splitlines(), clean.splitlines()):
                a, b = json.loads(before), json.loads(after)
                if a['event'] != 'model_ready':
                    assert a == b, (name, a['event'])
    save(out / 'archive-manifest.json', {
        'schema': 'epagent.private-archive.v1', 'source_commit': 'b7f962f2be1c409f0fce2d2fa18d5711eace9507',
        'verified_raw_inventory_files': len(inventory['files']), 'files': mapping,
        'normalization': 'Only repository prefixes become <REPOSITORY>. Original raw artifacts remain local.',
        'excluded': ['protected-before.json (private absolute paths)', 'model and adapter weights'],
        'primary_result': '0/8 exact targets',
        'limitation': 'History-present prompts also supplied a concrete object-shaped tool-call example; '
                      'history-absent prompts did not. The causal effect of misleading history is not isolated.'})
    print(json.dumps({'archived_files': len(mapping), 'verified_raw_files': len(inventory['files'])}))


if __name__ == '__main__':
    archive(Path(__file__).resolve().parents[1])
