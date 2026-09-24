"""SFT data/loss tests. All optimization calls are mocked; no model is trained."""

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from epagent.sft import config_at, load_prepared, main
from epagent.sft_data import assistant_loss, digest, reviewed_examples, tokenize_example

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/epagent-sft-v1'
MLX_CHECKS = os.environ.get('EPAGENT_TEST_MLX') == '1'


class DataTests(unittest.TestCase):
    def test_counts_roles_loss_targets_and_grouped_split(self):
        sets = reviewed_examples(DATA / 'trajectories')
        self.assertEqual({k: len(v) for k, v in sets.items()}, {'train': 57, 'valid': 19})
        self.assertEqual(len({r['episode_id'] for r in sets['train']}), 6)
        self.assertEqual(len({r['episode_id'] for r in sets['valid']}), 2)
        self.assertFalse({r['family'] for r in sets['train']} & {r['family'] for r in sets['valid']})
        heldout = json.loads((DATA / 'eval-fixtures.json').read_text())
        self.assertFalse({r['family'] for rows in sets.values() for r in rows} & {r['family'] for r in heldout})
        self.assertFalse({r['id'] for r in heldout} & {r['episode_id'] for rows in sets.values() for r in rows})
        for rows in sets.values():
            for row in rows:
                self.assertEqual(row['messages'][-1]['role'], 'assistant')
                self.assertEqual(len(row['messages']), len(row['message_kinds']))
                for message, kind in zip(row['messages'], row['message_kinds']):
                    if kind == 'tool_observation':
                        self.assertEqual(message['role'], 'user')
                        self.assertIn('tool_result', json.loads(message['content']))
                self.assertNotIn('hall-', row['episode_id'])
        finishes = [r for rows in sets.values() for r in rows if r['message_kinds'][-1] == 'assistant_finish']
        self.assertEqual(len(finishes), 8)
        for row in finishes:
            observation = json.loads(row['messages'][-2]['content'])['tool_result']
            self.assertEqual(observation['status'], 'completed')
            self.assertEqual(observation['stdout'].strip(), 'PASS ' + row['episode_id'])

    def test_failure_recovery_has_observed_error_but_no_failed_edit_target(self):
        sets = reviewed_examples(DATA / 'trajectories')
        reviews = json.loads((DATA / 'trajectories/reviews.json').read_text())['episodes']
        for review in reviews:
            examples = [r for r in sets[review['split']] if r['episode_id'] == review['episode_id']]
            self.assertFalse(set(review['excluded_failed_edit_steps']) & {r['step'] for r in examples})
            if review['excluded_failed_edit_steps']:
                recovery = next(r for r in examples if r['step'] == 8)
                error = json.loads(recovery['messages'][-2]['content'])['tool_result']
                self.assertEqual(error['detail'], 'old_text must match exactly once')
                self.assertEqual(json.loads(recovery['messages'][-1]['content'])['tool'], 'read_file')
                edit = next(r for r in examples if r['step'] == 9)
                observed = json.loads(edit['messages'][-2]['content'])['tool_result']['content']
                old = json.loads(edit['messages'][-1]['content'])['arguments']['old_text']
                self.assertEqual(observed.count(old), 1)

    def test_unreviewed_provider_data_tampering_and_cross_split_families_rejected(self):
        for mutation in ['origin', 'hash', 'split', 'selection']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as d:
                directory = Path(d) / 'traces'
                shutil.copytree(DATA / 'trajectories', directory)
                p = directory / 'reviews.json'
                review = json.loads(p.read_text())
                if mutation == 'origin':
                    review['episodes'][0]['origin'] = 'successful-proprietary-model'
                elif mutation == 'hash':
                    review['episodes'][0]['trace_sha256'] = 'changed'
                elif mutation == 'split':
                    review['episodes'][-1]['family'] = review['episodes'][0]['family']
                else:
                    review['episodes'][0]['selected_assistant_steps'].append(7)
                p.write_text(json.dumps(review))
                with self.assertRaises(ValueError):
                    reviewed_examples(directory)

    def test_cli_help_and_invalid_config_do_not_train(self):
        with patch('epagent.sft.train') as train:
            with self.assertRaises(SystemExit) as exit_code:
                main(['--help'])
            self.assertEqual(exit_code.exception.code, 0)
            train.assert_not_called()
        config = config_at(DATA / 'lora-config.json')
        self.assertEqual(config['iterations'], 40)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config.json'
            config['batch_size'] = 8
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                config_at(path)

    def test_frozen_evaluation_setup_produces_real_edit_failure_without_changes(self):
        from epagent.tools import execute
        fixtures = json.loads((DATA / 'eval-fixtures.json').read_text())
        protocol = json.loads((DATA / 'eval-protocol.json').read_text())
        self.assertEqual([r['id'] for r in fixtures], protocol['heldout_cases'])
        self.assertEqual(digest(DATA / 'eval-fixtures.json'), protocol['eval_fixtures_sha256'])
        self.assertEqual(config_at(DATA / 'lora-config.json')['iterations'], protocol['training_iterations'])
        for case in fixtures:
            with self.subTest(case=case['id']), tempfile.TemporaryDirectory() as d:
                workspace = Path(d)
                for name, content in case['files'].items():
                    path = workspace / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content)
                observed = execute(workspace, 'read_file', {'path': case['source']}, 8, 8192)
                self.assertEqual(observed['content'], case['files'][case['source']])
                with self.assertRaisesRegex(ValueError, 'old_text must match exactly once'):
                    execute(workspace, 'edit_file', case['forced_failed_edit']['arguments'], 8, 8192)
                self.assertEqual((workspace / case['source']).read_text(), observed['content'])


