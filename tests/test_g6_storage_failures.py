"""Failure closure of the shared artifact writer."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lae_simulator.simulation.canonical_store import write_artifact_bundle


class StorageFailureTests(unittest.TestCase):
    def test_manifest_serialization_failure_removes_partial_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(TypeError):
                write_artifact_bundle(root, 'run', {'events.jsonl': b'event'}, {'bad': object()})
            self.assertEqual(list(root.iterdir()), [])

    def test_failed_write_leaves_existing_run_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = write_artifact_bundle(root, 'old', {'events.jsonl': b'valid'}, {})
            before = (existing / 'events.jsonl').read_bytes()
            with patch.object(Path, 'write_bytes', side_effect=OSError('disk failure')), self.assertRaises(OSError):
                write_artifact_bundle(root, 'new', {'events.jsonl': b'partial'}, {})
            self.assertEqual((existing / 'events.jsonl').read_bytes(), before)
            self.assertFalse((root / 'new').exists())
            self.assertFalse((root / '.new.tmp').exists())
