# AEGIS — reproducibility protocol for the AMLBT IEEE paper

## Scope

Two distinct studies are reported:

1. **Historical Olist ML benchmarking** (actual published, historical e-commerce orders; retrospective labels). Requires obtaining original Olist files, Python and optional research ML packages. An old repeatedly inspected cohort is **not** an untouched future holdout.
2. **Synthetic supplier optimization and paired stress** (fictional supplier quotes/capacities and generated shocks). Requires bundled synthetic source CSVs and the Python scripts. A real-world supplier intervention is not established.

This repository is a source-only academic companion; the locally verified, complete Windows release should be kept independently for presentation. Deleting the Kaggle raw dataset from a GitHub copy invalidates the original *full-release* file manifest, so the `CHECK_AEGIS.bat` integrity script must only be run against the original unmodified complete release. Use the separate unit-test command below to inspect the source-only companion.

## Data acquisition and rights

Download the **Brazilian E-Commerce Public Dataset by Olist** from
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

Official license: **CC BY-NC-SA 4.0** (Attribution--NonCommercial--ShareAlike). This academic starter does not redistribute the licensed raw CSV files. Follow the license, include attribution, and respect any additional institutional data rules. Put the nine original CSV files into:

`Research/Public_Data/Olist_Raw/archive/`

Expected source files include `olist_orders_dataset.csv`, `olist_customers_dataset.csv`, `olist_order_items_dataset.csv`, and `olist_sellers_dataset.csv`. Verify their SHA-256 against the historical audit manifests before claiming exact reproduction; Kaggle dataset versions may differ.

## Python environment

- Run within the repository's `AEGIS_App` folder (Python 3 environment).
- App server is mostly Python standard library; optional local conversation uses externally installed Ollama/Qwen (not required for research reproducibility).
- Research benchmark optional packages: `numpy`, `pandas`, `scikit-learn`, `xgboost`, `lightgbm`, `catboost`.
- The project **does not bundle a verified pinned environment lock**. In your actual successful local Windows environment record precise versions with:

```bat
python --version
python -m pip freeze > environment-lock.txt
```

Install the reviewed dependencies after choosing versions consistent with the archived research environment. Changing Python/ML package versions may alter the model benchmark; compare metrics and source hashes.

## Regenerating historical benchmark reports

In `AEGIS_App`, with public Olist CSVs in the expected location:

```bat
python benchmark_candidates.py --olist-dir ../Research/Public_Data/Olist_Raw/archive --output BENCHMARK_REPRO.json
python benchmark_extended.py --olist-dir ../Research/Public_Data/Olist_Raw/archive --output BENCHMARK_EXTENDED_REPRO.json
python champion_diagnostics.py --olist-dir ../Research/Public_Data/Olist_Raw/archive --output DIAGNOSTICS_REPRO.json
```

Reference report files in `Research/Validation_Archive/Current_Validation_2026_11_07/` are `BROAD_ALGORITHM_BENCHMARK.json`, `EXPANDED_BENCHMARK_REPORT.json`, and `CHAMPION_TEMPORAL_DIAGNOSTICS.json`. **Do not overwrite them.** Compare expected cohort sizes, model-selection rule, AP, AUC, calibration and source input hashes. Model selection should not be reopened to tune to later inspected months.

## Synthetic paired stress rerun

From `AEGIS_App`:

```bat
python -B paired_stress.py --source ../Research/Integrated_v02 --output ../Reproduction_Stress_New --scenarios 500 --seed 191
```

The prior validated rerun produced 500 shared shocks, 80 eligible pairs and 40,000 exposure rows. `candidate_menu.csv`, `pair_summary.csv`, and `paired_exposures.csv` previously matched archived outputs byte-for-byte; audit/report JSON may differ by serialization. Recompute and compare, rather than copying these reference output files over rerun files.

## Tests and software launch

On the actual complete Windows release:

```bat
CHECK_AEGIS.bat
START_AEGIS.bat
```

The check script uses `AEGIS_OFFLINE_TEST_MODE=1` and prevents model calls in automated tests. Source-only GitHub copies are missing the full-release integrity manifest and original licensed data; use:

```bat
cd AEGIS_App
set "AEGIS_OFFLINE_TEST_MODE=1"
set "PYTHONUTF8=1"
python -B -m unittest discover -s tests -q
```

A modified source repository should be treated as a new unverified variant. Unit tests verify software behavior, **not** real-world ML accuracy or actual supplier feasibility.

## Evidence files

- Historical original score audit: `Research/Validation_Archive/Consolidated_003/consolidated_report.json`.
- Full benchmarking: `Research/Validation_Archive/Current_Validation_2026_11_07/`.
- Synthetic stress: `Research/Validation_Archive/Paired_Stress_191/`.
- Primary synthetic sources and notebooks: `Research/Integrated_v02/` and `Research/Original_v01/`.

Detailed result-to-source mapping is in the submission package: `Evidence/RESULTS_TRACEABILITY.md`.

## Critical limitations

No prospective validated probability forecast, authenticated historical as-of feature availability, causal supplier switch impact, validated actual savings, or autonomous procurement. The Qwen-enabled Copilot is an optional conversational layer, not a source of independently verified numeric results.
