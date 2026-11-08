AEGIS CONSOLIDATED RETROSPECTIVE VALIDATION
=========================================

PURPOSE
Combine the existing Olist/AEGIS validation work into a single safe pass.
This is a research audit, NOT production certification. It does NOT fix
fundamental evidence gaps in historical Olist records or make procurement
recommendations operationally valid.

HOW TO RUN (NO NEW LIBRARIES NEEDED)
1. Extract all files from AEGIS_Consolidated_Validation_Package.zip DIRECTLY
   into your existing AEGIS_Standalone_App folder (the folder containing
   AEGIS_App, AEGIS_step204_selection_report.json, and
   AEGIS_step205_eligibility_report.json).

   For this user's current folder, the target is:
   C:\Users\VISHAL\OneDrive\Desktop\AEGIS\AEGIS_4_0_Integrated_Dataset_v0_2\AEGIS_4_0_v0_2\AEGIS_Standalone_App\

2. Double-click RUN_AEGIS_VALIDATION.bat.
   It runs software checks and then the full consolidated audit.
   Alternatively, open CMD in that folder and use:
   python -B AEGIS_validation_consolidated.py

3. Open the new, numbered AEGIS_consolidated_validation_001 folder (or 002,
   etc. if you have run it before). Upload consolidated_report.json here.

REQUIRED EXISTING FILES
- AEGIS_App\data\aegis_bundle.json (frozen, unmodified)
- AEGIS_step200_olist_temporal_audit.json
- AEGIS_step204_selection_report.json
- AEGIS_step205_eligibility_report.json
- Original olist_orders_dataset.csv and olist_customers_dataset.csv under:
  AEGIS\AEGIS_Public_Data\Olist_Raw\archive\

WHAT IT CHECKS
- Original Olist data source hash and prior audit reconciliation
- Full order and customer relationship integrity
- Strict historical selection vs original purchase population
- Training/validation/test period assignment and source-label alignment
- Frozen scored IDs, purchase timestamps, customer state and promise features
- Exact tie-aware AUC / average precision WITHOUT scikit-learn
- Historical late rates, mean stored model scores, descriptive Brier results
- Monthly scoring and historical period instability
- Scores with and without delivery promises longer than 60 days
- Read-only input hash validation before and after processing

WHAT IT WILL NOT CERTIFY
- Whether Olist's recorded promise/customer state were available at purchase
- A pristine independent prospective holdout or live accuracy
- Calibrated future probabilities or a contractual delivery service level
- Causal impact of supplier changes, capacity feasibility, or ERP integration
- Autonomous business actions. These remain DISABLED.

SAFETY
- Python standard library only. No pip installs or sklearn needed.
- Existing AEGIS files, models, and CSVs are only READ.
- The script creates a NEW numbered output folder instead of overwriting.
- Its JSON report contains aggregate statistics and input file hashes only.
- A failed reconciliation is reported as a FAILURE, not hidden or corrected.

SOURCE NOTES
- Model features inspected in Version 2 Validation(5).ipynb Step 180.
- Actual raw Olist CSV and frozen bundle are LOCAL to the Windows laptop:
  they are NOT bundled here. The software's complete real-data result is
  therefore only known after the user runs it on their existing files.

TEST STATUS BEFORE DELIVERY
- 12/12 software self-tests passed (fictional cases).
- 22/22 end-to-end integration checks passed on a separate fictional dataset.
- Real-data baseline comparison and long-promise sensitivity: NOT YET RUN in
  the assistant environment (original Olist and bundle were not available).
