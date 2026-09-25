"""Allowlisted private archive of the fourth and final cart-total episode; never rerun it."""
import difflib
import json
from pathlib import Path
import re

from archive_sft_v2 import read, save, sha

RUN = 'attempts/replace-lines-7b-envelope-smoke'


def analyze(root, episode):
    """Static reading of recorded bytes and events. No re-run, no re-grading, no intent claims."""
    events = [json.loads(s) for s in (episode / 'trajectory.jsonl').read_text().splitlines()]
    report = read(episode / 'report.json')
    calls = {e['data']['step']: e['data'] for e in events if e['event'] == 'tool_call'}
    results = {e['data']['step']: e['data']['observation'] for e in events if e['event'] == 'tool_result'}
    said = {e['data']['step']: e['data']['text'] for e in events if e['event'] == 'assistant'}
    original = (episode / 'initial/cart.py').read_text()
    final = (episode / 'workspace/cart.py').read_text()
    shipped = (episode / 'initial/checks.py').read_text()

    rejected_schema = [e['step'] for e in report['errors'] if e['error'] == 'missing_arguments']
    step = rejected_schema[0]
    attempted = json.loads(re.sub(r'^```(?:json)?|```$', '', said[step].strip(), flags=re.M).strip())
    recovery = next(s for s in sorted(calls) if s > step and calls[s]['tool'] == 'edit_file')
    accepted = [s for s in sorted(calls)
                if calls[s]['tool'] == 'edit_file' and 'error' not in results[s]]
    stale = [s for s in sorted(calls)
             if calls[s]['tool'] == 'edit_file' and results[s].get('detail') == 'old_text must match exactly once']
    runs = [s for s in sorted(calls) if calls[s]['tool'] == 'run_python']
    agent_test = calls[runs[0]]['arguments']['code']
    diff = [l for l in difflib.unified_diff(shipped.splitlines(), agent_test.splitlines(),
                                            'initial/checks.py', 'agent run_python', lineterm='')
            if l.startswith(('+', '-')) and not l.startswith(('+++', '---'))]
    return {
        'schema': 'epagent.unverified-success-analysis.v1',
        'episode': episode.name,
        'headline': 'The agent-produced repair passed the independent grader, but the agent did not '
                    'execute the shipped tests, did not recognize its own success, and did not '
                    'complete the workflow. The episode ended on the step limit with no summary.',
        'method': 'Static reading of recorded events and fixture bytes only.',
        'outcome': {'status': report['status'], 'termination_reason': report['termination_reason'],
                    'steps': report['steps'], 'finish_calls': 0,
                    'schema_valid_calls': report['tool_calls'],
                    'schema_rejected': len(rejected_schema),
                    'tool_rejected': len(report['errors']) - len(rejected_schema),
                    'source_changed': report['development']['source_changed'],
                    'repair_passed': report['development']['repair_passed']},
        'schema_rejection_and_recovery': {
            'rejected_step': step, 'attempted_tool': attempted['tool'],
            'top_level_keys_supplied': sorted(k for k in attempted if k != 'tool'),
            'corrected_message_received': results[step]['detail'],
            'message_names_attempted_tool': 'for edit_file' in results[step]['detail'],
            'message_mentions_list_files': 'list_files' in results[step]['detail'],
            'recovery_step': recovery,
            'recovery_nested_under_arguments': True,
            'parameter_values_preserved_exactly': all(
                attempted[k] == calls[recovery]['arguments'][k] for k in ('path', 'old_text', 'new_text')),
            'note': 'One rejection, corrected on the next turn. This is the behavior the corrected '
                    'schema message targeted; one episode does not establish a causal effect.'},
        'accepted_edit': {
            'step': accepted[0], 'tool': 'edit_file',
            'arguments': calls[accepted[0]]['arguments'],
            'observation': results[accepted[0]],
            'verification_feedback': results[accepted[0]].get('verification'),
            'source_before': original, 'source_after': final,
            'patch': next(e['data']['patch'] for e in events
                          if e['event'] == 'tool_result' and e['data']['step'] == accepted[0]),
            'public_definitions_preserved': ['cart_total', 'label'],
            'tuple_representation_preserved': 'for price, quantity in rows' in final},
        'agent_authored_test': {
            'step': runs[0], 'code': agent_test, 'observation': results[runs[0]],
            'shipped_test_executed': False,
            'names_shipped_file': 'checks.py' in agent_test,
            'imports_shipped_module': 'import checks' in agent_test,
            'difference_from_shipped_test': diff,
            'incorrect_assertion': 'The agent retyped the shipped test and asserted 28 for '
                                   '[(7, 3), (2, 4)]. The specified total is 7*3 + 2*4 = 29, so the '
                                   'agent-authored assertion was wrong and its correct code failed it.',
            'consequence': 'The only execution in the episode reported failure for a repair that the '
                           'independent grader later passed.'},
        'stale_repeated_edits': {
            'steps': stale, 'count': len(stale),
            'all_identical': len({json.dumps(calls[s]['arguments'], sort_keys=True) for s in stale}) == 1,
            'error': 'old_text must match exactly once',
            'cause': 'The accepted edit at step %d replaced that exact text, so old_text occurred %d '
                     'times afterwards. These calls were schema-valid but stale.'
                     % (accepted[0], final.count(calls[stale[0]]['arguments']['old_text'])),
            'source_rereads_after_the_accepted_edit': sum(
                1 for s in calls if s > accepted[0] and calls[s]['tool'] == 'read_file'
                and calls[s]['arguments']['path'] == 'cart.py'),
            'note': 'The workspace was never re-read after the edit landed, so the already-applied '
                    'change was not observed.'},
        'verification_feedback_v2': {
            'protocol': report.get('verification_feedback'),
            'discovered_workspace_tests': report.get('workspace_tests'),
            'syntax_feedback_fired': True,
            'removed_definition_feedback_fired': False,
            'removed_definition_reason': 'The edit preserved both public definitions, so nothing was removed.',
            'finish_deferral_fired': False,
            'finish_deferral_reason': 'finish was never requested, so the reminder could not apply.',
            'gap': 'No mechanism covers an agent that edits correctly, tests with a faulty transcription '
                   'of the shipped test, and never finishes.'},
        'independent_grader': {
            'runs_after_backend_close': True, 'fed_back_to_model': False,
            'command': 'the original checks.py bytes, irrespective of any edit to checks.py',
            'result': report['development']['original_visible_tests'],
            'original_visible_tests_passed': report['development']['original_visible_tests_passed'],
            'repair_passed': report['development']['repair_passed'],
            'caveat': 'Functional success by the independent grader only. The agent neither observed '
                      'nor claimed it, so this is not an agent-verified repair.'},
        'workspace_reads': {
            'readme': sum(1 for c in calls.values()
                          if c['tool'] == 'read_file' and c['arguments']['path'] == 'README.md'),
            'checks': sum(1 for c in calls.values()
                          if c['tool'] == 'read_file' and c['arguments']['path'] == 'checks.py'),
            'source': sum(1 for c in calls.values()
                          if c['tool'] == 'read_file' and c['arguments']['path'] == 'cart.py')},
        'resources': {'agent_seconds': report['agent_seconds'], 'total_seconds': report['total_seconds'],
                      **report['usage']},
        'model': {k: report['model'][k] for k in ['model_id', 'revision', 'backend']},
        'limitations': 'One episode at temperature zero on one fixture, run after a fix made in response '
                       'to the previous failure. Not a causal estimate and not generalization evidence. '
                       'Across all four cart-total episodes the shipped test was never executed.'}


