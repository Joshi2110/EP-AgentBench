"""Negative-result provenance and v3 data checks; never train or generate model responses."""

from collections import Counter
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from epagent.sft import config_at
from epagent.sft_data import digest, reviewed_examples
from epagent.synthetic import export_fixture, inject_setup, registered, score_trajectory
from epagent.tools import parse_call, snapshot

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/epagent-sft-v3'
ARCHIVE = ROOT / 'artifacts/ep-agent/sft-v2'


def read(path):
    return json.loads(path.read_text())


def events(path):
    return [json.loads(s) for s in path.read_text().splitlines()]


class PreservationTests(unittest.TestCase):
    def test_archive_hashes_allowlist_and_private_paths(self):
        manifest = read(ARCHIVE / 'archive-manifest.json')
        self.assertEqual(manifest['verified_raw_inventory_files'], 132)
        self.assertEqual(len(manifest['files']), 97)
        for name, hashes in manifest['files'].items():
            path = ARCHIVE / name
            self.assertEqual(digest(path), hashes['archived_sha256'])
            self.assertNotIn('control', Path(name).parts)
            self.assertNotEqual(path.suffix, '.safetensors')
            self.assertNotRegex(path.read_text(), r'/(Users|home|private/var|var/folders)/')
            if not hashes['repository_prefix_replacements']:
                self.assertEqual(hashes['raw_sha256'], hashes['archived_sha256'])

    def test_rescore_all_eight_archived_trajectories_and_adapter_identity(self):
        cases = {c['id']: c for c in read(ROOT / 'data/epagent-sft-v2/eval-fixtures.json')}
        frozen = read(ARCHIVE / 'sft-runs/controlled-v2-experiment/result.json')
        training = read(ARCHIVE / 'sft-runs/tool-use-lora-v2/run.json')
        self.assertEqual(frozen['primary_endpoint']['base'], '0/4')
        self.assertEqual(frozen['primary_endpoint']['adapted'], '0/4')
        total = 0
        for arm in ['base', 'adapted']:
            for report in (ARCHIVE / f'attempts/tool-recovery-v2-{arm}/attempts').glob('*/report.json'):
                r = read(report)
                trace = events(report.with_name('trajectory.jsonl'))
                case = cases[r['task_id'].removeprefix('synthetic:')]
                self.assertEqual(score_trajectory(case, trace, r['initial_sha256']), r['behavior'])
                self.assertFalse(r['behavior']['primary_recovery'])
                self.assertEqual(r['initial_sha256'], r['final_sha256'])
                self.assertEqual(r['termination_reason'], 'step_limit')
                self.assertEqual(r['model']['sha256'], training['prepared']['model']['sha256'])
                self.assertEqual(r['model']['adapter']['loaded'], arm == 'adapted')
                ready = next(e['data']['metadata'] for e in trace if e['event'] == 'model_ready')
                self.assertEqual(ready['adapter'], r['model']['adapter'])
                if arm == 'adapted':
                    self.assertEqual(r['model']['adapter']['sha256']['adapters.safetensors'],
                                     training['checkpoint_sha256']['adapters.safetensors'])
                calls = Counter(e['data']['tool'] for e in trace if e['event'] == 'tool_call')
                self.assertEqual(calls, {'read_file': 6, 'edit_file': 6} if arm == 'base' else {'read_file': 12})
                for event in trace:
                    if event['event'] == 'assistant':
                        json.loads(event['data']['text'])
                        parse_call(event['data']['text'])
                total += 1
        self.assertEqual(total, 8)

    def test_diagnosis_matches_original_selected_targets(self):
        diagnosis = read(ARCHIVE / 'diagnosis.json')
        examples = reviewed_examples(ROOT / 'data/epagent-sft-v2/trajectories')
        for split, rows in examples.items():
            counts = Counter(parse_call(r['messages'][-1]['content'])[0] for r in rows)
            self.assertEqual(counts, diagnosis['training'][split]['targets_by_tool'])
        self.assertEqual(diagnosis['training']['train']['failed_edit_then_read_then_accepted_edit'], 3)


