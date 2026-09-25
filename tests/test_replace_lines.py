"""Engineering acceptance with scripted actions, never model inference."""
import json
from pathlib import Path
import tempfile
import unittest

from epagent.episode import Config, run_episode
from epagent.tools import ToolSession, execute, parse_call
from test_epagent import FakeModel, MACOS, call

ROOT = Path(__file__).resolve().parents[1]


class ReplaceLinesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'source.py'
        self.file.write_bytes(b'keep = 1\nvalue = 2\nlast = 3\n')
        self.session = ToolSession(self.root)

    def read(self, limit=8192):
        return execute(self.root, 'read_file', {'path': 'source.py'}, 8, limit, session=self.session)

    def edit(self, **overrides):
        args = dict(path='source.py', version='v1', start_line=2, end_line=2, new_text='value = 20')
        args.update(overrides)
        name, args = parse_call(call('replace_lines', **args))
        return execute(self.root, name, args, 8, 8192, session=self.session)

    def test_preserves_unrelated_bytes_and_newline_conventions(self):
        for sep in [b'\n', b'\r\n', b'\r']:
            for terminal in [True, False]:
                with self.subTest(sep=sep, terminal=terminal):
                    self.session = ToolSession(self.root)
                    original = sep.join([b'# keep', b'x = 2', b'# final']) + (sep if terminal else b'')
                    self.file.write_bytes(original)
                    self.read()
                    result = self.edit(new_text='x = 3\nmore = 4\n')
                    expected = original.replace(b'x = 2' + sep, b'x = 3' + sep + b'more = 4' + sep)
                    self.assertEqual(self.file.read_bytes(), expected)
                    self.assertTrue(result['changed'])
                    observation = self.read()
                    self.edit(version=observation['version'], start_line=4, end_line=4, new_text='# end\n')
                    self.assertEqual(self.file.read_bytes(), expected.replace(b'# final', b'# end'))

    def test_stale_unobserved_noop_and_failure_then_corrected_edit(self):
        with self.assertRaisesRegex(ValueError, 'unobserved'):
            self.edit()
        self.read()
        before = self.file.read_bytes()
        with self.assertRaisesRegex(ValueError, 'No bytes changed'):
            self.edit(new_text='value = 2\n')
        self.assertEqual(self.file.read_bytes(), before)
        self.assertTrue(self.edit()['changed'])
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.edit(new_text='value = 40')
        obs = self.read()
        self.file.write_bytes(self.file.read_bytes() + b'# external change\n')
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.edit(version=obs['version'])

    def test_bounds_types_size_truncation_and_mixed_newlines(self):
        self.read()
        before = self.file.read_bytes()
        for args in [dict(start_line=0), dict(end_line=4), dict(start_line=3, end_line=2),
                     dict(start_line=True), dict(start_line='2'), dict(new_text='é' * 128001)]:
            with self.subTest(args=list(args)), self.assertRaises(ValueError):
                self.edit(**args)
            self.assertEqual(self.file.read_bytes(), before)
        self.assertIsNone(self.read(limit=4)['version'])
        with self.assertRaisesRegex(ValueError, 'unobserved'):
            self.edit()
        self.file.write_bytes(b'a\r\nb\nc\n')
        version = self.read()['version']
        with self.assertRaisesRegex(ValueError, 'Mixed newline'):
            self.edit(version=version)

    def test_confinement_symlinks_hardlinks_and_version_path_binding(self):
        self.read()
        (self.root / 'other.py').write_bytes(self.file.read_bytes())
        (self.root / 'link.py').symlink_to(self.file)
        import os
        os.link(self.root / 'other.py', self.root / 'hard.py')
        for path in ['../escape.py', str(self.file), 'link.py', 'hard.py', 'other.py']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.edit(path=path)
        (self.root / 'hard.py').unlink()
        with self.assertRaisesRegex(ValueError, 'unobserved'):
            self.edit(path='other.py')

    def test_result_limit_deletion_unicode_and_schema(self):
        self.file.write_bytes(b'a' * 200000 + b'\nb\n')
        self.session.observe('source.py', self.file.read_bytes(), False)
        with self.assertRaisesRegex(ValueError, 'Result exceeds'):
            self.edit(new_text='c' * 100000)
        self.file.write_bytes('é\nλ\nend\n'.encode())
        obs = self.read()
        self.edit(version=obs['version'], new_text='')
        self.assertEqual(self.file.read_bytes(), 'é\nend\n'.encode())
        with self.assertRaisesRegex(ValueError, 'object'):
            parse_call(json.dumps({'tool': 'replace_lines', 'arguments': []}))


@unittest.skipUnless(MACOS, 'Uses the existing macOS constrained Python runner')
class ScriptedRepairTests(unittest.TestCase):
    def test_two_complete_repairs_with_failure_recovery_and_real_tests(self):
        replacements = {'cart-total': '    return sum(price * quantity for price, quantity in rows)',
                        'sorted-unique': '    return sorted(set(values))'}
        for ident, replacement in replacements.items():
            with self.subTest(fixture=ident), tempfile.TemporaryDirectory() as tmp:
                fixture = json.loads((ROOT / 'data/epagent-development' / (ident + '.json')).read_text())
                path = fixture['source']
                outputs = [call('list_files'), call('read_file', path=path),
                    call('replace_lines', path=path, version='v1', start_line=99, end_line=99, new_text=replacement),
                    call('replace_lines', path=path, version='v1', start_line=4, end_line=4, new_text=replacement),
                    call('run_python', code="exec(open('checks.py').read())"),
                    call('finish', summary='Changed the function and observed ' + fixture['pass_marker'])]
                model = FakeModel(outputs)
                report = run_episode('development:' + ident, tmp, model, Config(), development=fixture)
                self.assertEqual(report['status'], 'finished')
                self.assertTrue(report['development']['repair_passed'])
                self.assertIsNone(report['reward'])
                self.assertEqual(report['modified_files'], [path])
                original = fixture['files'][path]
                expected = original.splitlines(keepends=True)
                expected[3] = replacement + '\n'
                final = Path(report['paths']['workspace'], path).read_bytes()
                self.assertEqual(final, ''.join(expected).encode())
                self.assertIn('inclusive integer range', model.requests[3][-1]['content'])
                self.assertFalse(json.loads(model.requests[3][-1]['content'])['tool_result']['changed'])
                self.assertIn(fixture['pass_marker'], model.requests[-1][-1]['content'])
                self.assertTrue(model.closed)

    def test_noop_and_changed_test_cannot_claim_repair(self):
        fixture = json.loads((ROOT / 'data/epagent-development/cart-total.json').read_text())
        for outputs in [[call('finish', summary='done')],
                        [call('edit_file', path='checks.py', old_text=fixture['files']['checks.py'],
                              new_text='print("PASS cart-total")\n'), call('finish', summary='done')]]:
            with tempfile.TemporaryDirectory() as tmp:
                report = run_episode('development:cart-total', tmp, FakeModel(outputs), development=fixture)
                self.assertFalse(report['development']['repair_passed'])
                self.assertFalse(report['development']['original_visible_tests_passed'])
