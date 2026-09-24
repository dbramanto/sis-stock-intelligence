import io, os, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from stage1.history import save_validated_snapshot, list_snapshots, load_snapshot
from stage3.result_store import save_analysis_result, load_analysis_result, result_exists
from storage_adapter import JsonStore, StorageUnavailable

CLOUD_ENV={"SIS_STORAGE_BACKEND":"cloud","SIS_CLOUD_STORAGE_URL":"https://example.r2.cloudflarestorage.com","SIS_CLOUD_STORAGE_ACCESS_KEY":"access","SIS_CLOUD_STORAGE_SECRET_KEY":"secret","SIS_CLOUD_STORAGE_BUCKET":"sis-test","SIS_CLOUD_STORAGE_PREFIX":"sis"}

class PersistenceIntegrationTests(unittest.TestCase):
    def raw(self):return {i:f"B{i}\nvalid raw" for i in range(1,12)}
    def canonical(self):return [{"symbol":"AAA"}]
    def stage3(self):return {"status":"COMPLETE","candidate_count":1,"blocked":[],"candidates":[{"symbol":"AAA"}],"ranking":{"swing":{"top":[]},"long_term":{"top":[]}}}

    def test_history_roundtrip_via_filesystem_adapter(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{"SIS_DATA_DIR":td},clear=False):
            snap=save_validated_snapshot(self.raw(),self.canonical(),"PASS",metadata={"expected_total":1,"filter_fingerprint":"X"})
            self.assertTrue((Path(td)/"input_history"/f"{snap['snapshot_id']}.json").exists())
            self.assertEqual(load_snapshot(snap["snapshot_id"])["snapshot_id"],snap["snapshot_id"])
            self.assertEqual(list_snapshots(validated_only=True)[0]["snapshot_id"],snap["snapshot_id"])

    def test_result_roundtrip_via_filesystem_adapter(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{"SIS_DATA_DIR":td},clear=False):
            save_analysis_result("snap_1",self.stage3(),"2026-09-24")
            self.assertTrue((Path(td)/"analysis_results"/"snap_1.json").exists())
            self.assertTrue(result_exists("snap_1")); self.assertEqual(load_analysis_result("snap_1")["snapshot_id"],"snap_1")

    def test_cloud_mode_fails_closed_for_history(self):
        with patch.dict(os.environ,{"SIS_STORAGE_BACKEND":"cloud"},clear=True):
            with self.assertRaises(StorageUnavailable):list_snapshots(validated_only=True)

    def test_cloud_mode_fails_closed_for_results(self):
        with patch.dict(os.environ,{"SIS_STORAGE_BACKEND":"cloud"},clear=True):
            with self.assertRaises(StorageUnavailable):result_exists("snap_1")

    def _client(self):
        objects={}; client=Mock()
        client.put_object.side_effect=lambda **kw: objects.__setitem__(kw["Key"],kw["Body"]) or {}
        def head(**kw):
            if kw["Key"] not in objects:
                e=RuntimeError("not found"); e.response={"ResponseMetadata":{"HTTPStatusCode":404},"Error":{"Code":"404"}}; raise e
            return {}
        client.head_object.side_effect=head
        client.get_object.side_effect=lambda **kw:{"Body":io.BytesIO(objects[kw["Key"]])}
        client.list_objects_v2.side_effect=lambda **kw:{"Contents":[{"Key":k} for k in sorted(objects) if k.startswith(kw["Prefix"])],"IsTruncated":False}
        return client,objects

    def test_cloud_json_store_roundtrip_and_prefix(self):
        client,objects=self._client()
        with patch.dict(os.environ,CLOUD_ENV,clear=True):
            store=JsonStore("/ignored"); store._client=client
            store.put("input_history","snap_1",{"snapshot_id":"snap_1"})
            self.assertTrue(store.exists("input_history","snap_1"))
            self.assertEqual(store.get("input_history","snap_1")["snapshot_id"],"snap_1")
            self.assertEqual(store.list("input_history")[0]["snapshot_id"],"snap_1")
            self.assertIn("sis/input_history/snap_1.json",objects)

    def test_cloud_put_no_overwrite(self):
        client=Mock(); client.head_object.return_value={}
        with patch.dict(os.environ,CLOUD_ENV,clear=True):
            store=JsonStore("/ignored"); store._client=client
            with self.assertRaises(FileExistsError):store.put("analysis_results","snap_1",{"x":1},overwrite=False)
            client.put_object.assert_not_called()

    def test_cloud_list_pagination(self):
        client=Mock(); client.list_objects_v2.side_effect=[{"Contents":[{"Key":"sis/input_history/b.json"}],"IsTruncated":True,"NextContinuationToken":"next"},{"Contents":[{"Key":"sis/input_history/a.json"}],"IsTruncated":False}]
        payloads={"sis/input_history/a.json":b'{"snapshot_id":"a"}',"sis/input_history/b.json":b'{"snapshot_id":"b"}'}
        client.get_object.side_effect=lambda **kw:{"Body":io.BytesIO(payloads[kw["Key"]])}
        with patch.dict(os.environ,CLOUD_ENV,clear=True):
            store=JsonStore("/ignored"); store._client=client
            self.assertEqual([x["snapshot_id"] for x in store.list("input_history")],["b","a"]); self.assertEqual(client.list_objects_v2.call_count,2)

if __name__=="__main__":unittest.main()
