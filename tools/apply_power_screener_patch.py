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

p.write_text(s, encoding="utf-8")
print("POWER_SCREENER_APP_PATCH_OK")
