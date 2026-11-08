"""AEGIS Step 196: cautious read-only intervention-comparison audit.

This can describe source-recorded experimental groups if eight canonical
tables and a predeclared plan are supplied. It never proves supplier causality
or estimates verified causal benefit; those require independent design and
assignment review, source attestation, and mature prospective evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from asof_validation import _fixture, _timestamp, load_csv_folder, validate


ENDPOINT = "ESTIMATED_CALENDAR_DAY_RESEARCH_ONLY"


def _as_day(value):
    text = str(value or "").strip()
    if len(text) != 10:
        raise ValueError("Date must be YYYY-MM-DD")
    return date.fromisoformat(text)


def _plan(plan):
    expected = ("registered_at", "evaluation_start", "evaluation_end",
                "outcome_freeze_at", "endpoint", "minimum_mature_per_group")
    if not isinstance(plan, dict) or any(field not in plan for field in expected):
        raise ValueError("A complete comparison plan is required.")
    if plan["endpoint"] != ENDPOINT:
        raise ValueError("The endpoint must be explicitly research-only.")
    times = {key: _timestamp(plan[key]) for key in expected[:4]}
    if not (times["registered_at"] <= times["evaluation_start"]
            < times["evaluation_end"] < times["outcome_freeze_at"]):
        raise ValueError("The research plan has an invalid chronology.")
    minimum = plan["minimum_mature_per_group"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 2:
        raise ValueError("Require at least two mature outcomes per research group.")
    return times


def evaluate_comparison(tables, plan):
    """No input mutation; output reports aggregated counts only."""
    times = _plan(plan)
    provenance = validate(tables)
    order_rows = tables.get("orders_at_decision", ([], []))[1]
    group_rows = tables.get("comparison_assignment", ([], []))[1]
    outcome_rows = tables.get("realized_outcomes", ([], []))[1]
    orders = {row.get("order_id"): row for row in order_rows}
    groups = {}
    errors = Counter()

    for row in group_rows:
        oid = str(row.get("order_id", ""))
        group = str(row.get("evaluation_group", "")).strip().upper()
        if group not in ("CONTROL", "TREATMENT"):
            errors["INVALID_OR_UNDECLARED_GROUP"] += 1
            continue
        if oid in groups:
            errors["DUPLICATE_GROUP_ASSIGNMENT"] += 1
            continue
        if oid not in orders:
            errors["GROUP_ORDER_NOT_FOUND"] += 1
            continue
        try:
            assignment = _timestamp(row["assignment_timestamp"])
            decision = _timestamp(orders[oid]["decision_timestamp"])
        except (KeyError, ValueError, TypeError, OverflowError):
            errors["INVALID_ASSIGNMENT_DECISION_TIMESTAMP"] += 1
            continue
        if not times["evaluation_start"] <= decision <= times["evaluation_end"]:
            errors["OUTSIDE_PREREGISTERED_WINDOW"] += 1
            continue
        if assignment < times["registered_at"] or assignment > decision:
            errors["GROUP_ASSIGNED_OUTSIDE_PREDECISION_PLAN"] += 1
            continue
        groups[oid] = group

    outcomes = {}
    for row in outcome_rows:
        oid = str(row.get("order_id", ""))
        if oid in outcomes:
            errors["DUPLICATE_OUTCOME_ID"] += 1
            continue
        outcomes[oid] = row

    assigned_counts = Counter(groups.values())
    mature_counts = Counter()
    late_counts = Counter()
    not_mature = Counter()
    for oid, group in groups.items():
        row = outcomes.get(oid)
        if row is None or str(row.get("actual_delivery_timestamp", "")).strip() == "":
            not_mature[group] += 1
            continue
        if str(row.get("order_id", "")) != oid or str(row.get("actual_delivery_timestamp", "")).strip() == "":
            not_mature[group] += 1
            continue
        delivery_status = str(row.get("delivery_status") or row.get("order_status") or "").strip().lower()
        if not delivery_status:
            errors["MISSING_VERIFIED_DELIVERY_STATUS"] += 1
            continue
        if delivery_status != "delivered":
            not_mature[group] += 1
            continue
        try:
            actual = _timestamp(row["actual_delivery_timestamp"])
            recorded = _timestamp(row["outcome_recorded_at"])
            promise = _as_day(orders[oid]["promised_delivery_date"])
            decision = _timestamp(orders[oid]["decision_timestamp"])
        except (KeyError, ValueError, TypeError, OverflowError):
            errors["INVALID_OUTCOME_FOR_ASSIGNED_ORDER"] += 1
            continue
        if actual < decision or recorded < actual:
            errors["OUTCOME_CHRONOLOGY_CONFLICT"] += 1
            continue
        if recorded > times["outcome_freeze_at"]:
            not_mature[group] += 1
            continue
        mature_counts[group] += 1
        late_counts[group] += int(actual.date() > promise)

    enough = all(mature_counts[g] >= plan["minimum_mature_per_group"] for g in
                 ("CONTROL", "TREATMENT"))
    missing = sum(not_mature.values())
    if provenance["issues_total"] or errors:
        status = "BLOCKED_SOURCE_OR_DESIGN_INTEGRITY"
    elif missing:
        status = "INCOMPLETE_PROSPECTIVE_OUTCOMES"
    elif not enough:
        status = "INSUFFICIENT_COMPARISON_SAMPLE"
    else:
        status = "DESCRIPTIVE_GROUP_DIFFERENCE_ONLY_UNATTESTED"

    rates = {
        key.lower(): round(late_counts[key] / mature_counts[key], 6)
        if mature_counts[key] and status.startswith("DESCRIPTIVE") else None
        for key in ("CONTROL", "TREATMENT")
    }
    difference = (round(rates["treatment"] - rates["control"], 6)
                  if all(v is not None for v in rates.values()) else None)
    return {
        "product": "AEGIS",
        "study": "STEP_196_INTERVENTION_COMPARISON_READINESS",
        "status": status,
        "group_assignment_count": {k.lower(): assigned_counts[k] for k in ("CONTROL", "TREATMENT")},
        "mature_outcomes_by_group": {k.lower(): mature_counts[k] for k in ("CONTROL", "TREATMENT")},
        "unobserved_outcomes_by_group": {k.lower(): not_mature[k] for k in ("CONTROL", "TREATMENT")},
        "source_validation_issues": provenance["issues_total"],
        "design_issue_counts": dict(sorted(errors.items())),
        "recorded_late_rate_by_group": rates,
        "descriptive_treatment_minus_control": difference,
        "assignment_procedure_independently_verified": False,
        "intervention_execution_independently_verified": False,
        "source_provenance_independently_verified": False,
        "true_supplier_causality_certified": False,
        "true_intervention_benefit_certified": False,
        "prospective_operational_performance_certified": False,
        "new_model_training": "NONE",
        "automatic_business_actions": "DISABLED",
        "operational_approval": "NOT_GRANTED",
        "interpretation": (
            "If complete, this is a descriptive difference in *recorded* group rates, "
            "not an estimate of a causal treatment effect. Group assignment methods, "
            "actual supplier changes, confounding, definition of a contractual promise, "
            "outcome completeness and source-system history need independent review."
        ),
    }


def _fixture_comparison():
    from copy import deepcopy
    source = _fixture()
    # Four fictional orders; no business intervention or actual randomized trial.
    names = ("SOFTWARE-1", "SOFTWARE-2", "SOFTWARE-3", "SOFTWARE-4")
    for name in source:
        if name in ("supplier_quotes", "supplier_capacity"):
            continue  # These are one supplier-wide source snapshot, not four rows.
        original = source[name][1][0]
        source[name] = (source[name][0], [])
        for i, order_id in enumerate(names):
            row = deepcopy(original)
            if "order_id" in row:
                row["order_id"] = order_id
            if name == "comparison_assignment":
                row["evaluation_group"] = "TREATMENT" if i >= 2 else "CONTROL"
                row["assignment_timestamp"] = "2025-07-01T09:30:00+00:00"
            if name == "realized_outcomes":
                row["delivery_status"] = "delivered"
                row["actual_delivery_timestamp"] = (
                    "2025-07-11T12:00:00+00:00" if i >= 2 else "2025-07-09T12:00:00+00:00"
                )
                row["outcome_recorded_at"] = "2025-07-12T09:00:00+00:00"
            source[name][1].append(row)
    plan = {"registered_at": "2025-06-28T00:00:00+00:00",
            "evaluation_start": "2025-07-01T00:00:00+00:00",
            "evaluation_end": "2025-07-31T23:59:59+00:00",
            "outcome_freeze_at": "2025-08-31T00:00:00+00:00",
            "endpoint": ENDPOINT, "minimum_mature_per_group": 2}
    return source, plan


def self_test():
    from copy import deepcopy
    tables, plan = _fixture_comparison()
    baseline = evaluate_comparison(tables, plan)
    checks = {
        "four_row_synthetic_groups_only": (baseline["group_assignment_count"] ==
                                           {"control": 2, "treatment": 2}),
        "descriptive_difference_not_causal": (
            baseline["status"] == "DESCRIPTIVE_GROUP_DIFFERENCE_ONLY_UNATTESTED"
            and baseline["descriptive_treatment_minus_control"] == 1.0
            and not baseline["true_intervention_benefit_certified"]
        ),
        "approval_never_granted": baseline["operational_approval"] == "NOT_GRANTED",
    }
    invalid = deepcopy(tables)
    invalid["comparison_assignment"][1][0]["assignment_timestamp"] = "2025-07-03T10:00:00+00:00"
    checks["postdecision_assignment_rejected"] = (
        evaluate_comparison(invalid, plan)["status"] == "BLOCKED_SOURCE_OR_DESIGN_INTEGRITY"
    )
    missing = deepcopy(tables)
    missing["realized_outcomes"][1][0]["actual_delivery_timestamp"] = ""
    checks["missing_outcome_not_labeled_on_time"] = (
        evaluate_comparison(missing, plan)["descriptive_treatment_minus_control"] is None
    )
    no_quotes = deepcopy(tables)
    no_quotes.pop("supplier_quotes")
    checks["missing_operational_quotes_block"] = (
        evaluate_comparison(no_quotes, plan)["status"] == "BLOCKED_SOURCE_OR_DESIGN_INTEGRITY"
    )
    unsupported = deepcopy(tables)
    unsupported["comparison_assignment"][1][0]["evaluation_group"] = "UNSPECIFIED"
    checks["unknown_group_blocked"] = (
        evaluate_comparison(unsupported, plan)["status"] == "BLOCKED_SOURCE_OR_DESIGN_INTEGRITY"
    )
    return {"product": "AEGIS", "step": 196, "fixture": "SOFTWARE_ONLY_NO_REAL_INTERVENTION",
            "checks": checks, "all_pass": all(checks.values()),
            "real_causal_effect_established": False, "operational_approval": "NOT_GRANTED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--source-dir", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2))
        return 0 if result["all_pass"] else 1
    if not args.plan or not args.report:
        parser.error("--plan and --report are mandatory with --source-dir")
    if args.report.exists():
        parser.error("Refusing to overwrite an existing evidence report")
    result = evaluate_comparison(load_csv_folder(args.source_dir),
                                 json.loads(args.plan.read_text(encoding="utf-8")))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"].startswith("DESCRIPTIVE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
