# Cleaned historical benchmark feature export

**Attribution:** Brazilian E-Commerce Public Dataset by Olist, Kaggle, https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce. Derived data distributed under CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/). Noncommercial academic use; retain attribution and ShareAlike when sharing adaptations. Review institutional and contributor rights before publishing.

`AEGIS_Olist_Historical_Features.csv.gz` contains 89,852 mature labeled observations, 65 model features, `partition` and `label_late`. No original order/customer/seller IDs or raw personal fields are included. Features are the existing `extended_checkout_unattested` frame converted to float32 before model scaling, as in benchmark_candidates.py and champion_diagnostics.py. `label_late` compares actual and estimated calendar dates. Label maturity rules and preprocessing are preserved in `historical_challenger.py`. Missing values are encoded as -999, with clipping as in the archived implementation. Do not treat estimates as contractual SLAs or features as authenticated at decision time.

| Partition | Rows | Late events |
|---|---:|---:|
| development_training | 43,426 | 2,453 |
| development_selection | 7,069 | 403 |
| development_calibration | 6,555 | 926 |
| historical_stress_inspected | 7,003 | 1,328 |
| historical_audit_inspected | 25,799 | 1,028 |

The source file SHA-256 values and feature names match `BROAD_ALGORITHM_BENCHMARK.json`; all partition counts and late counts match `CHAMPION_TEMPORAL_DIAGNOSTICS.json`. The manifest records export hash and actual Python/numpy/pandas versions. This is a regenerated feature table, not a new fitting experiment or independent prospective validation. It does not include all 99,441 original registry orders. March and April–July were previously inspected.

To reproduce, install research dependencies and run `python export_historical_features.py --app-dir /path/to/AEGIS_App --olist-dir /path/to/official/Olist/archive --output-dir /path/to/new/export`. Read gzip with pandas `read_csv`; cast feature columns to float32 before standardization. Fit scaler on training only, not selection/calibration/audit rows. Do not change partitions to tune on later inspected data.
