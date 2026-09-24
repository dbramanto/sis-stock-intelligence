import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from storage_adapter import JsonStore, StorageUnavailable, storage_backend


class StorageAdapterTests(unittest.TestCase):
    def test_default_backend_is_filesystem(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(storage_backend(), "filesystem")

    def test_filesystem_round_trip(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {}, clear=True):
            store = JsonStore(Path(td))
            payload = {"snapshot_id": "abc", "status": "VALIDATED"}
            store.put("input_history", "abc", payload)
            self.assertTrue(store.exists("input_history", "abc"))
            self.assertEqual(store.get("input_history", "abc"), payload)
            self.assertEqual(store.list("input_history")[0], payload)

    def test_cloud_mode_fails_closed_without_credentials(self):
        env = {"SIS_STORAGE_BACKEND": "cloud"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(StorageUnavailable, "CLOUD_STORAGE_NOT_CONFIGURED"):
                JsonStore("/tmp/unused")

    def test_cloud_mode_never_falls_back_to_local(self):
        env = {
            "SIS_STORAGE_BACKEND": "cloud",
            "SIS_CLOUD_STORAGE_URL": "https://example.invalid",
            "SIS_CLOUD_STORAGE_ACCESS_KEY": "access",
            "SIS_CLOUD_STORAGE_SECRET_KEY": "secret",
            "SIS_CLOUD_STORAGE_BUCKET": "sis-test",
        }
        with patch.dict(os.environ, env, clear=True):
            store = JsonStore("/tmp/unused")
            client = Mock()
            client.list_objects_v2.side_effect = RuntimeError("cloud unavailable")
            store._client = client
            with self.assertRaisesRegex(StorageUnavailable, "CLOUD_STORAGE_LIST_FAILED"):
                store.list("input_history")
            self.assertFalse(Path("/tmp/unused/input_history").exists())


if __name__ == "__main__":
    unittest.main()
