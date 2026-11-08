# Independent fresh run of archived synthetic stress script

Command (executed inside `AEGIS_App`):

`python -B paired_stress.py --source ../Research/Integrated_v02 --output <new-empty-folder> --scenarios 500 --seed 191`

Completed successfully. `candidate_menu.csv`, `pair_summary.csv`, and `paired_exposures.csv` reproduced byte-identically to original archived step 191 data. `audit_report.json` and `synthetic_shared_shocks.json` differ at the bytes level due to non-substantive serialization/provenance representation. The synthetic experiment has 500 shared shocks, complete eligible-pair coverage and 40,000 paired exposure rows. These findings are not live supplier capacity or causal impact evidence.
