# AEGIS — JD.com external historical evaluation

Separate evidence add-on for the existing Windows and Streamlit V3 applications. No application changes or raw JD.com data included.

## Reproduce
Use Python 3.13.5. Install `python -m pip install -r requirements.txt`. Obtain the two JD CSVs from an authorized source, preserving the bytes corresponding to the SHA-256 values in `protocol.json`, and place them in a ZIP with the original filenames. Run:

```
python evaluate_jd.py /path/to/Dataset.zip --out reproduced.json
```

Compare with `result.json`. The evaluation was rerun in the existing environment and reproduced byte-for-byte. A fresh environment installation has not been tested. `freeze_manifest.json` records the protocol, script and model hashes established before the evaluation read any delivery outcome records; this is a local hash record, not independent timestamp certification. The existing `Review_V3/evidence/fitted_model.json` and related Olist contract/report are copied unchanged from both V3 editions. This is the January-calibrated artifact, not the separate February-calibrated app diagnostic.

## Data and interpretation
Shen et al., JD.com: Transaction-Level Data for the 2020 MSOM Data Driven Research Challenge, DOI https://doi.org/10.1287/msom.2020.0900 (Tables 4–5 and footnotes 13, 17). Official data access: https://connect.informs.org/msom/events/datadriven2020. The user-provided files match the public Hugging Face mirror's published SHA-256 values. Original publisher permission and prior non-exposure by team members are not independently established. Do not redistribute raw data without confirming terms.

This is a historical external evaluation, conditional on comparable observed deliveries. The strict cohort is first-party orders with consistent timestamps/promises, a single full-order package, March 1–24 purchase dates, and recorded arrival and deadline before April 1. The calendar-date target is not an hourly SLA. Missing and unresolved deliveries are excluded, not treated as timely. The 24 daily bootstrap clusters quantify limited conditional sampling uncertainty, not prospective or causal evidence. No model fitting or tuning on JD.com occurred. The cohort is now examined and cannot serve as a fresh untouched test for any subsequent model changes.

Results: 175,002 eligible orders; 19,951 late (11.4004%). AP 0.08951 and ROC-AUC 0.39425; calibration underestimates prevalence. Both probability variants have worse Brier and log loss than the frozen Olist training-prior baseline. Do not approve for operational risk prediction. This does not evaluate supplier-switch benefits. Retain all prior negative Olist findings. Before claiming independent validation, document team non-exposure and permitted research use. A future improved model needs a different untouched cohort.
