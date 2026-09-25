"""Evaluation 01 preparation checks. Scripted agents only; no model, no training."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from epagent.assessment import ARMS, independent_result, registered, run_suite, visible_fixture
from epagent.verification import discover_tests
from test_epagent import FakeModel, MACOS, call

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/epagent-evaluation-01'
FIXTURES, PROTOCOL = DATA / 'fixtures.json', DATA / 'protocol.json'
CASES = json.loads(FIXTURES.read_text())
SPEC = json.loads(PROTOCOL.read_text())
USED = set()
for name in ['v1', 'v2', 'v3']:
    for kind in ['fixtures', 'eval-fixtures']:
        for case in json.loads((ROOT / f'data/epagent-sft-{name}/{kind}.json').read_text()):
            USED.add(case['family'])
            USED.add(case['id'])


class FixtureDesignTests(unittest.TestCase):
    def test_ten_distinct_families_none_previously_used(self):
        self.assertEqual(len(CASES), 10)
        self.assertEqual(len({c['id'] for c in CASES}), 10)
        self.assertEqual(len({c['family'] for c in CASES}), 10)
        self.assertFalse({c['family'] for c in CASES} & USED)
        self.assertFalse({c['id'] for c in CASES} & USED)
        for reserved in ['cart-total', 'sorted-unique']:
            self.assertNotIn(reserved, {c['id'] for c in CASES})

    def test_visible_tests_are_not_copies_of_the_independent_tests(self):
        for case in CASES:
            with self.subTest(fixture=case['id']):
                visible = case['files']['checks.py']
                hidden = case['independent_test']
                self.assertNotEqual(visible, hidden)
                self.assertLess(case['visible_assertions'], case['independent_assertions'])
                extra = [l for l in hidden.splitlines()
                         if l.startswith('assert F') and l not in visible.splitlines()]
                self.assertGreaterEqual(len(extra), 3, 'the hidden test must cover more')
                self.assertNotEqual(case['independent_marker'], case['pass_marker'])

    def test_no_hidden_material_reaches_the_workspace(self):
        for case in CASES:
            with self.subTest(fixture=case['id']):
                exported = visible_fixture(case)
                self.assertEqual(sorted(exported), ['files', 'id', 'pass_marker', 'source'])
                blob = json.dumps(exported)
                self.assertNotIn(case['independent_marker'], blob)
                self.assertNotIn(case['reference_source'], blob)
                for line in case['independent_test'].splitlines():
                    if line.startswith('assert F') and line not in case['files']['checks.py']:
                        self.assertNotIn(line, blob)

    def test_layouts_are_varied_and_tests_discoverable(self):
        sources = {c['source'] for c in CASES}
        self.assertEqual(len(sources), 10)
        self.assertEqual(len({s.split('/')[0] for s in CASES[0]['files'] if '/' in s} |
                             {s.split('/')[0] for c in CASES for s in c['files'] if '/' in s}), 10)
        for case in CASES:
            with self.subTest(fixture=case['id']):
                self.assertIn('/', case['source'], 'source lives in a package directory')
                self.assertEqual(discover_tests(case['files']), ['checks.py'])
                self.assertGreaterEqual(len(case['files']), 4)

    def test_frozen_hashes_match_the_files_on_disk(self):
        self.assertEqual(SPEC['fixtures_sha256'],
                         hashlib.sha256(FIXTURES.read_bytes()).hexdigest())
        for name, expected in SPEC['frozen_sha256'].items():
            with self.subTest(path=name):
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
        self.assertIn('NOT independently pre-registered', SPEC['pre_registration_limits'])
        self.assertEqual(SPEC['execution_status'].startswith('No base or verification arm'), True)

    def test_offline_validation_record_is_complete(self):
        record = json.loads((DATA / 'validation.json').read_text())
        self.assertFalse(record['model_inference_performed'])
        self.assertTrue(record['hidden_material_absent_from_workspace'])
        self.assertTrue(record['sandbox_isolation']['direct_read_blocked'])
        self.assertEqual(len(record['fixtures']), 10)
        for entry in record['fixtures']:
            with self.subTest(fixture=entry['id']):
                self.assertTrue(entry['starter_fails_independent'])
                self.assertTrue(entry['starter_fails_visible'])
                self.assertTrue(entry['reference_passes_independent'])
                self.assertTrue(entry['reference_passes_visible'])
                self.assertFalse(entry['visible_equals_independent'])


class ProtocolTests(unittest.TestCase):
    def test_both_arms_share_everything_except_the_feedback_condition(self):
        base_cases, base_config, base_feedback, _ = registered(FIXTURES, PROTOCOL, 'baseline')
        arm_cases, arm_config, arm_feedback, _ = registered(FIXTURES, PROTOCOL, 'verification')
        self.assertEqual(base_config, arm_config)
        self.assertEqual([c['id'] for c in base_cases], [c['id'] for c in arm_cases])
        self.assertEqual((base_feedback, arm_feedback), (False, True))
        self.assertEqual(base_config.seed, 0)
        self.assertEqual(base_config.temperature, 0.0)
        self.assertIsNone(base_config.adapter_dir)

    def test_tampering_and_unknown_arms_are_refused(self):
        with self.assertRaises(ValueError):
            registered(FIXTURES, PROTOCOL, 'adapted')
        with tempfile.TemporaryDirectory() as d:
            changed = Path(d) / 'fixtures.json'
            changed.write_text(FIXTURES.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'registered ten-fixture'):
                registered(changed, PROTOCOL, 'baseline')


@unittest.skipUnless(MACOS, 'Uses existing macOS constrained execution')
class ScriptedArmTests(unittest.TestCase):
    def reference_agent(self, case):
        return [call('read_file', path=case['source']),
                call('edit_file', path=case['source'],
                     old_text=case['files'][case['source']], new_text=case['reference_source']),
                call('run_python', code="exec(open('checks.py').read())"),
                call('finish', summary='Repaired and ran checks.py.')]

    def suite(self, arm, script):
        models = []

        def factory(path, config):
            model = FakeModel(list(script))
            models.append(model)
            return model

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return run_suite(FIXTURES, PROTOCOL, Path('/unused'), Path(temp.name) / arm, arm,
                         backend_factory=factory), models

    def test_idle_agent_scores_zero_independent_successes_in_both_arms(self):
        for arm in sorted(ARMS):
            with self.subTest(arm=arm):
                report, models = self.suite(arm, [call('finish', summary='No repair attempted.')] * 3)
                self.assertEqual(report['status'], 'complete')
                self.assertEqual(report['independent_successes'], 0)
                self.assertEqual(report['primary'], '0/10')
                self.assertEqual(len(report['cases']), 10)
                self.assertTrue(all(m.closed for m in models))
                for entry in report['cases']:
                    self.assertFalse(entry['independent']['passed'])
                    self.assertFalse(entry['metrics']['source_changed'])
                    self.assertEqual(entry['metrics']['agent_initiated_test_executions'], 0)

    def test_reference_repair_scores_ten_out_of_ten_and_separates_the_two_counters(self):
        for arm in sorted(ARMS):
            with self.subTest(arm=arm):
                temp = tempfile.TemporaryDirectory()
                self.addCleanup(temp.cleanup)
                out = Path(temp.name) / arm
                cases = iter(CASES)

                def factory(path, config, cases=cases):
                    return FakeModel(self.reference_agent(next(cases)))

                report = run_suite(FIXTURES, PROTOCOL, Path('/unused'), out, arm,
                                   backend_factory=factory)
                self.assertEqual(report['primary'], '10/10')
                for entry in report['cases']:
                    metrics = entry['metrics']
                    self.assertTrue(entry['independent']['passed'])
                    self.assertIn('INDEPENDENT OK', entry['independent']['stdout'])
                    self.assertTrue(metrics['source_changed'])
                    self.assertTrue(metrics['unrelated_files_preserved'])
                    self.assertEqual(metrics['final_source_syntax'], 'valid')
                    self.assertEqual(metrics['agent_initiated_test_executions'], 1)
                    self.assertEqual(metrics['agent_initiated_observed_passes'], 1)
                    self.assertTrue(metrics['evidence_supported_finish'])
                    expected_runner = 1 if arm == 'verification' else 0
                    self.assertEqual(metrics['runner_initiated_test_executions'], expected_runner)
                    self.assertEqual(metrics['schema_errors'], 0)

    def test_hidden_test_is_unreachable_from_inside_an_episode(self):
        case = CASES[0]
        probe = [call('list_files'),
                 call('run_python', code="import pathlib; print(sorted(str(p) for p in "
                                         "pathlib.Path('.').rglob('*')))"),
                 call('finish', summary='Listed the workspace.')]
        report, _ = self.suite('baseline', probe)
        listing = report['cases'][0]
        trace = Path(listing['report']).parent / 'trajectory.jsonl'
        text = trace.read_text()
        self.assertNotIn(case['independent_marker'], text)
        self.assertNotIn(case['reference_source'].strip().splitlines()[-1], text)
        workspace = Path(listing['report']).parent / 'workspace'
        present = {p.name for p in workspace.rglob('*') if p.is_file()}
        self.assertNotIn('independent_test', present)

    def test_independent_grading_runs_on_the_final_source_only(self):
        case = next(c for c in CASES if c['id'] == 'interval-merge')
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            for name, content in case['files'].items():
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            starter = independent_result(case, workspace, 8, 8192)
            (workspace / case['source']).write_text(case['reference_source'])
            repaired = independent_result(case, workspace, 8, 8192)
            # A forged visible test cannot influence the independent result.
            (workspace / 'checks.py').write_text("print('PASS interval-merge')\n")
            still = independent_result(case, workspace, 8, 8192)
        self.assertFalse(starter['passed'])
        self.assertIn('AssertionError', starter['stderr'])
        self.assertTrue(repaired['passed'])
        self.assertTrue(still['passed'])
        self.assertIn('never present in the workspace', repaired['method'])


if __name__ == '__main__':
    unittest.main()
