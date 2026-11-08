# AEGIS — Validation and Limitations Register

Research audit based on the saved `Version 2 Validation.ipynb` notebook, its
Steps 150R–188, the original integrated synthetic dataset ZIP, the Step
191–196 safety gates, and the local application tests. This register is
intentionally separate from language-model and interface development.

## Status language

- **TESTED IN SOFTWARE**: A finite, reproducible check passed on a test input.
- **RESEARCH EVALUATED**: Historical/synthetic result was measured; it is not a
  validated operational claim.
- **AWAITING ORIGINAL RECORDS**: The data or independent source provenance is
  unavailable to this local release.
- **AWAITING PROSPECTIVE EVIDENCE**: Requires fresh operational observations,
  appropriate outcomes, and an evaluation protocol fixed before observation.

No status below means AEGIS may execute orders, change suppliers, or send
instructions to a business system. All such actions remain disabled.

## Current software-validation results (Steps 191–196)

These controls were exercised using the original integrated **synthetic**
dataset ZIP and deliberately invented safety-test fixtures. No company ERP,
supplier, carrier or contractual record was accessed. No model was retrained.

| Gate | Tested result | What it does **not** establish |
|---|---|---|
| Step 191 — paired synthetic stress | 80/80 source-derived supplier/order pairs; 500 shared hypothetical scenarios per pair; 40,000 paired rows | Real-world supplier benefit, delay or service improvement |
| Step 192 — as-of and allocation coherence | 9/9 software controls, including joint source-snapshot capacity and demand-to-allocation reconciliation | Genuine source timestamps, outside reservations, actual available capacity or units |
| Step 193 — historical Olist delivery semantics | 8/8 software controls, including status-confirmed delivery and exclusion counts | Contractually binding promised delivery date or certified SLA |
| Step 194 — prospective shadow-evaluation gate | 10/10 software controls, including feature availability at the time of scoring and model ID consistency | Verified future accuracy, calibrated probabilities, immutable source/model identity |
| Step 196 — intervention comparison gate | 7/7 software controls; descriptive CONTROL/TREATMENT comparison is guarded | Random assignment, actual intervention, causality or commercial ROI |

**34/34 combined software controls** (Steps 192–196) and **64/64
application tests** (including Step 200 audit fixtures) passed in the
development environment. Windows confirmation for Step 200 is pending.
These are necessary code checks, not external validation or production
certification. The original historical model scores remain uncalibrated.

## Seven remaining empirical validity limits

| Limit | Existing evidence | Remaining acceptance condition | Current status |
|---|---|---|---|
| Prospective validation | Step 194 shadow-evaluation gate; **0 independently verified prospective operational outcomes**. | Pre-registered prospective shadow study on genuinely unseen, outcome-mature real orders; independent evaluator and immutable predictions. | SOFTWARE GATE TESTED; AWAITING PROSPECTIVE EVIDENCE |
| Probability calibration | Steps 171, 175, 179 and 181 report metrics and drift. | Stable temporal calibration on held-out prospective data; reliability intervals, subgroup checks, abstention rules, and explicit deployment threshold approval. | RESEARCH EVALUATED; NOT CERTIFIED |
| Decision-time provenance and holdout | Steps 192/194 reject late-known features, expired input snapshots, and mismatched logged model identities. | Source-system audit history, signed model artifact/checksum, genuinely separate untouched future holdout and independent scoring-log verification. | SOFTWARE GATE TESTED; EXTERNAL ATTESTATION MISSING |
| Delivery-promise semantics | Step 193 excludes undelivered, canceled or impossible outcomes rather than guessing. | Data owner confirms estimated date vs contractual promise, timezone and calendar rules, partial delivery and cancellation policy. | SOFTWARE SEMANTICS TESTED; BUSINESS PROMISE PROVISIONAL |
| Supplier causality | Steps 135–161 model-dependence and coverage audits. | Verified comparison design, confounding control, supply assignment history and independent causal/operational evaluation. | NOT ESTABLISHED |
| Intervention effectiveness | Synthetic cost/capacity/Pareto exercises; Step 196 guards comparison group chronology. | Actual feasible alternatives, independently measured intervention results, pre-specified controls and savings/service trade-offs. | SOFTWARE GATE TESTED; NO REAL INTERVENTION |
| Genuine operational inputs | Step 182 defines eight canonical business tables; Steps 192/195 test shared-source snapshot capacity and demand coverage; Mode 3 connector inspects schema only. | Approved read-only genuine decision-time quotes, capacity, eligibility, allocations, cost basis, outcomes, and intervention logs; source-owner review. | SOFTWARE GATE TESTED; AWAITING ORIGINAL RECORDS |

## Newly completed: independent full-menu synthetic stress structure

**`paired_stress.py`** reconstructs the 2025-07 `CMP-007` pilot from four
unaltered source CSVs in the original integrated synthetic dataset ZIP.

