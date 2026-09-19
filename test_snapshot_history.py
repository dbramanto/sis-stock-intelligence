import io
import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from snapshot_history import SnapshotError, SnapshotStore


def sample(tag="A"):
    raw = [f"B1-{tag}", f"B2-{tag}", f"B3-{tag}"]
    normalized = [
        [{"Symbol": "AAA", "Price": 100}],
        [{"Symbol": "AAA", "NPM": 10}],
        [{"Symbol": "AAA", "FCF": 5}],
    ]
    merged = [{"Symbol": "AAA", "Price": 100, "Execution State": "AVAILABLE"}]
    validation = {
        "gate_state": "PASS",
        "symbols": 1,
        "conflicts": 0,
        "partial_symbols": 0,
        "schema_realigned_batches": [],
    }
    return raw, normalized, merged, validation


class SnapshotHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SnapshotStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, td="2026-09-18", tag="A", gate="PASS", created=None):
        raw, normalized, merged, validation = sample(tag)
        validation["gate_state"] = gate
        return self.store.save_daily_snapshot(
            trading_date=td,
            raw_batches=raw,
            normalized_batches=normalized,
            merged_stage1=merged,
            validation=validation,
            created_at=created,
        )

    def test_same_trading_day_same_data_is_idempotent(self):
        a = self.save(created=datetime(2026, 9, 18, 19, 0))
        b = self.save(created=datetime(2026, 9, 18, 23, 0))
        self.assertEqual(a.snapshot_id, b.snapshot_id)
        self.assertEqual(1, len(self.store.list_daily()))

    def test_same_day_changed_data_creates_revision_not_new_daily_row(self):
        a = self.save(tag="A")
        b = self.save(tag="B")
        self.assertEqual(a.trading_date, b.trading_date)
        self.assertEqual(1, a.revision)
        self.assertEqual(2, b.revision)
        rows = self.store.list_daily()
        self.assertEqual(1, len(rows))
        self.assertEqual(2, rows[0]["revision"])

    def test_after_midnight_created_at_does_not_change_trading_date(self):
        a = self.save(
            td="2026-09-18",
            created=datetime(2026, 9, 19, 0, 30),
        )
        self.assertEqual("2026-09-18", a.trading_date)
        self.assertTrue(a.created_at.startswith("2026-09-19T00:30:00"))

    def test_blocked_never_persists(self):
        with self.assertRaises(SnapshotError):
            self.save(gate="BLOCKED")
        self.assertEqual([], self.store.list_daily())

    def test_review_is_usable_and_persists(self):
        a = self.save(gate="REVIEW")
        self.assertEqual("REVIEW", a.gate_state)

    def test_exactly_three_batches_required(self):
        _, normalized, merged, validation = sample()
        with self.assertRaises(SnapshotError):
            self.store.save_daily_snapshot(
                trading_date="2026-09-18",
                raw_batches=["B1", "B2"],
                normalized_batches=normalized,
                merged_stage1=merged,
                validation=validation,
            )

    def test_tamper_detection(self):
        a = self.save()
        p = Path(self.tmp.name) / a.trading_date / "revision_001.json"
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["raw_batches"][0] = "TAMPERED"
        p.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(SnapshotError):
            self.store.load_effective(a.trading_date)

    def test_export_backup_contains_history_and_index(self):
        self.save(td="2026-09-18")
        self.save(td="2026-09-19")
        data = self.store.export_backup()
        self.assertTrue(data.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = set(zf.namelist())
            self.assertIn("BACKUP_INDEX.json", names)
            self.assertIn("2026-09-18/manifest.json", names)
            self.assertIn("2026-09-18/revision_001.json", names)
            self.assertIn("2026-09-19/manifest.json", names)
            index = json.loads(zf.read("BACKUP_INDEX.json"))
            self.assertEqual("SIS_DAILY_HISTORY_BACKUP", index["export_type"])
            self.assertEqual(2, len(index["daily_snapshots"]))

    def test_restore_round_trip(self):
        self.save(td="2026-09-18")
        self.save(td="2026-09-19")
        data = self.store.export_backup()
        with tempfile.TemporaryDirectory() as other:
            restored = SnapshotStore(other)
            result = restored.restore_backup(data)
            self.assertEqual({"restored_days": 2, "skipped_days": 0}, result)
            self.assertEqual(2, len(restored.list_daily()))
            self.assertEqual("2026-09-19", restored.list_daily()[0]["trading_date"])

    def test_restore_identical_is_idempotent(self):
        self.save(td="2026-09-18")
        data = self.store.export_backup()
        result = self.store.restore_backup(data)
        self.assertEqual({"restored_days": 0, "skipped_days": 1}, result)
        self.assertEqual(1, len(self.store.list_daily()))

    def test_restore_tampered_revision_is_blocked(self):
        self.save(td="2026-09-18")
        data = self.store.export_backup()
        source = zipfile.ZipFile(io.BytesIO(data), "r")
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in source.namelist():
                raw = source.read(name)
                if name.endswith("revision_001.json"):
                    payload = json.loads(raw)
                    payload["raw_batches"][0] = "TAMPERED"
                    raw = json.dumps(payload).encode()
                zf.writestr(name, raw)
        source.close()
        with tempfile.TemporaryDirectory() as other:
            restored = SnapshotStore(other)
            with self.assertRaises(SnapshotError):
                restored.restore_backup(out.getvalue())
            self.assertEqual([], restored.list_daily())

    def test_restore_conflict_never_overwrites(self):
        self.save(td="2026-09-18", tag="A")
        data = self.store.export_backup()
        with tempfile.TemporaryDirectory() as other:
            restored = SnapshotStore(other)
            raw, normalized, merged, validation = sample("B")
            restored.save_daily_snapshot(
                trading_date="2026-09-18",
                raw_batches=raw,
                normalized_batches=normalized,
                merged_stage1=merged,
                validation=validation,
            )
            before = restored.load_effective("2026-09-18")["content_hash"]
            with self.assertRaises(SnapshotError):
                restored.restore_backup(data)
            after = restored.load_effective("2026-09-18")["content_hash"]
            self.assertEqual(before, after)

    def test_days_are_independent_and_sorted_latest_first(self):
        self.save(td="2026-09-17")
        self.save(td="2026-09-19")
        rows = self.store.list_daily()
        self.assertEqual(["2026-09-19", "2026-09-17"], [x["trading_date"] for x in rows])


if __name__ == "__main__":
    unittest.main()
