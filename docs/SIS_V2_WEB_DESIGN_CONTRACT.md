# SIS v2 — Web Design Contract

Status: FROZEN for v2 build and visual acceptance.

## Product identity
SIS is a **Smart Investment Screener**, not a charting platform. The UI may show screening-derived numbers, status, ranking, narrative, and evidence, but must not introduce price charts, candlesticks, volume charts, or chart-reading behavior.

## Information hierarchy
- D1: Input Data & Validated Snapshot.
- D2: Hasil Screening / ranking, with Top 3 Swing and Top 3 Jangka Panjang as primary focus plus Lihat Semua.
- D3: Detail Saham with Ringkasan, Swing (Trading), Jangka Panjang (Investasi), and Analisis Lengkap.
- D4: Monitoring.
- D0: Beranda/control center is completed after the functional D modules.
- Progressive disclosure is used from screening result -> stock detail -> deeper analysis.

## D1 business contract
- Input remains B1–B11 and preserves the validated v1 business process.
- B1–B11 must come from one screening session and universe consistency must be guarded.
- Invalid input must never overwrite/corrupt the last valid snapshot.
- A snapshot becomes official only after required validation/analysis gates pass.
- Input after market close is the recommended workflow.

## Visual system
- Master visual language: navy SIS header, light blue page background, white rounded cards, restrained shadows/borders, blue primary accent, and green/amber/red semantic status badges.
- Navigation is compact and consistent across modules.
- Dense information must remain readable and nontechnical language is preferred in the user-facing layer.
- Light and Dark themes must be switchable without changing information architecture or status semantics.
- UI should not look like default Streamlit; native components must be visually integrated into the SIS design system.

## D2/D3 output contract
- Swing and Jangka Panjang are distinct horizons.
- Ranking is engine-derived; UI must not invent or modify rankings/recommendations.
- Detail view prioritizes: important numbers + status + narrative + evidence.
- Any space that might otherwise be used for a chart is used for narrative analysis, key data, catalysts, risks, valuation context, and evidence.

## Visual acceptance gate
A candidate is not READY solely because compile/unit/regression tests pass. Release requires:
1. Functional/business gate PASS.
2. Regression gate PASS.
3. Packaging/clean-room gate PASS.
4. Visual acceptance against the frozen SIS design contract, including Light/Dark behavior and responsive layout.

If visual acceptance has not been executed on an actual render, status must remain `VISUAL QA PENDING`, not `READY`.
