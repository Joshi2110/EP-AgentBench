"""Offline context provenance and tiny, randomly initialized Qwen gradient audit."""
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from epagent.sft_data import reviewed_examples

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('short_context', ROOT / 'scripts/prepare_short_context.py')
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


class ContextTests(unittest.TestCase):
    def test_whole_messages_targets_and_dependencies_preserved(self):
        sets = reviewed_examples(ROOT / 'data/epagent-sft-7b-v1/trajectories')
        for rows in sets.values():
            for row in rows:
                small = selector.minimize(row)
                indices = small['context_selection']['kept_indices']
                self.assertEqual(small['messages'], [row['messages'][i] for i in indices])
                self.assertEqual(small['messages'][:2], row['messages'][:2])
                self.assertEqual(small['messages'][-3:], row['messages'][-3:])
                for i in indices[2:-1]:
                    self.assertIn(i + 1 if i % 2 == 0 else i - 1, indices)
                target = json.loads(row['messages'][-1]['content'])
                if target['tool'] in ('edit_file', 'replace_lines'):
                    path = target['arguments']['path']
                    reads = [i for i in range(2, len(row['messages']) - 1, 2)
                             if json.loads(row['messages'][i]['content']) ==
                             {'tool': 'read_file', 'arguments': {'path': path}}]
                    self.assertTrue(reads)
                    self.assertIn(reads[-1], indices)
                    source = json.loads(row['messages'][reads[-1] + 1]['content'])['tool_result']
                    if target['tool'] == 'edit_file':
                        self.assertEqual(source['content'].count(target['arguments']['old_text']), 1)
                    else:
                        self.assertEqual(source['version'], target['arguments']['version'])


@unittest.skipUnless(os.environ.get('EPAGENT_TEST_MLX') == '1', 'native MLX opt-in')
class GradientTests(unittest.TestCase):
    def test_actual_tokenizer_no_target_truncation(self):
        from mlx_lm.utils import load_tokenizer
        from epagent.mlx_backend import configure_stop_tokens
        from epagent.sft_data import tokenize_example
        model_dir = ROOT / '.epagent-models/qwen2.5-coder-7b-4bit'
        if not model_dir.exists():
            self.skipTest('local tokenizer unavailable')
        tokenizer = load_tokenizer(model_dir, {'trust_remote_code': False}, eos_token_ids=151643)
        configure_stop_tokens(tokenizer)
        sets = reviewed_examples(ROOT / 'data/epagent-sft-7b-v1/trajectories')
        for split, rows in sets.items():
            total = 0
            maximum = 0
            for row in rows:
                full = tokenize_example(row, tokenizer, 8192)
                small = tokenize_example(selector.minimize(row), tokenizer, 1024)
                self.assertEqual(full['tokens'][full['offset']:], small['tokens'][small['offset']:])
                total += small['supervised_tokens']
                maximum = max(maximum, small['length'])
            self.assertEqual(total, 1948 if split == 'train' else 247)
            self.assertEqual(maximum, 1010 if split == 'train' else 874)

    def test_frozen_prefix_and_stop_boundary_equivalence(self):
        import mlx.core as mx
        import mlx.nn as nn
        from mlx.utils import tree_flatten
        from mlx_lm.models.qwen2 import Model, ModelArgs, TransformerBlock
        from mlx_lm.models.base import create_attention_mask
        from mlx_lm.tuner.utils import linear_to_lora_layers
        from mlx_lm.tuner.trainer import grad_checkpoint
        from epagent.sft_data import assistant_loss

        mx.random.seed(0)
        model = Model(ModelArgs(model_type='qwen2', hidden_size=32, num_hidden_layers=4,
                      intermediate_size=64, num_attention_heads=4, num_key_value_heads=2,
                      rms_norm_eps=1e-6, vocab_size=64, tie_word_embeddings=False))
        nn.quantize(model, group_size=32, bits=4)
        model.freeze()
        linear_to_lora_layers(model, 2, {'rank': 4, 'scale': 8., 'dropout': 0.,
                                       'keys': ['self_attn.q_proj', 'self_attn.v_proj']})
        calls = []
        @mx.custom_function
        def witness(x):
            return x
        @witness.vjp
        def witness_vjp(primals, cotangents, outputs):
            calls.append('lower boundary backward')
            return cotangents

        batch = mx.array([[1, 2, 3, 4, 5, 6]])
        lengths = mx.array([[3, 6]])
        def forward(tokens, detach=False):
            h = model.model.embed_tokens(tokens)
            mask = create_attention_mask(h, None)
            for i, layer in enumerate(model.layers):
                if i == 2:
                    h = witness(h)
                    if detach:
                        h = mx.stop_gradient(h)
                h = layer(h, mask, None)
            return model.lm_head(model.model.norm(h))

        original_call = TransformerBlock.__call__
        for checkpoint in (False, True):
            with patch.object(TransformerBlock, '__call__', original_call):
                if checkpoint:
                    grad_checkpoint(model.layers[0])
                self.assertTrue(mx.array_equal(model(batch), forward(batch)).item())
                self.assertTrue(mx.array_equal(forward(batch), forward(batch, True)).item())
                results = []
                for detach in (False, True):
                    calls.clear()
                    loss_fn = lambda m: assistant_loss(lambda x: forward(x, detach), batch, lengths)[0]
                    loss, grads = nn.value_and_grad(model, loss_fn)(model)
                    mx.eval(loss, grads)
                    self.assertEqual(calls, [])
                    flat = dict(tree_flatten(grads))
                    self.assertTrue(flat)
                    self.assertTrue(all(('.layers.2.' in k or '.layers.3.' in k)
                                        and ('lora_a' in k or 'lora_b' in k) for k in flat))
                    self.assertTrue(all(mx.all(mx.isfinite(g)).item() for g in flat.values()))
                    self.assertTrue(any(mx.any(g != 0).item() for g in flat.values()))
                    results.append((loss, flat))
                self.assertEqual(results[0][0].item(), results[1][0].item())
                for key, grad in results[0][1].items():
                    self.assertTrue(mx.array_equal(grad, results[1][1][key]).item())
        # Positive control: differentiating the prefix output itself invokes the witness.
        calls.clear()
        x = mx.ones((1, 2, 32))
        mx.eval(mx.grad(lambda h: mx.sum(witness(h) ** 2))(x))
        self.assertTrue(calls)
