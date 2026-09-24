from __future__ import annotations

"""User-facing Streamlit presentation for SIS Opportunity Funnel.

Presentation only. Ranking, entry area, targets, risk boundary, valuation state,
and horizon decisions must already exist in the frozen Stage 3 output.
"""

from opportunity_funnel import build_opportunity_funnel, _swing_action, _longterm_action, _longterm_row


def _fmt_price(value):
    if value is None:
        return "—"
    try:
        number = float(value)
        if number.is_integer():
            return f"{number:,.0f}".replace(",", ".")
        return f"{number:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return str(value)


def _entry_text(row):
    area = row.get("entry_area") or {}
    low, high = area.get("low"), area.get("high")
    if low is None or high is None:
        return "Belum tersedia"
    return f"{_fmt_price(low)} – {_fmt_price(high)}"


def _action_icon(action):
    if action in {"SIAP BELI JIKA HARGA SESUAI", "LAYAK DIBELI"}:
        return "🟢"
    if action in {"TUNGGU HARGA", "TUNGGU KONFIRMASI", "BAGUS, TUNGGU HARGA", "PERTIMBANGKAN / TUNGGU"}:
        return "🟡"
    return "🔴"


def _plain_reason(action):
    return {
        "SIAP BELI JIKA HARGA SESUAI": "Syarat entry sudah terpenuhi. Gunakan area beli dan batas risiko yang ditampilkan.",
        "TUNGGU HARGA": "Saham masih menarik, tetapi harga belum berada di area beli yang ideal.",
        "TUNGGU KONFIRMASI": "Harga bisa menarik, tetapi sinyal teknikal belum cukup kuat untuk entry.",
        "JANGAN BELI DULU": "Kondisi saat ini belum memenuhi syarat SIS untuk membuka posisi Swing.",
        "LAYAK DIBELI": "Prospek jangka panjang dan konteks akumulasi masih mendukung untuk dipertimbangkan.",
        "BAGUS, TUNGGU HARGA": "Prospek dapat tetap baik, tetapi harga saat ini belum cukup menarik. Tunggu harga yang lebih baik.",
        "PERTIMBANGKAN / TUNGGU": "Kandidat masih layak diperhatikan, tetapi konteks akumulasi dan risiko belum cukup kuat untuk meningkatkan keputusan menjadi Layak Dibeli.",
        "BELUM LAYAK": "Kombinasi prospek, valuasi, atau risiko saat ini belum memenuhi syarat SIS untuk pembelian jangka panjang.",
    }.get(action, "Buka analisis lengkap untuk melihat dasar penilaian SIS.")


def _top3_card(st, row, horizon, on_symbol=None):
    rank = row.get("rank") or "—"
    symbol = row.get("symbol") or "—"
    action = row.get("action") or "—"
    st.markdown(f"### #{rank} · {symbol}")
    st.markdown(f"{_action_icon(action)} **{action.title()}**")
    if horizon == "swing":
        st.write(f"Area beli: **{_entry_text(row)}**")
        st.caption(f"Target 1 {_fmt_price(row.get('target_1'))} · Target 2 {_fmt_price(row.get('target_2'))} · Batas risiko {_fmt_price(row.get('risk_boundary'))}")
    else:
        st.write(f"Prospek jangka panjang: **{row.get('prospect_summary') or 'Belum cukup data'}**")
        st.write(f"Kualitas bisnis: **{row.get('business_quality') or 'Belum cukup data'}**")
        st.write(f"Risiko: **{row.get('risk_summary') or 'Belum cukup data'}**")
        st.write(f"Konteks akumulasi: **{row.get('accumulation_context') or 'Belum cukup data'}**")
    st.caption(_plain_reason(action))
    if on_symbol and st.button("Buka rincian", key=f"top3_{horizon}_{symbol}", use_container_width=True):
        on_symbol(symbol, horizon)


