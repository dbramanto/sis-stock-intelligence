import tempfile
import unittest
import numpy as np
import pandas as pd
from sis_core import eng
from snapshot_history import SnapshotStore

class RealShapeBoundaryReplay(unittest.TestCase):
    def test_stage1_dataframe_round_trip_with_real_runtime_types(self):
        base=pd.DataFrame([
            {"Symbol":"AAA","Volume":np.int64(1000000),"Volume MA 20":np.float64(800000),"RSI (14)":np.float64(55),"Previous RSI (14)":np.float64(53),"MACD (12,26)":np.float64(1.2),"Previous MACD (12,26)":np.float64(1),"Rank (RS 9m)":np.float64(70),"Rank (RS 6m)":np.float64(80),"Rank (RS 3m)":np.float64(90),"Optional":np.nan},
            {"Symbol":"BBB","Volume":np.int64(500000),"Volume MA 20":np.float64(0),"RSI (14)":pd.NA,"Previous RSI (14)":np.float32("nan"),"MACD (12,26)":np.float64("inf"),"Previous MACD (12,26)":np.float64(0),"Rank (RS 9m)":np.nan,"Rank (RS 6m)":np.nan,"Rank (RS 3m)":np.nan,"Optional":pd.NA},
        ])
        derived=eng(base)
        raw=["B1 REAL-SHAPE","B2 REAL-SHAPE","B3 REAL-SHAPE"]
        validation={"gate_state":"PASS","symbols":2,"conflicts":0,"partial_symbols":0,"schema_realigned_batches":[]}
        with tempfile.TemporaryDirectory() as td:
            store=SnapshotStore(td)
            ref=store.save_daily_snapshot(trading_date="2026-09-19",raw_batches=raw,normalized_batches=[base.copy(),base.copy(),base.copy()],merged_stage1=derived,validation=validation,source="REAL_SHAPE_REPLAY")
            payload=store.load_effective(ref.trading_date)
            self.assertEqual(raw,payload["raw_batches"])
            rows=payload["merged_stage1"]
            self.assertEqual(2,len(rows))
            self.assertIsNone(rows[0]["Optional"])
            self.assertIsNone(rows[1]["Optional"])
            self.assertIsNone(rows[1]["RSI (14)"])
            self.assertIsNone(rows[1]["MACD (12,26)"])
            self.assertEqual("INSUFFICIENT",rows[1]["RS Trajectory"])

    def test_snapshot_write_is_idempotent_after_real_shape_normalization(self):
        frame=eng(pd.DataFrame([{"Symbol":"AAA","Volume":np.int64(10),"Volume MA 20":np.float64(5),"RSI (14)":np.float32("nan"),"Previous RSI (14)":np.float64(50),"MACD (12,26)":np.float64(1),"Previous MACD (12,26)":np.float64(1),"Rank (RS 9m)":np.float64(70),"Rank (RS 6m)":np.float64(80),"Rank (RS 3m)":np.float64(90)}]))
        with tempfile.TemporaryDirectory() as td:
            store=SnapshotStore(td)
            kwargs=dict(trading_date="2026-09-19",raw_batches=["B1","B2","B3"],normalized_batches=[frame,frame,frame],merged_stage1=frame,validation={"gate_state":"PASS"})
            a=store.save_daily_snapshot(**kwargs); b=store.save_daily_snapshot(**kwargs)
            self.assertEqual(a.snapshot_id,b.snapshot_id)
            self.assertEqual(1,len(store.list_daily()))

if __name__=="__main__":
    unittest.main()
