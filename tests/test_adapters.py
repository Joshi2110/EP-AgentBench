"""Adapter plumbing plus actual MLX loading of tiny surrogate tensors; no generation/training."""

from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from epagent.cli import main
from epagent.episode import Config, run_episode
from epagent.mlx_backend import MLXBackend, MODEL_ID, REVISION, adapter_manifest, verify_loaded_adapter, worker
from test_epagent import FakeModel, call
from test_synthetic import CASE


class AdapterTests(unittest.TestCase):
    def test_cli_config_selection_and_base_default(self):
        for adapter in [None, '/surrogate-adapter']:
            args = ['run','hall-thrust','--model-dir','/unused','--out','/unused']
            if adapter:
                args += ['--adapter-dir', adapter]
            with patch('epagent.cli.MLXBackend') as backend, patch('epagent.cli.run_episode') as episode, patch('sys.stdout'):
                episode.return_value = {'status':'finished','scored':True}
                self.assertEqual(main(args),0)
                self.assertEqual(backend.call_args.args[1]['adapter_dir'],adapter)
                self.assertEqual(episode.call_args.args[3].adapter_dir,adapter)
        with self.assertRaises(ValueError):
            Config(adapter_dir='').validate()

    def test_manifest_distinguishes_requested_base_and_changed_weights(self):
        self.assertEqual(adapter_manifest(None)['loaded'],False)
        self.assertEqual(adapter_manifest(None)['requested'],False)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'adapter_config.json').write_text(json.dumps({'fine_tune_type':'lora'}))
            (p/'adapters.safetensors').write_bytes(b'surrogate-not-real-weights')
            first=adapter_manifest(p)
            self.assertTrue(first['requested'])
            self.assertFalse(first['loaded'])
            self.assertEqual(first['path'],str(p.resolve()))
            self.assertEqual(set(first['sha256']),{'adapter_config.json','adapters.safetensors'})
            (p/'adapters.safetensors').write_bytes(b'changed-surrogate')
            self.assertNotEqual(adapter_manifest(p)['id'],first['id'])

    def test_ready_event_metadata_survives_final_report(self):
        # Protocol propagation only: these metadata are explicitly surrogate data.
        metadata={'model_id':MODEL_ID,'revision':REVISION,'adapter':{
            'requested':True,'loaded':True,'path':'/test-surrogate','id':'surrogate-sha',
            'config':{'fine_tune_type':'lora'},'sha256':{'adapters.safetensors':'surrogate'}}}
        class ReadyFake(FakeModel):
            def generate(self,messages,seconds,emit):
                self.metadata.update(metadata)
                emit('model_ready',{'event':'ready','metadata':metadata})
                return super().generate(messages,seconds,emit)
        with tempfile.TemporaryDirectory() as d:
            report=run_episode('synthetic:unit-probe',d,ReadyFake([call('finish',summary='Incomplete')]),
                               Config(adapter_dir='/test-surrogate'),synthetic=CASE)
            self.assertEqual(report['model']['adapter'],metadata['adapter'])
            events=[json.loads(s) for s in Path(report['paths']['trace']).read_text().splitlines()]
            ready=next(e for e in events if e['event']=='model_ready')
            self.assertEqual(ready['data']['metadata'],metadata)
            self.assertEqual(json.loads(Path(report['paths']['report']).read_text())['model']['adapter'],metadata['adapter'])


