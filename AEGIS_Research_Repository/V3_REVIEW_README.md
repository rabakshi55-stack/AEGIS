# AEGIS — V3 professor-review application update

This is a full update of the existing application, not a submission kit. The original research evidence and application workflows remain intact. The Windows edition retains local and Qwen modes; Streamlit retains hosted AI and standard analytics. New research evidence is read-only, not a deployed replacement model. No operational or procurement authority is granted.

## Findings and response to the review

1. The SHA-256-locked `AEGIS_App/review_v3/protocol.json` defines five calendar transforms of recorded order-purchase time, mature delivered-only labels, chronological cutoffs and a fixed model. Fit is from original raw Olist orders, not the cleaned feature export. February calibration and April–July 2018 diagnostics are separate from training. The diagnostic cohort contains 25,796 mature comparable orders out of 26,271 purchases, 1,025 late; AP 0.037464 vs prevalence 0.039735, ROC-AUC 0.457269. Raw Brier 0.038347; February-calibrated Brier 0.051449, calibrated gap +10.49 percentage points. Calibration worsened. Historical week-cluster bootstrap intervals and reliability bins are archived. Original source-system feature availability has not been independently witnessed; no untouched Olist cohort can be certified. Results remain retrospective, and neither operational ranking nor calibrated probability claims are supported. Original roughly 18-point bias and input-lock failures remain in V2 evidence.
2. `AEGIS_App/review_v3/evidence/allocation_review.json` gives an objective/constraint/information table and common-cost comparison. Exact monthly optimum $1,698,024; daily sequential under the same static quote/menu/capacity definition $1,717,967.50, with different information horizons. Original daily quoted $1,659,449.50 is a different problem. Holding a candidate-invariant order risk proxy constant changes no assignment. This is an illustrative negative control, not causal evidence. `Review_V3/evidence/allocation_report.json` additionally re-solves the original daily cost-only archived quote menu to $1,659,449.50, checks source commitments, and compares two static monthly policies with identical inputs and 500 shared shocks. Its proxy and 5% cost allowance are illustrative sensitivity assumptions, not an operational policy or proven savings.
3. The separate `Review_V3/feature_contract.json` is a frozen January-calibration sensitivity specification with March and April–July diagnostics, not a selected replacement. March AP 0.151761 vs prevalence 0.189633, AUC 0.392598 and gap -14.10 pp expose limitations. April–July gap +2.12 pp does not imply reliable ranking or probability estimates. Both protocols are disclosed; do not select between them using these diagnostic outcomes.

## Reproduce from a clean research environment

Use Python 3.13.5 (not the embedded Windows launch runtime). Create and activate an isolated environment; from the extracted application root run:

```
python --version
python -m pip install -r requirements-review.lock.txt
python -B reproduce_review.py --output Reproduction_V3_New
```

The output folder must be new; never overwrite original evidence. This command verifies protected inputs, fits both frozen protocols, runs controlled optimization and stress tests, and hashes results. Windows includes raw Olist; `VERIFY_PACKAGE.py` verifies the original protected files. Streamlit source intentionally omits licensed raw CSVs; obtain Brazilian E-Commerce Public Dataset by Olist (CC BY-NC-SA 4.0) at https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce and place `olist_orders_dataset.csv` in `Research/Public_Data/Olist_Raw/archive/`. The script verifies it against `review-input-hashes.json`. Do not commit original raw files or credentials publicly. The earlier 37-configuration benchmark requires nine original CSVs and optional ML packages; the historical environment is not retroactively pinned. The V3 lock covers the new end-to-end fitting workflow only. Clean installation on another machine has not been independently tested.

## Launch

Windows: extract to a new writable folder, run CHECK_AEGIS.bat, then START_AEGIS.bat. The V3 evidence is in the existing research view. The scientific environment is not needed for ordinary application use.

Streamlit: extract the repository and deploy `streamlit_app.py` with the existing secrets configuration if using hosted AI. Local launch: `python -m pip install -r requirements.txt`, then `python -m streamlit run streamlit_app.py`. V3 is in Research evidence. Publish the source, not the raw CSVs; test the public repository link in a signed-out browser. No external deployment or live AI test is claimed.

## Still unresolved

Independent untouched chronological validation, source-system feature availability, reliable ranking/calibration, causal supplier-switch impact, real savings and real operational feasibility remain unestablished. Need a genuinely unseen cohort with documented as-of provenance and one-time frozen evaluation; don't relabel already inspected Olist months as untouched. The original failures remain prominent. Actual Windows platform acceptance, live AI, Streamlit deployment, clean external installation and signed-out repository checks are separate.
