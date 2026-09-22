from __future__ import annotations

"""User-facing Streamlit presentation for SIS Opportunity Funnel.

Presentation only. Ranking, entry area, targets, risk boundary, valuation state,
and horizon decisions must already exist in the frozen Stage 3 output.
"""

from opportunity_funnel import build_opportunity_funnel


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


def _top3_card(st, row, horizon):
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


def render_opportunity_funnel(st, stage3, on_symbol=None):
    """Render Top 3 for each horizon and preserve access to the full universe."""
    funnel = build_opportunity_funnel(stage3, top_n=3)
    if funnel.get("status") != "COMPLETE":
        st.error("Hasil SIS belum dapat ditampilkan.")
        return funnel

    st.subheader("Peluang Utama SIS")
    st.caption(f"{funnel.get('candidate_count', 0)} saham dianalisis. Top 3 membantu fokus; seluruh saham tetap dapat dilihat.")
    st.info("Rencana Swing paling baik disiapkan setelah market tutup. Area beli, target, dan batas risiko adalah rencana untuk sesi market berikutnya berdasarkan data analisis yang digunakan.")
    swing_tab, long_tab = st.tabs(["Swing", "Jangka Panjang"])

    with swing_tab:
        st.caption("Apa artinya untuk besok? Jika belum ada saham berstatus “Siap Beli”, jangan memaksakan entry. Pantau saham berstatus “Tunggu Harga” dan “Tunggu Konfirmasi”.")
        top = funnel["swing"]["top3"]
        if top:
            cols = st.columns(len(top))
            for col, row in zip(cols, top):
                with col:
                    _top3_card(st, row, "swing")
                    if on_symbol and st.button(row.get("symbol"), key=f"funnel_swing_{row.get('symbol')}", help="Klik kode saham untuk melihat analisis lengkap", use_container_width=True):
                        on_symbol(row.get("symbol"), "swing")
        else:
            st.info("Belum ada peluang Swing yang siap dieksekusi. SIS menyarankan menunggu sampai ada saham yang memenuhi syarat entry. Seluruh saham tetap dapat dilihat di bagian “Lihat semua saham”.")
        with st.expander("Lihat semua saham", expanded=False):
            _render_all(st, funnel["swing"]["all"], "swing", on_symbol)

    with long_tab:
        top = funnel["long_term"]["top3"]
        if top:
            cols = st.columns(len(top))
            for col, row in zip(cols, top):
                with col:
                    _top3_card(st, row, "long_term")
                    if on_symbol and st.button(row.get("symbol"), key=f"funnel_long_{row.get('symbol')}", help="Klik kode saham untuk melihat analisis lengkap", use_container_width=True):
                        on_symbol(row.get("symbol"), "long_term")
        else:
            st.info("Belum ada saham yang memenuhi kriteria ranking Jangka Panjang pada data analisis ini.")
        with st.expander("Lihat semua saham", expanded=False):
            _render_all(st, funnel["long_term"]["all"], "long_term", on_symbol)

    st.caption("Top 3 mengikuti ranking engine SIS. Funnel tidak membuat skor baru dan tidak mengubah keputusan analitis Stage 3.")
    return funnel