@unittest.skipUnless(os.environ.get('EPAGENT_TEST_MLX')=='1','Explicit MLX surrogate loading check; no generation')
class SurrogateTests(unittest.TestCase):
    def test_cli_backend_worker_native_load_selects_surrogate_and_records_hashes(self):
        import mlx.core as mx
        from mlx.utils import tree_flatten
        from mlx_lm.models.qwen2 import Model, ModelArgs
        from mlx_lm.tuner.utils import linear_to_lora_layers
        from mlx_lm import load as native_load
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); base=root/'base'; base.mkdir()
            args=ModelArgs(model_type='qwen2',hidden_size=8,num_hidden_layers=1,intermediate_size=16,
                           num_attention_heads=2,num_key_value_heads=2,rms_norm_eps=1e-6,vocab_size=16)
            toy=Model(args)
            mx.save_safetensors(str(base/'model.safetensors'),dict(tree_flatten(toy.parameters())))
            (base/'config.json').write_text(json.dumps(asdict(args)))
            # This is an interface fixture, not the real pinned model: no inference
            # is attempted and the manifest explicitly identifies the surrogate.
            (base/'epagent-model.json').write_text(json.dumps({'model_id':MODEL_ID,'revision':REVISION,
                        'sha256':{},'test_fixture':'tiny untrained surrogate'}))
            adapter_config={'fine_tune_type':'lora','num_layers':1,'lora_parameters':{
                             'rank':2,'scale':1.0,'dropout':0.0,'keys':['self_attn.q_proj','self_attn.v_proj']}}
            toy.freeze()
            linear_to_lora_layers(toy,1,adapter_config['lora_parameters'])
            names=dict(tree_flatten(toy.trainable_parameters()))
            adapters=[]
            for number in [1,2]:
                path=root/f'adapter-{number}'; path.mkdir(); adapters.append(path)
                (path/'adapter_config.json').write_text(json.dumps(adapter_config))
                mx.save_safetensors(str(path/'adapters.safetensors'),{n:mx.full(v.shape,number/4) for n,v in names.items()})
            tokenizer=SimpleNamespace(eos_token='<|im_end|>',eos_token_ids={151643},chat_template='surrogate template')
            tokenizer.add_eos_token=lambda _:tokenizer.eos_token_ids.add(151645)
            observed_ids=[]
            for selected in [None,*adapters]:
                config=asdict(Config(adapter_dir=str(selected) if selected else None))
                backend=MLXBackend(base,config)
                control=root/('control-'+(selected.name if selected else 'base')); control.mkdir()
                with patch('epagent.mlx_backend.subprocess.Popen') as process:
                    backend.start(control)
                    command=process.call_args.args[0]
                    worker_config=json.loads(command[-1])
                    self.assertEqual(worker_config['adapter_dir'],str(selected.resolve()) if selected else None)
                backend.stderr.close()
                output=io.StringIO()
                with patch('mlx_lm.utils.load_tokenizer',return_value=tokenizer), \
                     patch('mlx_lm.load',wraps=native_load) as load, \
                     patch('mlx_lm.stream_generate') as generate, \
                     patch('sys.stdin',io.StringIO('')),patch('sys.stdout',output):
                    worker(base,worker_config)
                    generate.assert_not_called()
                    self.assertEqual(load.call_args.kwargs['adapter_path'],str(selected.resolve()) if selected else None)
                event=json.loads(output.getvalue())
                self.assertEqual(event['event'],'ready')
                self.assertEqual(event['metadata']['model_id'],MODEL_ID)
                self.assertEqual(event['metadata']['revision'],REVISION)
                self.assertEqual(event['metadata']['adapter'],adapter_manifest(selected,loaded=bool(selected)))
                self.assertEqual(event['metadata']['stop_token_ids'],[151643,151645])
                observed_ids.append(event['metadata']['adapter']['id'])
            self.assertEqual(len(set(observed_ids)),3)
            # Native strict=False must not silently label missing adapter tensors loaded.
            bad=root/'incomplete'; bad.mkdir()
            (bad/'adapter_config.json').write_text(json.dumps(adapter_config))
            mx.save_safetensors(str(bad/'adapters.safetensors'),{next(iter(names)):next(iter(names.values()))})
            with self.assertRaisesRegex(ValueError,'cover exactly'):
                verify_loaded_adapter(toy,adapter_manifest(bad))
            # A post-selection change is rejected before native load.
            backend=MLXBackend(base,asdict(Config(adapter_dir=str(adapters[0]))))
            (adapters[0]/'adapter_config.json').write_text(json.dumps(adapter_config)+'\n')
            with patch('mlx_lm.load') as load, self.assertRaisesRegex(ValueError,'changed between'):
                worker(base,backend.config)
            load.assert_not_called()
