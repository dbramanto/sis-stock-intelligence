import tempfile
import unittest
from datetime import datetime, timezone

from stage1.history import save_validated_snapshot, list_snapshots, load_snapshot, get_snapshot_batch


class TestD1ValidatedSnapshot(unittest.TestCase):
    def raw(self):
        return {i: f"B{i}\nvalid raw input" for i in range(1, 12)}

    def canonical(self):
        return [
            {"symbol": "ANTM", "price": 1000.0},
            {"symbol": "PGEO", "price": 1200.0},
        ]

    def meta(self):
        return {"expected_total": 2, "filter_fingerprint": "S0-6FILTER"}

    def save(self, td, canonical=None, status="PASS", metadata=None):
        return save_validated_snapshot(
            self.raw(), self.canonical() if canonical is None else canonical, status,
            base_dir=td, metadata=self.meta() if metadata is None else metadata,
        )

    def test_rejects_incomplete_b1_b11(self):
        raw=self.raw(); raw[11]=""
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_REQUIRES_B1_B11"):
                save_validated_snapshot(raw,self.canonical(),"PASS",base_dir=td,metadata=self.meta())
            self.assertEqual(list_snapshots(td),[])

    def test_rejects_nonpass_validation(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_REQUIRES_VALIDATED_STAGE1"):
                self.save(td,status="FAIL")
            self.assertEqual(list_snapshots(td),[])

    def test_rejects_empty_canonical(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_EMPTY_CANONICAL"):
                self.save(td,canonical=[])
            self.assertEqual(list_snapshots(td),[])

    def test_rejects_missing_or_duplicate_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_CANONICAL_MISSING_SYMBOL"):
                self.save(td,canonical=[{"symbol":"","price":1},{"symbol":"PGEO","price":2}])
            with self.assertRaisesRegex(ValueError,"HISTORY_CANONICAL_DUPLICATE_SYMBOL"):
                self.save(td,canonical=[{"symbol":"ANTM"},{"symbol":"antm"}])
            self.assertEqual(list_snapshots(td),[])

    def test_rejects_expected_total_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_CANONICAL_COUNT_MISMATCH"):
                self.save(td,metadata={"expected_total":3})
            self.assertEqual(list_snapshots(td),[])

    def test_valid_snapshot_is_official(self):
        with tempfile.TemporaryDirectory() as td:
            snap=save_validated_snapshot(
                self.raw(),self.canonical(),"PASS",base_dir=td,
                now=datetime(2026,9,23,9,0,tzinfo=timezone.utc),metadata=self.meta(),
            )
            self.assertEqual(snap["status"],"VALIDATED")
            self.assertTrue(snap["canonical_digest"])
            loaded=load_snapshot(snap["snapshot_id"],td)
            self.assertEqual(loaded["canonical_digest"],snap["canonical_digest"])
            self.assertEqual(len(list_snapshots(td,validated_only=True)),1)

    def test_identical_validated_data_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as td:
            first=self.save(td); second=self.save(td)
            self.assertEqual(first["snapshot_id"],second["snapshot_id"])
            self.assertEqual(len(list_snapshots(td,validated_only=True)),1)

    def test_changed_validated_data_creates_new_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            first=self.save(td)
            changed=self.canonical(); changed[0]["price"]=1010.0
            second=self.save(td,canonical=changed)
            self.assertNotEqual(first["snapshot_id"],second["snapshot_id"])
            self.assertEqual(len(list_snapshots(td,validated_only=True)),2)

    def test_invalid_attempt_cannot_replace_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            good=self.save(td)
            with self.assertRaises(ValueError): self.save(td,status="FAIL")
            history=list_snapshots(td,validated_only=True)
            self.assertEqual(len(history),1)
            self.assertEqual(history[0]["snapshot_id"],good["snapshot_id"])

    def test_batch_id_is_strictly_b1_to_b11(self):
        snap={"raw_batches":{str(i):f"B{i}" for i in range(1,12)}}
        self.assertEqual(get_snapshot_batch(snap,11),"B11")
        for bad in (0,12,-1,"x"):
            with self.assertRaises(ValueError): get_snapshot_batch(snap,bad)


if __name__=="__main__":
    unittest.main()
