from pathlib import Path

p = Path("app.py")
s = p.read_text(encoding="utf-8")

import_old = "from stage3.stage3_e2e_runner import run_stage3_universe\n"
import_new = import_old + "from stage3.opportunity_funnel_ui import render_opportunity_funnel\n"
if "from stage3.opportunity_funnel_ui import render_opportunity_funnel" not in s:
    if import_old not in s:
        raise SystemExit("APP_PATCH_IMPORT_ANCHOR_NOT_FOUND")
    s = s.replace(import_old, import_new, 1)

anchor = "    st.caption(f\"{counts.get('p10', 0)} saham selesai dianalisis. Pemeriksaan, analisis, dan pemeringkatan dijalankan otomatis di background.\")\n\n"
block = anchor + "    # Power Screener funnel: presentation only; Stage 3 remains the analytical source of truth.\n    def _select_funnel_symbol(symbol, horizon):\n        if horizon == \"swing\":\n            st.session_state[\"final_swing_symbol\"] = symbol\n        else:\n            st.session_state[\"final_lt_symbol\"] = symbol\n\n    render_opportunity_funnel(st, stage3, on_symbol=_select_funnel_symbol)\n    st.divider()\n    st.markdown(\"### Analisis Lengkap per Saham\")\n\n"
if "render_opportunity_funnel(st, stage3, on_symbol=_select_funnel_symbol)" not in s:
    if anchor not in s:
        raise SystemExit("APP_PATCH_RESULT_ANCHOR_NOT_FOUND")
    s = s.replace(anchor, block, 1)

# Every analyzed symbol must be a valid drilldown target, including WAIT/rejected rows.
swing_anchor = "        if options:\n            selected = st.selectbox(\"Pilih saham untuk melihat analisis Swing\", options, format_func=lambda x: labels.get(x, x), key=\"final_swing_symbol\")"
if "Semua saham lain tetap dapat dibuka" not in s:
    swing_block = "        for candidate in candidates:\n            sym = candidate.get(\"symbol\")\n            if sym and sym not in labels:\n                options.append(sym)\n                labels[sym] = f\"{sym} — Semua saham lain tetap dapat dibuka\"\n        if options:\n            selected = st.selectbox(\"Pilih saham untuk melihat analisis Swing\", options, format_func=lambda x: labels.get(x, x), key=\"final_swing_symbol\")"
    if swing_anchor not in s:
        raise SystemExit("APP_PATCH_SWING_DRILLDOWN_ANCHOR_NOT_FOUND")
    s = s.replace(swing_anchor, swing_block, 1)

lt_old = '''        if not top:\n            st.info("Belum ada kandidat Long-Term yang memenuhi kriteria ranking pada snapshot ini.")\n        else:\n            labels = {row.get("symbol"): f"#{row.get('rank')} {row.get('symbol')} — Quality {row.get('quality')} | Confidence {row.get('confidence')}" for row in top}\n            selected = st.selectbox("Pilih saham untuk melihat analisis Long-Term", [row.get("symbol") for row in top], format_func=lambda x: labels.get(x, x), key="final_lt_symbol")\n            cand = _candidate_for(stage3, selected)\n            st.subheader(f"{selected} — Analisis Long-Term", anchor=False)\n            _render_longterm_detail(cand, _package_for(packages, selected))\n'''
lt_new = '''        if not top:\n            st.info("Belum ada kandidat Long-Term yang memenuhi kriteria ranking pada snapshot ini.")\n        labels = {row.get("symbol"): f"#{row.get('rank')} {row.get('symbol')} — Quality {row.get('quality')} | Confidence {row.get('confidence')}" for row in top}\n        lt_options = [row.get("symbol") for row in top if row.get("symbol")]\n        for candidate in candidates:\n            sym = candidate.get("symbol")\n            if sym and sym not in labels:\n                lt_options.append(sym)\n                labels[sym] = f"{sym} — Lihat analisis lengkap"\n        if lt_options:\n            selected = st.selectbox("Pilih saham untuk melihat analisis Long-Term", lt_options, format_func=lambda x: labels.get(x, x), key="final_lt_symbol")\n            cand = _candidate_for(stage3, selected)\n            st.subheader(f"{selected} — Analisis Long-Term", anchor=False)\n            _render_longterm_detail(cand, _package_for(packages, selected))\n'''
if "lt_options = [row.get(\"symbol\")" not in s:
    if lt_old not in s:
        raise SystemExit("APP_PATCH_LT_DRILLDOWN_ANCHOR_NOT_FOUND")
    s = s.replace(lt_old, lt_new, 1)

p.write_text(s, encoding="utf-8")
print("POWER_SCREENER_APP_PATCH_OK")
