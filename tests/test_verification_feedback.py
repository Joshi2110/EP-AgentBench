"""Scripted engineering acceptance only; no model generation or physics changes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epagent.development import check_development
from epagent.episode import Config, run_episode
from epagent.tools import SYSTEM_PROMPT
from epagent.verification import (VerificationFeedback, check_syntax, discover_tests,
                                  executed_tests, public_definitions, removed_definitions,
                                  system_prompt)
from test_epagent import FakeModel, MACOS, call

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'data/epagent-development/cart-total.json').read_text())
CORRECT = '    return sum(price * quantity for price, quantity in rows)'


def read(path):
    return call('read_file', path=path)


def edit(text, version='v3', start=4, end=4):
    return call('replace_lines', path='cart.py', version=version,
                start_line=start, end_line=end, new_text=text)


def events(report):
    return [json.loads(line) for line in Path(report['paths']['trace']).read_text().splitlines()]


def feedback(report):
    return [e['data'] for e in events(report) if e['event'] == 'verification_feedback']


class VerificationUnitTests(unittest.TestCase):
    def test_prompt_is_opt_in_and_contains_no_worked_solution(self):
        self.assertEqual(system_prompt(), SYSTEM_PROMPT)
        prompt = system_prompt(True)
        self.assertTrue(prompt.startswith(SYSTEM_PROMPT))
        for text in ['relevant test source', 'function signatures', 'No code is automatically',
                     'test command and observed result', 'If you did not run tests']:
            self.assertIn(text, prompt)
        for text in ['cart_total', 'price * quantity', 'print(2 + 2)', 'exact existing text']:
            self.assertNotIn(text, prompt)
        with self.assertRaisesRegex(ValueError, 'Frozen synthetic'):
            run_episode('synthetic:x', 'unused', FakeModel([]), synthetic={'id': 'x'},
                        verification_feedback=True)

    def test_checker_limits_and_missing_output_never_mean_valid(self):
        changed = {'x.py': b'x = 1\n'}
        for result in [{'status': 'timeout'}, {'status': 'output_limit'},
                       {'status': 'completed', 'stdout': '{'},
                       {'status': 'completed', 'stdout': '{}'}]:
            with self.subTest(result=result), patch('epagent.verification.run_python', return_value=result):
                self.assertEqual(check_syntax('.', changed, 1, 8192)['status'], 'not_checked')
        with patch('epagent.verification.run_python') as runner:
            self.assertEqual(check_syntax('.', changed, 0, 8192)['status'], 'not_checked')
            runner.assert_not_called()

    def test_finish_evidence_excludes_stale_and_self_modifying_runs(self):
        state = VerificationFeedback()
        before = {'text.txt': b'old'}
        after = {'text.txt': b'new'}
        state.observe('.', 1, 'run_python', before, before, {'status': 'completed'}, 1, 8192)
        state.observe('.', 2, 'run_python', before, after, {'status': 'completed'}, 1, 8192)
        evidence = state.observe('.', 3, 'finish', after, after, {}, 1, 8192)['finish_evidence']
        self.assertEqual(evidence['post_change_python_runs'], [])
        self.assertEqual(evidence['claim_support'], 'no_post_change_execution')
        state.observe('.', 4, 'run_python', after, after, {'status': 'python_error'}, 1, 8192)
        evidence = state.observe('.', 5, 'finish', after, after, {}, 1, 8192)['finish_evidence']
        self.assertEqual(evidence['post_change_python_runs'], [{'step': 4, 'status': 'python_error'}])
        self.assertEqual(evidence['claim_support'], 'manual_review_required')


@unittest.skipUnless(MACOS, 'Uses existing macOS constrained execution')
class ScriptedVerificationTests(unittest.TestCase):
    def episode(self, outputs, *, enabled=True, status='finished'):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        model = FakeModel(outputs)

        def independent(*args):
            self.assertTrue(model.closed, 'Independent checks must follow agent termination')
            return check_development(*args)

        with patch('epagent.development.check_development', side_effect=independent):
            report = run_episode('development:cart-total', temp.name, model, development=FIXTURE,
                                 verification_feedback=enabled)
        self.assertEqual(report['status'], status, report['errors'])
        return report, model

    def test_invalid_write_is_visible_then_corrected_and_tested_without_rollback(self):
        outputs = [read('README.md'), read('checks.py'), read('cart.py'),
                   edit('    return 1', start=3, end=4), read('cart.py'),
                   edit('def cart_total(rows):\n' + CORRECT, version='v4', start=3, end=3),
                   call('run_python', code="exec(open('checks.py').read())"),
                   call('finish', summary='Restored cart_total and ran checks.py: PASS cart-total.')]
        report, model = self.episode(outputs)
        first, repaired, finish = feedback(report)
        self.assertEqual(first['write_status'], 'applied_with_syntax_errors')
        error = first['syntax']['files']['cart.py']
        self.assertEqual((error['error'], error['line']), ('IndentationError', 3))
        self.assertEqual(repaired['syntax']['status'], 'valid')
        self.assertIn('IndentationError', model.requests[4][-1]['content'])
        # Next source observation contains the invalid write, not repaired/reverted code.
        source_observation = json.loads(model.requests[5][-1]['content'])['tool_result']['content']
        self.assertIn('\n    return 1\n', source_observation)
        self.assertNotIn('def cart_total', source_observation)
        self.assertIn('PASS cart-total', model.requests[7][-1]['content'])
        self.assertTrue(report['development']['repair_passed'])
        self.assertIsNone(report['reward'])
        self.assertEqual(report['tool_calls'], len(outputs))  # Checker is not an agent action.
        self.assertEqual(report['modified_files'], ['cart.py'])
        expected = FIXTURE['files']['cart.py'].replace('    return sum(price for price, quantity in rows)', CORRECT)
        self.assertEqual(Path(report['paths']['workspace'], 'cart.py').read_bytes(), expected.encode())
        self.assertEqual(finish['finish_evidence']['post_change_python_runs'],
                         [{'step': 7, 'status': 'completed'}])

    def test_valid_syntax_and_printed_pass_do_not_replace_independent_tests(self):
        report, _ = self.episode([read('cart.py'), edit('    return 0', version='v1'),
                                 call('run_python', code="print('PASS cart-total')"),
                                 call('finish', summary='All tests pass'),
                                 call('finish', summary='All tests pass')])
        checks = feedback(report)
        self.assertEqual(checks[0]['syntax']['status'], 'valid')
        # Printing the marker is neither running checks.py nor independent verification.
        self.assertEqual(checks[-2]['finish_deferred']['reminders_used'], 1)
        self.assertEqual(checks[-1]['finish_evidence']['workspace_tests']['executed'], [])
        self.assertEqual(checks[-1]['finish_evidence']['claim_support'], 'no_workspace_test_execution')
        self.assertFalse(report['development']['repair_passed'])
        self.assertFalse(report['development']['original_visible_tests_passed'])

    def test_missing_tests_are_exposed_but_honest_unresolved_finish_is_allowed(self):
        honest = call('finish', summary='Changed code but did not run tests; unresolved.')
        report, _ = self.episode([read('cart.py'), edit('    return 0', version='v1'), honest, honest])
        self.assertEqual(feedback(report)[-2]['finish_deferred']['accepted'], False)
        self.assertEqual(feedback(report)[-1]['finish_evidence']['claim_support'], 'no_workspace_test_execution')
        self.assertFalse(report['development']['repair_passed'])

    def test_default_episode_prompt_and_observations_are_unchanged(self):
        with patch('epagent.verification.check_syntax') as checker:
            report, model = self.episode([read('cart.py'), edit(CORRECT, version='v1'),
                                         call('finish', summary='Not tested by agent')], enabled=False)
        checker.assert_not_called()
        self.assertEqual(model.requests[0][0]['content'], SYSTEM_PROMPT)
        self.assertNotIn('verification_feedback', report)
        self.assertEqual(feedback(report), [])
        self.assertTrue(report['development']['repair_passed'])

    def test_compiler_does_not_execute_or_import_workspace_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            side_effect = b"open('executed.txt', 'w').write('bad')\nraise RuntimeError('not executed')\n"
            (root / 'json.py').write_bytes(side_effect)
            result = check_syntax(root, {'json.py': side_effect, 'bad.py': b'    return 1\n',
                                        'empty.py': b'', 'null.py': b'\0', 'removed.py': None}, 8, 8192)
            self.assertEqual(result['status'], 'invalid')
            self.assertEqual(result['files']['json.py']['status'], 'valid')
            self.assertEqual(result['files']['empty.py']['status'], 'valid')
            self.assertEqual(result['files']['null.py']['status'], 'invalid')
            self.assertEqual(result['files']['removed.py']['status'], 'not_checked')
            self.assertFalse((root / 'executed.txt').exists())
            self.assertFalse((root / '__pycache__').exists())

    def test_python_run_writes_get_checked_too(self):
        invalid = "    return 1\n"
        broken = call('finish', summary='Source is invalid; no repair.')
        report, model = self.episode([call('run_python', code=f"open('cart.py', 'w').write({invalid!r})"),
                                     broken, broken])
        self.assertEqual(feedback(report)[0]['syntax']['status'], 'invalid')
        self.assertIn('IndentationError', model.requests[1][-1]['content'])
        self.assertEqual(Path(report['paths']['workspace'], 'cart.py').read_text(), invalid)
        self.assertFalse(report['development']['repair_passed'])


class DefinitionAndTestDiscoveryTests(unittest.TestCase):
    def source(self, text):
        return text.encode('utf-8')

    def test_removal_rename_class_and_unrelated_edits_are_distinguished(self):
        base = ('def cart_total(rows):\n    return 0\n\n'
                'class Report:\n    pass\n\ndef _hidden():\n    pass\n')
        self.assertEqual(public_definitions(base), ['Report', 'cart_total'], 'private names excluded')
        keep_class = 'class Report:\n    pass\n'
        for label, after, expected in [
                ('function removal', keep_class, ['cart_total']),
                ('function rename', 'def calculate_total(rows):\n    return 0\n\n' + keep_class, ['cart_total']),
                ('class removal', 'def cart_total(rows):\n    return 0\n', ['Report']),
                ('unrelated edit', 'def cart_total(rows):\n    return 1 + 1\n\n' + keep_class, []),
                ('private removal', 'def cart_total(rows):\n    return 0\n\n' + keep_class, [])]:
            with self.subTest(label=label):
                gone, skipped = removed_definitions({'m.py': self.source(base)},
                                                    {'m.py': self.source(after)})
                self.assertEqual(skipped, {})
                self.assertEqual(gone.get('m.py', []), expected)
                if not expected:
                    self.assertNotIn('m.py', gone, 'silent when nothing public disappeared')

    def test_invalid_python_is_skipped_not_crashed(self):
        valid = self.source('def a():\n    return 1\n')
        broken = self.source('    return 1\n')
        self.assertIsNone(public_definitions(broken.decode()))
        for label, before, after in [('after invalid', valid, broken), ('before invalid', broken, valid)]:
            with self.subTest(label=label):
                gone, skipped = removed_definitions({'m.py': before}, {'m.py': after})
                self.assertEqual(gone, {})
                self.assertIn('m.py', skipped)
        self.assertIsNone(public_definitions('def a(:'))

    def test_discovery_uses_conventions_not_task_specific_names(self):
        listing = ['cart.py', 'checks.py', 'queue_ops.py', 'tests/check_packing.py', 'verify_flags.py',
                   'test_suffix.py', 'validation/check_middle.py', 'notes.txt', 'checkout.py']
        self.assertEqual(discover_tests(listing),
                         ['checks.py', 'test_suffix.py', 'tests/check_packing.py',
                          'validation/check_middle.py', 'verify_flags.py'])
        self.assertEqual(discover_tests(['cart.py', 'main.py']), [])

    def test_execution_recognition_rejects_ad_hoc_commands(self):
        tests = ['checks.py', 'tests/check_packing.py']
        for label, code, expected in [
                ('exec of file', "exec(open('checks.py').read())", ['checks.py']),
                ('runpy', "import runpy; runpy.run_path('tests/check_packing.py', run_name='__main__')",
                 ['tests/check_packing.py']),
                ('import module', 'import checks', ['checks.py']),
                ('printed marker', "print('PASS cart-total')", []),
                ('ad-hoc call', "from cart import calculate_total\nprint(calculate_total([]))", []),
                ('names file but never runs it', "print('checks.py')", []),
                ('syntax error', 'def broken(:', [])]:
            with self.subTest(label=label):
                self.assertEqual(executed_tests(code, tests), expected)

    def test_finish_reminder_is_bounded_and_never_blocks(self):
        state = VerificationFeedback()
        self.assertIsNone(state.consider_finish(1, 12, 100), 'no discovered test must never defer')
        state.register_workspace({'cart.py': b'', 'checks.py': b'x'})
        self.assertEqual(state.workspace_tests, ['checks.py'])
        self.assertIsNotNone(state.consider_finish(1, 12, 100))
        self.assertIsNone(state.consider_finish(2, 12, 100), 'at most one reminder per episode')
        spent = VerificationFeedback()
        spent.register_workspace({'checks.py': b'x'})
        self.assertIsNone(spent.consider_finish(11, 12, 100), 'too few turns left to act')
        self.assertIsNone(spent.consider_finish(1, 12, 0), 'no wall time left to act')
        ran = VerificationFeedback()
        ran.register_workspace({'checks.py': b'x'})
        ran.observe('.', 1, 'run_python', {}, {}, {'status': 'completed'}, 1, 8192,
                    arguments={'code': "exec(open('checks.py').read())"})
        self.assertEqual(ran.executed(), ['checks.py'])
        self.assertIsNone(ran.consider_finish(2, 12, 100), 'a test already ran')


@unittest.skipUnless(MACOS, 'Uses existing macOS constrained execution')
class ContractFeedbackEpisodeTests(unittest.TestCase):
    RUN_CHECKS = call('run_python', code="exec(open('checks.py').read())")
    episode = ScriptedVerificationTests.episode

    def test_removed_definition_reaches_the_model_and_can_be_restored(self):
        report, model = self.episode([
            read('cart.py'),
            edit('def calculate_total(cart_items):\n    return 0', version='v1', start=3, end=4),
            read('cart.py'),
            edit('def cart_total(rows):\n' + CORRECT, version='v2', start=3, end=4),
            self.RUN_CHECKS,
            call('finish', summary='Restored cart_total and ran checks.py; it printed PASS cart-total.')])
        removal = feedback(report)[0]
        self.assertEqual(removal['removed_definitions'], {'cart.py': ['cart_total']})
        self.assertEqual(removal['syntax']['status'], 'valid', 'removal is reported even when syntax is fine')
        self.assertIn('removed_definitions', model.requests[2][-1]['content'])
        self.assertIn('cart_total', model.requests[2][-1]['content'])
        restored = feedback(report)[1]
        self.assertEqual(restored['removed_definitions'], {'cart.py': ['calculate_total']},
                         'the restoring edit removes the temporary name; removal is reported, not judged')
        self.assertIn('def cart_total(rows):', Path(report['paths']['workspace'], 'cart.py').read_text())
        evidence = feedback(report)[-1]['finish_evidence']
        self.assertEqual(evidence['workspace_tests']['executed'], ['checks.py'])
        self.assertEqual(evidence['claim_support'], 'manual_review_required')
        self.assertTrue(evidence['workspace_tests']['executions'][0]['tests_unmodified'])
        self.assertTrue(report['development']['repair_passed'])
        self.assertEqual(report.get('finish_reminders'), None, 'no reminder was needed')

    def test_premature_finish_is_deferred_once_then_accepted_after_the_real_test(self):
        report, model = self.episode([
            read('cart.py'), edit(CORRECT, version='v1'),
            call('finish', summary='Fixed it.'),
            self.RUN_CHECKS,
            call('finish', summary='Ran checks.py; it printed PASS cart-total.')])
        deferral = feedback(report)[1]['finish_deferred']
        self.assertFalse(deferral['accepted'])
        self.assertEqual((deferral['reminders_used'], deferral['reminders_allowed']), (1, 1))
        self.assertEqual(deferral['discovered_tests'], ['checks.py'])
        self.assertEqual(report['finish_reminders'], 1)
        # The reminder is actionable in the next request, and the workspace is untouched by it.
        self.assertIn('finish_deferred', model.requests[3][-1]['content'])
        self.assertIs(json.loads(model.requests[3][-1]['content'])['tool_result']['finished'], False)
        self.assertEqual(report['steps'], 5)
        self.assertEqual(report['termination_reason'], 'finish_tool')
        self.assertEqual(feedback(report)[-1]['finish_evidence']['claim_support'], 'manual_review_required')
        self.assertTrue(report['development']['repair_passed'])

    def test_repeated_finish_without_testing_is_accepted_and_never_loops(self):
        give_up = call('finish', summary='I did not run the workspace test.')
        report, _ = self.episode([read('cart.py'), edit(CORRECT, version='v1'), give_up, give_up])
        self.assertEqual(report['finish_reminders'], 1)
        self.assertEqual(report['steps'], 4, 'the second finish terminates the episode')
        self.assertEqual(report['termination_reason'], 'finish_tool')
        self.assertEqual(feedback(report)[-1]['finish_evidence']['claim_support'],
                         'no_workspace_test_execution')

    def test_no_reminder_when_the_budget_cannot_absorb_it(self):
        model = FakeModel([read('cart.py')] * 10 + [call('finish', summary='Out of turns; not tested.')] * 2)
        with tempfile.TemporaryDirectory() as temp:
            report = run_episode('development:cart-total', temp, model, Config(steps=11),
                                 development=FIXTURE, verification_feedback=True)
            events = [json.loads(s) for s in Path(report['paths']['trace']).read_text().splitlines()]
        self.assertEqual(report['status'], 'finished')
        self.assertEqual(report['termination_reason'], 'finish_tool')
        self.assertNotIn('finish_reminders', report, 'no turns left to act on a reminder')
        deferrals = [e for e in events if e['event'] == 'verification_feedback'
                     and 'finish_deferred' in e['data']]
        self.assertEqual(deferrals, [])

    def test_workspace_tests_are_discovered_from_the_original_export_only(self):
        forged = call('run_python', code="open('test_mine.py','w').write(\"print('PASS cart-total')\")")
        report, _ = self.episode([forged, call('finish', summary='Wrote my own test.'),
                                  call('finish', summary='Wrote my own test.')])
        evidence = feedback(report)[-1]['finish_evidence']
        self.assertEqual(evidence['workspace_tests']['discovered'], ['checks.py'])
        self.assertEqual(evidence['claim_support'], 'no_workspace_test_execution')
        self.assertFalse(report['development']['repair_passed'])


if __name__ == '__main__':
    unittest.main()