class V3DataTests(unittest.TestCase):
    def test_freeze_budget_hashes_and_preparation(self):
        freeze = read(DATA / 'training-freeze.json')
        protocol = read(DATA / 'eval-protocol.json')
        config = config_at(DATA / 'lora-config.json')
        for name, sha in {**freeze['dataset_files_sha256'], **freeze['implementation_sha256']}.items():
            # The production tool protocol has advanced; verify the original
            # frozen tool implementation preserved with the diagnostic archive.
            path = (ROOT / 'artifacts/ep-agent/edit-history-v1' / name
                    if name == 'src/epagent/tools.py' else ROOT / name)
            self.assertEqual(digest(path), sha, name)
        self.assertEqual(protocol['training_freeze_sha256'], digest(DATA / 'training-freeze.json'))
        self.assertGreater(protocol['authored_after_training_freeze'], freeze['frozen_at'])
        rows = reviewed_examples(DATA / 'trajectories')
        self.assertEqual({k: len(v) for k, v in rows.items()}, {'train': 69, 'valid': 21})
        self.assertEqual(config['iterations'], len(rows['train']) * freeze['completed_dataset_passes'])
        self.assertEqual(config['iterations'], 138)
        prepared = read(DATA / 'preparation-manifest.json')
        self.assertFalse(prepared['training_performed'])
        self.assertEqual(prepared['effective_training_passes'], 2)
        self.assertEqual(prepared['protocol_sha256'], digest(DATA / 'eval-protocol.json'))
        self.assertEqual(prepared['review_manifest_sha256'], digest(DATA / 'trajectories/reviews.json'))
        self.assertEqual(prepared['stop_token_ids'], [151643, 151645])

    def test_all_four_splits_disjoint_without_eval_targets_in_history(self):
        demos = read(DATA / 'fixtures.json')
        splits = [[c for c in demos if c['split'] == s] for s in ['train', 'valid']]
        splits += [read(ROOT / 'data/epagent-sft-v2/eval-fixtures.json'), read(DATA / 'eval-fixtures.json')]
        for i, left in enumerate(splits):
            for right in splits[i+1:]:
                self.assertFalse({c['id'] for c in left} & {c['id'] for c in right})
                self.assertFalse({c['family'] for c in left} & {c['family'] for c in right})
                self.assertFalse({c['files'][c['source']] for c in left} & {c['files'][c['source']] for c in right})
        serialized = json.dumps(reviewed_examples(DATA / 'trajectories'))
        for case in splits[2] + splits[3]:
            self.assertNotIn(case['id'], serialized)
            self.assertNotIn(json.dumps(case['files'][case['source']])[1:-1], serialized)

    def test_positive_edits_copy_observed_source_tests_and_honest_finishes(self):
        reviews = read(DATA / 'trajectories/reviews.json')['episodes']
        counts, lengths, double_recoveries = Counter(), set(), 0
        for review in reviews:
            trace = events(DATA / 'trajectories' / review['trace'])
            calls = [e['data'] for e in trace if e['event'] == 'tool_call']
            observations = {e['data']['step']: e['data']['observation'] for e in trace if e['event'] == 'tool_result'}
            lengths.add(len(calls))
            seen, selected = {}, set(review['selected_assistant_steps'])
            self.assertFalse(selected & set(review['excluded_failed_edit_steps'] + review['excluded_setup_read_steps']))
            failures = 0
            for i, call in enumerate(calls):
                name, args, step = call['tool'], call['arguments'], call['step']
                obs = observations[step]
                if review['split'] == 'train' and step in selected:
                    counts[name] += 1
                if name == 'read_file':
                    seen[args['path']] = obs['content']
                if name == 'edit_file' and step in selected:
                    self.assertEqual(seen[args['path']].count(args['old_text']), 1)
                    self.assertNotEqual(args['old_text'], args['new_text'])
                    self.assertEqual(calls[i+1]['tool'], 'run_python')
                failures += name == 'edit_file' and 'error' in obs
            double_recoveries += failures == 2
            last = observations[calls[-2]['step']]
            summary = calls[-1]['arguments']['summary']
            if review['outcome'] == 'success':
                self.assertEqual(last['stdout'].strip(), 'PASS ' + review['episode_id'])
                self.assertIn(last['stdout'].strip(), summary)
            else:
                self.assertEqual(last['status'], 'python_error')
                self.assertIn('incomplete', summary)
                self.assertNotIn('PASS', summary)
        self.assertEqual(counts, {'read_file': 19, 'edit_file': 14, 'run_python': 19, 'finish': 12, 'list_files': 5})
        self.assertEqual(double_recoveries, 3)
        self.assertGreaterEqual(len(lengths), 5)

    def test_scripted_demonstrations_reproduce_observations(self):
        spec = importlib.util.spec_from_file_location('build_v3', ROOT / 'scripts/build_sft_v3.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Replay the original demonstration prompt, never rewrite old training data
        # to adopt today's tool protocol.
        first = events(next((DATA / 'trajectories').glob('*.jsonl')))
        module.SYSTEM_PROMPT = next(e['data']['messages'][0]['content'] for e in first
                                    if e['event'] == 'model_request')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'traces'
            module.build(DATA / 'fixtures.json', out)
            for path in (DATA / 'trajectories').glob('*.jsonl'):
                self.assertEqual(events(path), events(out / path.name))

    def test_heldout_setup_is_registered_rejected_and_unchanged_no_agent(self):
        cases, config = registered(DATA / 'eval-fixtures.json', DATA / 'eval-protocol.json', 'base', None)
        for case in cases:
            with tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory) / 'workspace'
                export_fixture(case, workspace)
                before = snapshot(workspace)
                emitted = []
                inject_setup(case, workspace, [], lambda *args: emitted.append(args), config)
                self.assertEqual(snapshot(workspace), before)
                self.assertTrue(emitted[-1][1]['workspace_unchanged'])


if __name__ == '__main__':
    unittest.main()
