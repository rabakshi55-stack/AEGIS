"""AEGIS Step 194: prospective shadow-score evaluation, never a live scorer.

Requires a predeclared research plan and exact timestamped score/outcome rows.
It does not train models, estimate supplier causality, calibrate historical
scores as probabilities, or accept operational action requests.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io
import json
from pathlib import Path

from asof_validation import _timestamp


SCORE_COLUMNS = (
    "order_id", "decision_timestamp", "score_recorded_at",
    "feature_latest_known_at", "model_version", "model_sha256", "research_score",
)
OUTCOME_COLUMNS = (
    "order_id", "delivery_status", "estimated_delivery_date",
    "actual_delivery_timestamp", "outcome_recorded_at",
)
TARGET_CONTRACT = "ESTIMATED_CALENDAR_DAY_RESEARCH"
MAX_BYTES = 30 * 1024 * 1024


def _date(value):
    text = str(value or "").strip()
    if len(text) != 10:
        raise ValueError("calendar date must be YYYY-MM-DD")
    return date.fromisoformat(text)


def _score(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > 1:
            raise ValueError("Score must be finite and between 0 and 1")
        return float(number)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid score") from exc


def _auc(labels_and_scores):
    positives = sum(label for label, _ in labels_and_scores)
    negatives = len(labels_and_scores) - positives
    if not positives or not negatives:
        return None
    group = sorted(labels_and_scores, key=lambda item: item[1])
    concordant = 0.0
    negative_before = 0
    i = 0
    while i < len(group):
        j = i
        while j < len(group) and group[j][1] == group[i][1]:
            j += 1
        n_positive = sum(label for label, _ in group[i:j])
        n_negative = j - i - n_positive
        concordant += n_positive * (negative_before + 0.5 * n_negative)
        negative_before += n_negative
        i = j
    return round(concordant / (positives * negatives), 6)


def _average_precision(labels_and_scores):
    positive_total = sum(label for label, _ in labels_and_scores)
    if not positive_total:
        return None
    sorted_pairs = sorted(labels_and_scores, key=lambda item: item[1], reverse=True)
    score = 0.0
    true_positive = 0
    i = 0
    while i < len(sorted_pairs):
        j = i
        while j < len(sorted_pairs) and sorted_pairs[j][1] == sorted_pairs[i][1]:
            j += 1
        added_positives = sum(label for label, _ in sorted_pairs[i:j])
        true_positive += added_positives
        score += (added_positives / positive_total) * (true_positive / j)
        i = j
    return round(score, 6)


def _plan(plan):
    required = ("model_version", "model_sha256", "training_ended_at", "registered_at",
                "evaluation_start", "evaluation_end", "outcome_freeze_at",
                "target_contract", "minimum_mature_orders")
    if not isinstance(plan, dict) or any(k not in plan for k in required):
        raise ValueError("A complete predeclared evaluation plan is required.")
    if plan["target_contract"] != TARGET_CONTRACT:
        raise ValueError("Only estimated calendar-day research outcomes are supported.")
    if not isinstance(plan["model_sha256"], str) or len(plan["model_sha256"]) != 64 or any(
        c not in "0123456789abcdef" for c in plan["model_sha256"].lower()
    ):
        raise ValueError("Plan must contain a 64-digit hexadecimal model digest.")
    timestamps = {name: _timestamp(plan[name]) for name in
                  ("training_ended_at", "registered_at", "evaluation_start", "evaluation_end", "outcome_freeze_at")}
    if not (timestamps["training_ended_at"] < timestamps["registered_at"] <=
            timestamps["evaluation_start"] <= timestamps["evaluation_end"] < timestamps["outcome_freeze_at"]):
        raise ValueError("Plan violates the model/registration/evaluation/outcome chronology.")
    minimum = plan["minimum_mature_orders"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 2:
        raise ValueError("Minimum mature orders must be an integer of at least two.")
    return timestamps


def evaluate(scores, outcomes, plan):
    """Read-only. No raw IDs or record-level data are returned in the report."""
    times = _plan(plan)
    issues = Counter()
    def issue(name):
        issues[name] += 1

    indexed = {}
    for record in outcomes:
        oid = str(record.get("order_id", "")).strip()
        if not oid or oid in indexed:
            issue("BLANK_OR_DUPLICATE_OUTCOME_ID")
            continue
        indexed[oid] = record

    seen = set()
    results = []
    outside_window = 0
    outcomes_unavailable = 0
    total_in_window = 0
    for record in scores:
        oid = str(record.get("order_id", "")).strip()
        if not oid or oid in seen:
            issue("BLANK_OR_DUPLICATE_SCORE_ID")
            continue
        seen.add(oid)
        try:
            decision = _timestamp(record["decision_timestamp"])
            recorded = _timestamp(record["score_recorded_at"])
            known = _timestamp(record["feature_latest_known_at"])
            score = _score(record["research_score"])
        except (KeyError, ValueError, TypeError, OverflowError):
            issue("INVALID_SCORE_OR_TIMESTAMP")
            continue
        if not times["evaluation_start"] <= decision <= times["evaluation_end"]:
            outside_window += 1
            continue
        total_in_window += 1
        if (record.get("model_version") != plan["model_version"] or
                record.get("model_sha256", "").lower() != plan["model_sha256"].lower()):
            issue("MODEL_VERSION_OR_DIGEST_MISMATCH")
            continue
        if recorded > decision:
            issue("SCORE_RECORDED_AFTER_DECISION")
            continue
        if recorded < times["registered_at"]:
            issue("SCORE_RECORDED_BEFORE_RESEARCH_PLAN")
            continue
        if known > decision:
            issue("FEATURE_KNOWN_AFTER_DECISION")
            continue
        if known > recorded:
            issue("FEATURE_KNOWN_AFTER_SCORE_WAS_RECORDED")
            continue
        if recorded <= times["training_ended_at"]:
            issue("SCORE_NOT_AFTER_MODEL_TRAINING")
            continue
        actual = indexed.get(oid)
        if actual is None or actual.get("delivery_status", "").strip().lower() != "delivered":
            outcomes_unavailable += 1
            continue
        if not str(actual.get("actual_delivery_timestamp", "")).strip():
            outcomes_unavailable += 1
            continue
        try:
            delivered = _timestamp(actual["actual_delivery_timestamp"])
            recorded_outcome = _timestamp(actual["outcome_recorded_at"])
            estimated = _date(actual["estimated_delivery_date"])
        except (KeyError, ValueError, TypeError, OverflowError):
            issue("INVALID_DELIVERY_OUTCOME")
            continue
        if recorded_outcome > times["outcome_freeze_at"]:
            outcomes_unavailable += 1
            continue
        if delivered < decision or recorded_outcome < delivered:
            issue("IMPOSSIBLE_DELIVERY_CHRONOLOGY")
            continue
        # This is explicitly NOT a certified contractual promise or SLA.
        label = int(delivered.date() > estimated)
        results.append((label, score))

    mature = len(results)
    positives = sum(label for label, _ in results)
    negatives = mature - positives
    enough = mature >= plan["minimum_mature_orders"] and positives > 0 and negatives > 0
    if issues:
        status = "BLOCKED_INTEGRITY_ISSUES"
    elif not enough:
        status = "INSUFFICIENT_MATURE_OUTCOMES"
    else:
        status = "RETROSPECTIVE_METRICS_ONLY_UNATTESTED"
    # Suppress even descriptive model-performance metrics on invalid cohorts.
    report = {
        "product": "AEGIS",
        "study": "STEP_194_PROSPECTIVE_SHADOW_EVALUATION_GATE",
        "status": status,
        "score_rows_received": len(scores),
        "evaluation_window_scores": total_in_window,
        "outside_window_excluded": outside_window,
        "mature_outcomes": mature,
        "unknown_or_unmatured_outcomes": outcomes_unavailable,
        "observed_late_count": positives,
        "observed_not_late_count": negatives,
        "observed_late_rate_in_mature_cohort": round(positives / mature, 6) if mature else None,
        "auc_ranking": _auc(results) if status.startswith("RETROSPECTIVE") else None,
        "average_precision_ranking": _average_precision(results) if status.startswith("RETROSPECTIVE") else None,
        "average_precision_base_rate": round(positives / mature, 6) if status.startswith("RETROSPECTIVE") else None,
        "mean_uncalibrated_research_score": round(sum(score for _,score in results)/mature, 6) if status.startswith("RETROSPECTIVE") else None,
        "absolute_score_mean_vs_late_rate_gap": round(abs(sum(score for _,score in results)/mature - positives/mature), 6) if status.startswith("RETROSPECTIVE") else None,
        "brier_for_uncalibrated_scores": None,
        "issue_counts": dict(sorted(issues.items())),
        "model_digest_independently_verified": False,
        "plan_independently_preregistered": False,
        "feature_availability_independently_attested": False,
        "target_semantics_certified": False,
        "probability_calibration_certified": False,
        "prospective_generalization_certified": False,
        "commercial_intervention_benefit_established": False,
        "model_training_or_modification": "NONE",
        "operational_approval": "NOT_GRANTED",
        "automatic_business_action": "DISABLED",
        "interpretation": (
            "Metrics describe only the supplied mature cohort, if all temporal checks pass. "
            "Input timestamps, preregistration and model digest are not independently attested. "
            "Original research scores are rankings, not calibrated late-delivery probabilities. "
            "No business threshold, causal impact or operational approval is established."
        ),
    }
    return report


def _read_csv(path, fields):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Input CSV exceeds local size limit")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Missing or duplicate CSV headers")
        if not set(fields).issubset(reader.fieldnames):
            raise ValueError("Missing expected shadow-evaluation fields")
        rows = list(reader)
    if any(None in row or any(x is None for x in row.values()) for row in rows):
        raise ValueError("Malformed CSV rows")
    return rows


def _fixture():
    digest = "a" * 64  # Deliberately not a real model artifact.
    plan = {
        "model_version": "TEST-FROZEN", "model_sha256": digest,
        "training_ended_at": "2025-06-01T00:00:00+00:00",
        "registered_at": "2025-06-25T00:00:00+00:00",
        "evaluation_start": "2025-07-01T00:00:00+00:00",
        "evaluation_end": "2025-07-31T23:59:59+00:00",
        "outcome_freeze_at": "2025-08-31T23:59:59+00:00",
        "target_contract": TARGET_CONTRACT,
        "minimum_mature_orders": 4,
    }
    scores = []
    outcomes = []
    for i, (score, actual_date) in enumerate(((.9, 11), (.7, 12), (.2, 9), (.1, 10))):
        oid = f"SOFTWARE-FIXTURE-{i}"
        scores.append({"order_id": oid, "decision_timestamp": "2025-07-01T10:00:00+00:00",
                       "score_recorded_at": "2025-07-01T09:59:00+00:00",
                       "feature_latest_known_at": "2025-07-01T09:00:00+00:00",
                       "model_version": "TEST-FROZEN", "model_sha256": digest, "research_score": str(score)})
        outcomes.append({"order_id": oid, "delivery_status": "delivered",
                         "estimated_delivery_date": "2025-07-10",
                         "actual_delivery_timestamp": f"2025-07-{actual_date:02d}T12:00:00+00:00",
                         "outcome_recorded_at": "2025-07-15T00:00:00+00:00"})
    return scores, outcomes, plan


def self_test():
    from copy import deepcopy
    scores, outcomes, plan = _fixture()
    good = evaluate(scores, outcomes, plan)
    flags = {
        "positive_control_auc_correct": good["auc_ranking"] == 1.0,
        "positive_control_ap_correct": good["average_precision_ranking"] == 1.0,
        "no_false_probability_calibration": good["probability_calibration_certified"] is False,
        "no_operational_authorization": good["operational_approval"] == "NOT_GRANTED",
    }
    bad = deepcopy(scores)
    bad[0]["score_recorded_at"] = "2025-07-02T00:00:00+00:00"
    flags["late_recorded_score_blocks_metrics"] = (evaluate(bad, outcomes, plan)["status"] == "BLOCKED_INTEGRITY_ISSUES")
    future = deepcopy(scores)
    future[0]["feature_latest_known_at"] = "2025-07-02T00:00:00+00:00"
    flags["future_known_feature_blocks_metrics"] = (evaluate(future, outcomes, plan)["auc_ranking"] is None)
    feature_after_score = deepcopy(scores)
    feature_after_score[0]["feature_latest_known_at"] = "2025-07-01T09:59:30+00:00"
    flags["feature_not_available_at_scoring_blocked"] = (
        evaluate(feature_after_score, outcomes, plan)["status"] == "BLOCKED_INTEGRITY_ISSUES"
    )
    unknown = deepcopy(outcomes)
    unknown[0]["delivery_status"] = "canceled"
    flags["cancellation_never_counted_as_on_time"] = (evaluate(scores, unknown, plan)["status"] == "INSUFFICIENT_MATURE_OUTCOMES")
    extra = deepcopy(outcomes)
    extra[0]["outcome_recorded_at"] = "2025-09-01T00:00:00+00:00"
    flags["after_freeze_outcome_excluded"] = (evaluate(scores, extra, plan)["mature_outcomes"] == 3)
    tampered = deepcopy(scores)
    tampered[0]["model_sha256"] = "b" * 64
    flags["model_identity_mismatch_blocks"] = (evaluate(tampered, outcomes, plan)["status"] == "BLOCKED_INTEGRITY_ISSUES")
    return {"product": "AEGIS", "step": 194, "fixture": "SOFTWARE_ONLY_NOT_PROSPECTIVE_EVIDENCE",
            "checks": flags, "all_pass": all(flags.values()), "operational_approval": "NOT_GRANTED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--scores", type=Path)
    parser.add_argument("--outcomes", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.self_test:
        report = self_test()
        print(json.dumps(report, indent=2))
        return 0 if report["all_pass"] else 1
    if not all((args.scores, args.outcomes, args.plan, args.report)):
        parser.error("--scores, --outcomes, --plan and --report are required")
    if args.report.exists():
        parser.error("Refusing to overwrite an existing research report")
    result = evaluate(_read_csv(args.scores, SCORE_COLUMNS),
                      _read_csv(args.outcomes, OUTCOME_COLUMNS),
                      json.loads(args.plan.read_text(encoding="utf-8")))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "RETROSPECTIVE_METRICS_ONLY_UNATTESTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
