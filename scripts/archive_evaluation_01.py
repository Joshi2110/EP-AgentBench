"""Allowlisted private archive of both Evaluation 01 arms; never rerun them."""
import json
from pathlib import Path
import re

from archive_sft_v2 import read, save, sha

ARMS = {'baseline': 'attempts/evaluation-01-baseline',
        'verification': 'attempts/evaluation-01-verification'}
FIELDS = ['independent', 'files_changed', 'syntax', 'agent_tests', 'agent_observed_pass',
          'runner_tests', 'visible_passed', 'finish', 'supported_finish', 'schema_errors',
          'tool_errors', 'steps', 'step_limit', 'seconds', 'prompt_tokens', 'gen_tokens']


def row(entry, report):
    m = entry['metrics']
    return {'independent': entry['independent']['passed'],
            'files_changed': len(report['modified_files']),
            'modified_files': report['modified_files'],
            'syntax': m['final_source_syntax'],
            'agent_tests': m['agent_initiated_test_executions'],
            'agent_observed_pass': m['agent_initiated_observed_passes'],
            'runner_tests': m['runner_initiated_test_executions'],
            'visible_passed': m['visible_test_passed_after_episode'],
            'finish': m['finish_called'], 'supported_finish': m['evidence_supported_finish'],
            'schema_errors': m['schema_errors'], 'tool_errors': m['tool_errors'],
            'steps': m['steps'], 'step_limit': m['termination_reason'] == 'step_limit',
            'termination_reason': m['termination_reason'],
            'seconds': round(m['agent_seconds'], 1),
            'prompt_tokens': m['usage']['prompt_tokens'],
            'gen_tokens': m['usage']['generation_tokens'],
            'peak_mlx_bytes': m['usage']['peak_mlx_bytes'],
            'peak_rss_bytes': m['usage']['peak_rss_bytes'],
            'independent_stdout': entry['independent']['stdout'],
            'independent_status': entry['independent']['status']}


def analyze(root):
    arms, order = {}, None
    for arm, run in ARMS.items():
        suite = read(root / run / 'suite/suite.json')
        assert suite['status'] == 'complete' and len(suite['cases']) == 10, arm
        rows = {}
        for entry in suite['cases']:
            rows[entry['fixture']] = row(entry, read(Path(entry['report'])))
        order = order or [c['fixture'] for c in suite['cases']]
        arms[arm] = {'primary': suite['primary'],
                     'independent_successes': suite['independent_successes'],
                     'verification_feedback': suite['verification_feedback'],
                     'model_selection': suite['model_selection'],
                     'protocol_sha256': suite['protocol_sha256'],
                     'fixtures_sha256': suite['fixtures_sha256'],
                     'config': suite['config'], 'start_time': suite['start_time'],
                     'end_time': suite['end_time'], 'fixtures': rows,
                     'totals': {
                         'independent_repairs': sum(r['independent'] for r in rows.values()),
                         'source_changed': sum(1 for r in rows.values() if r['files_changed']),
                         'final_syntax_valid': sum(1 for r in rows.values() if r['syntax'] == 'valid'),
                         'agent_initiated_test_runs': sum(r['agent_tests'] for r in rows.values()),
                         'fixtures_with_agent_tests': sum(1 for r in rows.values() if r['agent_tests']),
                         'runner_initiated_test_runs': sum(r['runner_tests'] for r in rows.values()),
                         'visible_test_passed': sum(r['visible_passed'] for r in rows.values()),
                         'finish_called': sum(r['finish'] for r in rows.values()),
                         'evidence_supported_finish': sum(r['supported_finish'] for r in rows.values()),
                         'reached_step_limit': sum(r['step_limit'] for r in rows.values()),
                         'schema_rejections': sum(r['schema_errors'] for r in rows.values()),
                         'tool_failures': sum(r['tool_errors'] for r in rows.values()),
                         'agent_seconds': round(sum(r['seconds'] for r in rows.values()), 1),
                         'prompt_tokens': sum(r['prompt_tokens'] for r in rows.values()),
                         'generation_tokens': sum(r['gen_tokens'] for r in rows.values()),
                         'peak_mlx_bytes': max(r['peak_mlx_bytes'] for r in rows.values()),
                         'peak_rss_bytes': max(r['peak_rss_bytes'] for r in rows.values())}}
    base, ver = arms['baseline']['fixtures'], arms['verification']['fixtures']
    return {
        'schema': 'epagent.evaluation-01-results.v1',
        'headline': 'Negative result. Verification feedback v3 did not improve independent repair and '
                    'scored lower: baseline 3/10, verification 1/10. Neither arm produced a single '
                    'evidence-supported autonomous workflow.',
        'primary': {'baseline': arms['baseline']['primary'],
                    'verification': arms['verification']['primary']},
        'fixture_order': order,
        'paired': [{'fixture': f, 'family': None,
                    'baseline': {k: base[f][k] for k in FIELDS},
                    'verification': {k: ver[f][k] for k in FIELDS},
                    'independent_change': ('regressed' if base[f]['independent'] and not ver[f]['independent']
                                           else 'improved' if ver[f]['independent'] and not base[f]['independent']
                                           else 'unchanged')} for f in order],
        'regressions': [f for f in order if base[f]['independent'] and not ver[f]['independent']],
        'improvements': [f for f in order if ver[f]['independent'] and not base[f]['independent']],
        'solved_in_both': [f for f in order if base[f]['independent'] and ver[f]['independent']],
        'solved_in_neither': [f for f in order if not base[f]['independent'] and not ver[f]['independent']],
        'arms': arms,
        'observed_mechanism': {
            'baseline_terminations': 'finish_tool in 10 of 10',
            'verification_terminations': 'step_limit in 10 of 10; finish was never called',
            'prompt_growth': 'baseline mean 490 tokens on turn one rising to 1,227 on the last; '
                             'verification 689 rising to 4,048, peak 6,127',
            'context_limit_hit': False,
            'reading': 'The verification arm consumed its twelve turns without finishing and used 3.4x '
                       'the wall time and 4.5x the prompt tokens. Budget was exhausted by turn count, '
                       'not by context truncation. Ten fixtures cannot establish that the feedback '
                       'caused the two regressions.'},
        'separation': 'Runner-initiated executions are never counted as agent-initiated testing, and a '
                      'visible-test pass is never counted as a hidden-test pass. In the baseline four '
                      'fixtures passed the visible test while three passed the hidden test.',
        'repairs_versus_workflows': 'The three baseline successes are functionally successful repairs '
                                    'only. None ran the workspace test after its last change, so none '
                                    'is evidence-supported. Zero complete autonomous workflows overall.',
        'development_provenance': 'The agent architecture, tools, feedback mechanisms and graders were '
                                  'developed across four prior cart-total episodes. Those are '
                                  'development evidence and form no part of this campaign.',
        'limitations': 'Ten synthetic fixtures, one attempt per fixture per arm, temperature zero. No '
                       'uncertainty estimate, no significance claim, no generalization beyond these '
                       'fixtures. The overall architecture is not independently pre-registered.'}


