"""AEGIS Step 200: read-only, retrospective Olist outcome/score integrity audit.

No new model fitting. No proof of future accuracy, contractual lateness,
feature-as-of provenance, or causal supplier effects. This script reads the
original Olist order table and the previously frozen AEGIS app export only.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from hashlib import sha256
from io import StringIO
import json
import math
from pathlib import Path
from types import SimpleNamespace

from historical_outcomes import HistoricalOutcomes, MAX_OUTCOME_UPLOAD_BYTES
from prospective_validation import _auc, _average_precision


ROOT = Path(__file__).resolve().parent
DEFAULT_BUNDLE = ROOT / "data" / "aegis_bundle.json"
MIN_GROUP = 30
COMPARABLE = {"BEFORE_ESTIMATE", "ON_ESTIMATE_DATE", "AFTER_ESTIMATE"}


def _instant(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Missing timestamp")
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if value.tzinfo is not None and value.utcoffset() is None:
        raise ValueError("Unresolvable UTC offset")
    return value


def _metrics(items, total, minimum):
    mature = len(items)
    late = sum(label for label, _ in items)
    both_classes = 0 < late < mature
    rank_ready = mature >= minimum and both_classes
    return {
        "scored_orders": total,
        "comparable_delivered_orders": mature,
        "excluded_or_unknown_outcomes": total - mature,
        "late_after_estimated_calendar_date": late,
        "on_or_before_estimated_date": mature - late,
        "late_rate_among_comparable": round(late / mature, 6) if mature else None,
        "research_ranking_auc": _auc(items) if rank_ready else None,
        "research_ranking_average_precision": _average_precision(items) if rank_ready else None,
        "ranking_metric_not_available_reason": None if rank_ready else
            "INSUFFICIENT_COMPARABLE_ORDERS_OR_SINGLE_OUTCOME_CLASS",
    }


def audit(frozen, raw, *, filename="olist_orders_dataset.csv", min_group=MIN_GROUP):
    """Return aggregate-only outcomes; suppress ranking metrics on any ID/time breach.

    `frozen` is an already verified ResearchStore or a synthetic test fixture.
    The research bundle itself must be validated by ResearchStore.load first.
    """
    if not frozen.ready:
        raise ValueError("Frozen research bundle is not verified/available")
    if not isinstance(min_group, int) or isinstance(min_group, bool) or min_group < 2:
        raise ValueError("Invalid minimum group size")

    source_ids = frozen.bundle["original_order_ids"]
    recorded = HistoricalOutcomes(filename, raw, source_ids)
    scored = frozen.orders
    expected_scored = {str(row["order_id"]) for row in scored}
    if len(expected_scored) != len(scored) or not expected_scored.issubset(source_ids):
        raise ValueError("Frozen scored-order registry is invalid")

    # HistoricalOutcomes has already verified exact registry membership,
    # uniqueness, row counts and source delivery semantics. Re-read purchase
    # timestamps for *scored IDs only*, never export raw IDs or full records.
    reader = csv.DictReader(StringIO(raw.decode("utf-8-sig"), newline=""))
    purchase_by_scored_id = {}
    for row in reader:
        oid = row["order_id"].strip()
        if oid in expected_scored:
            purchase_by_scored_id[oid] = row["order_purchase_timestamp"]

    errors = Counter()
    phase_items = defaultdict(list)
    phase_totals = Counter()
    month_items = defaultdict(list)
    month_totals = Counter()
    all_items = []

    for row in scored:
        oid = str(row["order_id"])
        phase = str(row.get("Phase", "UNKNOWN")).upper().strip()
        phase_totals[phase] += 1
        try:
            source_purchase = _instant(purchase_by_scored_id[oid])
            frozen_purchase = _instant(row["Purchase_Time"])
            research_score = float(row["Research_Score_Uncalibrated"])
            if not math.isfinite(research_score):
                raise ValueError("Non-finite score")
            if source_purchase != frozen_purchase:
                errors["FROZEN_PURCHASE_TIMESTAMP_DIFFERS_FROM_SOURCE"] += 1
                continue
        except (KeyError, TypeError, ValueError, OverflowError):
            errors["INVALID_OR_ABSENT_SCORED_PURCHASE_OR_SCORE"] += 1
            continue
        month = source_purchase.strftime("%Y-%m")
        month_totals[month] += 1
        relation = recorded.by_id[oid]["relation"]
        if relation not in COMPARABLE:
            continue
        pair = (int(relation == "AFTER_ESTIMATE"), research_score)
        all_items.append(pair)
        phase_items[phase].append(pair)
        month_items[month].append(pair)

    good = not errors and sum(month_totals.values()) == len(scored)
    # Even a partial/misaligned cohort must not report potentially misleading
    # ranking metrics; its counts are kept for troubleshooting only.
    total = _metrics(all_items, len(scored), min_group)
    phases = {phase: _metrics(phase_items[phase], size, min_group)
              for phase, size in sorted(phase_totals.items())}
    months = {month: _metrics(month_items[month], size, min_group)
              for month, size in sorted(month_totals.items())}
    if not good:
        for item in [total, *phases.values(), *months.values()]:
            item["research_ranking_auc"] = None
            item["research_ranking_average_precision"] = None
            item["ranking_metric_not_available_reason"] = "SOURCE_ALIGNMENT_BLOCKED"

    return {
        "product": "AEGIS",
        "study": "STEP_200_RETROSPECTIVE_OLIST_RECONCILIATION",
        "status": "RETROSPECTIVE_SOURCE_ALIGNED_NOT_PROSPECTIVE" if good else
                  "BLOCKED_SOURCE_OR_FROZEN_PURCHASE_TIME_MISMATCH",
        "original_csv_sha256": sha256(raw).hexdigest(),
        "bundle_recorded_sha256": frozen.bundle.get("content_sha256"),
        "original_order_registry_count": recorded.summary["source_orders"],
        "original_outcome_semantics": dict(recorded.summary),
        "frozen_scored_order_count": len(scored),
        "source_alignment_issue_counts": dict(sorted(errors.items())),
        "overall_scored_cohort": total,
        "phase_tagged_cohorts": phases,
        "purchase_month_cohorts": months,
        "ranking_group_minimum": min_group,
        "input_records_written": False,
        "frozen_model_modified": False,
        "new_model_training": "NONE",
        "future_features_independently_proven_asof": False,
        "holdout_isolation_independently_verified": False,
        "contractual_delivery_promise_certified": False,
        "prospective_accuracy_certified": False,
        "risk_probabilities_calibrated": False,
        "supplier_causality_established": False,
        "operational_approval": "NOT_GRANTED",
        "automatic_business_action": "DISABLED",
        "interpretation": (
            "Historical source-record comparison only: observed delivery calendar "
            "date versus Olist estimated date. All displayed performance numbers "
            "are retrospective ranking statistics for the comparable, already-" 
            "delivered selected cohort. Source purchase-time equality is a "
            "consistency test, NOT evidence that model features were available "
            "at decision time, nor that the holdout remained untouched. "
            "Excluded outcomes may bias rates. No causal or operational claim."
        ),
    }


def _fixture():
    source = (
        "order_id,order_status,order_purchase_timestamp,order_estimated_delivery_date,"
        "order_delivered_customer_date\n"
        "A,delivered,2018-07-01 10:00:00,2018-07-10,2018-07-11\n"
        "B,delivered,2018-07-02 10:00:00,2018-07-10,2018-07-09\n"
        "C,canceled,2018-07-03 10:00:00,2018-07-10,\n"
        "D,delivered,2018-07-04 10:00:00,2018-07-10,2018-07-12\n"
    ).encode()
    frozen = SimpleNamespace(ready=True, bundle={"original_order_ids": ["A", "B", "C", "D"],
                                            "content_sha256": "fixture"}, orders=[
        {"order_id": "A", "Phase": "TEST", "Purchase_Time": "2018-07-01T10:00:00", "Research_Score_Uncalibrated": .9},
        {"order_id": "B", "Phase": "TEST", "Purchase_Time": "2018-07-02T10:00:00", "Research_Score_Uncalibrated": .1},
        {"order_id": "C", "Phase": "TRAIN", "Purchase_Time": "2018-07-03T10:00:00", "Research_Score_Uncalibrated": .5},
        {"order_id": "D", "Phase": "TRAIN", "Purchase_Time": "2018-07-04T10:00:00", "Research_Score_Uncalibrated": .7},
    ])
    return frozen, source


def self_test():
    frozen, source = _fixture()
    report = audit(frozen, source, min_group=2)
    from copy import deepcopy
    invalid = deepcopy(frozen)
    invalid.orders[0]["Purchase_Time"] = "2018-07-05T00:00:00"
    blocked = audit(invalid, source, min_group=2)
    checks = {
        "source_registry_reconciled": report["original_order_registry_count"] == 4,
        "canceled_not_labeled_on_time": report["overall_scored_cohort"]["comparable_delivered_orders"] == 3,
        "historical_auc_correct": report["overall_scored_cohort"]["research_ranking_auc"] == 1.0,
        "month_coverage_complete": report["purchase_month_cohorts"]["2018-07"]["scored_orders"] == 4,
        "mismatch_suppresses_all_ranking_metrics": blocked["overall_scored_cohort"]["research_ranking_auc"] is None,
        "no_causal_or_prospective_claim": not report["prospective_accuracy_certified"] and not report["supplier_causality_established"],
        "no_business_actions": report["automatic_business_action"] == "DISABLED",
    }
    return {"step": 200, "fixture": "SOFTWARE_ONLY_NOT_ACTUAL_OLIST_EVIDENCE",
            "checks": checks, "all_pass": all(checks.values())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="Run invented software fixtures only")
    parser.add_argument("--olist-orders", type=Path, help="Original, unmodified Olist orders CSV")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE,
                        help="Existing frozen AEGIS app data/aegis_bundle.json")
    parser.add_argument("--report", type=Path, help="New output JSON file; never overwrites")
    args = parser.parse_args(argv)
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2))
        return 0 if result["all_pass"] else 1
    if not args.olist_orders or not args.report:
        parser.error("--olist-orders and --report are required without --self-test")
    if args.report.exists():
        parser.error("Report already exists. Choose a fresh filename.")
    if not args.olist_orders.is_file() or args.olist_orders.stat().st_size > MAX_OUTCOME_UPLOAD_BYTES:
        parser.error("Original Olist CSV is missing or exceeds 30 MB")
    from app import ResearchStore
    frozen = ResearchStore(args.bundle)
    if not frozen.ready:
        parser.error(frozen.error)
    result = audit(frozen, args.olist_orders.read_bytes(), filename=args.olist_orders.name)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("AEGIS — STEP 200 HISTORICAL OUTCOME AUDIT (NO RETRAINING)")
    print("Source registry:", result["original_order_registry_count"])
    print("Frozen scored orders:", result["frozen_scored_order_count"])
    print("Recorded date-comparable scored orders:", result["overall_scored_cohort"]["comparable_delivered_orders"])
    print("Purchase-time alignment:", result["status"])
    print("Historical rank AUC (if available):", result["overall_scored_cohort"]["research_ranking_auc"])
    print("Prospective accuracy: NOT CERTIFIED | Contractual SLA: NOT CERTIFIED")
    print("Business action: DISABLED | Report:", args.report.resolve())
    return 0 if result["status"].startswith("RETROSPECTIVE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
