"""Allowlisted private archive of both development episodes; never rerun them."""
import json
from pathlib import Path
import re

from archive_sft_v2 import read, save, sha


def archive(root):
    control = root / 'sft-runs/replace-lines-7b-engineering'
    inventory = read(control / 'artifact-sha256.json')['files']
    for name, item in inventory.items():
        assert sha(root / name) == item['sha256'], name
    sources = []
    for arm in ['base', '7b']:
        folder = root / f'attempts/replace-lines-{arm}-smoke'
        sources += [folder / n for n in ['registration.json', 'result.json', 'cleanup.json']]
        report = read(folder / 'result.json')
        assert not report['development']['repair_passed']
        episode = Path(report['paths']['report']).parent
        sources += [episode / n for n in ['report.json', 'trajectory.jsonl', 'conversation.json', 'changes.diff']]
        for sub in ['initial', 'workspace']:
            sources += [p for p in (episode / sub).rglob('*') if p.is_file()]
    sources += [root / 'attempts/replace-lines-7b-smoke' / n for n in ['comparison.json', 'comparison.md']]
    # No model tensors, cache/control directories, private path inventories or
    # machine package-install logs. Raw originals remain unchanged locally.
    sources += [control / n for n in [
        'analyze.py', 'artifact-sha256.json', 'commands.md', 'compatibility.patch',
        'compatibility-source.json', 'comparability-before.json', 'compatibility.json',
        'compatibility-loaded-critical.json', 'tokenizer-check.json', 'native-template.diff',
        'download.log', 'huggingface-metadata.json', 'adapter-tests.log', 'selection-tests.log',
        'tool-tests.log', 'final-verification.json', 'preparation-status.json',
        'compatibility.stderr.log', 'compatibility-2.stderr.log', 'compatibility-3.stderr.log',
        'compatibility-4.stdout.log', 'compatibility-4.stderr.log']]
    sources += [root / '.epagent-models/qwen2.5-coder-7b-4bit/epagent-model.json']
    sources += [root / 'src/epagent' / n for n in ['tools.py', 'episode.py', 'execution.py', 'mlx_backend.py', 'development.py']]
    sources += [root / 'scripts/run_development_smoke.py', root / 'tests/test_model_selection.py']
    out = root / 'artifacts/ep-agent/7b-development-smoke'
    out.mkdir(parents=True, exist_ok=False)
    mapping = {}
    for source in sources:
        name = source.relative_to(root).as_posix()
        raw = source.read_bytes().decode('utf-8')
        clean = raw.replace(str(root), '<REPOSITORY>')
        assert not re.search(r'/(?:Users|home|private/var|var/folders)/', clean), name
        if source.name == 'trajectory.jsonl':
            for a, b in zip(raw.splitlines(), clean.splitlines()):
                before, after = json.loads(a), json.loads(b)
                if before['event'] in ['model_request', 'model_start', 'model_chunk', 'assistant', 'tool_call', 'tool_result']:
                    assert before == after, (name, before['event'])
        if 'workspace' in source.parts or 'initial' in source.parts or source.name == 'conversation.json':
            assert raw == clean, name
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(clean.encode('utf-8'))
        mapping[name] = {'raw_sha256': sha(source), 'archived_sha256': sha(target),
                         'repository_prefix_replacements': raw.count(str(root))}
    save(out / 'archive-manifest.json', {
        'source_head': '967e8517728c68a97487f931a0ec25a4ffece9d8',
        'source_compatibility_patch_sha256': sha(control / 'compatibility.patch'),
        'normalization': 'Repository prefixes in metadata/terminal traceback become <REPOSITORY>. '
                         'Model-visible events, generated responses, source bytes and conversations are unchanged.',
        'raw_evidence_retained_locally': True, 'files': mapping,
        'verified_original_inventory_entries': len(inventory),
        'limitations': 'One-episode development comparison, not an estimate of model-size effects.',
        'no_inference_or_rescoring': True})
    print(json.dumps({'archived_files': len(mapping), 'verified_inventory_entries': len(inventory)}))


if __name__ == '__main__':
    archive(Path(__file__).resolve().parents[1])
