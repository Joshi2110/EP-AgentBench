"""Evaluation 01: a fixed two-arm assessment. Hidden tests never enter the workspace."""
import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .episode import Config, now, run_episode, save
from .execution import run_python
from .mlx_backend import MLXBackend, MODEL_7B, REVISION_7B
from .tools import parse_call
from .verification import discover_tests, executed_tests

SCHEMA = 'epagent.evaluation-01.v1'
ARMS = {'baseline': False, 'verification': True}
SCHEMA_ERRORS = {'missing_arguments', 'schema_violation', 'invalid_tool', 'json_syntax', 'invalid_wrapper'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def visible_fixture(fixture):
    """Exactly what the agent may see. Hidden test and reference repair are dropped."""
    return {'id': fixture['id'], 'source': fixture['source'],
            'pass_marker': fixture['pass_marker'], 'files': dict(fixture['files'])}


def registered(fixtures, protocol, arm):
    spec = json.loads(Path(protocol).read_text())
    cases = json.loads(Path(fixtures).read_text())
    if (spec.get('schema') != SCHEMA or spec['model_id'] != MODEL_7B
            or spec['revision'] != REVISION_7B or digest(fixtures) != spec['fixtures_sha256']
            or [c['id'] for c in cases] != spec['fixtures'] or len(cases) != 10
            or spec['attempts_per_fixture_per_arm'] != 1 or len(spec['seeds']) != 1
            or sorted(spec['arms']) != sorted(ARMS)):
        raise ValueError('Expected the registered ten-fixture Evaluation 01 protocol and fixtures')
    if arm not in ARMS:
        raise ValueError('Arm must be one of: ' + ', '.join(sorted(ARMS)))
    config = Config(**spec['limits'], **spec['generation'], seed=spec['seeds'][0])
    config.validate()
    for case in cases:
        if case['source'] not in case['files'] or 'README.md' not in case['files']:
            raise ValueError('Fixture is missing required visible files')
        if case['independent_test'] in json.dumps(case['files']):
            raise ValueError('Hidden test must never appear in visible files')
    return cases, config, ARMS[arm], spec


def independent_result(fixture, workspace, seconds, output_bytes):
    """Run the hidden test after the episode. It is never written into the workspace."""
    outcome = run_python(Path(workspace), fixture['independent_test'], seconds, output_bytes)
    return {'passed': outcome['status'] == 'completed'
                      and fixture['independent_marker'] in outcome['stdout'].splitlines(),
            'status': outcome['status'], 'returncode': outcome['returncode'],
            'stdout': outcome['stdout'], 'stderr': outcome['stderr'],
            'method': 'hidden independent test executed after the backend closed, against the final '
                      'workspace source; never present in the workspace and never shown to the agent'}


def measure(fixture, report, events, workspace):
    """Metrics computed identically in both arms, from the recorded trajectory."""
    visible_tests = discover_tests(fixture['files'])
    marker = fixture['pass_marker']
    calls = {e['data']['step']: e['data'] for e in events if e['event'] == 'tool_call'}
    results = {e['data']['step']: e['data'] for e in events if e['event'] == 'tool_result'}
    last_change = max((s for s, d in results.items() if d.get('patch')), default=0)
    agent_runs, agent_passes = [], []
    for step, call in sorted(calls.items()):
        if call['tool'] != 'run_python':
            continue
        ran = executed_tests(call['arguments']['code'], visible_tests)
        if not ran:
            continue
        observation = results[step]['observation']
        record = {'step': step, 'tests': ran, 'status': observation.get('status'),
                  'marker_observed': marker in observation.get('stdout', '').splitlines(),
                  'after_last_change': step > last_change}
        agent_runs.append(record)
        if record['marker_observed'] and record['status'] == 'completed':
            agent_passes.append(record)
    runner_runs = [{'step': e['data']['step'], **r}
                   for e in events if e['event'] == 'verification_feedback'
                   and 'workspace_test_feedback' in e['data']
                   for r in e['data']['workspace_test_feedback']['results']]
    source = Path(workspace, fixture['source'])
    try:
        ast.parse(source.read_text())
        syntax = 'valid'
    except (SyntaxError, ValueError):
        syntax = 'invalid'
    except OSError:
        syntax = 'missing'
    errors = report['errors']
    finished = report['termination_reason'] == 'finish_tool'
    supported = bool(finished and any(r['after_last_change'] for r in agent_passes))
    return {
        'source_changed': report['development']['source_changed'],
        'unrelated_files_preserved': report['development']['unrelated_original_files_preserved'],
        'final_source_syntax': syntax,
        'agent_initiated_test_executions': len(agent_runs),
        'agent_initiated_observed_passes': len(agent_passes),
        'agent_test_runs': agent_runs,
        'runner_initiated_test_executions': len([r for r in runner_runs
                                                 if r.get('execution') != 'not_checked']),
        'runner_test_runs': runner_runs,
        'visible_test_passed_after_episode': report['development']['original_visible_tests_passed'],
        'finish_called': finished,
        'evidence_supported_finish': supported,
        'finish_summaries': report['development']['final_summaries'],
        'schema_errors': len([e for e in errors if e.get('error') in SCHEMA_ERRORS]),
        'tool_errors': len([e for e in errors if e.get('error') not in SCHEMA_ERRORS]),
        'steps': report['steps'], 'accepted_tool_calls': report['tool_calls'],
        'termination_reason': report['termination_reason'],
        'agent_seconds': report['agent_seconds'], 'usage': report['usage'],
        'separation': 'agent_initiated_* counts only the agent\'s own run_python calls that execute a '
                      'discovered workspace test. runner_initiated_* counts verification-feedback '
                      'executions. They are never added together.'}


def run_suite(fixtures, protocol, model_dir, out, arm, *, backend_factory=MLXBackend):
    cases, config, feedback, spec = registered(fixtures, protocol, arm)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': SCHEMA, 'arm': arm, 'verification_feedback': feedback, 'start_time': now(),
              'status': 'running', 'protocol_sha256': digest(protocol),
              'fixtures_sha256': digest(fixtures), 'config': asdict(config), 'protocol': spec,
              'registered_fixtures': len(cases), 'cases': [],
              'independent_successes': 0, 'scorable_cases': 0}
    path = out / 'suite.json'
    save(path, report)
    selected = None
    try:
        for case in cases:
            backend = backend_factory(model_dir, asdict(config))
            if selected is not None and backend.metadata != selected:
                raise ValueError('Model selection changed within the registered arm')
            selected = dict(backend.metadata)
            report['model_selection'] = selected
            episode = run_episode('development:' + case['id'], out / 'episodes', backend, config,
                                  development=visible_fixture(case), verification_feedback=feedback)
            workspace = episode['paths']['workspace']
            independent = independent_result(case, workspace, config.tool_seconds, config.output_bytes)
            metrics = measure(case, episode, [json.loads(s) for s in
                                              Path(episode['paths']['trace']).read_text().splitlines()],
                              workspace)
            report['cases'].append({'fixture': case['id'], 'family': case['family'],
                                    'report': episode['paths']['report'], 'status': episode['status'],
                                    'independent': independent, 'metrics': metrics})
            report['independent_successes'] += int(independent['passed'])
            report['scorable_cases'] += int(episode['scored'])
            save(path, report)
        report['status'] = 'complete'
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'infrastructure_failure',
                      error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['end_time'] = now()
        report['unattempted_fixtures'] = [c['id'] for c in cases[len(report['cases']):]]
        report['primary'] = f"{report['independent_successes']}/{len(cases)}"
        save(path, report)
    return report
