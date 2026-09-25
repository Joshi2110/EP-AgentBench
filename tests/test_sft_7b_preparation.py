"""Offline 7B SFT preparation acceptance. No real-model forward/backward or generation."""
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from epagent.assessment02 import registered, run_suite
from epagent.mlx_backend import adapter_manifest
from epagent.sft import config_at, lora_plan, local_model
from epagent.sft_data import digest, reviewed_examples, tokenize_example, write_json
from test_epagent import FakeModel, MACOS, call

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/epagent-sft-7b-v1'
EVAL = ROOT / 'data/epagent-evaluation-02'
SPEC = json.loads((EVAL / 'protocol.json').read_text())
CASES = json.loads((EVAL / 'fixtures.json').read_text())


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]):
        spec.loader.exec_module(module)
    return module


class PreparationTests(unittest.TestCase):
    def test_counts_transitions_and_failed_calls_are_context_only(self):
        sets = reviewed_examples(DATA / 'trajectories')
        self.assertEqual({s: len(v) for s, v in sets.items()}, {'train': 62, 'valid': 8})
        self.assertEqual(len({r['episode_id'] for r in sets['train']}), 12)
        self.assertEqual(len({r['episode_id'] for r in sets['valid']}), 2)
        train_tools = [json.loads(r['messages'][-1]['content'])['tool'] for r in sets['train']]
        self.assertEqual(train_tools.count('read_file'), 17)
        self.assertEqual(train_tools.count('run_python'), 18)
        for split in sets.values():
            for row in split:
                action = json.loads(row['messages'][-1]['content'])
                if action['tool'] == 'run_python':
                    self.assertEqual(action['arguments']['code'], "exec(open('checks.py').read())")
                if action['tool'] == 'finish':
                    previous = json.loads(row['messages'][-2]['content'])['tool_result']
                    summary = action['arguments']['summary']
                    if 'Incomplete:' in summary:
                        self.assertEqual(previous['status'], 'python_error')
                        self.assertIn('AssertionError', previous['stderr'])
                    else:
                        self.assertEqual(previous['status'], 'completed')
                        self.assertIn('PASS ' + row['episode_id'], previous['stdout'])
        for review in json.loads((DATA / 'trajectories/reviews.json').read_text())['episodes']:
            self.assertFalse(set(review['selected_assistant_steps']) & set(review['excluded_steps']))

    def test_family_separation_and_offline_reference_validation(self):
        used = {'cart-total', 'sorted-unique'}
        for version in ('v1', 'v2', 'v3'):
            for name in ('fixtures.json', 'eval-fixtures.json'):
                for case in json.loads((ROOT / f'data/epagent-sft-{version}' / name).read_text()):
                    used.update((case['id'], case['family']))
        for case in json.loads((ROOT / 'data/epagent-evaluation-01/fixtures.json').read_text()):
            used.update((case['id'], case['family']))
        demos = json.loads((DATA / 'fixtures.json').read_text())
        for case in demos:
            used.update((case['id'], case['family']))
        self.assertFalse({c['id'] for c in CASES} & used)
        self.assertFalse({c['family'] for c in CASES} & used)
        self.assertEqual(len({c['family'] for c in CASES}), 10)
        train = {c['family'] for c in demos if c['split'] == 'train'}
        valid = {c['family'] for c in demos if c['split'] == 'valid'}
        self.assertFalse(train & valid)
        for c in json.loads((EVAL / 'validation.json').read_text())['fixtures']:
            for field in ('starter_fails_visible', 'starter_fails_independent',
                          'reference_passes_visible', 'reference_passes_independent'):
                self.assertTrue(c[field])
            self.assertGreaterEqual(c['assertions_only_in_independent'], 3)
        script('build_evaluation_02').hidden_material_absent(CASES)

    def test_config_model_dimensions_and_all_frozen_hashes(self):
        config = config_at(DATA / 'lora-config.json')
        self.assertEqual((config['iterations'], config['batch_size'], config['max_seq_length']), (124, 1, 1536))
        self.assertEqual(config['iterations'] / 62, 2)
        for container, field in [(SPEC, 'frozen_sha256'),
                (json.loads((DATA / 'training-freeze.json').read_text()), 'sha256')]:
            for name, expected in container[field].items():
                self.assertEqual(digest(ROOT / name), expected, name)
        with tempfile.TemporaryDirectory() as tmp:
            # Test the analytical parameter count without instantiating a model.
            shape = {'model_type': 'qwen2', 'hidden_size': 3584, 'num_attention_heads': 28,
                     'num_key_value_heads': 4, 'num_hidden_layers': 28}
            write_json(Path(tmp) / 'config.json', shape)
            plan = lora_plan(tmp, config)
        self.assertEqual(plan['trainable_parameters'], 360448)
        self.assertEqual(plan['layers'], [24, 25, 26, 27])

    def test_no_adapter_for_base_and_only_registered_7b_adapter_for_adapted(self):
        _, base, _ = registered(EVAL / 'fixtures.json', EVAL / 'protocol.json', 'base')
        self.assertIsNone(base.adapter_dir)
        for arm, adapter in [('base', 'some-adapter'), ('adapted', None)]:
            with self.assertRaises(ValueError):
                registered(EVAL / 'fixtures.json', EVAL / 'protocol.json', arm, adapter)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.make_adapter(directory)
            _, adapted, _ = registered(EVAL / 'fixtures.json', EVAL / 'protocol.json', 'adapted', directory)
            self.assertEqual({**asdict(adapted), 'adapter_dir': None}, asdict(base))
            (directory / 'adapters.safetensors').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'training artifact'):
                registered(EVAL / 'fixtures.json', EVAL / 'protocol.json', 'adapted', directory)

    @staticmethod
    def make_adapter(directory):
        prepared = json.loads((DATA / 'preparation.json').read_text())
        config = prepared['config']
        write_json(directory / 'adapter_config.json', {'fine_tune_type': 'lora',
            'num_layers': config['num_layers'], 'lora_parameters': config['lora_parameters']})
        (directory / 'adapters.safetensors').write_bytes(b'mock identity only; never loaded as tensors')
        write_json(directory / 'run.json', {'status': 'complete', 'updates_requested': 124,
            'prepared_manifest_sha256': SPEC['prepared_manifest_sha256'], 'prepared': prepared,
            'checkpoint_sha256': {'adapters.safetensors': digest(directory / 'adapters.safetensors')}})

    def test_memory_check_requires_authorization_and_normal_pressure(self):
        module = script('check_7b_training_memory')
        with tempfile.TemporaryDirectory() as tmp:
            args = ['probe', '--prepared', tmp, '--model-dir', tmp, '--out', str(Path(tmp) / 'out')]
            with patch.object(sys, 'argv', args), patch.object(module, 'backward_probe') as backward:
                with self.assertRaises(SystemExit):
                    module.main()
                backward.assert_not_called()
            with patch.object(sys, 'argv', args + ['--confirm-backward']), \
                 patch.object(module, 'pressure', return_value=2), \
                 patch.object(module.subprocess, 'Popen') as launch:
                with self.assertRaisesRegex(SystemExit, 'not normal'):
                    module.main()
                launch.assert_not_called()
        self.assertEqual(module.LIMIT, 7 * 1024**3)

    def test_streamed_local_identity_rejects_unknown_model_and_corrupt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'config.json').write_text('{}')
            manifest = {'model_id': SPEC['model_id'], 'revision': SPEC['revision'],
                        'sha256': {'config.json': digest(p / 'config.json')}}
            write_json(p / 'epagent-model.json', manifest)
            self.assertEqual(local_model(p), manifest)
            (p / 'config.json').write_text('{"tampered":true}')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                local_model(p)
            manifest['revision'] = 'unknown'
            write_json(p / 'epagent-model.json', manifest)
            with self.assertRaisesRegex(ValueError, 'pinned'):
                local_model(p)

    def test_memory_supervisor_preserves_missing_result_failure_and_cleans_up(self):
        module = script('check_7b_training_memory')
        process = Mock(); process.poll.return_value = 0; process.wait.return_value = 0
        inhibitor = Mock(); inhibitor.wait.return_value = 0
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            args = ['probe', '--prepared', tmp, '--model-dir', tmp, '--out', str(out), '--confirm-backward']
            with patch.object(sys, 'argv', args), patch.object(module, 'pressure', return_value=1), \
                 patch.object(module.subprocess, 'Popen', side_effect=[process, inhibitor]), \
                 patch.object(module, 'backward_probe') as backward:
                with self.assertRaises(FileNotFoundError):
                    module.main()
                backward.assert_not_called()
            report = json.loads((out / 'supervisor.json').read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertTrue(report['child_exited'])
            inhibitor.terminate.assert_called_once()


@unittest.skipUnless(MACOS, 'Existing constrained macOS Python runner')
class ReplayTests(unittest.TestCase):
    def test_all_demonstrations_replay_identically(self):
        builder = script('build_sft_7b')
        cases = json.loads((DATA / 'fixtures.json').read_text())
        self.assertEqual(builder.fixtures(), cases)
        with tempfile.TemporaryDirectory() as tmp:
            builder.replay(cases, Path(tmp) / 'traces')
            for path in (DATA / 'trajectories').glob('*'):
                self.assertEqual(path.read_bytes(), (Path(tmp) / 'traces' / path.name).read_bytes(), path.name)

    def test_both_arms_with_scripted_repairs_real_tests_and_independent_checks(self):
        for arm in ('base', 'adapted'):
            with self.subTest(arm=arm), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                adapter = None
                if arm == 'adapted':
                    adapter = directory / 'adapter'; adapter.mkdir()
                    PreparationTests.make_adapter(adapter)
                models = []
                def factory(model_dir, config):
                    case = CASES[len(models)]
                    model = FakeModel([call('read_file', path=case['source']),
                        call('edit_file', path=case['source'], old_text=case['files'][case['source']],
                             new_text=case['reference_source']),
                        call('run_python', code="exec(open('checks.py').read())"),
                        call('finish', summary='Ran checks.py and observed ' + case['pass_marker'])])
                    model.metadata['adapter'] = adapter_manifest(config['adapter_dir'], loaded=arm == 'adapted')
                    models.append(model)
                    return model
                with patch('epagent.assessment02.local_model', return_value=SPEC['model_manifest']):
                    report = run_suite(EVAL / 'fixtures.json', EVAL / 'protocol.json', 'mock',
                                       directory / 'run', arm, adapter, backend_factory=factory)
                self.assertEqual((report['primary'], report['independent']), ('10/10', '10/10'))
                self.assertTrue(all(m.closed for m in models))
                self.assertTrue(all(c['metrics']['runner_initiated_test_executions'] == 0 for c in report['cases']))
                for model, case in zip(models, CASES):
                    text = json.dumps(model.requests)
                    self.assertNotIn(case['independent_marker'], text)
                    # Hidden assertions only appear after backend closure, never in requests.
                    for line in case['independent_test'].splitlines():
                        if line.startswith('assert F') and line not in case['files']['checks.py']:
                            self.assertNotIn(json.dumps(line)[1:-1], text)

    def test_printed_pass_and_finish_are_not_primary_success_and_no_retry_on_failure(self):
        def run(outputs):
            models = []
            def factory(*args):
                model = FakeModel(outputs)
                model.metadata['adapter'] = adapter_manifest(None)
                models.append(model)
                return model
            with tempfile.TemporaryDirectory() as tmp, \
                 patch('epagent.assessment02.local_model', return_value=SPEC['model_manifest']):
                return run_suite(EVAL / 'fixtures.json', EVAL / 'protocol.json', 'mock',
                                 Path(tmp) / 'out', 'base', backend_factory=factory)
        report = run([call('run_python', code='print("PASS reachable-nodes")'),
                      call('finish', summary='Tests passed')])
        self.assertEqual((report['primary'], report['independent']), ('0/10', '0/10'))
        from epagent.mlx_backend import BackendError
        with self.assertRaisesRegex(ValueError, 'infrastructure/grading failure'):
            run([BackendError('mock failure')])


@unittest.skipUnless(os.environ.get('EPAGENT_TEST_MLX') == '1', 'Actual tokenizer only; no model')
class TokenizerTests(unittest.TestCase):
    def test_actual_7b_token_counts_full_history_and_assistant_only_mask(self):
        from mlx_lm.utils import load_tokenizer
        from epagent.mlx_backend import configure_stop_tokens
        path = ROOT / '.epagent-models/qwen2.5-coder-7b-4bit'
        if not path.exists():
            self.skipTest('Actual tokenizer absent; do not claim verified')
        tokenizer = load_tokenizer(path, {'trust_remote_code': False}, eos_token_ids=151643)
        self.assertEqual(configure_stop_tokens(tokenizer), [151643, 151645])
        for split, rows in reviewed_examples(DATA / 'trajectories').items():
            counts = json.loads((DATA / 'preparation.json').read_text())['counts'][split]
            encoded = [tokenize_example(row, tokenizer, 1536) for row in rows]
            self.assertEqual(sum(r['supervised_tokens'] for r in encoded), counts['supervised_tokens'])
            self.assertEqual(max(r['length'] for r in encoded), counts['max_tokens'])
            for row, tokens in zip(rows, encoded):
                self.assertEqual(tokenizer.decode(tokens['tokens'][tokens['offset']:]),
                                 row['messages'][-1]['content'] + tokenizer.eos_token)
                prefix = tokenizer.apply_chat_template(row['messages'][:-1], tokenize=True, add_generation_prompt=True)
                self.assertEqual(prefix, tokens['tokens'][:tokens['offset']])


if __name__ == '__main__':
    unittest.main()
