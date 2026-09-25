"""Check preserved evidence bytes without model inference or rescoring."""
import hashlib
import json
from pathlib import Path
import unittest


class ArchiveTests(unittest.TestCase):
    def test_archive_integrity(self):
        root = Path(__file__).resolve().parents[1] / 'artifacts/ep-agent/edit-history-v1'
        manifest = json.loads((root / 'archive-manifest.json').read_text())
        self.assertEqual(manifest['primary_result'], '0/8 exact targets')
        self.assertEqual(manifest['verified_raw_inventory_files'], 55)
        for name, item in manifest['files'].items():
            data = (root / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['archived_sha256'])
            self.assertNotRegex(data.decode(), r'/(Users|home|private/var|var/folders)/')
            if not item['repository_prefix_replacements']:
                self.assertEqual(item['raw_sha256'], item['archived_sha256'])
        traces = list((root / 'attempts/edit-history-v1').glob('*/trace.jsonl'))
        self.assertEqual(len(traces), 8)