def _render_all(st, rows, horizon, on_symbol=None):
    st.markdown("#### Semua saham")
    query = st.text_input("Cari kode saham", key=f"funnel_search_{horizon}").strip().upper()
    filtered = [r for r in rows if not query or query in str(r.get("symbol", "")).upper()]
    if horizon == "swing":
        table = [{
            "Saham": r.get("symbol"),
            "Saran SIS": f"{_action_icon(r.get('action'))} {str(r.get('action') or '').title()}",
            "Harga": _fmt_price(r.get("current_price")),
            "Area beli": _entry_text(r),
            "Target 1": _fmt_price(r.get("target_1")),
            "Batas risiko": _fmt_price(r.get("risk_boundary")),
        } for r in filtered]
    else:
        table = [{
            "Saham": r.get("symbol"),
            "Prospek jangka panjang": r.get("prospect_summary") or "Belum cukup data",
            "Kualitas bisnis": r.get("business_quality") or "Belum cukup data",
            "Risiko": r.get("risk_summary") or "Belum cukup data",
            "Konteks akumulasi": r.get("accumulation_context") or "Belum cukup data",
            "Saran SIS": f"{_action_icon(r.get('action'))} {str(r.get('action') or '').title()}",
        } for r in filtered]
    st.dataframe(table, use_container_width=True, hide_index=True)
    if on_symbol and filtered:
        symbols = [r.get("symbol") for r in filtered if r.get("symbol")]
        selected = st.selectbox("Pilih saham untuk melihat rincian", symbols, key=f"funnel_all_detail_{horizon}")
        if st.button(f"Lihat rincian {selected}", key=f"funnel_all_open_{horizon}", use_container_width=True):
            on_symbol(selected, horizon)


def _candidate(stage3, symbol):
    wanted = str(symbol or "").strip().upper()
    for row in (stage3.get("candidates") or []):
        if str((row or {}).get("symbol") or "").strip().upper() == wanted:
            return row
    return None


def _reason_text(code):
    return {
        "AVOID_CHASING_EXTENDED_PRICE": "Harga sudah terlalu jauh dari area referensi; hindari mengejar harga.",
        "CURRENT_RANGE_EXHAUSTED": "Pergerakan harian sudah banyak terpakai; ruang entry baru lebih terbatas.",
        "TREND_NOT_BULL": "Tren belum memenuhi syarat bullish SIS.",
        "EXECUTION_CONFIRMATION_WEAK": "Konfirmasi momentum/partisipasi belum cukup kuat.",
        "REWARD_RISK_BELOW_MINIMUM": "Perbandingan potensi hasil terhadap risiko belum memenuhi batas SIS.",
        "NO_DEFENSIBLE_RISK_BOUNDARY": "Batas risiko yang layak belum dapat ditentukan dari data.",
        "RR_NOT_COMPUTABLE": "Reward/risk belum dapat dihitung dengan aman.",
        "TECHNICAL_DATA_NOT_FRESH": "Data teknikal belum cukup mutakhir untuk eksekusi.",
        "INSUFFICIENT_INTERNAL_EXECUTION_EVIDENCE": "Bukti internal belum cukup untuk menyusun rencana entry.",
    }.get(str(code), str(code).replace("_", " ").title())