def archive(root):
    out = root / 'artifacts/ep-agent/evaluation-01'
    out.mkdir(parents=True, exist_ok=False)
    sources = [root / 'data/epagent-evaluation-01' / n
               for n in ['fixtures.json', 'protocol.json', 'validation.json', 'README.md']]
    sources += [root / 'scripts/build_evaluation_01.py', root / 'scripts/run_evaluation_01.py',
                root / 'src/epagent/assessment.py', root / 'src/epagent/verification.py',
                root / 'src/epagent/episode.py', root / 'src/epagent/development.py',
                root / 'src/epagent/tools.py', root / 'src/epagent/mlx_backend.py',
                root / 'tests/test_evaluation_01.py',
                root / '.epagent-models/qwen2.5-coder-7b-4bit/epagent-model.json']
    for run in ARMS.values():
        folder = root / run
        sources += [folder / n for n in ['registration.json', 'cleanup.json']]
        sources.append(folder / 'suite/suite.json')
        for episode in sorted((folder / 'suite/episodes').iterdir()):
            sources += [episode / n for n in
                        ['report.json', 'trajectory.jsonl', 'conversation.json', 'changes.diff']]
            for sub in ['initial', 'workspace']:
                sources += sorted(p for p in (episode / sub).rglob('*') if p.is_file())
    mapping, touched = {}, {}
    for source in sources:
        name = source.relative_to(root).as_posix()
        raw = source.read_bytes().decode('utf-8')
        clean = raw.replace(str(root), '<REPOSITORY>')
        assert not re.search(r'/(?:Users|home|private/var|var/folders)/', clean), name
        # Lossless and exactly reversible: the substitution is the only difference.
        assert clean.replace('<REPOSITORY>', str(root)) == raw, name
        if source.name == 'trajectory.jsonl':
            for line in raw.splitlines():
                if str(root) in line:
                    touched[json.loads(line)['event']] = touched.get(json.loads(line)['event'], 0) + 1
        if 'workspace' in source.parts or 'initial' in source.parts:
            # Fixture and final source bytes must never contain a machine path at all.
            assert raw == clean, name
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(clean.encode('utf-8'))
        mapping[name] = {'raw_sha256': sha(source), 'archived_sha256': sha(target),
                         'repository_prefix_replacements': raw.count(str(root))}
    results = json.loads(json.dumps(analyze(root)).replace(str(root), '<REPOSITORY>'))
    assert not re.search(r'/(?:Users|home|private/var|var/folders)/', json.dumps(results))
    save(out / 'results.json', results)
    save(out / 'archive-manifest.json', {
        'schema': 'epagent.archive-manifest.v1',
        'source_head': '9c58aff837f1be3caa3b990c1c843ebb1c695a69',
        'run_directories': list(ARMS.values()), 'episodes': 20, 'arms': 2, 'retries': 0,
        'normalization': 'Every occurrence of the repository root becomes <REPOSITORY>. The '
                         'substitution is the only difference and is exactly reversible, verified per '
                         'file. Workspace and initial source bytes contain no machine path at all and '
                         'are byte-identical. Unlike the earlier archives, some model-visible events '
                         'here DID contain the path: agent run_python tracebacks report the absolute '
                         'workspace file, so tool_result, the model_request history that repeats it, '
                         'and verification_feedback stdout were normalized too.',
        'model_visible_events_normalized': touched,
        'normalization_caveat': 'Read those tracebacks as <REPOSITORY>/... where the model saw the '
                                'absolute path. Raw originals under attempts/ are unchanged.',
        'raw_evidence_retained_locally': True, 'files': mapping,
        'no_inference_or_rescoring': True, 'control_directories_excluded': True,
        'result': 'negative: verification feedback v3 scored lower than the baseline'})
    print(json.dumps({'archived_files': len(mapping),
                      'baseline': results['primary']['baseline'],
                      'verification': results['primary']['verification'],
                      'regressions': results['regressions']}))


if __name__ == '__main__':
    archive(Path(__file__).resolve().parents[1])
