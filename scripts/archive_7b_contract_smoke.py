"""Allowlisted private archive of the third 7B development episode; never rerun it."""
import json
from pathlib import Path
import re
import tempfile

from archive_sft_v2 import read, save, sha
from epagent.execution import run_python
from epagent.tools import ARGUMENTS, safe_path

RUN = 'attempts/replace-lines-7b-contract-smoke'


def counterfactual(episode, intended):
    """Apply the intended edit OUTSIDE the episode, in a throwaway copy of the fixture.

    This is an offline check of the generated text only. The agent never applied
    this edit, never ran checks.py, and this is not an agent-completed repair.
    """
    original = (episode / 'initial/cart.py').read_text()
    checks = (episode / 'initial/checks.py').read_text()
    if original.count(intended['old_text']) != 1:
        return {'applicable': False, 'reason': 'old_text did not match the original source exactly once'}
    repaired = original.replace(intended['old_text'], intended['new_text'], 1)
    with tempfile.TemporaryDirectory(prefix='epagent-counterfactual-') as tmp:
        workspace = Path(tmp)
        for name, text in [('cart.py', repaired), ('checks.py', checks)]:
            safe_path(workspace, name).write_text(text)
        result = run_python(workspace, checks, 8, 8192)
    result.pop('elapsed_seconds', None)
    return {
        'applicable': True,
        'method': 'The rejected call\'s own old_text/new_text placed in a valid envelope and applied to a '
                  'fresh copy of the original fixture, outside the episode, in the existing bounded runner.',
        'repaired_source': repaired, 'checks_result': result,
        'checks_passed': result['status'] == 'completed' and 'PASS cart-total' in result['stdout'].splitlines(),
        'not_an_agent_repair': 'The agent never applied this edit and never executed checks.py. The episode '
                               'workspace was returned unchanged and the independent grader failed.'}


def analyze(root, episode):
    events = [json.loads(s) for s in (episode / 'trajectory.jsonl').read_text().splitlines()]
    report = read(episode / 'report.json')
    calls = {e['data']['step']: e['data'] for e in events if e['event'] == 'tool_call'}
    results = {e['data']['step']: e['data'] for e in events if e['event'] == 'tool_result'}
    said = {e['data']['step']: e['data']['text'] for e in events if e['event'] == 'assistant'}
    rejected = sorted(e['step'] for e in report['errors'])
    decoded = []
    for step in rejected:
        text = said[step].strip()
        body = re.sub(r'^```(?:json)?|```$', '', text, flags=re.M).strip()
        decoded.append(json.loads(body))
    first = decoded[0]
    sequence = [{'step': s, 'tool': calls[s]['tool'] if s in calls else None,
                 'accepted': s in calls,
                 'error': results[s]['observation'].get('error') if s in results else None}
                for s in sorted(results)]
    return {
        'schema': 'epagent.envelope-failure-analysis.v1',
        'episode': episode.name,
        'method': 'Static reading of recorded events plus one offline counterfactual clearly marked below. '
                  'No re-run, no re-grading, no claim about model intent.',
        'outcome': {'status': report['status'], 'termination_reason': report['termination_reason'],
                    'steps': report['steps'], 'accepted_tool_calls': report['tool_calls'],
                    'rejected_calls': len(report['errors']),
                    'source_changed': report['development']['source_changed'],
                    'repair_passed': report['development']['repair_passed'],
                    'workspace_unchanged': report['initial_sha256'] == report['final_sha256']},
        'action_sequence': sequence,
        'envelope_error': {
            'rejected_steps': rejected,
            'all_rejected_calls_identical': len({said[s] for s in rejected}) == 1,
            'category': 'missing_arguments',
            'message_received': results[rejected[0]]['observation']['detail'],
            'attempted_tool': first['tool'],
            'top_level_keys_supplied': sorted(k for k in first if k != 'tool'),
            'registered_arguments_for_tool': sorted(ARGUMENTS[first['tool']]),
            'defect': 'The parameters were correct but sat at the top level instead of inside the required '
                      '"arguments" object. Only the envelope shape was wrong.',
            'message_defect': 'The rejection text was a fixed string naming list_files whatever tool was '
                              'attempted, and never said to nest the parameters under "arguments".',
            'observed_next_action': {str(s): calls.get(s + 1, {}).get('tool') for s in rejected},
            'attribution': 'The message names list_files and the next recorded action was list_files in all '
                           'three cases. This records co-occurrence only, not model intent.'},
        'intended_edit': {
            'old_text': first['old_text'], 'new_text': first['new_text'],
            'preserves_required_name': first['new_text'].startswith('def cart_total(rows):'),
            'preserves_tuple_representation': 'for price, quantity in rows' in first['new_text'],
            'never_applied': True},
        'offline_counterfactual': counterfactual(episode, first),
        'verification_feedback_v2': {
            'protocol': report.get('verification_feedback'),
            'discovered_workspace_tests': report.get('workspace_tests'),
            'removed_definition_feedback_exercised': False,
            'syntax_feedback_exercised': False,
            'finish_deferral_exercised': False,
            'reason': 'No edit was ever applied and finish was never requested, so no file changed and no '
                      'finish evidence was produced. The episode failed upstream of every v2 path.',
            'emitted_events': sum(1 for e in events if e['event'] == 'verification_feedback')},
        'workspace_reads': {
            'readme': sum(1 for c in calls.values()
                          if c['tool'] == 'read_file' and c['arguments']['path'] == 'README.md'),
            'checks': sum(1 for c in calls.values()
                          if c['tool'] == 'read_file' and c['arguments']['path'] == 'checks.py'),
            'source': sum(1 for c in calls.values()
                          if c['tool'] == 'read_file' and c['arguments']['path'] == 'cart.py'),
            'checks_executed': False},
        'resources': {'agent_seconds': report['agent_seconds'], 'total_seconds': report['total_seconds'],
                      **report['usage']},
        'model': {k: report['model'][k] for k in ['model_id', 'revision', 'backend']},
        'grader': {'independent': True, 'runs_after_backend_close': True, 'fed_back_to_model': False,
                   'result': report['development']['original_visible_tests']['stderr'].strip().splitlines()[-1],
                   'repair_passed': report['development']['repair_passed']},
        'limitations': 'One episode at temperature zero. Not a causal estimate of any intervention and not a '
                       'model-size comparison. The third distinct failure mode across three 7B episodes.'}