def render_stock_detail(st, stage3, symbol, horizon="swing"):
    """Render evidence already present in frozen Stage 3; no new score/decision."""
    c = _candidate(stage3, symbol)
    if not c:
        st.warning("Rincian saham tidak ditemukan pada hasil analisis ini.")
        return
    sw = (c.get("swing_execution") or {})
    lt = (c.get("longterm_outlook") or {})
    syn = (c.get("synthesis") or {})
    st.markdown("---")
    st.subheader(f"Rincian {str(symbol).upper()}")
    swing_tab, long_tab = st.tabs(["Swing", "Jangka Panjang"])
    with swing_tab:
        action = _swing_action(c)
        st.markdown("**Saran SIS**")
        st.markdown(f"### {_action_icon(action)} {action.title()}")
        a,b,c1,d = st.columns(4)
        a.metric("Harga analisis", _fmt_price(sw.get("current_price")))
        b.metric("Area beli", _entry_text(_swing_row_for_detail(sw)))
        c1.metric("Target 1", _fmt_price(sw.get("target_1")))
        d.metric("Batas risiko", _fmt_price(sw.get("risk_boundary")))
        st.write(_plain_reason(action))
        st.markdown("**Mengapa?**")
        reasons = list(sw.get("reason_codes") or [])
        if reasons:
            for code in reasons:
                st.write("• " + _reason_text(code))
        else:
            st.write("• Tidak ada penghambat utama yang tercatat pada hasil analisis Swing.")
        rr = sw.get("reward_risk") or {}
        st.caption(f"Target 2: {_fmt_price(sw.get('target_2'))} · Reward/Risk T1: {rr.get('target_1') if rr.get('target_1') is not None else '—'} · Reward/Risk T2: {rr.get('target_2') if rr.get('target_2') is not None else '—'}")
    with long_tab:
        action = _longterm_action(c)
        st.markdown("**Saran SIS**")
        st.markdown(f"### {_action_icon(action)} {action.title()}")
        row = _longterm_row_for_detail(c)
        a,b,c1,d = st.columns(4)
        a.metric("Valuasi", row["price_assessment"])
        b.metric("Prospek", row["prospect_summary"])
        c1.metric("Kualitas bisnis", row["business_quality"])
        d.metric("Risiko", row["risk_summary"])
        st.write(_plain_reason(action))
        st.markdown("**Mengapa?**")
        st.write(f"Prospek jangka panjang: {row['prospect_summary']}. Kualitas bisnis: {row['business_quality']}. Valuasi: {row['price_assessment']}. Risiko: {row['risk_summary']}. Konteks akumulasi: {row['accumulation_context']}.")
        outlook = lt.get("outlook") or {}
        cols = st.columns(3)
        for col, period in zip(cols, ("1Y","3Y","5Y")):
            item = outlook.get(period) or {}
            col.metric(f"Outlook {period}", item.get("state") or "—")
            if item.get("confidence") is not None:
                col.caption(f"Confidence: {item.get('confidence')}")
        drivers = list(lt.get("forward_drivers") or [])
        risks = list(lt.get("forward_risks") or [])
        if drivers:
            st.markdown("**Pendorong yang tercatat**")
            st.write(" · ".join(str(x).replace("_", " ").title() for x in drivers))
        if risks:
            st.markdown("**Risiko yang tercatat**")
            st.write(" · ".join(str(x).replace("_", " ").title() for x in risks))


def _swing_row_for_detail(sw):
    return {"entry_area": sw.get("entry_area")}


def _longterm_row_for_detail(candidate):
    return _longterm_row(candidate)

def render_opportunity_funnel(st, stage3, on_symbol=None):
    """Render Top 3 for each horizon and preserve access to the full universe."""
    funnel = build_opportunity_funnel(stage3, top_n=3)
    if funnel.get("status") != "COMPLETE":
        st.error("Hasil SIS belum dapat ditampilkan.")
        return funnel

    st.subheader("Peluang Utama SIS")
    st.caption(f"{funnel.get('candidate_count', 0)} saham dianalisis. Top 3 membantu fokus; seluruh saham tetap dapat dilihat.")
    st.info("Rencana Swing paling baik disiapkan setelah market tutup. Area beli, target, dan batas risiko adalah rencana untuk sesi market berikutnya berdasarkan data analisis yang digunakan.")
    with st.expander("Lihat semua saham", expanded=False):
        all_swing_tab, all_long_tab = st.tabs(["Swing", "Jangka Panjang"])
        with all_swing_tab:
            _render_all(st, funnel["swing"]["all"], "swing", on_symbol)
        with all_long_tab:
            _render_all(st, funnel["long_term"]["all"], "long_term", on_symbol)

    swing_tab, long_tab = st.tabs(["Swing", "Jangka Panjang"])

    with swing_tab:
        st.caption("Apa artinya untuk besok? Jika belum ada saham berstatus “Siap Beli”, jangan memaksakan entry. Pantau saham berstatus “Tunggu Harga” dan “Tunggu Konfirmasi”.")
        top = funnel["swing"]["top3"]
        if top:
            cols = st.columns(len(top))
            for col, row in zip(cols, top):
                with col:
                    _top3_card(st, row, "swing", on_symbol)
        else:
            st.info("Belum ada peluang Swing yang siap dieksekusi. SIS menyarankan menunggu sampai ada saham yang memenuhi syarat entry. Seluruh saham tetap dapat dilihat di bagian “Lihat semua saham”.")

    with long_tab:
        top = funnel["long_term"]["top3"]
        if top:
            cols = st.columns(len(top))
            for col, row in zip(cols, top):
                with col:
                    _top3_card(st, row, "long_term", on_symbol)
        else:
            st.info("Belum ada saham yang memenuhi kriteria ranking Jangka Panjang pada data analisis ini.")

    st.caption("Top 3 mengikuti ranking engine SIS. Funnel tidak membuat skor baru dan tidak mengubah keputusan analitis Stage 3.")
    return funnel
