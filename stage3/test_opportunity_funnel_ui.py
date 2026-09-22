from opportunity_funnel_ui import _action_icon, _entry_text, _fmt_price, _plain_reason


def test_price_format_is_indonesian_user_friendly():
    assert _fmt_price(3140) == "3.140"
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


def test_swing_plain_language_wording_is_actionable():
    assert _plain_reason("SIAP BELI JIKA HARGA SESUAI") == "Syarat entry sudah terpenuhi. Gunakan area beli dan batas risiko yang ditampilkan."
    assert _plain_reason("TUNGGU HARGA") == "Saham masih menarik, tetapi harga belum berada di area beli yang ideal."
    assert _plain_reason("TUNGGU KONFIRMASI") == "Harga bisa menarik, tetapi sinyal teknikal belum cukup kuat untuk entry."
    assert _plain_reason("JANGAN BELI DULU") == "Kondisi saat ini belum memenuhi syarat SIS untuk membuka posisi Swing."

def test_price_format_has_no_currency_symbol():
    assert _fmt_price(1250) == "1.250"
    assert _fmt_price(1250.5) == "1.250,50"
    assert "Rp" not in _fmt_price(1250)


if __name__ == "__main__":
    test_price_format_is_indonesian_user_friendly()
    test_price_format_has_no_currency_symbol()
    test_entry_text_uses_existing_engine_range_only()
    test_action_icons_are_consistent()
    test_plain_language_reason_is_present_for_every_user_action()
    test_swing_plain_language_wording_is_actionable()
    print("PASS OPPORTUNITY FUNNEL UI RC1")
