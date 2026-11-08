# AEGIS — Verified research application update

Date: 7 November 2026
Release scope: **research-only**. Neither operational prediction nor autonomous procurement is authorized.

## Source material inspected

The complete AEGIS project archive, including the Jupyter research notebook, all nine original Olist CSVs, the local app (Python standard-library server and browser UI), the frozen research bundle, earlier audit outputs and the synthetic paired stress experiment. No original notebook, model weights, original source CSV or prior audit files were rewritten.

## Changes actually implemented in this copy

1. **Model evidence built into Governance & Evidence.** The application now displays archived, validated historical scores for TRAIN, VALIDATION, TEST and ALL. It visibly warns about the weak validation period, score miscalibration and unverified operational features. It avoids conflating software checks with prospective certification.
2. **Evidence-to-bundle consistency guard.** The new `/api/model-validation` endpoint validates the stored reference SHA-256 against the exact current frozen bundle and cross-checks cohort/late counts. It refuses to show archived metrics if the bundle does not match. The archived report is not a signed attestation; the UI does not independently reread original Olist CSVs.
3. **Frozen research-score input hardening.** The server rejects Boolean, NaN, infinity, and out-of-range score fields before generating score-based views.
4. **Automated tests.** Added model-evidence and score-guard tests. Existing tests remain intact. The local software suite now passes **79/79 tests**.
5. **Synthetic joint monthly capacity allocator.** Added an exact, standard-library whole-order assignment optimizer using source-defined supplier qualifications, eligible supplier–plant lanes, minimum quantities and hard component-month capacities. On the existing synthetic July 2025 CMP-007 pilot, all 16 orders were allocated, the exact cost optimum was independently confirmed by a 0/1 knapsack reference, and hard monthly capacities were respected. This is **separate** from both the original ten frontier scenarios and the 500-shock paired stress experiment. It does NOT establish daily or multi-component shared capacity, real quotations, supplier causality or realized business savings. The result appears in Scenario Lab and has a read-only source-derived endpoint (`/api/joint-capacity`).
6. **Single-click check.** Added `CHECK_AEGIS_UPDATE.bat` in the Standalone_App folder; double-click to run all application tests in the existing Python environment.

## Verified during this review

| Check | Observed result |
| --- | --- |
| Original application suite | 64/64 passed before changes |
| Updated suite | 79/79 passed |
| Historical source/report reconciliation | 23/23 checks in archived consolidated report |
| Validation foundations | 34/34 checks recomputed |
| Paired synthetic experiment | 16 orders, 80 pairs, 500 shared scenarios, 40,000 paired rows, 100% coverage |
| App HTTP smoke test | `/api/status`, `/api/model-validation`, `/api/joint-capacity`, `/api/overview`, `/api/scenarios`, `/api/policies`, `/api/readiness` returned 200 |
| Local browser isolation smoke test | Request with untrusted Origin rejected (403) |
| Original Olist order registry | 99,441 orders |
| Frozen scored research cohort | 58,911 orders |

## Historical model outcome (not a production forecast)

| Cohort | ROC-AUC | Observed late rate | Mean frozen score |
| --- | --- | --- | --- |
| TRAIN | 0.703115 | 3.64% | 3.64% |
| VALIDATION | **0.558705** | **12.83%** | **5.62%** |
| TEST | 0.702624 | 2.28% | 3.25% |
| ALL | 0.674583 | 6.57% | 4.25% |

The March 2018 validation-period deterioration and large predicted-versus-observed gap are **not resolved**. Existing scores remain historical ranking evidence, not calibrated risk probabilities. The test period has been inspected repeatedly, so it cannot become a pristine holdout.

## New synthetic joint-capacity study — separate evidence lane

Source: original integrated *fictional* supplier orders, options, suppliers, and route CSVs for component CMP-007, July 2025. The new exact optimizer uses unsplittable order assignments, one supplier per order, monthly supplier/component capacities as hard bounds, qualification, approved sourcing, minimum order quantities and the presence of a supplier–plant lane. It does not use Olist model scores or post-receipt delivery outcomes.

