"""Pinned model selection and download regressions; no network or inference."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epagent.episode import Config
from epagent.mlx_backend import MLXBackend, MODEL_ID, REVISION, MODEL_7B, REVISION_7B, download


class ModelSelectionTests(unittest.TestCase):
    def test_both_exact_revisions_without_adapter_and_unchanged_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name, revision in [(MODEL_ID, REVISION), (MODEL_7B, REVISION_7B)]:
                (path / 'epagent-model.json').write_text(json.dumps({'model_id': name, 'revision': revision}))
                backend = MLXBackend(path, asdict(Config()))
                self.assertEqual(backend.metadata['model_id'], name)
                self.assertFalse(backend.metadata['adapter']['requested'])
                self.assertEqual(backend.config['steps'], 12)
                self.assertEqual(backend.config['max_tokens'], 768)
                self.assertEqual(backend.config['temperature'], 0)
                self.assertIsNone(backend.process)

    def test_unknown_or_changed_revision_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for name, revision in [(MODEL_7B, REVISION), (MODEL_ID, REVISION_7B), ('unknown', REVISION_7B)]:
                (path / 'epagent-model.json').write_text(json.dumps({'model_id': name, 'revision': revision}))
                with self.assertRaisesRegex(ValueError, 'reviewed pinned'):
                    MLXBackend(path, asdict(Config()))

    def test_unknown_download_rejected_without_network_or_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch('urllib.request.urlopen') as network:
            out = Path(directory) / 'absent'
            with self.assertRaises(ValueError):
                download(out, model_id='unknown')
            network.assert_not_called()
            self.assertFalse(out.exists())
