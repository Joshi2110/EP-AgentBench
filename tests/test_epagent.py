"""Deterministic environment tests: no weights, inference, or hosted agent calls."""

import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from epbench import grader
from epbench.cli import init
from epagent.cli import main
from epagent.episode import Config, run_episode
from epagent.execution import preflight, run_python
from epagent.mlx_backend import BackendError, ContextLimit, configure_stop_tokens
from epagent.reward import grade_submission
from epagent.tools import execute, parse_call, safe_path, snapshot

ROOT = Path(__file__).resolve().parents[1]
MACOS = sys.platform == 'darwin' and Path('/usr/bin/sandbox-exec').exists()


def call(name, **arguments):
    return json.dumps({'tool': name, 'arguments': arguments})


class FakeModel:
    """Scripted tool decisions, explicitly marked fake in every report."""
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.metadata = {'backend': 'deterministic-fake', 'model_id': 'test-script', 'revision': 'v1'}
        self.closed = False
        self.requests = []

    def start(self, control):
        pass

    def generate(self, messages, seconds, emit):
        self.requests.append(json.loads(json.dumps(messages)))
        result = next(self.outputs)
        if isinstance(result, Exception):
            raise result
        return {'text': result, 'generation_tokens': None, 'prompt_tokens': None}

    def close(self):
        self.closed = True


