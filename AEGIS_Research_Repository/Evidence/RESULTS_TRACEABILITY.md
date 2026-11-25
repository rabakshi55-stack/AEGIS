# AEGIS Research Results — claim-to-source traceability

All paths below refer to the preserved **AEGIS/Research/** tree in the final Windows release archive `AEGIS_Windows_Submission.zip (Precision Edition + runtime repair)`. These are evidence artifacts, not third-party experimental endorsements. They have been inspected and source values transcribed without recomputing the full Olist model training.

| Paper claim | Exact value | Primary evidence file / JSON key | Required caveat |
|---|---|---|---|
| Olist order registry | 99,441 | `Validation_Archive/Consolidated_003/consolidated_report.json` -> `original_population.orders` | Original orders, not model training rows |
| Earlier frozen scored cohort | 58,911 | same -> `original_population.frozen_selected` | Different model/cut than new benchmark |
| January training cohort | 43,426 | `Validation_Archive/Current_Validation_2026_11_07/CHAMPION_TEMPORAL_DIAGNOSTICS.json` -> `models.logistic_l2.development_training.rows` | 2017, historical comparable labels |
| January selection cohort | 7,069 | same -> `models.logistic_l2.development_selection.rows` | Late events 403 |
| Selected L2 logistic AP / ROC-AUC | 0.145852 / 0.690373 | same -> `models.logistic_l2.development_selection` | Selected on these data |
| January prevalence/AP baseline | 0.057009 | `BROAD_ALGORITHM_BENCHMARK.json` -> first `selection_results` | Not a universal AP baseline |
| L1 logistic AP / ROC-AUC | 0.145779 / 0.692032 | benchmark and temporal diagnostics | Small difference from L2 |
| Balanced linear SVM AP / ROC-AUC | 0.145340 / 0.693405 | benchmark and temporal diagnostics | SVM was evaluated |
| MLP AP / ROC-AUC | 0.142801 / 0.699121 | `MODEL_BENCHMARK_OUTCOME.md` / expanded report | January only |
| Number of tested model configurations | 38 | `MODEL_BENCHMARK_OUTCOME.md`, `EXPANDED_BENCHMARK_REPORT.json` and broad benchmark | 38 configurations, not 38 fundamentally distinct algorithms |
| March period ROC-AUC / AP | 0.634753 / 0.304187 | `CHAMPION_TEMPORAL_DIAGNOSTICS.json` -> `historical_stress_inspected` | 7,003 later historical records, previously inspected |
| April--July ROC-AUC / AP | 0.678720 / 0.075016 | same -> `historical_audit_inspected` | 25,799 previously inspected records |
| April--July mean calibrated score | 0.219829 | same -> `historical_audit_inspected.mean_calibrated_score` | Not a trustworthy probability estimate |
| April--July observed late fraction | 0.039847 | same -> `observed_late_rate` | 3.9847% |
| Absolute difference | 0.179982 | same -> `absolute_mean_calibration_gap` | 17.9982 percentage points, not percent relative error |
| Paired bootstrap (L2 - SVM AP) | +0.000512; 95% interval [-0.005466, 0.005998] | same -> `paired_january_ap_uncertainty.linear_svm_balanced` | Interval includes 0; development selection data reused |
| Older frozen model validation AUC | 0.558705 | `Validation_Archive/Consolidated_003/consolidated_report.json` -> `frozen_model_historical_metrics` | **Not directly comparable** to new challenger |
| Synthetic component/month | CMP-007 / July 2025 | `Validation_Archive/Paired_Stress_191/audit_report.json`; source CSVs | Fictional inputs |
| Synthetic orders / units | 16 / 13,900 | archived synthetic monthly joint-capacity report in application | Fictional, one-component instance |
| Modeled baseline cost | USD 1,928,061 | `AEGIS/RELEASE_NOTES.md` / joint-capacity research report | Modeled, not invoice evidence |
| Model exact cost | USD 1,698,024 | same | Exact subject to modeled constraints |
| Modeled difference | USD 230,037 | same | **Not realized business savings** |
| Paired synthetic stress | 500 shocks, 80 pairs, 40,000 records | `Validation_Archive/Paired_Stress_191/audit_report.json` | Not a validated risk distribution; no supplier causal effects |

### Claims explicitly *not* supported

- Operationally calibrated probabilities or a verified prospective independent holdout.
- Authenticated time-of-decision availability for all original model inputs.
- A contractual business SLA proven by Olist's estimated delivery date.
- Real current supplier quotations, daily capacities, routes, invoices, or cost improvements.
- Causal benefits from switching suppliers.
- Independently demonstrated truthfulness of every free-form Qwen answer.
- An objectively measured AI-use percentage below the professor's threshold.

### Scholarly references independently verified

1. D. Bertsimas and N. Kallus, *From Predictive to Prescriptive Analytics*, Management Science, 66(3), 1025--1044, 2020. https://doi.org/10.1287/mnsc.2018.3253
2. T. Fawcett, *An introduction to ROC analysis*, Pattern Recognition Letters, 27(8), 861--874, 2006. https://doi.org/10.1016/j.patrec.2005.10.010
3. T. Saito and M. Rehmsmeier, *The precision-recall plot is more informative than the ROC plot when evaluating binary classifiers on imbalanced datasets*, PLOS ONE, 10(3):e0118432, 2015. https://doi.org/10.1371/journal.pone.0118432
4. D. Sculley et al., *Hidden Technical Debt in Machine Learning Systems*, NeurIPS 2015, pp. 2503--2511. https://research.google/pubs/hidden-technical-debt-in-machine-learning-systems/
5. Olist, *Brazilian E-Commerce Public Dataset by Olist*, Kaggle. https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce (CC BY-NC-SA 4.0).

### Current application and demo evidence (15 November 2026)

| Claim | Evidence | Boundary |
|---|---|---|
| 349 online app and 91 cloud tests passed | `Evidence/online_tests.log`, `cloud_tests.log` | Fresh source execution on Linux |
| 352 full Windows source tests passed | `Evidence/windows_tests.log` | Linux with research dependencies |
| 350 portable tests passed; two research-only deferred | `Evidence/portable_tests.log`; `Windows_runtime_check.png` | Linux no-site simulation and actual user Windows screenshot, separately |
| 559/559 release files matched | `Evidence/windows_integrity.log`; Windows screenshot | Integrity, not correctness |
| 34/34 foundation controls | Windows screenshot and logs | Software gates; no operational approval |
| 120 sample orders, 4 suppliers, INR 472268, 54/114 late | `Demo/verify_sample.py`, `EXPECTED_RESULTS.json` | Independent fictional data calculation, not live AI result |

The screenshot is cropped to show the verification results without local paths. A Windows runtime pass is not a second-device or interactive browser acceptance test. No live Groq calls or full benchmark retraining were performed in this submission refresh.

Cleaned historical export: `Reproducibility/Cleaned_Data/FEATURE_EXPORT_MANIFEST.json` records matching source hashes, 65 features and 89,852 rows across five partitions. The feature export was regenerated without retraining. `SAMPLE_STANDARD_ENGINE_CHECK.md` records actual source-level standard analytics output; numeric metrics match, but the full ranking is not explicitly sorted.
