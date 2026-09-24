"""Execute inspectable scripted fixtures through EP-Agent tools; no model involved."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from epagent.execution import preflight
from epagent.tools import SYSTEM_PROMPT, changes, execute, safe_path, snapshot


def build(fixtures, out):
    cases = json.loads(fixtures.read_text())
    out.mkdir(parents=True, exist_ok=False)
    reviews = []
    for case in cases:
        outcome = case.get('outcome', 'success')
        with tempfile.TemporaryDirectory(prefix='epagent-demo-') as directory:
            workspace = Path(directory)
            for name, content in case['files'].items():
                path = safe_path(workspace, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            preflight(workspace, [Path(__file__)])
            check = f"import runpy; runpy.run_path({case['test']!r}, run_name='__main__')"
            actions = [('list_files', {}, True), ('read_file', {'path': 'README.md'}, True),
                       ('read_file', {'path': case['test']}, True),
                       ('read_file', {'path': case['source']}, True),
                       ('run_python', {'code': check}, True),
                       ('read_file', {'path': case['test']}, True)]
            if case['recovery'] or outcome == 'unresolved_edit':
                # A controlled exact-match failure. It remains context, never a target.
                actions += [('edit_file', {'path': case['source'],
                             'old_text': case['files'][case['source']].replace('    ', '  '),
                             'new_text': case['replacement']}, False),
                            ('read_file', {'path': case['source']}, True)]
            if outcome in ('success', 'incomplete'):
                actions += [('edit_file', {'path': case['source'], 'old_text': case['files'][case['source']],
                             'new_text': case['replacement']}, True), ('run_python', {'code': check}, True)]
            summaries = {
                'success': f"Updated {case['source']}. The final check printed PASS {case['id']}.",
                'failed_check': 'The check failed with ZeroDivisionError. I made no changes; the repair is incomplete.',
                'unresolved_edit': 'The check failed and my edit was rejected: old_text must match exactly once. The reread confirms the original source remains. This is unresolved.',
                'incomplete': 'I changed the source, but the rerun still failed with AssertionError. The repair is incomplete.'}
            actions.append(('finish', {'summary': summaries[outcome]}, True))
            budget = case.get('budget_steps', 12)
            assert len(actions) <= budget
            messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': 'Repair this synthetic Python workspace. ' + case['requirement']
                         + f' You have at most {budget} tool turns. Finish when you can report the observed outcome honestly.'}]
            events, selected = [], []
            def emit(kind, data):
                events.append({'schema': 'epagent.episode.v1', 'episode_id': case['id'],
                               'sequence': len(events) + 1, 'event': kind, 'data': data})
            emit('episode_start', {'task_id': 'synthetic:' + case['id'],
                                  'config': {'steps': budget},
                                  'model': {'backend': 'scripted-demonstration', 'model_id': None},
                                  'provenance': 'New task-author fixture; no harvested model trajectory'})
            for step, (name, args, learn) in enumerate(actions, 1):
                # JSON round trip takes an immutable snapshot of the conversation.
                emit('model_request', {'step': step, 'messages': json.loads(json.dumps(messages))})
                text = json.dumps({'tool': name, 'arguments': args})
                emit('assistant', {'step': step, 'text': text})
                emit('tool_call', {'step': step, 'tool': name, 'arguments': args})
                messages.append({'role': 'assistant', 'content': text})
                before = snapshot(workspace)
                try:
                    observation = execute(workspace, name, args, 8, 8192)
                except ValueError as exc:
                    observation = {'error': 'ValueError', 'detail': str(exc)}
                # Normalize only nondeterministic runtime metadata. Imported
                # modules can put the temporary workspace prefix in tracebacks.
                observation.pop('elapsed_seconds', None)
                for key in ['stdout', 'stderr']:
                    if key in observation:
                        for prefix in [str(workspace.resolve()), str(workspace)]:
                            observation[key] = observation[key].replace(prefix + '/', '<workspace>/')
                if name == 'run_python':
                    expected = 'completed' if outcome == 'success' and step != 5 else 'python_error'
                    assert observation['status'] == expected, observation
                    if expected == 'completed':
                        assert observation['stdout'].strip() == 'PASS ' + case['id']
                    else:
                        assert 'AssertionError' in observation['stderr'] or 'ZeroDivisionError' in observation['stderr']
                if not learn:
                    assert observation == {'error': 'ValueError', 'detail': 'old_text must match exactly once'}
                elif 'error' in observation:
                    raise ValueError(observation)
                emit('tool_result', {'step': step, 'observation': observation,
                                     'patch': changes(before, snapshot(workspace))})
                messages.append({'role': 'user', 'content': json.dumps({'tool_result': observation,
                                 'steps_remaining': budget - step})})
                if learn:
                    selected.append(step)
            expected_source = case['replacement'] if outcome in ('success', 'incomplete') else case['files'][case['source']]
            assert (workspace / case['source']).read_text() == expected_source
            path = out / (case['id'] + '.jsonl')
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
            reviews.append({'episode_id': case['id'], 'split': case['split'], 'family': case['family'],
                            'trace': path.name, 'trace_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                            'origin': 'authored-synthetic-fixture', 'rights': 'project-authored; no imported provider trajectories',
                            'review': 'Inspected fixture, executed observations and terminal claims verified; maintainer review pending',
                            'outcome': outcome, 'budget_steps': budget,
                            'selected_assistant_steps': selected,
                            'excluded_failed_edit_steps': [7] if case['recovery'] or outcome == 'unresolved_edit' else []})
    (out / 'reviews.json').write_text(json.dumps({'schema': 'epagent.sft-review.v1',
        'observation_normalization': 'elapsed_seconds omitted; temporary workspace prefixes in stdout/stderr replaced with <workspace>/',
        'fixtures_sha256': hashlib.sha256(fixtures.read_bytes()).hexdigest(), 'episodes': reviews}, indent=2) + '\n')
    return reviews


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.fixtures, args.out)
    print(json.dumps({'episodes': len(result), 'selected_assistant_turns': sum(len(r['selected_assistant_steps']) for r in result)}))