class ToolTests(unittest.TestCase):
    def test_chat_end_token_is_honored_even_if_model_config_disagrees(self):
        tokenizer = SimpleNamespace(eos_token='<|im_end|>', eos_token_ids={151643})
        def add(token):
            self.assertEqual(token, '<|im_end|>')
            tokenizer.eos_token_ids.add(151645)
        tokenizer.add_eos_token = add
        self.assertEqual(configure_stop_tokens(tokenizer), [151643, 151645])
        tokenizer.eos_token = None
        with self.assertRaises(ValueError):
            configure_stop_tokens(tokenizer)

    def test_json_protocol_rejects_malformed_unknown_and_extra_arguments(self):
        for text in ['oops', '[]', '{}', '```json\n{}\n```',
                     call('shell', command='pwd'), call('read_file', path=123),
                     call('finish', summary='done', reward=1)]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_call(text)
        self.assertEqual(parse_call(call('list_files')), ('list_files', {}))

    def test_paths_links_and_exact_edits(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace = root / 'workspace'
            workspace.mkdir()
            private = root / 'private'
            private.write_text('private')
            for name in ['../private', str(private), 'a/../../private', '']:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    safe_path(workspace, name)
            (workspace / 'linked').symlink_to(private)
            with self.assertRaises(ValueError):
                safe_path(workspace, 'linked')
            with self.assertRaises(ValueError):
                snapshot(workspace)
            (workspace / 'linked').unlink()
            os.link(private, workspace / 'hardlink')
            with self.assertRaises(ValueError):
                safe_path(workspace, 'hardlink')
            (workspace / 'hardlink').unlink()
            execute(workspace, 'edit_file', {'path': 'x.py', 'old_text': '', 'new_text': 'x=1\nx=1\n'}, 1, 256)
            with self.assertRaises(ValueError):
                execute(workspace, 'edit_file', {'path': 'x.py', 'old_text': 'x=1', 'new_text': 'x=2'}, 1, 256)
            with self.assertRaises(FileNotFoundError):
                execute(workspace, 'read_file', {'path': 'missing'}, 1, 256)
            (workspace / 'large').write_bytes(b'a' * 256001)
            with self.assertRaises(ValueError):
                snapshot(workspace)

    def test_configuration_and_clean_cli_errors(self):
        for values in [{'steps': 0}, {'seconds': float('nan')}, {'seconds': float('inf')},
                       {'tool_seconds': -1}, {'context_tokens': 0}, {'max_tokens': 2049},
                       {'temperature': -0.1}, {'output_bytes': 0}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                Config(**values).validate()
        with patch('sys.stderr'):
            self.assertEqual(main(['run', 'hall-thrust', '--model-dir', '/missing', '--out', '/missing', '--steps', '0']), 2)
            self.assertEqual(main(['run', 'hall-thrust', '--model-dir', '/missing', '--out', '/missing']), 2)

    def test_preflight_failure_never_starts_model(self):
        with tempfile.TemporaryDirectory() as d:
            model = FakeModel([])
            with patch('epagent.episode.preflight', side_effect=RuntimeError('denied')), patch.object(model, 'start') as start:
                report = run_episode('hall-thrust', d, model)
            start.assert_not_called()
            self.assertEqual(report['status'], 'infrastructure_failure')
            self.assertIsNone(report['reward'])
            self.assertFalse(report['scored'])
            self.assertTrue(Path(report['paths']['report']).exists())


@unittest.skipUnless(MACOS, 'macOS restricted-development execution is required')
class ExecutionTests(unittest.TestCase):
    def test_runtime_preflight_and_denied_private_reads_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace = root / 'workspace'
            workspace.mkdir()
            private = root / 'private'
            private.write_text('DO_NOT_EXPOSE')
            self.assertTrue(preflight(workspace, [private, grader.__file__])['verified'])
            for code in [f"open({str(private)!r}).read()", f"open({str(private)!r}, 'w').write('bad')",
                         f"open({'/System/Volumes/Data' + str(private.resolve())!r}).read()",
                         "import subprocess; subprocess.run(['/bin/echo', 'bad'])",
                         "import os; os.listdir('..')"]:
                result = run_python(workspace, code)
                self.assertEqual(result['status'], 'python_error')
                self.assertIn('PermissionError', result['stderr'])
                self.assertNotIn('DO_NOT_EXPOSE', result['stdout'])
            self.assertEqual(private.read_text(), 'DO_NOT_EXPOSE')

    def test_python_failure_timeout_and_output_limit(self):
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            self.assertEqual(run_python(workspace, 'raise ValueError("bad")')['status'], 'python_error')
            self.assertEqual(run_python(workspace, 'while True: pass', seconds=0.2)['status'], 'timeout')
            result = run_python(workspace, 'print("x" * 10000)', output_bytes=256)
            self.assertEqual(result['status'], 'output_limit')
            self.assertLessEqual(len(result['stdout']) + len(result['stderr']), 256)
            result = run_python(workspace, "open('created.txt', 'w').write('ok'); print(2+2)")
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['stdout'].strip(), '4')

    def test_all_references_pass_through_unchanged_verifiers(self):
        original = grader.subprocess
        for task in grader.WORKSPACES:
            with self.subTest(task=task):
                result = grade_submission(task, ROOT / 'examples' / 'solutions' / task)
                self.assertEqual(result['reward'], 1)
                self.assertEqual(result['grading']['passed'], 13)
                self.assertIs(grader.subprocess, original)

    def test_grading_blocks_private_read_and_parent_symlink_attack(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            workspace, private = root / 'workspace', root / 'private'
            private.write_text('PRIVATE_CONTENT')
            init('hall-thrust', workspace)
            momentum = workspace / 'momentum.py'
            original = momentum.read_text()
            momentum.write_text(f'open({str(private)!r}).read()\n' + original)
            result = grade_submission('hall-thrust', workspace)
            self.assertEqual(result['reward'], 0)
            self.assertNotIn('PRIVATE_CONTENT', json.dumps(result))
            momentum.write_text(f"import os\nos.symlink({str(private)!r}, 'result.json')\nos._exit(0)\n" + original)
            with self.assertRaisesRegex(ValueError, 'unsafe result'):
                grade_submission('hall-thrust', workspace)

    def test_full_fake_episode_repair_run_finish_grade_save(self):
        outputs = [call('list_files'), call('read_file', path='momentum.py'),
                   call('edit_file', path='momentum.py',
                        old_text='u_next = speed[-1] + dx * electric / flux_next',
                        new_text='u_next = speed[-1] + dx * (electric + s_face * (p.u_neutral_m_per_s - speed[-1])) / flux_next'),
                   call('run_python', code='from momentum import Parameters, solve\nr=solve(Parameters())\nprint(r["thrust_momentum_n_per_m2"], r["thrust_force_n_per_m2"])'),
                   call('finish', summary='Deterministic fixture repair and diagnostic executed')]
        with tempfile.TemporaryDirectory() as d:
            model = FakeModel(outputs)
            def terminal_grade(*args):
                self.assertTrue(model.closed)
                self.assertNotIn('terminal_reward', json.dumps(model.requests))
                return grade_submission(*args)
            with patch('epagent.episode.grade_submission', side_effect=terminal_grade):
                report = run_episode('hall-thrust', d, model, Config(steps=5))
            self.assertEqual(report['status'], 'finished')
            self.assertEqual(report['reward'], 1)
            self.assertEqual(report['grading']['passed'], 13)
            self.assertEqual(report['tool_calls'], 5)
            self.assertEqual(report['modified_files'], ['momentum.py'])
            self.assertIsNone(report['usage']['generation_tokens'])
            self.assertEqual(json.loads(Path(report['paths']['report']).read_text()), report)
            trace = [json.loads(line) for line in Path(report['paths']['trace']).read_text().splitlines()]
            events = [row['event'] for row in trace]
            self.assertLess(events.index('agent_terminated'), events.index('terminal_reward'))
            self.assertEqual([r['sequence'] for r in trace], list(range(1, len(trace) + 1)))
            self.assertIn('s_face *', Path(report['paths']['patch']).read_text())
            self.assertEqual({p.name for p in Path(report['paths']['initial_workspace']).iterdir()},
                             {'README.md', 'physics.py', 'momentum.py', 'run.py'})
            second = run_episode('hall-thrust', d, FakeModel([call('finish', summary='unchanged')]), Config(steps=1))
            self.assertNotEqual(report['episode_id'], second['episode_id'])
            self.assertEqual(report['initial_sha256'], second['final_sha256'])
            self.assertEqual(second['grading']['passed'], 3)
            self.assertEqual(second['reward'], 0)

    def test_bad_calls_and_python_failures_are_observations(self):
        outputs = ['not json', call('read_file', path='missing'),
                   call('run_python', code='raise ValueError("intentional")'),
                   call('run_python', code='while True: pass')]
        with tempfile.TemporaryDirectory() as d:
            report = run_episode('hall-thrust', d, FakeModel(outputs), Config(steps=4, tool_seconds=0.2))
            self.assertEqual(report['termination_reason'], 'step_limit')
            self.assertTrue(report['scored'])
            self.assertEqual(report['reward'], 0)
            trace = Path(report['paths']['trace']).read_text()
            for marker in ['JSONDecodeError', 'FileNotFoundError', 'python_error', 'timeout']:
                self.assertIn(marker, trace)

    def test_inference_failures_context_limit_and_wall_timeout(self):
        for error, status, reason in [(BackendError('broken'), 'backend_failure', 'inference_error'),
                                      (ContextLimit('full'), 'unfinished', 'context_limit'),
                                      (TimeoutError('expired'), 'timeout', 'wall_time_limit')]:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as d:
                model = FakeModel([error])
                report = run_episode('hall-thrust', d, model)
                self.assertEqual((report['status'], report['termination_reason']), (status, reason))
                self.assertTrue(model.closed)
                self.assertIsNone(report['reward'])
                self.assertFalse(report['scored'])
                self.assertTrue(Path(report['paths']['trace']).exists())

    def test_partial_episode_is_preserved_and_scored_after_backend_failure(self):
        with tempfile.TemporaryDirectory() as d:
            model = FakeModel([call('run_python', code="open('diagnostic.txt','w').write('observed')"), BackendError('stopped')])
            report = run_episode('hall-thrust', d, model)
            self.assertEqual(report['status'], 'backend_failure')
            self.assertTrue(report['scored'])
            self.assertEqual(report['reward'], 0)
            self.assertIn('diagnostic.txt', report['modified_files'])

    def test_grading_failure_is_separate_from_agent_termination(self):
        with tempfile.TemporaryDirectory() as d:
            model = FakeModel([call('run_python', code="import os; os.unlink('momentum.py')"),
                               call('finish', summary='invalid submission')])
            report = run_episode('hall-thrust', d, model)
            self.assertEqual(report['status'], 'finished')
            self.assertEqual(report['evaluation_status'], 'grading_failure')
            self.assertIsNone(report['reward'])
            self.assertFalse(report['scored'])
            self.assertIn('momentum.py', report['modified_files'])


if __name__ == '__main__':
    unittest.main()
