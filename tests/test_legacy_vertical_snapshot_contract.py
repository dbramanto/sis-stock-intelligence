import json
import unittest
from pathlib import Path
from stage1.clipboard import parse_clipboard_text
from stage1.pipeline import run_stage1

class LegacyVerticalSnapshotContractTest(unittest.TestCase):
    def test_missing_volume_header_is_repaired_by_verified_batch_layout(self):
        fixture = Path(__file__).resolve().parent / "fixtures" / "legacy_153711.json"
        if not fixture.exists():
            self.skipTest("legacy fixture not packaged")
        raw = json.loads(fixture.read_text(encoding="utf-8"))["raw_batches"]
        batches = {}
        for i in range(1, 12):
            df, issues = parse_clipboard_text(raw[str(i)], batch_id=i)
            self.assertEqual([], issues, (i, issues))
            batches[i] = df
        result = run_stage1(batches, expected_total=15, filter_fingerprint="S0-6FILTER")
        self.assertEqual("PASS", result["status"], result["issues"])
        self.assertEqual(15, len(result["canonical"]))

if __name__ == "__main__": unittest.main()
