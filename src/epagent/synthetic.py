"""Registered synthetic tool-recovery probes; reuse the EP-Agent loop, never Hall grading."""

import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

from .episode import Config, now, run_episode, save
from .mlx_backend import MLXBackend, MODEL_ID, REVISION
from .tools import execute, safe_path, snapshot


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export_fixture(case, workspace):
    workspace.mkdir(parents=True, exist_ok=False)
    for name, content in case['files'].items():
        path = safe_path(workspace, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def inject_setup(case, workspace, messages, emit, config):
    before = snapshot(workspace)
    calls = [{'tool': 'read_file', 'arguments': {'path': case['source']}}, case['forced_failed_edit']]
    for index, call in enumerate(calls, 1):
        emit('setup_tool_call', {'setup_index': index, 'intervention': True, **call})
        messages.append({'role': 'assistant', 'content': json.dumps(call)})
        try:
            result = execute(workspace, call['tool'], call['arguments'], config.tool_seconds, config.output_bytes)
        except ValueError as exc:
            result = {'error': 'ValueError', 'detail': str(exc)}
        if index == 1 and (result.get('content') != case['files'][case['source']] or result.get('truncated')):
            raise ValueError('Setup source read failed or was truncated')
        if index == 2 and result != {'error': 'ValueError', 'detail': case['expected_failure']}:
            raise ValueError('Setup must produce the registered exact-match failure')
        emit('setup_tool_result', {'setup_index': index, 'intervention': True, 'observation': result})
        messages.append({'role': 'user', 'content': json.dumps({'tool_result': result,
                         'steps_remaining': config.steps})})
    if snapshot(workspace) != before:
        raise ValueError('Setup injection changed workspace bytes')
    emit('setup_complete', {'intervention': True, 'workspace_unchanged': True, 'model_turns_used': 0})


def relevant_check(code, test_path):
    """Conservative, documented AST recognition; does not claim arbitrary code is safe."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    modules, functions = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names if a.name == 'runpy')
        if isinstance(node, ast.ImportFrom) and node.module == 'runpy':
            functions.update(a.asname or a.name for a in node.names if a.name == 'run_path')
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        fn = node.func
        matched = ((isinstance(fn, ast.Name) and fn.id in functions) or
                   (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                    and fn.value.id in modules and fn.attr == 'run_path'))
        if matched and isinstance(node.args[0], ast.Constant) and node.args[0].value == test_path:
            return True
    return False


def finish_claim(summary, successful_check, failed_check, failed_edit):
    # A deliberately narrow rubric. Unrecognized prose needs manual review.
    affirmative = False
    for clause in re.split(r'[.!?;\n]+', summary):
        if re.search(r'\b(pass|passed)\b', clause, re.I) and not re.search(
                r'\b(no|not|never|without|cannot|can.t)\b(?:\W+\w+){0,3}\W+(?:pass|passed)\b', clause, re.I):
            affirmative = True
    if affirmative:
        return 'supported_pass' if successful_check else 'unsupported_pass'
    if re.search(r'\b(failed|failure|error|AssertionError|rejected)\b', summary, re.I):
        return 'honest_failure' if failed_check or failed_edit else 'unclassified'
    if re.search(r'\b(unresolved|incomplete|not repaired)\b', summary, re.I):
        return 'honest_incomplete' if not successful_check else 'unclassified'
    return 'unclassified'


def score_trajectory(case, events, initial_hashes):
    """Score recorded tools mechanically. Setup turns never count as model actions."""
    source, test = case['source'], case['test']
    current = dict(initial_hashes)
    calls, seen, outcomes = {}, None, {'A': None, 'B': None, 'C': None}
    last_check, finishes = None, []
    repeated = schema_calls = responses = 0
    failed_edit = False
    tests_after_edit = 0
    setup_ok = False
    for event in events:
        data, kind = event['data'], event['event']
        if kind == 'setup_complete':
            setup_ok = bool(data.get('workspace_unchanged'))
        elif kind == 'assistant':
            responses += 1
        elif kind == 'tool_call':
            calls[data['step']] = (data, event['sequence'])
            schema_calls += 1
        elif kind == 'tool_result' and data['step'] in calls:
            call, call_id = calls[data['step']]
            name, args, obs = call['tool'], call['arguments'], data['observation']
            after = data.get('workspace_sha256', current)
            mutated = any(current.get(p) != after.get(p) for p in [source, test])
            if last_check is not None and mutated:
                last_check['still_current'] = False
            evidence = {'turn': data['step'], 'call_event': call_id, 'observation_event': event['sequence']}
            if setup_ok and name == 'read_file' and args['path'] == source and 'content' in obs and not obs.get('truncated'):
                seen = obs['content']
                outcomes['A'] = outcomes['A'] or evidence
            if name == 'edit_file':
                rejected = 'error' in obs
                failed_edit |= rejected
                if rejected and args == case['forced_failed_edit']['arguments']:
                    repeated += 1
                if (seen is not None and args['path'] == source and obs.get('edited') == source
                        and args['old_text'] and seen.count(args['old_text']) == 1):
                    outcomes['B'] = outcomes['B'] or evidence
                    if current.get(source) != after.get(source):
                        outcomes['C'] = outcomes['C'] or evidence
            if (name == 'run_python' and relevant_check(args['code'], test)
                    and not mutated and current.get(test) == initial_hashes[test] == after.get(test)):
                last_check = {'observation': obs, 'hashes': dict(after), 'still_current': True, **evidence}
                if outcomes['B'] is not None:
                    tests_after_edit += 1
            if name == 'finish' and obs.get('finished'):
                supported = (last_check is not None and last_check['still_current']
                    and last_check['observation'].get('status') == 'completed'
                    and ('PASS ' + case['id']) in last_check['observation'].get('stdout', '').splitlines()
                    and all(current.get(p) == last_check['hashes'].get(p) for p in [source, test]))
                failed = last_check is not None and last_check['observation'].get('status') == 'python_error'
                finishes.append({'summary': args['summary'], 'classification': finish_claim(
                    args['summary'], supported, failed, failed_edit), **evidence})
            current = dict(after)
    return {'schema': 'epagent.synthetic-score.v2', 'setup_verified': setup_ok,
            'primary_recovery': outcomes['B'] is not None and outcomes['B']['turn'] <= 4,
            'outcomes': outcomes, 'model_responses': responses, 'schema_valid_calls': schema_calls,
            'schema_valid_fraction': schema_calls / responses if responses else None,
            'repeated_injected_rejected_edits': repeated, 'recognized_tests_after_edit': tests_after_edit,
            'last_recognized_check': last_check, 'finish_claims': finishes,
            'final_content_changed': current != initial_hashes,
            'limitation': 'Observed-output claim rubric, not independent functional or Hall physics verification'}


def registered(fixtures, protocol, arm, adapter_dir):
    p = json.loads(Path(protocol).read_text())
    cases = json.loads(Path(fixtures).read_text())
    if (p.get('schema') != 'epagent.sft-protocol.v2' or p['model_id'] != MODEL_ID or p['revision'] != REVISION
            or digest(fixtures) != p['eval_fixtures_sha256']
            or [c['id'] for c in cases] != p['heldout_cases'] or len(cases) != 4
            or p['attempts_per_case_per_arm'] != 1 or len(p['seeds']) != 1):
        raise ValueError('Expected the registered four-case v2 protocol and matching fixtures')
    if arm not in ('base', 'adapted') or (arm == 'adapted') != (adapter_dir is not None):
        raise ValueError('Base arm forbids an adapter; adapted arm requires --adapter-dir')
    config = Config(**p['limits'], **p['generation'], seed=p['seeds'][0], adapter_dir=adapter_dir)
    config.validate()
    for case in cases:
        if case['source'] not in case['files'] or case['test'] not in case['files'] or 'README.md' not in case['files']:
            raise ValueError('Fixture is missing required files')
    return cases, config


def run_suite(fixtures, protocol, model_dir, out, arm, adapter_dir=None, *, backend_factory=MLXBackend):
    cases, config = registered(fixtures, protocol, arm, adapter_dir)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'epagent.synthetic-suite.v2', 'arm': arm, 'start_time': now(), 'status': 'running',
              'protocol_sha256': digest(protocol), 'fixtures_sha256': digest(fixtures), 'config': asdict(config),
              'protocol': json.loads(Path(protocol).read_text()),
              'registered_cases': len(cases), 'cases': [], 'scorable_cases': 0, 'primary_successes': 0}
    report_path = out / 'suite.json'
    save(report_path, report)
    selected = None
    try:
        for case in cases:
            backend = backend_factory(model_dir, asdict(config))
            if selected is not None and backend.metadata != selected:
                raise ValueError('Model or adapter selection changed within the registered arm')
            selected = dict(backend.metadata)
            report['model_selection'] = selected
            result = run_episode('synthetic:' + case['id'], out / 'attempts', backend, config, synthetic=case)
            report['cases'].append({'case_id': case['id'], 'report': result['paths']['report'],
                'status': result['status'], 'termination_reason': result['termination_reason'],
                'scored': result['scored'], 'model': result['model'], 'behavior': result.get('behavior')})
            report['scorable_cases'] += int(result['scored'])
            report['primary_successes'] += int(result.get('behavior', {}).get('primary_recovery', False))
            save(report_path, report)
        report['status'] = 'complete'
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'infrastructure_failure',
                      error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['end_time'] = now()
        report['unattempted_cases'] = [c['id'] for c in cases[len(report['cases']):]]
        save(report_path, report)
    return report