def archive(root):
    run = root / RUN
    report = read(run / 'result.json')
    assert not report['development']['repair_passed'], 'Archive preserves the recorded failure'
    episode = Path(report['paths']['report']).parent
    sources = [run / n for n in ['registration.json', 'result.json', 'cleanup.json']]
    sources += [episode / n for n in ['report.json', 'trajectory.jsonl', 'conversation.json', 'changes.diff']]
    for sub in ['initial', 'workspace']:
        sources += sorted(p for p in (episode / sub).rglob('*') if p.is_file())
    sources += [root / '.epagent-models/qwen2.5-coder-7b-4bit/epagent-model.json',
                root / 'data/epagent-development/cart-total.json',
                root / 'scripts/run_development_smoke.py',
                root / 'tests/test_verification_feedback.py']
    sources += [root / 'src/epagent' / n for n in
                ['verification.py', 'episode.py', 'development.py', 'tools.py', 'mlx_backend.py']]
    out = root / 'artifacts/ep-agent/7b-contract-smoke'
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
                if before['event'] in ['model_request', 'model_start', 'model_chunk', 'model_done',
                                       'assistant', 'tool_call', 'tool_result', 'verification_feedback']:
                    assert before == after, (name, before['event'])
        if 'workspace' in source.parts or 'initial' in source.parts or source.name == 'conversation.json':
            assert raw == clean, name
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(clean.encode('utf-8'))
        mapping[name] = {'raw_sha256': sha(source), 'archived_sha256': sha(target),
                         'repository_prefix_replacements': raw.count(str(root))}
    analysis = json.loads(json.dumps(analyze(root, episode)).replace(str(root), '<REPOSITORY>'))
    assert not re.search(r'/(?:Users|home|private/var|var/folders)/', json.dumps(analysis))
    save(out / 'envelope-analysis.json', analysis)
    save(out / 'archive-manifest.json', {
        'schema': 'epagent.archive-manifest.v1',
        'source_head': 'cf421bbc294b3b50b7b42d72a3b3c3c6d52ab54d',
        'run_directory': RUN, 'episode_id': episode.name,
        'normalization': 'Repository prefixes in metadata and terminal tracebacks become <REPOSITORY>. '
                         'Model-visible events, generated responses, source bytes and the conversation '
                         'are byte-identical to the raw records.',
        'raw_evidence_retained_locally': True, 'files': mapping,
        'episodes_run': 1, 'retries': 0, 'no_inference_or_rescoring': True,
        'earlier_7b_episodes_unchanged': True,
        'limitations': 'The episode applied no edit, so verification-feedback v2 was never exercised.'})
    print(json.dumps({'archived_files': len(mapping), 'episode': episode.name,
                      'counterfactual_passes': analysis['offline_counterfactual']['checks_passed']}))


if __name__ == '__main__':
    archive(Path(__file__).resolve().parents[1])
