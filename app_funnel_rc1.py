"""Isolated RC1 entrypoint for validating the new SIS Opportunity Funnel.

It deliberately reuses the production app unchanged, then appends the candidate
funnel only when a COMPLETE Stage 3 result exists in session state. This keeps
main/production behavior untouched during the release gate.
"""

import app  # noqa: F401 - executes the existing Streamlit application
import streamlit as st

from stage3.opportunity_funnel_ui import render_opportunity_funnel


result = st.session_state.get("stage3_result") or {}
stage3 = result.get("stage3") or {}
if result.get("status") == "COMPLETE" and stage3:
    st.divider()
    render_opportunity_funnel(st, stage3)
