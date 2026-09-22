import unittest
import pandas as pd
from stage2.runner import run_stage2


def row(symbol="AAA"):
    return {"symbol": symbol, "Price": 100, "Price MA20": 95, "Price MA50": 90}


class TestStage2Runner(unittest.TestCase):
    def test_empty_is_valid(self):
        r=run_stage2(pd.DataFrame(columns=["symbol"]))
        self.assertEqual(r.status,"PASS"); self.assertEqual(r.packages,[])
    def test_missing_symbol_blocks(self):
        r=run_stage2(pd.DataFrame([{"Price":1}]))
        self.assertEqual(r.status,"BLOCKED")
    def test_duplicate_blocks(self):
        r=run_stage2(pd.DataFrame([row("AAA"),row("aaa")]))
        self.assertEqual(r.status,"BLOCKED")
    def test_one_symbol_two_independent_horizons(self):
        r=run_stage2(pd.DataFrame([row()]))
        self.assertEqual(r.status,"PASS"); self.assertEqual(len(r.packages),1)
        self.assertEqual(r.packages[0]["swing"]["horizon"],"SWING")
        self.assertEqual(r.packages[0]["long_term"]["horizon"],"LONG_TERM")
    def test_no_decision_fields(self):
        r=run_stage2(pd.DataFrame([row()]))
        text=str(r.packages).lower()
        for k in ("recommendation","entry","take profit","stop loss","rank","score"):
            self.assertNotIn(k,text)

if __name__ == "__main__": unittest.main()
