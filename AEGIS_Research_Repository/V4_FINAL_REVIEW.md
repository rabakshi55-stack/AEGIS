# AEGIS V4 — external validation and final review evidence

This is the complete application release update, not a replacement research paper. V3 evidence, frozen model and original research archives are retained. New V4 evidence is read-only in the application. No automatic purchasing, causal claims or new production forecast is approved.

## Professor's review: disposition

| Requirement | Disposition |
|---|---|
| Immutable decision-time features and mature labels | V3 frozen contract retained; V4 separate hashed challenger protocol with explicit maturity cutoffs. Actual original feature availability still not independently attested. |
| Untouched chronological evaluation | Frozen Olist artifact evaluated on JD.com historical external cohort with fixed deadline conversion. Conditional on team non-exposure and original publisher data-use permission; neither independently established. JD is now inspected and cannot be used as a fresh holdout for challengers. |
| Discrimination/calibration/uncertainty | Both reported separately; 500 day-cluster bootstrap replicates for external model; 500 week-cluster replicates for each Olist challenger diagnostic. |
| Allocation formulations/common information | Original V3 reconciled constraint/objective evidence and 500 shared-shock scenarios retained; no causal supplier-switch effect. |
| Pinned environment/end-to-end fitting | V3 lock, V4 evaluation lock and historical benchmark lock with a combined reproduction command. Exact original historical environment is unknown; current lock is a repeatable target, not proof of original environment. |
| Negative findings in final conclusions | See conclusions below; final manuscript still needs to be updated separately. |
| Public access | Deploy updated Streamlit repository, test signed out and verify links. Native Windows/live AI/Streamlit deployment acceptance are not established by offline tests. |

## Research conclusions (retain prominently)

The fixed January-calibrated calendar-only Olist model was tested on 175,002 eligible first-party JD.com orders (19,951 late; 11.4004%). AP 0.08951 vs prevalence 0.11400; AUC 0.39425 (95% day-cluster interval 0.36985–0.42678). Calibrated average 4.1527%, below observed prevalence by 7.2478 percentage points; calibrated Brier 0.106943 and log loss 0.410422 vs frozen training-prior baseline 0.105653 and 0.392991. Ranking and calibration fail external baseline comparison. These are historical outcomes conditional on observed comparable deliveries, not prospective results.

Four Olist-only challengers use identical mature chronological samples: calendar logistic/HGB and calendar plus recorded promise-days logistic/HGB. January selection (1,001 mature rows, 10 late) and February calibration (510, 14 late) are extremely limited by strict cutoffs. Both selected HGB. The promise feature is not independently attested at purchase. April–July inspected diagnostics: calendar raw AP 0.04580, AUC 0.55436, Brier 0.03831; calibrated AP 0.03347, AUC 0.44564, Brier 0.03877. The unconstrained sigmoid fitted on February reverses ranking in this calendar model; retain the failure rather than promote it. Conditional promise model raw/calibrated AP 0.04305 and AUC 0.54719; raw Brier 0.03848 and calibrated Brier 0.04502; frozen training-prior Brier 0.03819. In March promise-model AP/AUC are below prevalence/random references. Neither candidate provides reliable discrimination and calibration together; no promotion. No JD tuning, no new independent validation of challengers. Future improvement requires time-attested decision features, more mature training/calibration cases and a fresh externally controlled cohort.

The monthly common-cost synthetic optimum ($1,698,024) and daily common-cost sequential result ($1,717,967.50) retain the same static cost and capacity definitions. The original daily quoted-cost formulation ($1,659,449.50) is distinct. Risk-input locking eliminates the claimed assignment change under the corresponding V3 controlled setup. These are fictional allocation studies, not realized savings or causal supplier effects.

## Reproduction instructions

Use Python **3.13.5**, in a new environment. From the extracted application root:

```
python -m venv .venv
```

Activate `.venv` using your OS-specific command, then:

```
python -m pip install -r requirements-review.lock.txt
python -B reproduce_final.py --jd-archive /path/to/Dataset.zip --output Reproduction_V4_New
```

On Streamlit source, acquire the original Olist CSVs under `Research/Public_Data/Olist_Raw/archive/` according to `DATA_SOURCE_AND_LICENSE.md` and `V3_REVIEW_README.md`. The Windows academic package already contains the original Olist files. Do not commit raw JD files. Obtain JD files from an authorized source (see `Review_V4/JD/README.md`); raw CSV SHA-256 must match frozen `protocol.json`. `Dataset.zip` is the original user-supplied archive and is not redistributed here. If running `VERIFY_RELEASE.py` after adding raw Olist files to the online package, the manifest covers existing release files only; verify input hashes separately using the reproduction command.

For the full historical benchmark target environment:

```
python -m pip install -r Review_V4/requirements-historical.lock.txt
python -B reproduce_final.py --jd-archive /path/to/Dataset.zip --output Reproduction_All_New --historical
```

This refits broad and expanded historical configurations and champion diagnostics, compares archived AP/AUC excluding timing, and preserves prior negative evidence. It does not certify that the original historical environment used these exact versions. Fresh dependency installation and exact expanded benchmark reproduction are not claimed unless documented in the release verification report.

## Final external validation declaration (team action)

Before academic submission, verify permitted research use with the original JD publisher, and document whether each team member had used these records for development before the protocol freeze. Do not sign a false declaration. Independent timestamp certification of the protocol is not established; local hashes preserve byte integrity. If either requirement cannot be established, describe this as conditional external historical evaluation. Do not present a failed model as reliable. No new validation data is needed to use the application, only to make a stronger scientific claim.

## Historical rerun evidence

The 17 broad configurations were refitted in the current target environment: all 17 AP/AUC pairs matched their archived values to 1e-6, and logistic L2 remained the January winner. The champion temporal diagnostic JSON matched its archived content exactly. See `Review_V4/evidence/historical_rerun/`. The expanded 21-configuration supplementary benchmark has a pinned target and executable command but has not been rerun during this release; exact full benchmark reproduction is not certified. The previously reported 37 non-baseline configurations correspond to 38 including the baseline.
