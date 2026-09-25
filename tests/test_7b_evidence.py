"""Byte provenance and offline syntax reconstruction; never run a model or grader."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'artifacts/ep-agent/7b-development-smoke'


class EvidenceTests(unittest.TestCase):
    def test_hashes_and_sanitization(self):
        manifest = json.loads((ARCHIVE / 'archive-manifest.json').read_text())
        self.assertEqual(manifest['verified_original_inventory_entries'], 53)
        for name, item in manifest['files'].items():
            data = (ARCHIVE / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['archived_sha256'])
            self.assertNotRegex(data.decode(), r'/(Users|home|private/var|var/folders)/')
            if not item['repository_prefix_replacements']:
                self.assertEqual(item['raw_sha256'], item['archived_sha256'])
            self.assertFalse(name.endswith('.safetensors'))

    def test_every_edit_reconstructs_and_first_syntax_failure_is_step_five(self):
        spec = importlib.util.spec_from_file_location('analyze_7b', ROOT / 'scripts/analyze_7b_edits.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        result = module.analyze(ARCHIVE)
        self.assertEqual(result, json.loads((ARCHIVE / 'edit-analysis.json').read_text()))
        self.assertEqual(result['first_syntax_breaking_step'], 5)
        self.assertEqual([e['syntax_after']['valid'] for e in result['edits']], [True, False, False, False, False])
        self.assertEqual([e['call_event'] for e in result['edits']], [142, 261, 396, 515, 634])
        self.assertEqual(result['edits'][1]['syntax_after']['line'], 3)
        self.assertTrue(all(not e['required_cart_total_declared'] for e in result['edits']))

    def test_frozen_comparison_and_exact_responses_remain_negative(self):
        comparison = json.loads((ARCHIVE / 'attempts/replace-lines-7b-smoke/comparison.json').read_text())
        self.assertEqual(comparison['primary_repair_result'], {'1.5B': False, '7B': False})
        arm = comparison['base_7b']
        self.assertEqual((arm['schema_valid_calls'], arm['content_changing_edits']), (12, 5))
        self.assertEqual(arm['python_test_runs_by_agent'], 0)
        self.assertEqual(arm['final_summaries'], [])
        self.assertIn('IndentationError', arm['independent_visible_test_outcome']['stderr'])
