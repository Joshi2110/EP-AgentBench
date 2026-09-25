"""Tool-envelope rejection feedback. Scripted decisions only; no model, no training."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epagent.episode import run_episode
from epagent.tools import ARGUMENTS, CallError, argument_help, envelope_shape, parse_call
from test_epagent import FakeModel, MACOS, call

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'data/epagent-development/cart-total.json').read_text())
CORRECT = 'def cart_total(rows):\n    return sum(price * quantity for price, quantity in rows)'
BUGGY = 'def cart_total(rows):\n    return sum(price for price, quantity in rows)'


def rejection(text):
    with unittest.TestCase().assertRaises(CallError) as caught:
        parse_call(text)
    return caught.exception.category, str(caught.exception)


class EnvelopeErrorTests(unittest.TestCase):
    def test_missing_arguments_on_edit_file_names_its_own_tool_and_schema(self):
        category, detail = rejection(json.dumps({'tool': 'edit_file'}))
        self.assertEqual(category, 'missing_arguments')
        self.assertIn('Missing arguments object for edit_file', detail)
        self.assertIn('"arguments" is required and must be a JSON object containing', detail)
        for field in ARGUMENTS['edit_file']:
            self.assertIn(field, detail)
        self.assertNotIn('list_files', detail, 'must not name a tool the agent did not call')

    def test_top_level_edit_file_parameters_are_named_and_values_preserved(self):
        category, detail = rejection(json.dumps(
            {'tool': 'edit_file', 'path': 'cart.py', 'old_text': BUGGY, 'new_text': CORRECT}))
        self.assertEqual(category, 'missing_arguments')
        self.assertIn('Found new_text, old_text, path at the top level', detail)
        self.assertIn('move them inside "arguments" and keep the same values', detail)
        self.assertIn('"tool": "edit_file", "arguments": {"new_text": "<new_text>"', detail)
        self.assertNotIn('list_files', detail)
        # A structural placeholder example only; never the caller's own values.
        self.assertNotIn(CORRECT, detail.split('Shape: ')[1])
        self.assertNotIn('price * quantity', detail.split('Shape: ')[1])

    def test_single_misplaced_parameter_uses_singular_wording(self):
        _, detail = rejection(json.dumps({'tool': 'read_file', 'path': 'cart.py'}))
        self.assertIn('Found path at the top level; move it inside "arguments"', detail)

    def test_list_files_takes_an_empty_arguments_object(self):
        self.assertEqual(parse_call(json.dumps({'tool': 'list_files', 'arguments': {}})),
                         ('list_files', {}))
        category, detail = rejection(json.dumps({'tool': 'list_files'}))
        self.assertEqual(category, 'missing_arguments')
        self.assertIn('list_files takes no parameters, so use an empty object', detail)
        self.assertIn('{"tool": "list_files", "arguments": {}}', detail)

    def test_every_registered_tool_reports_its_own_schema(self):
        for name, fields in ARGUMENTS.items():
            with self.subTest(tool=name):
                _, detail = rejection(json.dumps({'tool': name}))
                self.assertIn(f'Missing arguments object for {name}', detail)
                self.assertIn(envelope_shape(name), detail)
                for field in fields:
                    self.assertIn(field, detail)
                for other in ARGUMENTS:
                    if other != name:
                        self.assertNotIn(f'for {other}', detail)
        self.assertIn('<integer>', envelope_shape('replace_lines'), 'integer fields stay integers')
        self.assertIn('no parameters', argument_help('list_files'))

    def test_non_object_arguments_are_rejected_and_named(self):
        for value in [[], 'path=cart.py', 3, None, True]:
            with self.subTest(value=value):
                category, detail = rejection(json.dumps({'tool': 'edit_file', 'arguments': value}))
                self.assertEqual(category, 'schema_violation')
                self.assertIn('arguments for edit_file must be a JSON object', detail)
                self.assertIn(type(value).__name__, detail)

    def test_strict_validation_is_unchanged(self):
        # Extra top-level keys alongside a present arguments object stay a violation.
        self.assertEqual(rejection(json.dumps(
            {'tool': 'list_files', 'arguments': {}, 'note': 'x'}))[0], 'schema_violation')
        # Missing keys inside arguments, wrong types, unknown tools and bad JSON all still fail.
        self.assertEqual(rejection(json.dumps({'tool': 'edit_file', 'arguments': {'path': 'a'}}))[0],
                         'missing_arguments')
        self.assertEqual(rejection(json.dumps({'tool': 'replace_lines', 'arguments': {
            'path': 'a', 'version': 'v1', 'start_line': '1', 'end_line': 1, 'new_text': ''}}))[0],
            'schema_violation')
        self.assertEqual(rejection(json.dumps({'tool': 'nope', 'arguments': {}}))[0], 'invalid_tool')
        self.assertEqual(rejection('{"tool": "list_files", "arguments": {}')[0], 'json_syntax')
        self.assertEqual(rejection('not json at all')[0], 'json_syntax')

    def test_historical_rejection_text_is_preserved_in_the_archive(self):
        analysis = json.loads((ROOT / 'artifacts/ep-agent/7b-contract-smoke'
                                      '/envelope-analysis.json').read_text())
        self.assertIn('use an empty object for list_files',
                      analysis['envelope_error']['message_received'],
                      'the archived episode must keep the message it actually received')
        self.assertEqual(analysis['outcome']['repair_passed'], False)
        self.assertFalse(analysis['offline_counterfactual']['not_an_agent_repair'] == '')


@unittest.skipUnless(MACOS, 'Uses existing macOS constrained execution')
class CorrectedEnvelopeEpisodeTests(unittest.TestCase):
    def test_agent_reads_the_accurate_error_fixes_the_envelope_and_repairs(self):
        malformed = json.dumps({'tool': 'edit_file', 'path': 'cart.py',
                                'old_text': BUGGY, 'new_text': CORRECT})
        outputs = [call('read_file', path='cart.py'), malformed,
                   call('edit_file', path='cart.py', old_text=BUGGY, new_text=CORRECT),
                   call('run_python', code="exec(open('checks.py').read())"),
                   call('finish', summary='Corrected the envelope, edited cart.py, '
                                          'ran checks.py: PASS cart-total.')]
        model = FakeModel(outputs)
        order = []
        import epagent.development as development
        real = development.check_development

        def spy(*args):
            order.append(model.closed)
            return real(*args)

        with tempfile.TemporaryDirectory() as temp, \
             patch('epagent.development.check_development', side_effect=spy):
            report = run_episode('development:cart-total', temp, model, development=FIXTURE,
                                 verification_feedback=True)
            workspace = Path(report['paths']['workspace'], 'cart.py').read_text()
            events = [json.loads(s) for s in Path(report['paths']['trace']).read_text().splitlines()]
        # The rejection is accurate, actionable and did not execute the call.
        rejected = next(e['data']['observation'] for e in events
                        if e['event'] == 'tool_result' and e['data']['step'] == 2)
        self.assertEqual(rejected['error'], 'missing_arguments')
        self.assertIn('Missing arguments object for edit_file', rejected['detail'])
        self.assertIn('move them inside "arguments"', rejected['detail'])
        self.assertNotIn('list_files', rejected['detail'])
        self.assertEqual(json.loads(model.requests[2][-1]['content'])['tool_result']['error'],
                         'missing_arguments')
        self.assertFalse(any(e['event'] == 'tool_result' and e['data']['step'] == 2
                             and e['data']['patch'] for e in events), 'rejected call must not run')
        # The corrected envelope carries the same values through to a real repair.
        self.assertEqual(report['status'], 'finished')
        self.assertEqual(report['modified_files'], ['cart.py'])
        self.assertIn(CORRECT, workspace)
        self.assertTrue(report['development']['repair_passed'])
        self.assertEqual(order, [True], 'grader runs only after the backend closes')
        self.assertFalse(any('repair_passed' in json.dumps(q) for q in model.requests),
                         'no grader result may reach the model')

    def test_verification_feedback_v2_still_reports_removal_and_defers_finish(self):
        model = FakeModel([
            call('read_file', path='cart.py'),
            call('edit_file', path='cart.py', old_text='def cart_total(rows):',
                 new_text='def renamed(rows):'),
            call('finish', summary='Renamed it.'),
            call('run_python', code="exec(open('checks.py').read())"),
            call('finish', summary='Ran checks.py; it failed.')])
        with tempfile.TemporaryDirectory() as temp:
            report = run_episode('development:cart-total', temp, model, development=FIXTURE,
                                 verification_feedback=True)
            events = [json.loads(s) for s in Path(report['paths']['trace']).read_text().splitlines()]
        feedback = [e['data'] for e in events if e['event'] == 'verification_feedback']
        self.assertEqual(feedback[0]['removed_definitions'], {'cart.py': ['cart_total']})
        self.assertEqual(feedback[1]['finish_deferred']['reminders_used'], 1)
        self.assertEqual(report['finish_reminders'], 1)
        self.assertEqual(report['termination_reason'], 'finish_tool')
        self.assertFalse(report['development']['repair_passed'])


if __name__ == '__main__':
    unittest.main()
