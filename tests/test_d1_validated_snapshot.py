import tempfile
import unittest
from datetime import datetime, timezone

from stage1.history import save_validated_snapshot, list_snapshots, load_snapshot


class TestD1ValidatedSnapshot(unittest.TestCase):
    def raw(self):
        return {i: f"B{i}\nvalid raw input" for i in range(1, 12)}

    def canonical(self):
        return [
            {"symbol": "ANTM", "price": 1000.0},
            {"symbol": "PGEO", "price": 1200.0},
        ]

    def test_rejects_incomplete_b1_b11(self):
        raw = self.raw(); raw[11] = ""
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "HISTORY_REQUIRES_B1_B11"):
                save_validated_snapshot(raw, self.canonical(), "PASS", base_dir=td)
            self.assertEqual(list_snapshots(td), [])

    def test_rejects_nonpass_validation(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "HISTORY_REQUIRES_VALIDATED_STAGE1"):
                save_validated_snapshot(self.raw(), self.canonical(), "FAIL", base_dir=td)
            self.assertEqual(list_snapshots(td), [])

    def test_valid_snapshot_is_official(self):
        with tempfile.TemporaryDirectory() as td:
            snap = save_validated_snapshot(
                self.raw(), self.canonical(), "PASS", base_dir=td,
                now=datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc),
                metadata={"expected_total": 2},
            )
            self.assertEqual(snap["status"], "VALIDATED")
            self.assertTrue(snap["canonical_digest"])
            loaded = load_snapshot(snap["snapshot_id"], td)
            self.assertEqual(loaded["canonical_digest"], snap["canonical_digest"])
            self.assertEqual(len(list_snapshots(td, validated_only=True)), 1)

    def test_identical_validated_data_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as td:
            first = save_validated_snapshot(self.raw(), self.canonical(), "PASS", base_dir=td)
            second = save_validated_snapshot(self.raw(), self.canonical(), "PASS", base_dir=td)
            self.assertEqual(first["snapshot_id"], second["snapshot_id"])
            self.assertEqual(len(list_snapshots(td, validated_only=True)), 1)

    def test_changed_validated_data_creates_new_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            first = save_validated_snapshot(self.raw(), self.canonical(), "PASS", base_dir=td)
            changed = self.canonical(); changed[0]["price"] = 1010.0
            second = save_validated_snapshot(self.raw(), changed, "PASS", base_dir=td)
            self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
            self.assertEqual(len(list_snapshots(td, validated_only=True)), 2)

    def test_invalid_attempt_cannot_replace_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            good = save_validated_snapshot(self.raw(), self.canonical(), "PASS", base_dir=td)
            with self.assertRaises(ValueError):
                save_validated_snapshot(self.raw(), self.canonical(), "FAIL", base_dir=td)
            history = list_snapshots(td, validated_only=True)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["snapshot_id"], good["snapshot_id"])


if __name__ == "__main__":
    unittest.main()