| Synthetic assignment result | Model output |
| --- | ---: |
| Purchase orders | 16 |
| Candidate supplier assignments | 80 |
| Supplier/component monthly capacities considered | 5 |
| Ordered units | 13,900 |
| Baseline synthetic landed cost | $1,928,061 |
| Exact feasible minimum landed cost | $1,698,024 |
| **Hypothetical difference, NOT verified savings** | **$230,037** |
| Solver nodes | 351 |
| Independent reference method | 0/1 knapsack, same exact cost optimum |
| Monthly hard-capacity violations | 0 |
| Real procurement actions | DISABLED |

Joint synthetic capacity allocations: SUP-014 9,225 units against 9,425 capacity; SUP-045 4,675 against 18,523 capacity; other eligible suppliers 0 units in this single cost-focused demonstration. This solution is *not* a risk-resilience optimal policy, not daily feasible scheduling, not as-of contractual verification, and not an approved supplier recommendation. Cost is the only optimized objective. The earlier 500-shock paired synthetic experiment's `joint_capacity_feasibility_retested: false` remains a property of that **different** experiment.

## Explicitly unresolved — needs evidence or further design work

- **Original decision-time truth:** Olist's retrospective recorded delivery estimate, customer state and seller information are not independently backed by as-of revision/source-ingestion records. A valid join cannot prove that information was available when a decision was made.
- **Prospective accuracy and calibration:** A future, mature and independently assessed order cohort is required before certification. Do not recalibrate against the repeatedly inspected test interval and claim it is a new holdout.
- **Outcome-dependent selection:** The 58,911-order research cohort uses retrospective delivery eligibility; real-time prediction eligibility must be based on purchase-time inputs, with separately matured outcomes.
- **Supplier decisions:** The synthetic paired stress is internally consistent but has **not established joint actual capacity feasibility**, real quotations, supplier-switch causality, or realized benefit in a live system.
- **Enterprise readiness:** API-driven ERP integration, authentication/access controls, change approvals, monitoring, retention, operations runbooks and authorized enterprise data remain out of scope.
- **Copilot grounding:** Local model rewrites are optional and checked by heuristics, not mathematically proven faithful. No LLM upgrade was performed in this update.

## Safe next-stage priorities (not yet implemented)

1. Research-only deployment release: exercise app workflows in Windows, including uploads, negative testing, and browser UI inspection; pilot only on synthetic/local data.
2. Decision validation: the limited synthetic *monthly* hard-capacity experiment is now implemented; the next work is supplier-wide multi-component/day/route commitments and paired shock evaluation of jointly feasible policies, with clearly identified synthetic-only outcomes. Do not infer causal savings from Olist scores.
3. Prospective data contract: create source-controlled snapshots for order-time features and recorded label-maturity timestamps, then collect genuinely future outcomes before treating model probabilities as usable.

## Installation / use

**Safer option:** Extract the `AEGIS_Reviewed_Research_Copy.zip` somewhere separate from your existing AEGIS folder. Keep your original untouched. In the resulting `AEGIS_Standalone_App` folder, double-click `CHECK_AEGIS_UPDATE.bat` to run tests. Launch your existing application through `AEGIS_App\launch_aegis.bat`.

**Small patch option:** Back up the original `AEGIS_App` folder first. Extract `AEGIS_Reviewed_Patch.zip` into the **existing** `AEGIS_Standalone_App` folder (merge `AEGIS_App`, allow replacement of the included app.py, index.html and app.js). Double-click `CHECK_AEGIS_UPDATE.bat` after extraction. This patch changes no original CSVs, notebook cells, frozen bundle, previous audit reports, or executable configurations.

Always keep `AEGIS` as the application name and preserve the original shield/favicon. The source folders still contain historical version naming for backward compatibility.
