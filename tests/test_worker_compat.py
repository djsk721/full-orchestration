import json
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestra.ssh import SSHClient, WorkerFeatureUnavailable, WorkerIncompatible, worker_compatibility
from orchestra.worker_compat import worker_manifest


class WorkerCompatibilityTests(unittest.TestCase):
    def test_legacy_and_transitional_features(self):
        before, transitional = (worker_compatibility(report) for report in ({}, {"git_context": True}))
        self.assertEqual(before["state"], "legacy")
        self.assertIsNone(before["version"])
        self.assertNotIn("git.diff", before["capabilities"])
        self.assertIn("git.diff", transitional["capabilities"])

    def test_modern_ranges_and_malformed_metadata(self):
        current = worker_manifest(1)
        self.assertNotIn("files.upload", worker_compatibility({"compatibility": current})["capabilities"])
        with self.assertRaises(WorkerIncompatible):
            worker_compatibility({"compatibility": worker_manifest(2)})
        with self.assertRaises(WorkerIncompatible):
            worker_compatibility({"compatibility": current | {"capabilities": [True]}})

    def test_incompatible_envelope_and_missing_optional_feature(self):
        client = SSHClient(Path("."), "qa", {"name": "Fixture", "host": "localhost", "user": "operator",
                                            "worker_dir": "/opt/workspace"})
        with patch.object(client, "call", return_value={}) as call:
            with self.assertRaises(WorkerFeatureUnavailable):
                client.worker_git("git_diff", repo="/shared/example", path="readme.md")
            call.assert_called_once_with("info", compatibility_only=True)
        other = json.dumps({"version": 2, "ok": False}).encode()
        with patch.object(client, "_command", return_value=other):
            with self.assertRaises(WorkerIncompatible):
                client.call("info")
