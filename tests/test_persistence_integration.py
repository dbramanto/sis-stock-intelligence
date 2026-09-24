import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stage1.history import save_validated_snapshot, list_snapshots, load_snapshot
from stage3.result_store import save_analysis_result, load_analysis_result, result_exists
from storage_adapter import StorageUnavailable


class PersistenceIntegrationTests(unittest.TestCase):
    def raw(self):
        return {i: f"B{i}\nvalid raw" for i in range(1, 12)}

    def canonical(self):
        return [{"symbol": "AAA"}]

    def stage3(self):
        return {
            "status": "COMPLETE",
            "candidate_count": 1,
            "blocked": [],
            "candidates": [{"symbol": "AAA"}],
            "ranking": {"swing": {"top": []}, "long_term": {"top": []}},
        }

    def test_history_roundtrip_via_filesystem_adapter(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"SIS_DATA_DIR": td}, clear=False):
            snap = save_validated_snapshot(
                self.raw(), self.canonical(), "PASS",
                metadata={"expected_total": 1, "filter_fingerprint": "X"},
            )
            self.assertTrue((Path(td) / "input_history" / f"{snap['snapshot_id']}.json").exists())
            self.assertEqual(load_snapshot(snap["snapshot_id"])["snapshot_id"], snap["snapshot_id"])
            self.assertEqual(list_snapshots(validated_only=True)[0]["snapshot_id"], snap["snapshot_id"])

    def test_result_roundtrip_via_filesystem_adapter(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"SIS_DATA_DIR": td}, clear=False):
            save_analysis_result("snap_1", self.stage3(), "2026-09-24")
            self.assertTrue((Path(td) / "analysis_results" / "snap_1.json").exists())
            self.assertTrue(result_exists("snap_1"))
            self.assertEqual(load_analysis_result("snap_1")["snapshot_id"], "snap_1")

    def test_cloud_mode_fails_closed_for_history(self):
        env = {"SIS_STORAGE_BACKEND": "cloud"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(StorageUnavailable):
                list_snapshots(validated_only=True)

    def test_cloud_mode_fails_closed_for_results(self):
        env = {"SIS_STORAGE_BACKEND": "cloud"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(StorageUnavailable):
                result_exists("snap_1")


if __name__ == "__main__":
    unittest.main()
