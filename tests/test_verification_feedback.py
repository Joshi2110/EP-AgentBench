"""Scripted engineering acceptance only; no model generation or physics changes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epagent.development import check_development
from epagent.episode import run_episode
from epagent.tools import SYSTEM_PROMPT
from epagent.verification import VerificationFeedback, check_syntax, system_prompt
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
    def episode(self, outputs, *, enabled=True):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        model = FakeModel(outputs)

        def independent(*args):
            self.assertTrue(model.closed, 'Independent checks must follow agent termination')
            return check_development(*args)

        with patch('epagent.development.check_development', side_effect=independent):
            report = run_episode('development:cart-total', temp.name, model, development=FIXTURE,
                                 verification_feedback=enabled)
        self.assertEqual(report['status'], 'finished', report['errors'])
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
                                 call('finish', summary='All tests pass')])
        checks = feedback(report)
        self.assertEqual(checks[0]['syntax']['status'], 'valid')
        self.assertEqual(checks[-1]['finish_evidence']['claim_support'], 'manual_review_required')
        self.assertFalse(report['development']['repair_passed'])
        self.assertFalse(report['development']['original_visible_tests_passed'])

    def test_missing_tests_are_exposed_but_honest_unresolved_finish_is_allowed(self):
        report, _ = self.episode([read('cart.py'), edit('    return 0', version='v1'),
                                 call('finish', summary='Changed code but did not run tests; unresolved.')])
        self.assertEqual(feedback(report)[-1]['finish_evidence']['claim_support'], 'no_post_change_execution')
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
        report, model = self.episode([call('run_python', code=f"open('cart.py', 'w').write({invalid!r})"),
                                     call('finish', summary='Source is invalid; no repair.')])
        self.assertEqual(feedback(report)[0]['syntax']['status'], 'invalid')
        self.assertIn('IndentationError', model.requests[1][-1]['content'])
        self.assertEqual(Path(report['paths']['workspace'], 'cart.py').read_text(), invalid)
        self.assertFalse(report['development']['repair_passed'])


if __name__ == '__main__':
    unittest.main()
