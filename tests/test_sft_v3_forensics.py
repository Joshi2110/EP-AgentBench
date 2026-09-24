"""Offline evidence checks only: never rescore, train, infer, or execute edited code."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'artifacts/ep-agent/sft-v3'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OfflineForensicsTests(unittest.TestCase):
    def test_archive_hashes_exclusions_and_unchanged_frozen_outcome(self):
        manifest = read(ARCHIVE / 'archive-manifest.json')
        self.assertEqual(manifest['verified_raw_inventory_files'], 138)
        self.assertEqual(len(manifest['files']), 107)
        for name, record in manifest['files'].items():
            p = ARCHIVE / name
            self.assertEqual(sha(p), record['archived_sha256'])
            if not record['repository_prefix_replacements'] and not record['removed_fields']:
                self.assertEqual(record['raw_sha256'], record['archived_sha256'])
            self.assertNotRegex(p.read_text(), r'/(Users|home|private/var|var/folders|opt/homebrew)/')
            self.assertNotIn('control', p.relative_to(ARCHIVE).parts)
            self.assertNotEqual(p.suffix, '.safetensors')
        frozen = read(ARCHIVE / 'sft-runs/controlled-v3-experiment/result.json')
        self.assertEqual(frozen['primary_endpoint'], {'base': '0/4', 'adapted': '0/4'})
        self.assertEqual(frozen['training']['updates_completed'], 138)
        self.assertEqual(frozen['training']['trained_assistant_tokens'], 5062)

    def test_every_rejection_and_latest_observation_is_accounted_for(self):
        rows = read(ARCHIVE / 'edit-failures.json')['rejections']
        indexed = {(r['episode_id'], r['observation_event']): r for r in rows}
        self.assertEqual(len(indexed), 54)
        seen = set()
        for path in ARCHIVE.glob('attempts/*/attempts/*/trajectory.jsonl'):
            calls, observations, setup = {}, {}, None
            for event in [json.loads(s) for s in path.read_text().splitlines()]:
                d, kind = event['data'], event['event']
                if kind == 'setup_tool_call':
                    setup = event
                if kind == 'tool_call':
                    calls[d['step']] = event
                if kind in ['setup_tool_result', 'tool_result']:
                    call = setup if kind == 'setup_tool_result' else calls[d['step']]
                    c = call['data']; args = c['arguments']; obs = d['observation']
                    if c['tool'] == 'read_file':
                        observations[args['path']] = (event['sequence'], obs['content'])
                    if kind == 'tool_result' and c['tool'] == 'edit_file' and 'error' in obs:
                        key = (event['episode_id'], event['sequence']); r = indexed[key]; seen.add(key)
                        seq, source = observations[args['path']]
                        self.assertEqual(r['latest_source_observation']['observation_event'], seq)
                        self.assertEqual(r['latest_source_observation']['content'], source)
                        self.assertEqual(r['old_text'], args['old_text'])
                        self.assertEqual(r['new_text'], args['new_text'])
                        self.assertEqual(r['occurrences'], source.count(args['old_text']))
                        self.assertEqual(r['call_event'], call['sequence'])
        self.assertEqual(seen, set(indexed))

    def test_taxonomy_and_adaptation_counts(self):
        rows = read(ARCHIVE / 'edit-failures.json')['rejections']
        self.assertEqual(Counter(r['cause'] for r in rows), {'indentation': 24, 'quoting': 12, 'duplicated_span': 18})
        self.assertEqual(Counter(r['occurrences'] for r in rows), {0: 36, 2: 18})
        self.assertEqual(Counter(r['next_action'] for r in rows), {'reinspect_same_source': 35, 'repeat_same_rejected_edit': 11, 'budget_end': 8})
        self.assertFalse(any(r['subsequent_edit_arguments_changed'] for r in rows))
        self.assertTrue(all(r['matches_injected_arguments'] for r in rows))
        self.assertEqual(sum(r['latest_source_observation']['setup_intervention'] for r in rows), 12)

    def test_scope_counterfactuals_are_not_mislabeled_as_repairs(self):
        rows = read(ARCHIVE / 'edit-failures.json')['rejections']
        for r in rows:
            source = r['latest_source_observation']['content']
            self.assertEqual(r['new_text'], source)
            self.assertFalse(r['whole_file_old_text_alternative']['changes_bytes'])
            for c in r['minimal_correction_candidates']:
                self.assertEqual(source.count(c['old_text']), 1)
                self.assertEqual(c['resulting_source'], source.replace(c['old_text'], r['new_text'], 1))
                if r['cause'] == 'duplicated_span':
                    self.assertTrue(c['changes_bytes'])
                    self.assertFalse(c['resulting_python_parseable'])
                else:
                    self.assertFalse(c['changes_bytes'])
                    self.assertTrue(c['resulting_python_parseable'])
            if r['cause'] == 'duplicated_span':
                self.assertEqual([c['added_characters'] for c in r['minimal_correction_candidates']], [1, 4])

    def test_demonstration_distribution_and_reproducible_analysis(self):
        original = read(ARCHIVE / 'edit-failures.json')
        self.assertEqual(original['demonstrations']['train']['whole_file_targets'], 11)
        self.assertEqual(original['demonstrations']['train']['positive_old_text_characters']['median'], 50.5)
        self.assertEqual(original['demonstrations']['valid']['whole_file_targets'], 4)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'archive'
            shutil.copytree(ARCHIVE, target)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_sft_v3_edits.py'),
                                     '--archive', str(target)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read(target / 'edit-failures.json'), original)
            for name, record in read(target / 'archive-manifest.json')['files'].items():
                self.assertEqual(sha(target / name), record['archived_sha256'])


if __name__ == '__main__':
    unittest.main()
