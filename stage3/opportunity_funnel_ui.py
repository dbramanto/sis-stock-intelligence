from __future__ import annotations

"""Streamlit presentation for SIS Opportunity Funnel.

This module is deliberately presentation-only. Analytical decisions, ranking,
entry areas, targets, and risk boundaries must already exist in Stage 3 output.
"""

from opportunity_funnel import build_opportunity_funnel


def _fmt_price(value):
    if value is None:
        return "—"
    try:
        number = float(value)
        return f"Rp{number:,.0f}".replace(",", ".")
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
        st.write(f"Harga sekarang: **{_fmt_price(row.get('current_price'))}**")
        st.caption(f"Penilaian harga: {row.get('price_assessment') or 'Belum dapat dinilai'}")


def _render_all(st, rows, horizon):
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
            "Saran SIS": f"{_action_icon(r.get('action'))} {str(r.get('action') or '').title()}",
            "Harga": _fmt_price(r.get("current_price")),
            "Penilaian harga": r.get("price_assessment") or "Belum dapat dinilai",
        } for r in filtered]
    st.dataframe(table, use_container_width=True, hide_index=True)


def render_opportunity_funnel(st, stage3, on_symbol=None):
    """Render Top 3 Swing/Long-Term plus expandable complete universe.

    `on_symbol` is an optional callback used by the host app to open the existing
    detailed SIS intelligence for a selected symbol. No analytical calculation is
    performed here.
    """
    funnel = build_opportunity_funnel(stage3, top_n=3)
    if funnel.get("status") != "COMPLETE":
        st.error("Hasil SIS belum dapat ditampilkan.")
        return funnel

    st.subheader("Peluang Utama SIS")
    st.caption(f"{funnel.get('candidate_count', 0)} saham dianalisis. Top 3 ditampilkan untuk memudahkan fokus; seluruh saham tetap dapat dilihat.")
    swing_tab, long_tab = st.tabs(["Swing", "Jangka Panjang"])

    with swing_tab:
        top = funnel["swing"]["top3"]
        if top:
            cols = st.columns(len(top))
            for col, row in zip(cols, top):
                with col:
                    _top3_card(st, row, "swing")
                    if on_symbol and st.button(f"Lihat {row.get('symbol')}", key=f"funnel_swing_{row.get('symbol')}", use_container_width=True):
                        on_symbol(row.get("symbol"), "swing")
        else:
            st.info("Belum ada saham yang masuk Top 3 Swing pada snapshot ini.")
        with st.expander("Lihat semua saham", expanded=False):
            _render_all(st, funnel["swing"]["all"], "swing")

    with long_tab:
        top = funnel["long_term"]["top3"]
        if top:
            cols = st.columns(len(top))
            for col, row in zip(cols, top):
                with col:
                    _top3_card(st, row, "long_term")
                    if on_symbol and st.button(f"Lihat {row.get('symbol')}", key=f"funnel_long_{row.get('symbol')}", use_container_width=True):
                        on_symbol(row.get("symbol"), "long_term")
        else:
            st.info("Belum ada saham yang masuk Top 3 Jangka Panjang pada snapshot ini.")
        with st.expander("Lihat semua saham", expanded=False):
            _render_all(st, funnel["long_term"]["all"], "long_term")

    st.caption("Top 3 mengikuti ranking engine SIS. Funnel tidak membuat skor baru dan tidak mengubah keputusan analitis Stage 3.")
    return funnel