- 16 synthetic orders × five eligible suppliers = **80 pairs**.
- 500 reproducible shared exogenous-shock scenarios per pair = **40,000 rows**.
- Every pair has exactly one record for every scenario; one baseline supplier
  per order; all baseline self-comparisons equal zero.
- Scenarios expose the complete common global/region shock vector; results are
  checked with three *assumed* weights.
- Source CSV SHA-256 hashes are recorded; source files are never overwritten.
- Independent common-shock coverage checks: **6 passed**.

This **does not repair the old frozen-model simulation retroactively**. The
original Step 158–161 audit saw 43 of 80 unique candidate pairs. The new
experiment is *separate* and deliberately uses a hypothetical, dimensionless
stress index. Its formula is disclosed in the generated `audit_report.json`.
It does **not** predict delivery delay, prove a preferred supplier, or produce
an approved procurement recommendation.

## Newly completed: Step 192 decision-time software gate

`asof_validation.py` independently checks the eight original Step 182
business-table schemas without requiring a live company connection:

- Explicit timezone-aware decision and information-availability timestamps.
- Basic source-key, field-completeness and cross-table reconciliation.
- Quotes and capacity snapshots recorded and still valid at the decision time.
- Source-listed supplier eligibility, minimum-order quantity and individual
  recorded capacity bounds at the decision time.
- Outcome recording time relative to actual delivery and unobserved outcomes.
- Comparison group assignment before decision, and execution-log human approval.
- Nine software-only positive/negative fixture controls pass.
- The sum of baseline allocations must match every order item's recorded
  demand; shortfalls and over-allocations are reported.
- Multiple allocations jointly using the **same** supplier/item capacity
  snapshot must not exceed its recorded availability. This does not detect
  outside reservations, replenishment, or true unit compatibility.

It returns issue counts, never uploads source rows, and does not modify any
source business data. Even if all checks pass, its status remains
`STRUCTURE_AND_ASOF_CONSISTENT_UNATTESTED`. A corrupt, backfilled, fabricated,
or revised source timestamp cannot be detected from these tables alone;
independent source-system attestation is still required. Source-owner
definitions, external capacity reservations, currency compatibility, model
calibration, prospective validity, causal benefit and security approval remain
**not certified**. Automatic actions remain disabled.

## Step 193 — recorded historical delivery semantics

Attaching the original `olist_orders_dataset.csv` to the app now requires
`order_status`, actual delivery, estimated delivery and purchase timestamps,
as well as the exact original order ID. The before/on/after comparison admits
only **status-confirmed delivered** rows with coherent dates. Undelivered,
canceled, contradictory, missing, impossible or timezone-incompatible rows
are separately counted as exclusions. The denominator reconciles to the
original order registry. Eight synthetic fixture checks pass. Olist's
**estimated** delivery date is not independently certified as a contractual
promise, so these counts are not business-approved on-time delivery KPIs.

## Step 194 — frozen-model prospective shadow evaluation

`prospective_validation.py` takes an explicitly fixed JSON research plan,
timestamped score logs, model identity/digest and later recorded outcomes.
It rejects after-the-fact scores, source features known only after scoring,
model-version/digest mismatches, inconsistent chronology, and insufficient
mature outcomes. With a coherent mature cohort, it computes tie-aware AUC
and average precision **for ranking**, never a calibrated probability or
certified prediction. Ten software-only controls pass. A hash entered into
a CSV and self-declared timestamps do not establish an actual frozen model,
reserved holdout, independent registration or tamper-proof history.

## Step 195 — joint allocation integrity

Part of the Step 192 validator: checks each baseline allocation against its
own valid-time quote and capacity, adds quantities sharing one capacity
snapshot, and reconciles each demand line's required units against all its
baseline allocated units. These conservative tests catch internal source
contradictions; they cannot see capacity reserved outside the input tables,
restocking, currency conversion, labor constraints or contractual eligibility.

## Step 196 — intervention-comparison readiness

`intervention_evidence.py` accepts the Step 182 eight-table contract plus a
fixed comparison window and endpoint. It checks CONTROL/TREATMENT assignments
were made in time, whether as-of constraints are coherent, and whether
recorded outcomes are mature. With coherent and complete groups it can show
an **observed descriptive difference** in late-date rates. Seven software
controls pass. It cannot establish that a supplier switch occurred or that
the switch **caused** any difference. Assignment selection, confounding,
actual execution and independently measured costs still require external
review. No purchasing or supplier change is ever performed.

## Step 200 — full historical Olist reconciliation and drift inspection

`olist_temporal_audit.py` is a **new read-only retrospective check**. It needs
the existing original `olist_orders_dataset.csv` and the **already exported**
`AEGIS_App/data/aegis_bundle.json`; no Jupyter run, model retraining or new
dataset is required. It validates exact order-ID registry coverage against the
99,441-order source and checks the 58,911 frozen score records against the
original purchase timestamps. Orders not marked delivered, lacking comparable
delivery dates, or displaying contradictory source data are excluded.

