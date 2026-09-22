from opportunity_funnel import build_opportunity_funnel


def _candidate(symbol, swing="READY", reasons=None, lt_status="PASS", dca="FAVORABLE", valuation="POSITIVE_MODERATE", o3="POSITIVE", risk="NEUTRAL"):
    return {
        "symbol": symbol,
        "synthesis": {
            "swing": {"analytical_status": "PASS", "quality": 80, "confidence": 80},
            "long_term": {"analytical_status": lt_status, "quality": 80, "confidence": 80},
            "shared": {"evidence_ledger": {"VALUATION": {"state": valuation}, "RISK": {"state": risk}}},
        },
        "swing_execution": {
            "execution_status": swing, "current_price": 1000,
            "entry_area": {"low": 950, "high": 1000}, "target_1": 1100, "target_2": 1200,
            "risk_boundary": 900, "reward_risk": {"target_1": 2.0, "target_2": 4.0},
            "reason_codes": reasons or [],
        },
        "longterm_outlook": {
            "status": "COMPLETE", "dca_context": dca,
            "outlook": {"1Y": {"state": "POSITIVE"}, "3Y": {"state": o3}, "5Y": {"state": "STABLE"}},
            "forward_drivers": [], "forward_risks": [],
        },
    }


def _stage3():
    cs = [_candidate("AAA"), _candidate("BBB", swing="WAIT", reasons=["AVOID_CHASING_EXTENDED_PRICE"], valuation="NEGATIVE_STRONG"), _candidate("CCC", swing="WAIT"), _candidate("DDD", swing="NOT_ATTRACTIVE", lt_status="REVIEW")]
    return {
        "candidates": cs,
        "ranking": {
            "swing": {"top": [{"rank": 1, "symbol": "AAA"}]},
            "long_term": {"top": [{"rank": 1, "symbol": "AAA"}, {"rank": 2, "symbol": "BBB"}, {"rank": 3, "symbol": "CCC"}]},
        },
    }


def test_top3_follows_existing_ranking_only():
    out = build_opportunity_funnel(_stage3(), top_n=3)
    assert [x["symbol"] for x in out["swing"]["top3"]] == ["AAA"]
    assert [x["symbol"] for x in out["long_term"]["top3"]] == ["AAA", "BBB", "CCC"]
    assert out["policy"] == "PRESENTATION_ONLY_NO_NEW_SCORE"


def test_simple_swing_language():
    out = build_opportunity_funnel(_stage3())
    rows = {x["symbol"]: x for x in out["swing"]["all"]}
    assert rows["AAA"]["action"] == "SIAP BELI JIKA HARGA SESUAI"
    assert rows["BBB"]["action"] == "TUNGGU HARGA"
    assert rows["CCC"]["action"] == "TUNGGU KONFIRMASI"
    assert rows["DDD"]["action"] == "JANGAN BELI DULU"


def test_longterm_language_and_price_assessment():
    out = build_opportunity_funnel(_stage3())
    rows = {x["symbol"]: x for x in out["long_term"]["all"]}
    assert rows["AAA"]["action"] == "LAYAK DIBELI"
    assert rows["AAA"]["price_assessment"] == "Menarik"
    assert rows["BBB"]["action"] == "BAGUS, TUNGGU HARGA"
    assert rows["BBB"]["price_assessment"] == "Mahal"
    assert rows["DDD"]["action"] == "BELUM LAYAK"


def test_all_stock_view_keeps_entire_universe():
    out = build_opportunity_funnel(_stage3())
    assert out["candidate_count"] == 4
    assert len(out["swing"]["all"]) == 4
    assert len(out["long_term"]["all"]) == 4


def test_invalid_input():
    assert build_opportunity_funnel(None)["status"] == "INVALID"
    assert build_opportunity_funnel({}, top_n=0)["status"] == "INVALID"


if __name__ == "__main__":
    test_top3_follows_existing_ranking_only()
    test_simple_swing_language()
    test_longterm_language_and_price_assessment()
    test_all_stock_view_keeps_entire_universe()
    test_invalid_input()
    print("PASS OPPORTUNITY FUNNEL RC1")
