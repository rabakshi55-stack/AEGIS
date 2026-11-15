# AEGIS — analytical relevance and derived charts

Applies to the audited Streamlit edition. Copy this ZIP's contents into the existing `AEGIS_Research_Repository`, replace matching files, commit/push, and reboot Streamlit. No credential, runtime, or dependency changes are needed.

- Supplier/region/item comparisons of quantity or purchase value versus delivery performance use a checked group-level scatter chart, not record counts. The online adapter recomputes the points from the current dataset on creation, displays denominators on hover, retains the specification in Visualizations, and invalidates it when the dataset/mapping changes. The current chart-context selector still covers the original automatic and custom charts only; derived comparisons can be discussed by asking about their measures.
- Scope/currency/coverage checks refuse misleading substitutes; no inferred currency. Groups without complete X measures or comparable dates are omitted and disclosed. Two to 100 eligible groups required.
- Named supplier reliability/decision challenges use the actual recorded rate, denominator, missing/invalid date coverage and proportionate human-review guidance. They do not inherit an unrelated chart from chat history.
- Chart history now requires a chart referent, not just generic question words. Unresolved relationship charts do not default to counts. Hosted chart requests for the supported derived comparisons use the same checked tool without consuming Groq quota.
- The online session version is advanced so old objects are not retained.

Verification: 296 application tests and 86 cloud tests passed in the build environment with `AEGIS_OFFLINE_TEST_MODE=1` and UTF-8. Ten new cloud tests cover the reported failures, derived chart points, dataset replacement, scope and currency, provider outage and history. The live Streamlit interface and actual hosted provider are not independently tested by these offline tests. No source research files were modified. The Windows release archive has not been rebuilt here; the shared modules include text guidance for the local builder, but the derived chart UI is online-only in this release.
