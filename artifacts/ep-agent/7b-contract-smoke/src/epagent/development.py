"""Visible engineering fixtures and post-episode checks; no physics or ML scorer."""
from .execution import run_python
from .tools import safe_path, snapshot


def export_development(fixture, workspace):
    workspace.mkdir(parents=True, exist_ok=False)
    for name, content in fixture['files'].items():
        path = safe_path(workspace, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode('utf-8'))


def check_development(fixture, workspace, initial, events):
    final = snapshot(workspace)
    source = fixture['source']
    changed = initial[source] != final.get(source)
    unrelated = all(final.get(n) == b for n, b in initial.items() if n != source)
    # Execute the original visible tests, irrespective of any edits to checks.py.
    check = run_python(workspace, initial['checks.py'].decode('utf-8'), 8, 8192)
    passed = check['status'] == 'completed' and fixture['pass_marker'] in check['stdout'].splitlines()
    calls = {e['data']['step']: e['data'] for e in events if e['event'] == 'tool_call'}
    last_change = max((e['data']['step'] for e in events
                       if e['event'] == 'tool_result' and e['data']['patch']), default=0)
    observed_tests = []
    summaries = []
    for event in events:
        if event['event'] != 'tool_result':
            continue
        data = event['data']
        call, obs = calls.get(data['step'], {}), data['observation']
        if call.get('tool') == 'run_python':
            observed_tests.append({'step': data['step'], 'code': call['arguments']['code'],
                'observation': obs, 'after_final_change': data['step'] > last_change})
        if call.get('tool') == 'finish':
            summaries.append(call['arguments']['summary'])
    return {'source_changed': changed, 'unrelated_original_files_preserved': unrelated,
            'original_visible_tests': check, 'original_visible_tests_passed': passed,
            'repair_passed': changed and unrelated and passed,
            'agent_python_runs': observed_tests, 'final_summaries': summaries,
            'summary_substantiation': 'Manual review against recorded observations required',
            'scope': 'Engineering smoke test; not scientific repair or generalization evidence'}