@unittest.skipUnless(MLX_CHECKS, 'Set EPAGENT_TEST_MLX=1 for actual local tokenizer/loss checks; no training')
class MLXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mlx_lm.utils import load_tokenizer
        from epagent.mlx_backend import configure_stop_tokens
        cls.model_dir = Path(os.environ.get('EPAGENT_MODEL_DIR', ROOT / '.epagent-models/qwen2.5-coder-1.5b-4bit'))
        if not cls.model_dir.exists():
            raise unittest.SkipTest('Real local tokenizer unavailable; not verified by mocks')
        config_eos = json.loads((cls.model_dir / 'config.json').read_text())['eos_token_id']
        cls.tokenizer = load_tokenizer(cls.model_dir, {'trust_remote_code': False}, eos_token_ids=config_eos)
        configure_stop_tokens(cls.tokenizer)

    def test_actual_template_masks_every_context_and_observation_token(self):
        examples = reviewed_examples(DATA / 'trajectories')
        for row in examples['train'] + examples['valid']:
            encoded = tokenize_example(row, self.tokenizer, 2048)
            prompt = self.tokenizer.apply_chat_template(row['messages'][:-1], tokenize=True, add_generation_prompt=True)
            self.assertEqual(encoded['tokens'][:encoded['offset']], prompt)
            target = self.tokenizer.decode(encoded['tokens'][encoded['offset']:])
            self.assertEqual(target, row['messages'][-1]['content'] + self.tokenizer.eos_token)
            self.assertEqual(encoded['tokens'][-1], self.tokenizer.eos_token_id)
            with self.assertRaises(ValueError):
                tokenize_example(row, self.tokenizer, 5)
        self.assertEqual(self.tokenizer.eos_token_id, 151645)

    def test_loss_includes_first_assistant_and_eos_but_excludes_prompt_and_padding(self):
        import mlx.core as mx
        # Original token positions 0..5; assistant begins at 3 and EOS at 4.
        # Index 5 is padding. Exactly two targets must contribute to loss.
        batch = mx.array([[0, 1, 2, 3, 4, 0]], dtype=mx.int32)
        bounds = mx.array([[3, 5]], dtype=mx.int32)
        base = mx.zeros((1, 5, 8))
        baseline, n = assistant_loss(lambda _: base, batch, bounds)
        self.assertEqual(n.item(), 2)
        for logit_position in [0, 1, 4]:
            changed = mx.array(base)
            changed[0, logit_position, 7] = 30
            loss, _ = assistant_loss(lambda _: changed, batch, bounds)
            self.assertAlmostEqual(loss.item(), baseline.item(), places=6)
        for logit_position in [2, 3]:
            changed = mx.array(base)
            changed[0, logit_position, 7] = 30
            loss, _ = assistant_loss(lambda _: changed, batch, bounds)
            self.assertGreater(loss.item(), baseline.item())
        # Different offsets in a padded batch also exclude the first pad target.
        both = mx.array([[0, 1, 2, 3, 4, 0], [0, 1, 2, 3, 0, 0]], dtype=mx.int32)
        loss, count = assistant_loss(lambda _: mx.zeros((2, 5, 8)), both, mx.array([[3, 5], [2, 4]]))
        self.assertEqual(count.item(), 4)

    def test_prepare_and_training_wiring_without_any_optimizer_update(self):
        from epagent.sft import prepare, train
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            with patch('mlx_lm.tuner.trainer.train') as optimizer_loop:
                metadata = prepare(DATA / 'trajectories', self.model_dir, DATA / 'lora-config.json',
                                   DATA / 'eval-protocol.json', directory / 'prepared')
                optimizer_loop.assert_not_called()
            self.assertFalse(metadata['training_performed'])
            self.assertEqual(metadata['counts']['train']['examples'], 57)
            original_hash = digest(self.model_dir / 'model.safetensors')
            with patch('epagent.sft.adapt', return_value=(Mock(), {'trainable_parameters': 1})), \
                 patch('mlx_lm.tuner.trainer.train') as optimizer_loop, \
                 patch('mlx_lm.tuner.trainer.evaluate', return_value=0.5), \
                 patch('mlx.optimizers.Adam') as optimizer:
                def simulated_checkpoint(**kwargs):
                    kwargs['args'].adapter_file.write_bytes(b'test-only mocked checkpoint; no model weights')
                optimizer_loop.side_effect = simulated_checkpoint
                result = train(directory / 'prepared', self.model_dir, directory / 'run')
                self.assertIs(optimizer_loop.call_args.kwargs['loss'], assistant_loss)
                self.assertEqual(optimizer_loop.call_args.kwargs['args'].iters, 40)
                optimizer.return_value.update.assert_not_called()
                self.assertEqual(result['final_validation_loss'], 0.5)
                self.assertEqual(set(result['checkpoint_sha256']), {'adapters.safetensors'})
                self.assertTrue((directory / 'run/adapter_config.json').is_file())
            self.assertEqual(digest(self.model_dir / 'model.safetensors'), original_hash)
            path = directory / 'prepared/train.tokens.jsonl'
            path.write_text(path.read_text() + '\n')
            with self.assertRaises(ValueError):
                load_prepared(directory / 'prepared')


if __name__ == '__main__':
    unittest.main()
