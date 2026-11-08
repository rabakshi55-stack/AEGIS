#!/usr/bin/env python3
"""AEGIS: consolidated READ-ONLY retrospective validation (standard library).

Input: original Olist orders/customers CSV; unchanged local AEGIS frozen bundle;
Step 200/204/205 aggregate audit JSON reports. No training, predictions,
optimization, network access, business actions, or input-file writes.

Use: place beside AEGIS_App in AEGIS_Standalone_App and run:
    python -B AEGIS_validation_consolidated.py
Or: python -B AEGIS_validation_consolidated.py --self-test
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import pathlib
import sys

WINDOWS = {
    "TRAIN": (dt.datetime(2017, 1, 1), dt.datetime(2017, 10, 1), dt.datetime(2018, 1, 1)),
    "VALIDATION": (dt.datetime(2018, 1, 1), dt.datetime(2018, 4, 1), dt.datetime(2018, 6, 1)),
    "TEST": (dt.datetime(2018, 6, 1), dt.datetime(2018, 8, 1), None),
}
CATEGORIES = ("DELIVERED_COMPARABLE_STRICT",
              "DELIVERED_COMPARABLE_FLAGGED_CHRONOLOGY_OR_PROMISE",
              "DELIVERED_STATUS_MISSING_COMPARABLE_DATES",
              "CANCELED_WITHOUT_COMPARABLE_DELIVERY",
              "UNAVAILABLE_WITHOUT_COMPARABLE_DELIVERY",
              "OTHER_STATUS_WITHOUT_COMPARABLE_DELIVERY")


def read_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def csv_rows(path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def date_time(s):
    if s is None or str(s).strip() in ("", "NaT", "None"):
        return None
    v = dt.datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    if v.tzinfo:
        raise ValueError("Timezone-aware historical timestamp: explicit clock policy required")
    return v


def phase_of(purchase):
    for name, (lo, hi, _) in WINDOWS.items():
        if purchase is not None and lo <= purchase < hi:
            return name
    return None


def promise_band(n):
    if n <= 7: return "0-7d"
    if n <= 14: return "8-14d"
    if n <= 21: return "15-21d"
    if n <= 30: return "22-30d"
    if n <= 45: return "31-45d"
    return "46d_plus"


def auc_ap(y, scores):
    """Exact tie-aware ROC AUC and average precision, no external packages.

    AP groups tied scores, matching sklearn's non-interpolated average precision.
    """
    if len(y) != len(scores) or not y:
        return None, None
    npos = sum(y)
    nneg = len(y) - npos
    if not npos or not nneg:
        return None, None
    pairs = sorted(zip(scores, y), reverse=True)
    true_seen = false_seen = 0
    concordant = 0.0
    average_precision = 0.0
    i = 0
    while i < len(pairs):
        s = pairs[i][0]
        pos = neg = 0
        while i < len(pairs) and pairs[i][0] == s:
            if pairs[i][1]: pos += 1
            else: neg += 1
            i += 1
        concordant += pos * (nneg - false_seen - neg) + 0.5 * pos * neg
        true_seen += pos
        false_seen += neg
        average_precision += (pos / npos) * (true_seen / (true_seen + false_seen))
    return concordant / (npos * nneg), average_precision


def scores_metrics(items):
    n = len(items)
    if not n:
        return {"count": 0, "roc_auc": None, "average_precision": None}
    y = [x["late"] for x in items]
    scores = [x["score"] for x in items]
    auc, ap = auc_ap(y, scores)
    positives = sum(y)
    k = max(1, math.ceil(0.1 * n))
    top = sorted(items, key=lambda x: x["score"], reverse=True)[:k]
    capture = sum(x["late"] for x in top) / positives if positives else None
    late_rate = positives / n
    top_rate = sum(x["late"] for x in top) / len(top)
    return {
        "count": n, "late_count": positives, "observed_late_rate": late_rate,
        "mean_frozen_score": sum(scores) / n,
        "mean_score_minus_observed_rate": sum(scores) / n - late_rate,
        "roc_auc": auc, "average_precision": ap,
        "brier_descriptive_not_calibration_certification": sum((s - t) ** 2 for s, t in zip(scores, y)) / n,
        "top_10pct_capture": capture,
        "top_10pct_lift": top_rate / late_rate if late_rate else None,
    }


def comparison_metrics(actual, recorded, eps=0.000003):
    return actual is not None and recorded is not None and abs(actual - float(recorded)) < eps


def describe_order(r):
    purchase = date_time(r["order_purchase_timestamp"])
    estimate = date_time(r["order_estimated_delivery_date"])
    delivery = date_time(r["order_delivered_customer_date"])
    carrier = date_time(r["order_delivered_carrier_date"])
    status = r["order_status"].strip().lower()
    bad_chronology = bool((carrier and purchase and carrier < purchase)
                          or (delivery and carrier and delivery < carrier)
                          or (delivery and purchase and delivery < purchase))
    valid_promise = bool(purchase and estimate and estimate >= purchase)
    observed = bool(status == "delivered" and delivery and estimate)
    strict = bool(observed and valid_promise and not bad_chronology)
    phase = phase_of(purchase)
    cutoff = WINDOWS[phase][2] if phase else None
    selected = bool(strict and phase and (not cutoff or delivery < cutoff))
    if strict: category = CATEGORIES[0]
    elif observed: category = CATEGORIES[1]
    elif status == "delivered": category = CATEGORIES[2]
    elif status == "canceled": category = CATEGORIES[3]
    elif status == "unavailable": category = CATEGORIES[4]
    else: category = CATEGORIES[5]
    return {
        "purchase": purchase, "estimate": estimate, "delivery": delivery,
        "status": status, "phase": phase, "valid_promise": valid_promise,
        "promise_days": ((estimate.date() - purchase.date()).days if purchase and estimate else None),
        "observed": observed, "strict": strict, "selected": selected,
        "category": category, "late": bool(delivery.date() > estimate.date()) if observed else None,
    }


def detect_raw_folder(project_dir):
    for base in (project_dir, *project_dir.parents):
        cand = base / "AEGIS_Public_Data" / "Olist_Raw" / "archive"
        if (cand / "olist_orders_dataset.csv").is_file() and (cand / "olist_customers_dataset.csv").is_file():
            return cand
    raise FileNotFoundError("Could not locate AEGIS_Public_Data\\Olist_Raw\\archive. Use --raw-folder PATH.")


def check_entry(checks, name, ok, detail, critical=True):
    checks.append({"name": name, "passed": bool(ok), "severity": "BLOCK" if critical else "WARN", "detail": detail})


def do_audit(project_dir, raw_dir, bundle_file, baseline200, baseline204, baseline205):
    source_orders = raw_dir / "olist_orders_dataset.csv"
    source_customers = raw_dir / "olist_customers_dataset.csv"
    for f in (source_orders, source_customers, bundle_file, baseline200, baseline204, baseline205):
        if not f.is_file():
            raise FileNotFoundError(f"Required input not found: {f}")
    before = {str(f): file_hash(f) for f in (source_orders, source_customers, bundle_file, baseline200, baseline204, baseline205)}
    s200, s204, s205, bundle = [read_json(f) for f in (baseline200, baseline204, baseline205, bundle_file)]
    checks = []
    check_entry(checks, "Original orders CSV SHA256 matches Step 200", before[str(source_orders)] == s200["original_csv_sha256"], "Protects against a different Olist source version")
    check_entry(checks, "Original orders CSV SHA256 matches Step 204 and 205", before[str(source_orders)] == s204["original_csv_sha256"] == s205["original_csv_sha256"], "Same original CSV across three historical audits")
    check_entry(checks, "Frozen bundle declared digest matches Step 200", bundle.get("content_sha256") == s200["bundle_recorded_sha256"], "Compares recorded bundle digest, not an independent cryptographic signature")
    check_entry(checks, "Prior Step 204/205 reconciliation passed", bool(s204.get("step200_count_reconciliation", {}).get("all_pass")) and bool(s205.get("step204_reconciliation", {}).get("all_pass")), "All reported historical reconciliation checks true")

    customer = {}
    duplicate_customer_ids = missing_states = 0
    for row in csv_rows(source_customers):
        cid = row["customer_id"]
        if cid in customer: duplicate_customer_ids += 1
        if not row["customer_state"].strip(): missing_states += 1
        customer[cid] = row["customer_state"].strip()
    check_entry(checks, "Customer ID uniqueness and state coverage", duplicate_customer_ids == 0 and missing_states == 0, f"duplicate_ids={duplicate_customer_ids}, missing_states={missing_states}")

    records = {}
    duplicate_orders = missed_customers = 0
    categories = collections.Counter()
    window_count = collections.Counter()
    phase_observed = collections.Counter()
    phase_selected = collections.Counter()
    phase_long = collections.Counter()
    strict_count = long_count = eligible_calendar_count = 0
    for row in csv_rows(source_orders):
        oid = row["order_id"]
        if oid in records: duplicate_orders += 1
        if row["customer_id"] not in customer: missed_customers += 1
        info = describe_order(row)
        records[oid] = {"customer_id": row["customer_id"], **info}
        categories[info["category"]] += 1
        eligible_calendar_count += (info["purchase"] is not None)
        strict_count += info["strict"]
        if info["promise_days"] is not None and info["promise_days"] > 60: long_count += 1
        if info["phase"]:
            window_count[info["phase"]] += 1
            phase_observed[info["phase"]] += info["observed"]
            phase_selected[info["phase"]] += info["selected"]
            if info["promise_days"] is not None and info["promise_days"] > 60: phase_long[info["phase"]] += 1

    check_entry(checks, "Original order uniqueness and registry population", duplicate_orders == 0 and len(records) == s200["original_order_registry_count"] == s205["source_order_count"], f"source={len(records)}, duplicate_order_ids={duplicate_orders}")
    check_entry(checks, "Every order has exactly one customer match", missed_customers == 0 and len(customer) == len(records), f"unmatched={missed_customers}, customer_records={len(customer)}")
    check_entry(checks, "Purchase-calendar eligibility count", eligible_calendar_count == s205["full_original_population"]["purchase_calendar_eligible"], f"eligible={eligible_calendar_count}")
    check_entry(checks, "Historical strict eligibility agrees with Step 205", strict_count == s205["full_original_population"]["strict_historical_label_candidate"], f"strict={strict_count}")
    check_entry(checks, "Outcome category population agrees with Step 205", dict(categories) == {k:int(v) for k,v in s205["full_original_population"]["category_counts"].items()}, "All six mutually exclusive final-status categories")
    for phase in WINDOWS:
        old = s205["research_phases"][phase]
        check_entry(checks, f"{phase}: population/observability/selection reconciliation",
                    window_count[phase] == old["all_orders"] and phase_observed[phase] == old["observed_comparable_outcome"] and phase_selected[phase] == old["historical_frozen_selected"],
                    f"purchase={window_count[phase]}, observed={phase_observed[phase]}, selected={phase_selected[phase]}")

    expected_selected = {oid for oid, r in records.items() if r["selected"]}
    scored = bundle["research_orders"]
    bundle_original_ids = bundle.get("original_order_ids")
    check_entry(checks, "Bundle original order registry matches Olist source", isinstance(bundle_original_ids, list) and len(bundle_original_ids) == len(records) and len(set(bundle_original_ids)) == len(records) and set(bundle_original_ids) == set(records), "No missing, extra, duplicated original order IDs")
    check_entry(checks, "Frozen scored population matches Step 200/205", len(scored) == len(expected_selected) == s200["frozen_scored_order_count"], f"scored={len(scored)}, source_selected={len(expected_selected)}")
    seen = set()
    matched = []
    problems = collections.Counter()
    for r in scored:
        required_fields = ("order_id", "Phase", "Purchase_Time", "Destination_State", "Promise_Days", "Promise_Band", "Research_Score_Uncalibrated")
        for field in required_fields:
            if field not in r or r[field] is None or str(r[field]).strip() == "":
                problems[f"missing_required_{field}"] += 1
        oid = r.get("order_id")
        if oid in seen: problems["duplicate_scored_id"] += 1
        seen.add(oid)
        source = records.get(oid)
        if not source:
            problems["scored_id_not_in_source"] += 1
            continue
        if not source["selected"]: problems["not_frozen_selected_by_source"] += 1
        if str(r.get("Phase", "")).upper() != str(source["phase"]): problems["phase_mismatch"] += 1
        if r.get("Purchase_Time") is not None and date_time(r["Purchase_Time"]) != source["purchase"]:
            problems["purchase_time_mismatch"] += 1
        if r.get("Promise_Days") is None:
            problems["bundle_promise_days_missing"] += 1
        elif int(r["Promise_Days"]) != source["promise_days"]:
            problems["promise_days_mismatch"] += 1
        if r.get("Destination_State") is not None and str(r["Destination_State"]).strip() != customer[source["customer_id"]]:
            problems["customer_state_mismatch"] += 1
        if r.get("Promise_Band") is not None and str(r["Promise_Band"]) != promise_band(source["promise_days"]):
            problems["promise_band_mismatch"] += 1
        try: score = float(r["Research_Score_Uncalibrated"])
        except (ValueError, TypeError, KeyError):
            problems["invalid_frozen_score"] += 1
            continue
        if not math.isfinite(score) or not 0 <= score <= 1:
            problems["out_of_range_frozen_score"] += 1
            continue
        if source["late"] is None:
            problems["scored_without_comparable_outcome"] += 1
            continue
        matched.append({"phase": source["phase"], "month": source["purchase"].strftime("%Y-%m"),
                        "late": int(source["late"]), "score": score,
                        "long_promise": source["promise_days"] > 60})
    check_entry(checks, "Every frozen scored ID belongs to original eligible cohort", seen == expected_selected, f"missing_from_bundle={len(expected_selected-seen)}, unexpected_in_bundle={len(seen-expected_selected)}")
    check_entry(checks, "Frozen source features, score ranges and dates reconcile", not problems and len(matched) == len(scored), f"problems={dict(problems)}")

    by_phase = {}
    by_month = {}
    sensitivity = {}
    for phase in ("ALL", *WINDOWS):
        sub = matched if phase == "ALL" else [x for x in matched if x["phase"] == phase]
        by_phase[phase] = scores_metrics(sub)
        long = [x for x in sub if x["long_promise"]]
        trimmed = [x for x in sub if not x["long_promise"]]
        sensitivity[phase] = {
            "all": scores_metrics(sub), "promise_over_60_days": scores_metrics(long),
            "promise_at_most_60_days": scores_metrics(trimmed),
            "auc_difference_trimmed_minus_all": (
                scores_metrics(trimmed)["roc_auc"] - scores_metrics(sub)["roc_auc"]
                if scores_metrics(trimmed)["roc_auc"] is not None and scores_metrics(sub)["roc_auc"] is not None else None),
            "interpretation": "Descriptive re-evaluation of the same frozen scores; not a new independent test",
        }
    for month in sorted(set(r["month"] for r in matched)):
        by_month[month] = scores_metrics([x for x in matched if x["month"] == month])

    base_metrics = {"ALL": s200["overall_scored_cohort"], **s200["phase_tagged_cohorts"]}
    for phase in ("ALL", *WINDOWS):
        ref = base_metrics[phase]
        actual = by_phase[phase]
        check_entry(checks, f"{phase} frozen-score ROC AUC and AP reproduce Step 200",
                    actual["count"] == ref["scored_orders"] and actual["late_count"] == ref["late_after_estimated_calendar_date"] and
                    comparison_metrics(actual["roc_auc"], ref["research_ranking_auc"]) and
                    comparison_metrics(actual["average_precision"], ref["research_ranking_average_precision"]),
                    f"AUC={actual['roc_auc']}, AP={actual['average_precision']}, late={actual['late_count']}")
    if len(records) == 99441 and len(scored) == 58911:
        check_entry(checks, "Historical long-promise registry matches previous inspection",
                    long_count == 260 and sum(r["long_promise"] for r in matched) == 144,
                    f"all_original_over_60={long_count}, frozen_scored_over_60={sum(r['long_promise'] for r in matched)}")
    check_entry(checks, "No source or evidence input file modified", all(file_hash(pathlib.Path(p)) == digest for p,digest in before.items()), "Input SHA256s unchanged after audit")

    warnings = [
        "Original Olist snapshot does not certify original quoted delivery-promise availability or immutability at order purchase.",
        "Customer state may be historically consistent but customer-state as-of availability/version history is not proven.",
        "The strict frozen model cohort requires known delivery outcomes: retrospective selection bias remains for actual prospective scoring.",
        "The test period has been inspected repeatedly; it is not a pristine independent holdout.",
        "Historical discrimination, sensitivity and calibration descriptors do not prove future model reliability.",
        "Olist estimated delivery is not independently verified as an enforceable contractual customer commitment.",
        "Olist delivery prediction does not prove supplier-switch counterfactuals, causal gains, capacity feasibility or ERP suitability.",
        "Existing AEGIS model risk-score values are not certified calibrated probabilities.",
        "Real procurement actions must remain disabled and subject to human approval.",
    ]
    if by_phase.get("VALIDATION") and by_phase["VALIDATION"].get("roc_auc") is not None:
        if by_phase["VALIDATION"]["roc_auc"] < .60:
            warnings.insert(0, "Validation-period ROC AUC below 0.60; material discrimination weakness in that historical period.")
    if by_phase.get("VALIDATION") and by_phase["VALIDATION"].get("mean_score_minus_observed_rate") is not None:
        delta = by_phase["VALIDATION"]["mean_score_minus_observed_rate"]
        if abs(delta) > .03:
            warnings.insert(0, "Validation-period mean model score differs from observed late rate by over 3 percentage points.")

    outcome = {
        "study": "AEGIS_CONSOLIDATED_RETROSPECTIVE_VALIDATION",
        "status": "HISTORICAL_RESEARCH_ONLY_NOT_PROSPECTIVELY_CERTIFIED",
        "inputs_sha256": before,
        "software_data_reconciliation": {"passed": sum(c["passed"] for c in checks),
                                         "total": len(checks), "all_pass": all(c["passed"] for c in checks),
                                         "checks": checks},
        "original_population": {"orders": len(records), "customer_rows": len(customer),
                                "historical_strict_candidates": strict_count,
                                "frozen_selected": len(expected_selected),
                                "outcome_categories": dict(categories), "source_promises_over_60_days": long_count,
                                "phase_purchases": dict(window_count), "phase_selected": dict(phase_selected),
                                "phase_promises_over_60_days": dict(phase_long)},
        "frozen_model_historical_metrics": by_phase,
        "by_purchase_month": by_month,
        "frozen_long_promise_sensitivity": sensitivity,
        "operational_evidence_gaps": warnings,
        "feature_as_of_availability_certified": False,
        "pristine_prospective_holdout": False,
        "probability_calibration_certified": False,
        "supplier_counterfactual_validity_certified": False,
        "automatic_business_actions": "DISABLED",
        "source_input_modifications": "NONE",
        "new_model_training": "NONE",
        "note": "All scored metrics are retrospective; descriptive probability metrics do not imply calibration. No new score or outcome predictions made.",
    }
    return outcome


def self_test():
    passed = 0
    tests = [
        ("perfect_auc", lambda: auc_ap([0,1],[0.1,0.9])[0] == 1.0),
        ("reversed_auc", lambda: auc_ap([1,0],[0.1,0.9])[0] == 0.0),
        ("tied_auc", lambda: auc_ap([1,0],[0.5,0.5])[0] == 0.5),
        ("ties_ap", lambda: auc_ap([1,0],[0.5,0.5])[1] == 0.5),
        ("perfect_ap", lambda: auc_ap([1,0,1],[0.9,0.1,0.8])[1] == 1.0),
        ("none_single_class", lambda: auc_ap([0,0],[.1,.9]) == (None,None)),
        ("calendar_phase", lambda: phase_of(dt.datetime(2017,7,1)) == 'TRAIN'),
        ("missing_phase", lambda: phase_of(dt.datetime(2017,11,1)) is None),
        ("border_valid", lambda: phase_of(dt.datetime(2018,1,1)) == 'VALIDATION'),
        ("promise_46plus", lambda: promise_band(61) == '46d_plus'),
        ("promise_30", lambda: promise_band(30) == '22-30d'),
        ("metrics_brier", lambda: math.isclose(scores_metrics([{'late':1,'score':.8},{'late':0,'score':.2}])['brier_descriptive_not_calibration_certification'], .04)),
    ]
    fail = []
    for name, test in tests:
        try: good = bool(test())
        except Exception: good = False
        passed += int(good)
        if not good: fail.append(name)
    return {'study': 'AEGIS_CONSOLIDATED_SELF_TEST_FICTIONAL_FIXTURES', 'passed': passed,
            'total': len(tests), 'failed': fail, 'all_pass': not fail}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--self-test', action='store_true', help='Run software tests; no source data required')
    parser.add_argument('--project-dir', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent)
    parser.add_argument('--raw-folder', type=pathlib.Path)
    parser.add_argument('--output-prefix', default='AEGIS_consolidated_validation', help='Creates a new numbered subfolder under project-dir; never overwrites')
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2))
        return 0 if result['all_pass'] else 1
    project = args.project_dir.resolve()
    raw = args.raw_folder.resolve() if args.raw_folder else detect_raw_folder(project)
    report = do_audit(project, raw, project / 'AEGIS_App' / 'data' / 'aegis_bundle.json',
                      project / 'AEGIS_step200_olist_temporal_audit.json',
                      project / 'AEGIS_step204_selection_report.json',
                      project / 'AEGIS_step205_eligibility_report.json')
    for attempt in range(1,1000):
        out = project / f'{args.output_prefix}_{attempt:03d}'
        try:
            out.mkdir(mode=0o700)
            break
        except FileExistsError: continue
    else:
        raise RuntimeError('No available numbered output folder; no files overwritten')
    out_json = out / 'consolidated_report.json'
    out_txt = out / 'SUMMARY.txt'
    with out_json.open('x',encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, allow_nan=False)
    lines = [
        'AEGIS -- CONSOLIDATED RETROSPECTIVE VALIDATION',
        'This is historical research, not prospective certification.',
        f"Software/source checks: {report['software_data_reconciliation']['passed']}/{report['software_data_reconciliation']['total']}",
        f"All reconciliation checks passed: {report['software_data_reconciliation']['all_pass']}",
        '', 'HISTORICAL FROZEN-SCORE METRICS',
    ]
    for ph, m in report['frozen_model_historical_metrics'].items():
        lines.append(f"{ph}: n={m['count']} late={m['late_count']} AUC={m['roc_auc']:.6f} AP={m['average_precision']:.6f} observed_late={m['observed_late_rate']:.4%} mean_score={m['mean_frozen_score']:.4%}")
    lines.extend(['', 'LONG-PROMISE SENSITIVITY (>60 CALENDAR DAYS)'])
    for ph, m in report['frozen_long_promise_sensitivity'].items():
        lines.append(f"{ph}: long_n={m['promise_over_60_days']['count']} kept_n={m['promise_at_most_60_days']['count']} AUC_trimmed_minus_full={m['auc_difference_trimmed_minus_all']}")
    lines.extend(['', 'UNRESOLVED CERTIFICATION GAPS'])
    lines.extend('- ' + w for w in report['operational_evidence_gaps'])
    lines.extend(['', 'INPUTS WERE READ ONLY. NO MODEL RETRAINING. NO OPERATIONAL APPROVAL.'])
    with out_txt.open('x',encoding='utf-8') as f:
        f.write('\n'.join(lines)+'\n')
    print('\n'.join(lines))
    print('\nREPORT:',out_json)
    print('SUMMARY:',out_txt)
    return 0 if report['software_data_reconciliation']['all_pass'] else 2

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as e:
        print('AEGIS VALIDATION BLOCKED:',str(e),file=sys.stderr)
        sys.exit(2)