def archive(root):
    run = root / RUN
    report = read(run / 'result.json')
    assert report['development']['repair_passed'], 'This archive preserves the first grader-passing run'
    assert report['status'] == 'unfinished', 'The agent did not complete the workflow'
    episode = Path(report['paths']['report']).parent
    sources = [run / n for n in ['registration.json', 'result.json', 'cleanup.json']]
    sources += [episode / n for n in ['report.json', 'trajectory.jsonl', 'conversation.json', 'changes.diff']]
    for sub in ['initial', 'workspace']:
        sources += sorted(p for p in (episode / sub).rglob('*') if p.is_file())
    sources += [root / '.epagent-models/qwen2.5-coder-7b-4bit/epagent-model.json',
                root / 'data/epagent-development/cart-total.json',
                root / 'scripts/run_development_smoke.py',
                root / 'tests/test_schema_feedback.py',
                root / 'tests/test_verification_feedback.py']
    sources += [root / 'src/epagent' / n for n in
                ['verification.py', 'episode.py', 'development.py', 'tools.py', 'mlx_backend.py']]
    out = root / 'artifacts/ep-agent/7b-envelope-smoke'
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
    save(out / 'unverified-success-analysis.json', analysis)
    save(out / 'archive-manifest.json', {
        'schema': 'epagent.archive-manifest.v1',
        'source_head': '4252ebf9b3c9da0470a2507a2e5735593af7f5f8',
        'run_directory': RUN, 'episode_id': episode.name,
        'normalization': 'Repository prefixes in metadata and terminal tracebacks become <REPOSITORY>. '
                         'Model-visible events, generated responses, source bytes and the conversation '
                         'are byte-identical to the raw records.',
        'raw_evidence_retained_locally': True, 'files': mapping,
        'episodes_run': 1, 'retries': 0, 'no_inference_or_rescoring': True,
        'earlier_7b_episodes_unchanged': True,
        'limitations': 'Grader-passing but not agent-verified; the shipped test was never executed.'})
    print(json.dumps({'archived_files': len(mapping), 'episode': episode.name,
                      'repair_passed': analysis['outcome']['repair_passed'],
                      'agent_verified': False}))


if __name__ == '__main__':
    archive(Path(__file__).resolve().parents[1])
