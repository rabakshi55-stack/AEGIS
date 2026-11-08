"""AEGIS research validation suite — software tests vs. real-world evidence.

Runs deterministic synthetic controls for Steps 191–196. It does NOT turn a
research prototype into a certified operational predictor or optimizer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from asof_validation import self_test as asof_self_test
from historical_outcomes import HistoricalOutcomes
from intervention_evidence import self_test as intervention_self_test
from paired_stress import run_experiment
from prospective_validation import self_test as prospective_self_test


def _outcome_semantics_self_test():
    ids = ["SOFTWARE-A", "SOFTWARE-B", "SOFTWARE-C", "SOFTWARE-D", "SOFTWARE-E"]
    records = (
        "order_id,order_status,order_estimated_delivery_date,order_delivered_customer_date,order_purchase_timestamp\n"
        "SOFTWARE-A,delivered,2025-07-10,2025-07-09,2025-07-01\n"
        "SOFTWARE-B,canceled,2025-07-10,2025-07-08,2025-07-01\n"
        "SOFTWARE-C,shipped,2025-07-10,,2025-07-01\n"
        "SOFTWARE-D,delivered,2025-07-10,2025-06-20,2025-07-01\n"
        "SOFTWARE-E,delivered,2025-07-10,2025-07-11,2025-07-01\n"
    ).encode("utf-8")
    result = HistoricalOutcomes("olist_orders_dataset.csv", records, ids)
    status = result.summary
    checks = {
        "only_confirmed_deliveries_compared": status["comparable"] == 2,
        "source_day_before_count_correct": status["before"] == 1,
        "source_day_after_count_correct": status["after"] == 1,
        "canceled_record_with_actual_excluded": status["contradictory_status_delivery"] == 1,
        "shipped_unknown_never_on_time": status["not_recorded_as_delivered"] == 1,
        "delivery_before_purchase_blocked": status["delivery_before_purchase"] == 1,
        "all_source_rows_reconciled": status["all_records_reconciled"],
        "contractual_kpi_not_certified": not status["business_kpi_certified"],
    }
    return {"step": 193, "fixture": "SOFTWARE_ONLY_NOT_OLIST_SOURCE_EVIDENCE",
            "checks": checks, "all_pass": all(checks.values()),
            "real_world_promise_definition_certified": False}


def run_all(synthetic_source=None):
    results = {
        "step_192_asof": asof_self_test(),
        "step_193_outcome_semantics": _outcome_semantics_self_test(),
        "step_194_shadow_evaluation": prospective_self_test(),
        "step_196_intervention_evidence": intervention_self_test(),
    }
    for result in results.values():
        if not result["all_pass"]:
            raise AssertionError("An AEGIS software safety gate failed: " + str(result.get("step")))

    synthetic = {"status": "NOT_RUN", "reason": "Optional original synthetic input not supplied"}
    if synthetic_source:
        result = run_experiment(synthetic_source, scenarios=500, seed=191)
        report = result["report"]
        expected = (report["order_count"] == 16 and report["candidate_pair_count"] == 80
                    and report["paired_rows"] == 40000 and report["coverage_percent"] == 100)
        if not expected or not all(report["independent_checks"].values()):
            raise AssertionError("Step 191 source-derived experiment differs from the verified pilot")
        synthetic = {"status": "VERIFIED_IN_NEW_SYNTHETIC_EXPERIMENT",
                     "orders": report["order_count"], "pairs": report["candidate_pair_count"],
                     "scenarios": report["scenario_count"], "paired_rows": report["paired_rows"],
                     "coverage_percent": report["coverage_percent"],
                     "source_sha256": report["source_sha256"],
                     "model_retraining": False, "real_world_supplier_benefit": "NOT_ESTABLISHED"}

    gate_count = sum(len(item["checks"]) for item in results.values())
    return {
        "product": "AEGIS",
        "scope": "VALIDATION_FOUNDATIONS_STEPS_191_TO_196",
        "software_gate_checks_passed": gate_count,
        "all_software_fixtures_pass": True,
        "step_191_synthetic_pair_coverage": synthetic,
        "other_steps": results,
        "limitations": {
            "source_timestamp_truth_and_revision_history": "NEEDS_INDEPENDENT_SOURCE_OWNER_EVIDENCE",
            "contractual_delivery_promise_and_timezone": "NEEDS_BUSINESS_DEFINITIONS",
            "genuine_prospective_model_accuracy": "NEEDS_NEW_MATURE_REAL_OUTCOMES",
            "calibrated_operational_probabilities": "NOT_ESTABLISHED",
            "live_supplier_quotes_capacity_and_commercial_eligibility": "NEEDS_APPROVED_REAL_SOURCE_DATA",
            "external_capacity_reservations_and_constraints": "NOT_CERTIFIED",
            "supplier_causality": "NOT_ESTABLISHED",
            "supplier_switch_intervention_effect": "NOT_ESTABLISHED",
            "operational_security_and_business_approval": "NOT_GRANTED",
        },
        "new_ml_training": "NONE",
        "original_data_modified": False,
        "automatic_procurement": "DISABLED",
        "operational_approval": "NOT_GRANTED",
        "overall_interpretation": (
            "These are software and synthetic research-control results, NOT full resolution "
            "of empirical validity limitations. Original company-side data, externally "
            "verified timestamps, a mature prospective study and independent intervention "
            "evaluation are prerequisites for any production claim."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-source", type=Path,
                        help="Original integrated dataset ZIP or extracted root; optional")
    parser.add_argument("--report", type=Path, help="New output JSON path; optional")
    args = parser.parse_args(argv)
    if args.report and args.report.exists():
        parser.error("The report path already exists; AEGIS will not overwrite earlier evidence")
    report = run_all(args.synthetic_source)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("AEGIS — VALIDATION FOUNDATION STATUS (RESEARCH ONLY)")
    print("Software controls:", report["software_gate_checks_passed"], "of",
          report["software_gate_checks_passed"], "PASS")
    for name, result in report["other_steps"].items():
        print(name, ":", "PASS" if result["all_pass"] else "FAIL",
              f"({len(result['checks'])} checks)")
    synthetic = report["step_191_synthetic_pair_coverage"]
    print("Step 191 synthetic paired stress:", synthetic["status"])
    if "paired_rows" in synthetic:
        print("  Paired synthetic rows:", synthetic["paired_rows"])
    print("Real-world validation: NOT CERTIFIED")
    print("Operational approval: NOT GRANTED | Business actions: DISABLED")
    if args.report:
        print("Detailed JSON report:", args.report.resolve())
    else:
        print("For full limitations and audit details, rerun with --report NEW_FILENAME.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
