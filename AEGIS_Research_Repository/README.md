> **V4 release:** see [V4_FINAL_REVIEW.md](V4_FINAL_REVIEW.md) for JD.com external validation, Olist challenger experiments, pinned historical benchmark target and updated reproduction command. The original negative findings remain visible; no operational model is certified.

# V3 professor-review update

See [V3_REVIEW_README.md](V3_REVIEW_README.md) for the new evidence and reproduction instructions. Older instructions below remain for the original application workflow.

# AEGIS: Evidence-Grounded Supply-Chain Decision Intelligence

AMLBT research prototype, GIM PGDM-BDA. Research only; no business execution.

Existing repository: https://github.com/rabakshi55-stack/AEGIS. Online demo: https://aegis-decision-intelligence.streamlit.app. This is the 15 November 2026 source snapshot; deployment is not changed by downloading it. See STREAMLIT_DEPLOYMENT.md for configuration.

- `AEGIS_App/`: shared application code, tests and preserved research artifacts.
- `streamlit_app.py`, `cloud_engine.py`, `cloud_tests/`: hosted demo and offline verification.
- `Research/`: original notebooks, synthetic inputs and archived results; raw Olist CSVs omitted.
- `Cleaned_Data/`: regenerated 89,852-row historical feature dataset with attribution, manifest and export code.
- `Paper/`: updated IEEE report and editable source.
- `Evidence/`: claim-to-source traceability and release verification.
- `Demo/`: fictional sample and independent answer key.

Full Windows application is supplied separately, with the portable runtime repair integrated. Full research test dependencies differ from the lightweight runtime. See REPRODUCE_AEGIS.md. Optional hosted GPT-OSS uses Groq with consent, and local Qwen uses Ollama. Do not commit keys or upload sensitive data.

Latest verification: 349 shared online and 91 cloud tests passed; 352 full Windows source tests and 350 portable tests passed (two explicitly deferred research-only tests). Actual user Windows check confirmed 559 file matches and 34 software controls. Live AI, second-device portability and prospective/business validation remain unverified.

Historical Olist results and fictional optimization are separate; no realized savings or certified future forecasts. Review data rights (CC BY-NC-SA 4.0) and author AI-use compliance before submitting/publishing. See DATA_SOURCE_AND_LICENSE.md.