The audit optionally reports descriptive **historical ranking** AUC and
average precision for the observed comparable subset, with phase and
purchase-month breakdowns where both classes and a sufficient sample exist.
It suppresses ranking metrics if any scored purchase-time record is
misaligned. Counts, excluded fractions and source hashes remain visible in
the report. Any observed temporal drift is **retrospective**, not a measure of
prospective generalization. The frozen `Phase` tag alone is not proof that
train/validation/test isolation was independently enforced; an exact purchase
timestamp match does not attest feature availability or source revisions.
Olist's estimated date is **not** a certified contractual promise. Selection
of only delivered/comparable records can bias results; intervention effects,
future accuracy and probability calibration remain unverified.

Seven invented Step 200 software fixture checks pass. To run the actual local
audit in your `AEGIS_Standalone_App` Command Prompt, supply the original Olist
file at its existing location:

```bat
python AEGIS_App\olist_temporal_audit.py --olist-orders "C:\Users\VISHAL\OneDrive\Desktop\AEGIS\AEGIS_Public_Data\Olist_Raw\archive\olist_orders_dataset.csv" --report "AEGIS_step200_olist_temporal_audit.json"
```

This creates a **new JSON report** in `AEGIS_Standalone_App`, refuses to
overwrite an existing report, prints only aggregate figures, and leaves the
source file and frozen model unchanged. It will not mark a real-world
deployment approved, even if historical reconciliation passes.

## One-command local validation status

Open Windows Command Prompt in your existing `AEGIS_Standalone_App` folder.
If its parent folder still has the original integrated synthetic dataset's
`data` directory, run:

```bat
python AEGIS_App\validation_suite.py --synthetic-source ".." --report "AEGIS_validation_foundation_report.json"
```

The command prints a brief result and creates a detailed JSON evidence report
with source hashes, experiment flags and unresolved limitations. It refuses
to overwrite an existing report. If original synthetic data are unavailable,
omit `--synthetic-source` and run the software fixtures alone. Independently:

```bat
python AEGIS_App\asof_validation.py --self-test
python AEGIS_App\prospective_validation.py --self-test
python AEGIS_App\intervention_evidence.py --self-test
```

These self-tests contain **no actual company records**. They can verify
software behavior but cannot certify operational outcomes.

## Historical quality caution

Step 181's frozen-model time-window tests show strong temporal variation. For
example, the calendar-promise-state model's historical AUC was approximately
**0.590** (2017 Q4 gap), **0.615** (2018 Apr–May gap), and **0.715** (2018 Aug
later), with substantial changes in observed and predicted late proportions.
These are retrospective research windows, not prospective or live-company
verification. Avoid the terms "reliable risk probability" or "production
forecaster" based on this evidence.

## Suggested remaining order of work (before LLM development)

1. **Next — Independently verified decision-time data:** test Step 192 on
   explicitly authorized original source-system history with revision logs;
   obtain source-owner attestation. Its synthetic fixture passing does not
   establish that the source timestamps are true. Add explicit currency,
   units, and contractual business definitions before any feasibility claim.
2. **Semantics and label policy:** document exact source-owner definition of
   *promised*, *estimated*, *late*, *cancelled*, *partially delivered*, and
   *unknown*, including timezone, corrections, and missingness.
3. **Prediction evidence:** use genuinely fresh decision-time snapshots with
   mature outcomes to audit calibration, temporal/subgroup drift, coverage,
   abstention, confidence intervals, and external reproducibility. **No
   retraining or deployment approval merely to make metrics look better.**
4. **Recovery feasibility:** obtain verified valid-time quotes, bill of
   materials, MOQ, capacity, supplier eligibility, lead times, cost currency,
   and baseline sourcing decisions; test chronological constraints and
   no-good-case behavior on these real records.
5. **Intervention evaluation:** pre-register comparative method with the
   business, obtain approvals and consent where applicable, measure actual
   intervention outcomes and uncertainty. Do not claim causal supplier
   benefits from observational risk rankings alone.
6. **Operational readiness/security:** company-specific connector, access
   review, secrets controls, audit retention, human authorization, model
   monitoring and rollback procedure. No autonomous business action is
   implemented in the research app.

## Independent proof needed from a future company pilot

The app can accept a local file and inspect its shape, but a local upload alone
cannot establish when an ERP record first became known. Independent evidence
is needed from the source-system owner. The notebook's eight canonical tables
are `orders_at_decision`, `demand_lines`, `supplier_quotes`,
`supplier_capacity`, `baseline_allocations`, `realized_outcomes`,
`decision_log`, and `comparison_assignment`. Business definitions and source
system timestamp/version attestations are additional requirements.

Until these gates are met, AEGIS remains a **local research decision-support
prototype**, with human review required, procurement disabled, and no
operational certification.
