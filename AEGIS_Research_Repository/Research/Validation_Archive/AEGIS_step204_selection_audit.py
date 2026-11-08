#!/usr/bin/env python3
"""AEGIS Step 204: read-only Olist research-cohort selection audit.

Replicates selection rules in Version 2 Validation.ipynb Steps 164-165 and
170. Reports how outcome-dependent eligibility differs from purchase-time
eligibility. Does not train, score, optimize, or modify original data.

Standard library only. Writes aggregate-only JSON to --report if specified.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REQUIRED_FIELDS = (
    "order_id", "customer_id", "order_status", "order_purchase_timestamp",
    "order_delivered_carrier_date", "order_delivered_customer_date",
    "order_estimated_delivery_date",
)
PHASES = {
    "TRAIN": (datetime(2017, 1, 1), datetime(2017, 10, 1), datetime(2018, 1, 1)),
    "VALIDATION": (datetime(2018, 1, 1), datetime(2018, 4, 1), datetime(2018, 6, 1)),
    "TEST": (datetime(2018, 6, 1), datetime(2018, 8, 1), None),
}


def as_dt(s):
    if not s or not s.strip():
        return None
    try:
        dt = datetime.fromisoformat(s.strip())
    except ValueError as e:
        raise ValueError(f"Unparseable Olist timestamp {s!r}") from e
    if dt.tzinfo is not None:
        raise ValueError("Time-zone aware timestamp: source comparison requires a documented clock policy")
    return dt


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fresh_counts():
    keys = (
        "all_purchases", "calendar_purchase_candidates", "recorded_promise_candidates",
        "observed_delivery_outcome", "unknown_or_unobserved_outcome",
        "recorded_promise_missing_or_invalid", "strict_historical_candidates",
        "excluded_observed_due_to_chronology_or_invalid_promise",
        "labels_delivered_after_phase_cutoff", "selected_frozen_rule",
        "late_calendar_day_among_observed", "late_calendar_day_among_selected",
    )
    return {key: 0 for key in keys}


def phase_for(purchase):
    for name, (start, end, _) in PHASES.items():
        if purchase is not None and start <= purchase < end:
            return name
    return None


def analyze_rows(rows):
    counts = {name: fresh_counts() for name in PHASES}
    total = fresh_counts()
    anomaly_kinds = Counter()
    unseen_statuses = Counter()
    unique_ids = set()
    n_rows = 0
    invalid_purchase = 0
    outside_windows = 0
    outside_observed = 0
    missed_cutoff_not_strict = 0
    for row in rows:
        n_rows += 1
        oid = row["order_id"]
        if not oid or oid in unique_ids:
            raise ValueError(f"Blank or duplicate order_id at row {n_rows}")
        unique_ids.add(oid)

        purchase = as_dt(row["order_purchase_timestamp"])
        carrier = as_dt(row["order_delivered_carrier_date"])
        delivered = as_dt(row["order_delivered_customer_date"])
        estimated = as_dt(row["order_estimated_delivery_date"])
        phase = phase_for(purchase)
        if purchase is None:
            invalid_purchase += 1
        if phase is None:
            outside_windows += 1

        observed = row["order_status"] == "delivered" and delivered is not None and estimated is not None
        if not observed:
            unseen_statuses[row["order_status"]] += 1
        if phase is None and observed:
            outside_observed += 1
        carrier_before_purchase = bool(carrier and purchase and carrier < purchase)
        delivery_before_carrier = bool(delivered and carrier and delivered < carrier)
        delivery_before_purchase = bool(delivered and purchase and delivered < purchase)
        invalid_promise = bool(purchase and estimated and estimated < purchase)
        chronology = carrier_before_purchase or delivery_before_carrier or delivery_before_purchase
        if carrier_before_purchase: anomaly_kinds["carrier_before_purchase"] += 1
        if delivery_before_carrier: anomaly_kinds["delivery_before_carrier"] += 1
        if delivery_before_purchase: anomaly_kinds["delivery_before_purchase"] += 1
        if invalid_promise: anomaly_kinds["estimated_before_purchase"] += 1

        # Step 165: strict_candidate_only requires known post-delivery outcomes.
        strict = observed and not chronology and not invalid_promise
        # This is a recorded-field proxy, NOT certified as a purchase-time feature.
        recorded_promise_candidate = bool(purchase and estimated and not invalid_promise)
        calendar_late = bool(observed and delivered.date() > estimated.date())
        cutoff = PHASES[phase][2] if phase else None
        too_late = bool(strict and cutoff and delivered >= cutoff)
        selected = bool(phase and strict and not too_late)
        if phase and observed and cutoff and delivered >= cutoff and not strict:
            missed_cutoff_not_strict += 1

        for c in (total, counts[phase] if phase else None):
            if c is None:
                continue
            c["all_purchases"] += 1
            c["calendar_purchase_candidates"] += int(purchase is not None)
            c["recorded_promise_candidates"] += int(recorded_promise_candidate)
            c["recorded_promise_missing_or_invalid"] += int(not recorded_promise_candidate)
            c["observed_delivery_outcome"] += int(observed)
            c["unknown_or_unobserved_outcome"] += int(not observed)
            c["strict_historical_candidates"] += int(strict)
            c["excluded_observed_due_to_chronology_or_invalid_promise"] += int(observed and not strict)
            c["labels_delivered_after_phase_cutoff"] += int(too_late)
            c["selected_frozen_rule"] += int(selected)
            c["late_calendar_day_among_observed"] += int(calendar_late)
            c["late_calendar_day_among_selected"] += int(calendar_late and selected)

    for name, c in [*counts.items(), ("ALL_SOURCE_ORDERS", total)]:
        assert c["observed_delivery_outcome"] + c["unknown_or_unobserved_outcome"] == c["all_purchases"], name
        assert c["strict_historical_candidates"] + c["excluded_observed_due_to_chronology_or_invalid_promise"] == c["observed_delivery_outcome"], name
        assert c["selected_frozen_rule"] <= c["strict_historical_candidates"], name
        c["selected_share_of_all_purchases"] = round(c["selected_frozen_rule"] / c["all_purchases"], 6) if c["all_purchases"] else None
        c["observed_outcome_share_of_all_purchases"] = round(c["observed_delivery_outcome"] / c["all_purchases"], 6) if c["all_purchases"] else None
        c["late_rate_among_selected"] = round(c["late_calendar_day_among_selected"] / c["selected_frozen_rule"], 6) if c["selected_frozen_rule"] else None
        c["late_rate_among_observed"] = round(c["late_calendar_day_among_observed"] / c["observed_delivery_outcome"], 6) if c["observed_delivery_outcome"] else None

    if sum(c["all_purchases"] for c in counts.values()) + outside_windows != n_rows:
        raise RuntimeError("Phase coverage failed reconciliation")
    if sum(c["selected_frozen_rule"] for c in counts.values()) != total["selected_frozen_rule"]:
        raise RuntimeError("Selected-cohort totals disagree")
    return {
        "source_order_count": n_rows,
        "unique_order_id_count": len(unique_ids),
        "invalid_or_missing_purchase_timestamps": invalid_purchase,
        "purchases_outside_three_research_windows": outside_windows,
        "observed_outcomes_outside_three_windows": outside_observed,
        "all_source_orders": total,
        "phases": counts,
        "timeline_anomaly_flag_counts": dict(sorted(anomaly_kinds.items())),
        "unobserved_outcome_final_statuses": dict(sorted(unseen_statuses.items())),
        "observed_after_cutoff_but_not_strict": missed_cutoff_not_strict,
    }


def run_self_test():
    def row(oid, purchase, delivery="", status="delivered", estimate="2017-09-15 00:00:00", carrier="", customer="c"):
        return {
            "order_id": oid, "customer_id": customer, "order_status": status,
            "order_purchase_timestamp": purchase, "order_delivered_carrier_date": carrier,
            "order_delivered_customer_date": delivery,
            "order_estimated_delivery_date": estimate,
        }
    rows = [
        row("a", "2017-09-01 10:00:00", "2017-09-15 14:00:00"),  # same day as estimate -> not late
        row("b", "2017-09-02 10:00:00", "2017-09-16 10:00:00"),  # selected late
        row("c", "2017-09-03 10:00:00", "2018-01-03 10:00:00"),  # missed train cutoff
        row("d", "2017-09-04 10:00:00", "", status="canceled"), # unknown outcome
        row("e", "2017-09-05 10:00:00", "2017-09-12 10:00:00", carrier="2017-09-01 00:00:00"), # anomaly
        row("f", "2017-09-06 10:00:00", "2017-09-07 10:00:00", estimate="2017-09-01 00:00:00"), # invalid promise
        row("g", "2018-02-01 10:00:00", "2018-02-20 10:00:00", estimate="2018-02-18 00:00:00"), # validation selected
        row("h", "2018-02-02 10:00:00", "2018-06-04 10:00:00", estimate="2018-06-10 00:00:00"), # missed validation cutoff
        row("i", "2018-06-05 10:00:00", "2018-06-19 10:00:00", estimate="2018-06-20 00:00:00"), # test selected
        row("j", "2017-11-05 10:00:00", "2017-11-19 10:00:00", estimate="2017-11-20 00:00:00"), # outside windows
    ]
    a = analyze_rows(rows)
    checks = {
        "ten_orders_reconciled": a["source_order_count"] == 10,
        "train_purchase_population": a["phases"]["TRAIN"]["all_purchases"] == 6,
        "train_selection_count": a["phases"]["TRAIN"]["selected_frozen_rule"] == 2,
        "training_cutoff_exclusion": a["phases"]["TRAIN"]["labels_delivered_after_phase_cutoff"] == 1,
        "unknown_delivery_not_selected": a["phases"]["TRAIN"]["unknown_or_unobserved_outcome"] == 1,
        "strict_selection_excludes_two_anomalies": a["phases"]["TRAIN"]["excluded_observed_due_to_chronology_or_invalid_promise"] == 2,
        "same_day_delivery_not_late": a["phases"]["TRAIN"]["late_calendar_day_among_selected"] == 1,
        "validation_selection_count": a["phases"]["VALIDATION"]["selected_frozen_rule"] == 1,
        "validation_cutoff_exclusion": a["phases"]["VALIDATION"]["labels_delivered_after_phase_cutoff"] == 1,
        "test_selection_count": a["phases"]["TEST"]["selected_frozen_rule"] == 1,
        "out_of_period_reported": a["purchases_outside_three_research_windows"] == 1,
        "totals_reconciled": a["all_source_orders"]["selected_frozen_rule"] == 4,
    }
    print(json.dumps({"study": "AEGIS_STEP_204_SELECTION_AUDIT_SELF_TEST", "checks": checks,
                      "passed": sum(checks.values()), "total": len(checks),
                      "all_pass": all(checks.values())}, indent=2))
    if not all(checks.values()):
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true", help="Use 10 fictional fixtures, no Olist file required")
    p.add_argument("--orders", type=Path, help="Original Olist orders CSV")
    p.add_argument("--baseline", type=Path, help="Optional frozen Step 200 audit JSON for reconciliation")
    p.add_argument("--report", type=Path, help="Aggregate-only output JSON; original CSV is never changed")
    args = p.parse_args()
    if args.self_test:
        run_self_test()
        return
    if args.orders is None:
        p.error("--orders is required unless using --self-test")
    if not args.orders.is_file():
        p.error(f"Original Olist CSV not found: {args.orders}")

    digest = sha256_file(args.orders)
    baseline = None
    if args.baseline:
        with open(args.baseline, "r", encoding="utf-8") as f:
            baseline = json.load(f)
        known_hash = baseline.get("original_csv_sha256")
        if known_hash and digest != known_hash:
            raise RuntimeError("Olist source SHA256 differs from Step 200 baseline. Stop: check source files.")
    with open(args.orders, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = set(REQUIRED_FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Original CSV missing fields: {sorted(missing)}")
        results = analyze_rows(reader)

    results["study"] = "AEGIS_STEP_204_OUTCOME_DEPENDENT_SELECTION_AUDIT"
    results["status"] = "RETROSPECTIVE_SELECTION_AUDITED_NOT_PROSPECTIVE"
    results["original_csv_sha256"] = digest
    results["source_definition"] = "Frozen Step 165 strict eligibility and Step 170 B_WITH_GAPS selection"
    results["feature_contract"] = {
        "calendar_only": "Purchase timestamp is present; other required data provenance not audited",
        "recorded_promise_proxy": "Recorded estimated timestamp exists and is not before purchase, but availability at purchase has NOT been proven",
        "geography": "Customer location was NOT examined; it may need independent as-of verification",
    }
    results["limitations"] = [
        "Strict selection depends on final status/delivery and is not a prospective prediction eligibility rule",
        "Observed-only late rates cannot establish population-wide late rates for missing/undelivered outcomes",
        "The saved estimated delivery date is not independently proven to be the originally communicated promise",
        "Recorded delivery time does not independently prove when the source outcome became available to an operator",
        "The previously inspected test period is not a pristine held-out prospective evaluation",
        "This is an audit, not model training, causal evaluation or operational authorization",
    ]
    if baseline:
        checks = {
            "source_registry_count": results["source_order_count"] == baseline.get("original_order_registry_count"),
            "frozen_cohort_total": results["all_source_orders"]["selected_frozen_rule"] == baseline.get("frozen_scored_order_count"),
        }
        for name, count in results["phases"].items():
            expected = baseline.get("phase_tagged_cohorts", {}).get(name, {}).get("scored_orders")
            checks[f"{name.lower()}_selected_count"] = (expected is not None and count["selected_frozen_rule"] == expected)
        results["step200_count_reconciliation"] = {"checks": checks, "all_pass": all(checks.values())}
        if not all(checks.values()):
            results["status"] = "FROZEN_COHORT_RECONCILIATION_MISMATCH_INVESTIGATE"
    if args.report:
        if args.report.resolve() == args.orders.resolve():
            raise ValueError("Report path must not overwrite the source CSV")
        if args.baseline and args.report.resolve() == args.baseline.resolve():
            raise ValueError("Report path must not overwrite the baseline report")
        if args.report.exists():
            raise FileExistsError(f"Report already exists; refusing overwrite: {args.report}")
        args.report.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("AEGIS STEP 204 — read-only selection audit")
    print("Olist orders:", results["source_order_count"])
    print("Calendar purchase candidates:", results["all_source_orders"]["calendar_purchase_candidates"])
    print("Recorded promise candidates (as-of NOT certified):", results["all_source_orders"]["recorded_promise_candidates"])
    print("Observed delivery outcomes:", results["all_source_orders"]["observed_delivery_outcome"])
    print("Strict historical candidates:", results["all_source_orders"]["strict_historical_candidates"])
    print("Selected frozen cohort:", results["all_source_orders"]["selected_frozen_rule"])
    for name, c in results["phases"].items():
        print(f" {name}: all={c['all_purchases']}, observed={c['observed_delivery_outcome']}, strict={c['strict_historical_candidates']}, cutoff_excluded={c['labels_delivered_after_phase_cutoff']}, selected={c['selected_frozen_rule']}")
    if baseline:
        print("Step 200 counts reconciled:", results["step200_count_reconciliation"]["all_pass"])
    print("STATUS:", results["status"])
    if args.report:
        print("Aggregate report:", args.report)


if __name__ == "__main__":
    main()
