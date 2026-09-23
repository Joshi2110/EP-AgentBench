"""Private evidence/replay regressions; no MLX model or tokenizer substitute."""

import hashlib
import io
import json
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest

from epagent.mlx_backend import MLXBackend
from epagent.tools import decode_call, parse_call

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'artifacts/ep-agent/smoke-001'
REPLAY = ROOT / 'artifacts/ep-agent/audit-v0.1-fixes/replay-tokenizer.json'


class EvidenceTests(unittest.TestCase):
    def test_original_payload_is_immutable_and_allowlisted(self):
        manifest = json.loads((ARCHIVE / 'manifest.json').read_text())
        allowed = {'report.json', 'trajectory.jsonl', 'conversation.json', 'changes.diff'}
        for name, digest in manifest['files'].items():
            p = ARCHIVE / name
            self.assertTrue(name in allowed or (p.relative_to(ARCHIVE).parts[0] in
                            {'initial', 'workspace', 'runner-source'} and p.suffix in {'.py', '.md'}))
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest)
        self.assertEqual(manifest['files']['report.json'],
                         '836c8db143fec2a05f55c1252543b8bfb8af229520c65d1c8996963efd1ab132')
        self.assertEqual(manifest['files']['trajectory.jsonl'],
                         'a67fe423864d7f86c6136eac38446ce98689ef73941b464056e7168ad84427d9')
        payload = {str(p.relative_to(ARCHIVE)) for p in ARCHIVE.rglob('*') if p.is_file()}
        self.assertEqual(payload, set(manifest['files']) | {'manifest.json'})
        report = json.loads((ARCHIVE / 'report.json').read_text())
        events = [json.loads(s) for s in (ARCHIVE / 'trajectory.jsonl').read_text().splitlines()]
        self.assertEqual(sum(e['event'] == 'assistant' for e in events), 12)
        self.assertFalse(any(e['event'] == 'tool_call' for e in events))
        self.assertEqual(report['tool_calls'], 0)
        self.assertEqual(report['reward'], 0)
        self.assertEqual(report['modified_files'], [])
        self.assertEqual(report['grading']['passed'], 3)
        self.assertEqual(report['grading']['total'], 13)
        self.assertEqual(report['initial_sha256'], report['final_sha256'])
        self.assertEqual((ARCHIVE / 'changes.diff').read_bytes(), b'')
        self.assertEqual(next(e['data'] for e in events if e['event'] == 'episode_end'), report)
        for name, digest in report['initial_sha256'].items():
            for folder in ['initial', 'workspace']:
                self.assertEqual(hashlib.sha256((ARCHIVE / folder / name).read_bytes()).hexdigest(), digest)

    def test_replay_counts_and_copied_examples_are_not_original_successes(self):
        audit = json.loads(REPLAY.read_text())
        events = [json.loads(s) for s in (ARCHIVE / 'trajectory.jsonl').read_text().splitlines()]
        raw = [e['data'] for e in events if e['event'] == 'assistant']
        self.assertEqual(len(audit['replay']), 12)
        for response, replay in zip(raw, audit['replay']):
            with self.subTest(step=replay['step']):
                self.assertEqual(response['step'], replay['step'])
                # The checked real tokenizer projection is also the original
                # text prefix before its chat terminator, not arbitrary extraction.
                eos = audit['tokenizer']['tokenizer_eos_token']
                self.assertEqual(replay['stopped_text'], response['text'].split(eos, 1)[0])
                with self.assertRaises(ValueError):
                    parse_call(response['text'])
                self.assertIsInstance(decode_call(replay['stopped_text']), dict)
                tool, args = parse_call(replay['stopped_text'])
                self.assertEqual(tool, replay['tool'])
                for key, value in replay['copied_arguments'].items():
                    self.assertEqual(args[key], value)
        self.assertEqual(audit['replay_totals'], {'stopped_bare_json_valid': 0,
                         'stopped_envelope_json_valid': 12, 'stopped_tool_schema_valid': 12})
        self.assertEqual([r['step'] for r in audit['replay'] if 'old_text' in r['copied_arguments']], [3, 5, 7, 9, 11])
        self.assertEqual([r['step'] for r in audit['replay'] if 'code' in r['copied_arguments']], [4, 6, 8, 10, 12])
        self.assertFalse(audit['inference_performed'])
        self.assertFalse(audit['tools_executed'])
        self.assertEqual(audit['original_tool_calls'], 0)

    def test_unavailable_real_tokenizer_is_explicitly_unverified(self):
        namespace = runpy.run_path(str(ROOT / 'scripts/audit_epagent.py'))
        result = namespace['audit'](None)
        self.assertIn('unverified', result['tokenizer_status'])
        self.assertIsNone(result['replay'])
        self.assertNotIn('tokenizer', result)

    def test_ready_event_keeps_configured_stop_ids_for_future_trajectories(self):
        # Protocol plumbing only. Actual tokenizer evidence comes from the
        # separately executed offline audit, never from this simulated event.
        stop_ids = json.loads(REPLAY.read_text())['tokenizer']['configured_stop_token_ids']
        backend = MLXBackend.__new__(MLXBackend)
        backend.metadata = {}
        ready = {'event': 'ready', 'metadata': {'stop_token_ids': stop_ids}}
        done = {'event': 'done', 'text': '{"tool":"list_files","arguments":{}}'}
        backend.buffer = bytearray((json.dumps(ready) + '\n' + json.dumps(done) + '\n').encode())
        read_fd, write_fd = os.pipe()
        try:
            with os.fdopen(read_fd, 'rb') as output:
                backend.process = SimpleNamespace(stdin=io.BytesIO(), stdout=output)
                events = []
                self.assertEqual(backend.generate([], 1, lambda *args: events.append(args)), done)
                self.assertEqual(backend.metadata['stop_token_ids'], stop_ids)
                self.assertEqual(events[0], ('model_ready', ready))
        finally:
            os.close(write_fd)


if __name__ == '__main__':
    unittest.main()
