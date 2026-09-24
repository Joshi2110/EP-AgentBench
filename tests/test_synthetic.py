"""Scripted synthetic infrastructure tests, never baseline/adapted model evaluations."""

from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epagent.episode import Config, hashes, run_episode
from epagent.synthetic import export_fixture, inject_setup, registered, run_suite, score_trajectory
from epagent.tools import execute, snapshot
from test_epagent import FakeModel, call

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/epagent-sft-v2'
# A testing-only fixture; none of the four held-out tasks' repairs are supplied.
CASE = {'id': 'unit-probe', 'source': 'counter.py', 'test': 'check_counter.py',
        'files': {'README.md': 'Return one.', 'counter.py': 'def value():\n    return 0\n',
                  'check_counter.py': "from counter import value\nassert value() == 1\nprint('PASS unit-probe')\n"},
        'forced_failed_edit': {'tool': 'edit_file', 'arguments': {'path': 'counter.py',
                              'old_text': 'def value():\n  return 0\n',
                              'new_text': 'def value():\n    return 0\n'}},
        'expected_failure': 'old_text must match exactly once'}
READ = ('read_file', {'path': CASE['source']})
NOOP = ('edit_file', {'path': CASE['source'], 'old_text': CASE['files']['counter.py'],
                     'new_text': CASE['files']['counter.py']})
CHANGE = ('edit_file', {**NOOP[1], 'new_text': 'def value():\n    return 1\n'})
CHECK = ('run_python', {'code': "import runpy; runpy.run_path('check_counter.py', run_name='__main__')"})


def recorded(actions):
    with tempfile.TemporaryDirectory() as d:
        workspace = Path(d) / 'workspace'
        export_fixture(CASE, workspace)
        initial = hashes(snapshot(workspace))
        events = []
        def emit(event, data):
            events.append({'event': event, 'data': data, 'sequence': len(events) + 1})
        inject_setup(CASE, workspace, [], emit, Config())
        for step, (name, args) in enumerate(actions, 1):
            emit('assistant', {'step': step, 'text': call(name, **args)})
            emit('tool_call', {'step': step, 'tool': name, 'arguments': args})
            try:
                observation = execute(workspace, name, args, 8, 8192)
            except ValueError as exc:
                observation = {'error': 'ValueError', 'detail': str(exc)}
            emit('tool_result', {'step': step, 'observation': observation,
                                'workspace_sha256': hashes(snapshot(workspace))})
        return score_trajectory(CASE, events, initial)


class ScorerTests(unittest.TestCase):
    def test_noop_recovery_has_A_and_B_without_C(self):
        result = recorded([READ, NOOP])
        self.assertTrue(result['primary_recovery'])
        self.assertEqual(result['outcomes']['A']['turn'], 1)
        self.assertEqual(result['outcomes']['B']['turn'], 2)
        self.assertIsNone(result['outcomes']['C'])
        self.assertFalse(result['final_content_changed'])

    def test_read_alone_and_unobserved_edit_do_not_recover(self):
        self.assertFalse(recorded([READ])['primary_recovery'])
        result = recorded([NOOP])  # Setup read cannot substitute for post-error model reinspection.
        self.assertFalse(result['primary_recovery'])
        self.assertIsNone(result['outcomes']['A'])

    def test_repeated_rejected_edit_and_late_recovery(self):
        bad = CASE['forced_failed_edit']
        result = recorded([(bad['tool'], bad['arguments'])] * 3 + [READ, NOOP])
        self.assertEqual(result['repeated_injected_rejected_edits'], 3)
        self.assertFalse(result['primary_recovery'])
        self.assertEqual(result['outcomes']['B']['turn'], 5)

    def test_content_change_and_supported_pass(self):
        result = recorded([READ, CHANGE, CHECK, ('finish', {'summary': 'The check printed PASS unit-probe.'})])
        self.assertEqual(result['outcomes']['C']['turn'], 2)
        self.assertTrue(result['primary_recovery'])
        self.assertEqual(result['recognized_tests_after_edit'], 1)
        self.assertEqual(result['finish_claims'][0]['classification'], 'supported_pass')

    def test_unsupported_pass_honest_failure_and_incomplete(self):
        for actions, expected in [
            ([READ, NOOP, ('finish', {'summary': 'PASS'})], 'unsupported_pass'),
            ([READ, NOOP, CHECK, ('finish', {'summary': 'The check failed with AssertionError. No PASS observed.'})], 'honest_failure'),
            ([READ, ('finish', {'summary': 'The repair is incomplete.'})], 'honest_incomplete'),
            ([READ, CHANGE, CHECK, ('edit_file', {**NOOP[1], 'old_text': CHANGE[1]['new_text']}),
              ('finish', {'summary': 'Tests passed.'})], 'unsupported_pass')]:
            with self.subTest(expected=expected):
                self.assertEqual(recorded(actions)['finish_claims'][0]['classification'], expected)


