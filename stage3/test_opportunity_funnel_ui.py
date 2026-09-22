from opportunity_funnel_ui import _action_icon, _entry_text, _fmt_price, _plain_reason


def test_price_format_is_indonesian_user_friendly():
    assert _fmt_price(3140) == "Rp3.140"
    assert _fmt_price(None) == "—"


def test_entry_text_uses_existing_engine_range_only():
    assert _entry_text({"entry_area": {"low": 3100, "high": 3170}}) == "Rp3.100 – Rp3.170"
    assert _entry_text({"entry_area": None}) == "Belum tersedia"


def test_action_icons_are_consistent():
    assert _action_icon("SIAP BELI JIKA HARGA SESUAI") == "🟢"
    assert _action_icon("LAYAK DIBELI") == "🟢"
    assert _action_icon("TUNGGU HARGA") == "🟡"
    assert _action_icon("BAGUS, TUNGGU HARGA") == "🟡"
    assert _action_icon("BELUM LAYAK") == "🔴"


def test_plain_language_reason_is_present_for_every_user_action():
    actions = [
        "SIAP BELI JIKA HARGA SESUAI", "TUNGGU HARGA", "TUNGGU KONFIRMASI", "JANGAN BELI DULU",
        "LAYAK DIBELI", "BAGUS, TUNGGU HARGA", "PERTIMBANGKAN / TUNGGU", "BELUM LAYAK",
    ]
    for action in actions:
        reason = _plain_reason(action)
        assert isinstance(reason, str)
        assert len(reason) >= 20


if __name__ == "__main__":
    test_price_format_is_indonesian_user_friendly()
    test_entry_text_uses_existing_engine_range_only()
    test_action_icons_are_consistent()
    test_plain_language_reason_is_present_for_every_user_action()
    print("PASS OPPORTUNITY FUNNEL UI RC1")
