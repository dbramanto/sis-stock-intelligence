import json
import tempfile
import unittest
from datetime import datetime, timezone
from stage1.history import save_validated_snapshot, update_snapshot_analysis, list_snapshots, load_snapshot, get_snapshot_batch

class TestD1ValidatedSnapshot(unittest.TestCase):
    def raw(self,tag="A"):return {i:f"B{i}\nvalid raw {tag}" for i in range(1,12)}
    def canonical(self):return [{"symbol":"ANTM","price":1000.0},{"symbol":"PGEO","price":1200.0}]
    def meta(self,fp="S0-6FILTER"):return {"expected_total":2,"filter_fingerprint":fp,"analysis_status":"COMPLETE"}
    def save(self,td,canonical=None,status="PASS",metadata=None,raw=None):
        return save_validated_snapshot(raw or self.raw(),self.canonical() if canonical is None else canonical,status,base_dir=td,metadata=self.meta() if metadata is None else metadata)
    def test_rejects_incomplete_b1_b11(self):
        raw=self.raw();raw[11]=""
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_REQUIRES_B1_B11"):save_validated_snapshot(raw,self.canonical(),"PASS",base_dir=td,metadata=self.meta())
            self.assertEqual(list_snapshots(td),[])
    def test_rejects_nonpass_validation(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_REQUIRES_VALIDATED_STAGE1"):self.save(td,status="FAIL")
            self.assertEqual(list_snapshots(td),[])
    def test_stage1_pass_autosaves_before_analysis_complete(self):
        with tempfile.TemporaryDirectory() as td:
            m=self.meta();m["analysis_status"]="PENDING"
            x=self.save(td,metadata=m)
            self.assertEqual(x["status"],"VALIDATED")
            self.assertEqual(load_snapshot(x["snapshot_id"],td)["metadata"]["analysis_status"],"PENDING")
    def test_analysis_status_updates_same_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            m=self.meta();m["analysis_status"]="PENDING"
            x=self.save(td,metadata=m);sid=x["snapshot_id"]
            y=update_snapshot_analysis(sid,"S3_BLOCKED",base_dir=td)
            self.assertEqual(y["snapshot_id"],sid);self.assertEqual(y["metadata"]["analysis_status"],"S3_BLOCKED")
            z=update_snapshot_analysis(sid,"COMPLETE",base_dir=td,metadata_updates={"stage3_status":"COMPLETE"})
            self.assertEqual(z["snapshot_id"],sid);self.assertEqual(z["metadata"]["stage3_status"],"COMPLETE")
    def test_rejects_empty_canonical(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_EMPTY_CANONICAL"):self.save(td,canonical=[])
    def test_rejects_missing_or_duplicate_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"HISTORY_CANONICAL_MISSING_SYMBOL"):self.save(td,canonical=[{"symbol":"","price":1},{"symbol":"PGEO","price":2}])
            with self.assertRaisesRegex(ValueError,"HISTORY_CANONICAL_DUPLICATE_SYMBOL"):self.save(td,canonical=[{"symbol":"ANTM"},{"symbol":"antm"}])
    def test_rejects_expected_total_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            m=self.meta();m["expected_total"]=3
            with self.assertRaisesRegex(ValueError,"HISTORY_CANONICAL_COUNT_MISMATCH"):self.save(td,metadata=m)
    def test_valid_snapshot_is_official(self):
        with tempfile.TemporaryDirectory() as td:
            snap=save_validated_snapshot(self.raw(),self.canonical(),"PASS",base_dir=td,now=datetime(2026,9,23,9,0,tzinfo=timezone.utc),metadata=self.meta())
            self.assertEqual(snap["status"],"VALIDATED");self.assertEqual(len(snap["canonical_digest"]),64);self.assertEqual(len(snap["context_digest"]),64);self.assertEqual(load_snapshot(snap["snapshot_id"],td)["snapshot_id"],snap["snapshot_id"])
    def test_identical_canonical_and_context_is_deduplicated_even_if_raw_differs(self):
        with tempfile.TemporaryDirectory() as td:
            a=self.save(td,raw=self.raw("A"));b=self.save(td,raw=self.raw("B"));self.assertEqual(a["snapshot_id"],b["snapshot_id"]);self.assertEqual(len(list_snapshots(td,validated_only=True)),1)
    def test_row_order_does_not_create_false_new_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            a=self.save(td);rows=list(reversed(self.canonical()));b=self.save(td,canonical=rows);self.assertEqual(a["snapshot_id"],b["snapshot_id"])
    def test_changed_context_creates_new_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            a=self.save(td,metadata=self.meta("FILTER-A"));b=self.save(td,metadata=self.meta("FILTER-B"));self.assertNotEqual(a["snapshot_id"],b["snapshot_id"])
    def test_changed_validated_data_creates_new_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            a=self.save(td);changed=self.canonical();changed[0]["price"]=1010.0;b=self.save(td,canonical=changed);self.assertNotEqual(a["snapshot_id"],b["snapshot_id"])
    def test_invalid_attempt_cannot_replace_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            good=self.save(td)
            with self.assertRaises(ValueError):self.save(td,status="FAIL")
            h=list_snapshots(td,validated_only=True);self.assertEqual(len(h),1);self.assertEqual(h[0]["snapshot_id"],good["snapshot_id"])
    def test_tampered_v5_validated_snapshot_is_rejected_and_hidden(self):
        with tempfile.TemporaryDirectory() as td:
            x=self.save(td);p=__import__('pathlib').Path(td)/(x["snapshot_id"]+".json");d=json.loads(p.read_text());d.pop("canonical_digest");p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,"INVALID_VALIDATED_SNAPSHOT"):load_snapshot(x["snapshot_id"],td)
            self.assertEqual(list_snapshots(td,validated_only=True),[])
    def test_batch_id_is_strictly_b1_to_b11(self):
        snap={"raw_batches":{str(i):f"B{i}" for i in range(1,12)}};self.assertEqual(get_snapshot_batch(snap,11),"B11")
        for bad in (0,12,-1,"x"):
            with self.assertRaises(ValueError):get_snapshot_batch(snap,bad)
if __name__=="__main__":unittest.main()
