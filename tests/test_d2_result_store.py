import tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from stage3.result_store import save_analysis_result, load_analysis_result, result_exists

class TestD2ResultStore(unittest.TestCase):
    def sample(self):
        return {"status":"COMPLETE","candidate_count":1,"blocked":[],"candidates":[{"symbol":"AAA"}],"ranking":{"swing":{"top":[]},"long_term":{"top":[]}},"recommendation":None}
    def test_roundtrip_and_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            s=self.sample(); a=save_analysis_result("snap_1",s,"2026-09-23",td,datetime(2026,9,23,tzinfo=timezone.utc)); b=save_analysis_result("snap_1",s,"2026-09-23",td)
            self.assertEqual(a["stage3_digest"],b["stage3_digest"]); self.assertTrue(result_exists("snap_1",td)); self.assertEqual(load_analysis_result("snap_1",td)["stage3"],s)
    def test_reject_noncomplete_and_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): save_analysis_result("snap_1",{"status":"BLOCKED"},"2026-09-23",td)
            save_analysis_result("snap_1",self.sample(),"2026-09-23",td)
            x=self.sample(); x["candidate_count"]=2
            with self.assertRaises(ValueError): save_analysis_result("snap_1",x,"2026-09-23",td)
    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): load_analysis_result("../x",td)

if __name__ == '__main__': unittest.main()