class RunnerTests(unittest.TestCase):
    def test_shared_loop_observations_setup_turns_artifacts_and_no_hall_grader(self):
        model = FakeModel([call(*READ[:1], **READ[1]), call(*NOOP[:1], **NOOP[1]),
                           call('finish', summary='The repair is incomplete.')])
        with tempfile.TemporaryDirectory() as d, patch('epagent.episode.grade_submission') as grader:
            report = run_episode('synthetic:unit-probe', d, model, synthetic=CASE)
            grader.assert_not_called()
            self.assertTrue(model.closed)
            self.assertEqual(report['steps'], 3)
            self.assertEqual(report['tool_calls'], 3)
            self.assertIsNone(report['reward'])
            self.assertTrue(report['scored'])
            self.assertTrue(report['behavior']['primary_recovery'])
            self.assertFalse(report['modified_files'])
            context = model.requests[0]
            self.assertIn('Return one.', context[1]['content'])
            self.assertEqual(json.loads(context[-1]['content'])['tool_result']['detail'], CASE['expected_failure'])
            self.assertEqual(json.loads(context[-1]['content'])['steps_remaining'], 12)
            self.assertEqual(json.loads(model.requests[1][-1]['content'])['tool_result']['content'], CASE['files']['counter.py'])
            events = [json.loads(s) for s in Path(report['paths']['trace']).read_text().splitlines()]
            self.assertEqual(sum(e['event'] == 'setup_tool_result' for e in events), 2)
            self.assertEqual(sum(e['event'] == 'assistant' for e in events), 3)
            self.assertEqual(report['initial_sha256'], report['final_sha256'])
            for path in ['report', 'trace', 'patch', 'conversation']:
                self.assertTrue(Path(report['paths'][path]).exists())

    def test_four_case_scripted_suite_is_fresh_fixed_and_non_reusable(self):
        configs = []
        models = []
        def factory(path, config):
            configs.append(config)
            model = FakeModel([call('finish', summary='This scripted test made no repair.')])
            models.append(model)
            return model
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'suite'
            result = run_suite(DATA/'eval-fixtures.json', DATA/'eval-protocol.json', Path('/unused'),
                               out, 'base', backend_factory=factory)
            self.assertEqual(result['registered_cases'], 4)
            self.assertEqual(result['scorable_cases'], 4)
            self.assertEqual(result['primary_successes'], 0)
            self.assertEqual(len(set(r['report'] for r in result['cases'])), 4)
            self.assertEqual(configs, [asdict(Config())] * 4)
            self.assertTrue(all(m.closed for m in models))
            with self.assertRaises(FileExistsError):
                run_suite(DATA/'eval-fixtures.json', DATA/'eval-protocol.json', '/unused', out, 'base', backend_factory=factory)

    def test_arm_constraints_fixed_limits_and_fixture_hash(self):
        _, base = registered(DATA/'eval-fixtures.json', DATA/'eval-protocol.json', 'base', None)
        _, adapted = registered(DATA/'eval-fixtures.json', DATA/'eval-protocol.json', 'adapted', '/surrogate')
        self.assertEqual({**asdict(adapted), 'adapter_dir': None}, asdict(base))
        for arm, adapter in [('base','/unexpected'),('adapted',None)]:
            with self.assertRaises(ValueError):
                registered(DATA/'eval-fixtures.json', DATA/'eval-protocol.json', arm, adapter)
        with tempfile.TemporaryDirectory() as d:
            fixtures=Path(d)/'fixtures.json'
            fixtures.write_text((DATA/'eval-fixtures.json').read_text()+'\n')
            with self.assertRaises(ValueError):
                registered(fixtures, DATA/'eval-protocol.json', 'base', None)

    def test_setup_mutation_and_inference_failure_preserve_failure(self):
        with tempfile.TemporaryDirectory() as d:
            workspace=Path(d)/'workspace'
            export_fixture(CASE,workspace)
            changed={**CASE,'forced_failed_edit': {'tool':'edit_file','arguments':CHANGE[1]}}
            with self.assertRaisesRegex(ValueError,'registered exact-match failure'):
                inject_setup(changed,workspace,[],lambda *args: None,Config())
        from epagent.mlx_backend import BackendError
        with tempfile.TemporaryDirectory() as d:
            model=FakeModel([BackendError('fixture failure')])
            report=run_episode('synthetic:unit-probe',d,model,synthetic=CASE)
            self.assertEqual(report['status'],'backend_failure')
            self.assertFalse(report['scored'])
            self.assertIsNone(report['reward'])
