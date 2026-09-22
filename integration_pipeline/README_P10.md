# SIS Integration Pipeline — P10 End-to-End Orchestrator R1

P10 composes the frozen modular contracts into one deterministic Stage2 → Pipeline → Stage3-payload flow.

Flow:
P2 Stage2 mapper → P3 raw evidence store → P4 validation/freshness gate →
P5 deterministic derivations → P6 reconciliation → P9 Stage3 payload builder.

P7 remains provider-neutral acquisition infrastructure and P8 remains the Python-first disclosure/event engine; their provider-specific normalization/binding is intentionally outside P10 core until an actual provider is approved.

Invariants:
- Stage2 eligibility/state is never recalculated or upgraded.
- REVIEW may remain in deep-analysis scope.
- enrichment failure/missing data never removes a Stage2 symbol.
- future evidence is blocked.
- out-of-scope raw evidence is rejected.
- missing is never converted to zero.
- no conflict winner is selected.
- no recommendation/ranking/decision output.
