"""AEGIS Step 192: local, read-only decision-time evidence checks.

This is a *software gate*, not source-system attestation or production approval.
Reports use counts and issue codes; source rows are never exported or sent to
any language model. The eight table names follow the original Step 182 contract.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import csv
from datetime import date, datetime
import json
from pathlib import Path


CONTRACTS = {
    "orders_at_decision": (
        ("order_id",),
        ("order_id", "purchase_timestamp", "promised_delivery_date", "destination_state",
         "decision_timestamp", "purchase_known_at", "promise_known_at", "destination_known_at"),
    ),
    "demand_lines": (
        ("order_id", "item_id"),
        ("order_id", "item_id", "required_units", "required_by_date"),
    ),
    "supplier_quotes": (
        ("item_id", "supplier_id", "quote_recorded_at"),
        ("item_id", "supplier_id", "unit_cost", "quoted_lead_days", "minimum_order_qty",
         "eligible_for_item", "quote_recorded_at", "quote_valid_until"),
    ),
    "supplier_capacity": (
        ("item_id", "supplier_id", "capacity_asof"),
        ("item_id", "supplier_id", "available_units", "capacity_asof", "capacity_valid_until"),
    ),
    "baseline_allocations": (
        ("order_id", "item_id", "supplier_id"),
        ("order_id", "item_id", "supplier_id", "allocated_units", "baseline_total_cost"),
    ),
    "realized_outcomes": (
        ("order_id",),
        ("order_id", "actual_delivery_timestamp", "realized_total_cost", "outcome_recorded_at"),
    ),
    "decision_log": (
        ("order_id", "decision_timestamp"),
        ("order_id", "decision_timestamp", "recommended_action", "human_approved",
         "action_executed", "execution_timestamp"),
    ),
    "comparison_assignment": (
        ("order_id",),
        ("order_id", "evaluation_group", "assignment_timestamp", "assignment_method"),
    ),
}
OPTIONALLY_EMPTY = {"actual_delivery_timestamp", "realized_total_cost", "outcome_recorded_at",
                    "execution_timestamp"}
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000


def _timestamp(value):
    """Reject offset-naive timestamps, including a bare date or local clock."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp absent")
    result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("timestamp lacks explicit UTC offset")
    return result


def _date(value):
    if not isinstance(value, str) or len(value.strip()) != 10:
        raise ValueError("date must be ISO YYYY-MM-DD")
    return date.fromisoformat(value.strip())


def _number(value, *, positive=False):
    from decimal import Decimal, InvalidOperation

    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid numeric value") from exc
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        raise ValueError("invalid nonnegative numeric")
    return amount


def _flag(value):
    value = str(value).strip().lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    raise ValueError("invalid boolean")


def load_csv_folder(root):
    """Read only the eight named CSV files, with simple local resource limits."""
    root = Path(root)
    if not root.is_dir():
        raise ValueError("Input must be a directory of eight named CSV files.")
    tables = {}
    for name in CONTRACTS:
        path = root / (name + ".csv")
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"{name} exceeds the local per-table size limit.")
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fields = reader.fieldnames or []
                if not fields or len(fields) != len(set(fields)):
                    raise ValueError(f"{name} has missing or duplicate headers.")
                rows = []
                for item in reader:
                    if len(rows) == MAX_ROWS:
                        raise ValueError(f"{name} exceeds the local row limit.")
                    if None in item or any(v is None for v in item.values()):
                        raise ValueError(f"{name} has a malformed CSV row.")
                    rows.append(item)
                tables[name] = (fields, rows)
        except UnicodeError as exc:
            raise ValueError(f"{name} must be a UTF-8 CSV.") from exc
    return tables


def validate(tables):
    """Validate in-memory {table: (headers, rows)}; never change the input."""
    issues = Counter()
    table_summary = {}
    accepted = {}

    def issue(code, n=1):
        issues[code] += n

    for name, (keys, required) in CONTRACTS.items():
        if name not in tables:
            issue("MISSING_TABLE")
            table_summary[name] = {"status": "MISSING_TABLE", "rows": 0}
            continue
        value = tables[name]
        if not isinstance(value, tuple) or len(value) != 2:
            issue("INVALID_TABLE")
            table_summary[name] = {"status": "INVALID_TABLE", "rows": 0}
            continue
        fields, rows = value
        absent = [field for field in required if field not in fields]
        if absent:
            issue("MISSING_REQUIRED_COLUMNS", len(absent))
            table_summary[name] = {"status": "MISSING_REQUIRED_COLUMNS", "rows": len(rows),
                                   "missing_columns": absent}
            continue
        if not rows:
            issue("EMPTY_TABLE")
            table_summary[name] = {"status": "EMPTY_TABLE", "rows": 0}
            continue
        seen = set()
        for row in rows:
            grain = tuple(str(row[k]).strip() for k in keys)
            if any(not x for x in grain):
                issue("BLANK_KEY")
            if grain in seen:
                issue("DUPLICATE_KEY")
            seen.add(grain)
            if any(not str(row[field]).strip() for field in required if field not in OPTIONALLY_EMPTY):
                issue("BLANK_REQUIRED_FIELD")
        accepted[name] = rows
        table_summary[name] = {"status": "SCHEMA_INSPECTED", "rows": len(rows)}

    orders = accepted.get("orders_at_decision", [])
    decisions = {}
    purchases = {}
    for row in orders:
        try:
            purchase = _timestamp(row["purchase_timestamp"])
            decision = _timestamp(row["decision_timestamp"])
            _date(row["promised_delivery_date"])
            if decision < purchase:
                issue("DECISION_BEFORE_PURCHASE")
            for col in ("purchase_known_at", "promise_known_at", "destination_known_at"):
                if _timestamp(row[col]) > decision:
                    issue("FUTURE_KNOWN_ORDER_FEATURE")
            decisions[row["order_id"]] = decision
            purchases[row["order_id"]] = purchase
        except (ValueError, TypeError, OverflowError):
            issue("INVALID_ORDER_TIMESTAMP_OR_DATE")

    lines = {(r["order_id"], r["item_id"]) for r in accepted.get("demand_lines", [])}
    demand_units = {}
    for row in accepted.get("demand_lines", []):
        if row["order_id"] not in decisions:
            issue("UNMATCHED_DEMAND_ORDER")
        try:
            required = _number(row["required_units"], positive=True)
            _date(row["required_by_date"])
            demand_units[(row["order_id"], row["item_id"])] = required
        except (ValueError, TypeError):
            issue("INVALID_DEMAND_QUANTITY_OR_DATE")

    quotes = defaultdict(list)
    for row in accepted.get("supplier_quotes", []):
        try:
            start = _timestamp(row["quote_recorded_at"])
            end = _timestamp(row["quote_valid_until"])
            _number(row["unit_cost"])
            _number(row["quoted_lead_days"])
            _number(row["minimum_order_qty"], positive=True)
            eligible = _flag(row["eligible_for_item"])
            if end < start:
                issue("QUOTE_EXPIRY_BEFORE_START")
            quotes[(row["item_id"], row["supplier_id"])].append((start, end, row, eligible))
        except (ValueError, TypeError, OverflowError):
            issue("INVALID_QUOTE_OR_TIMESTAMP")

    capacities = defaultdict(list)
    for row in accepted.get("supplier_capacity", []):
        try:
            start = _timestamp(row["capacity_asof"])
            end = _timestamp(row["capacity_valid_until"])
            units = _number(row["available_units"])
            if end < start:
                issue("CAPACITY_EXPIRY_BEFORE_START")
            capacities[(row["item_id"], row["supplier_id"])].append((start, end, units))
        except (ValueError, TypeError, OverflowError):
            issue("INVALID_CAPACITY_OR_TIMESTAMP")

    # The same source snapshot must not be independently reused for several
    # allocations whose *combined* quantity exceeds its recorded availability.
    # This check cannot detect external reservations absent from source data.
    joint_allocation = defaultdict(lambda: {"sum": 0, "available": 0})
    allocations_per_line = defaultdict(int)
    for row in accepted.get("baseline_allocations", []):
        order_id = row["order_id"]
        if (order_id, row["item_id"]) not in lines:
            issue("UNMATCHED_ALLOCATION_DEMAND")
        decision = decisions.get(order_id)
        if decision is None:
            issue("UNMATCHED_ALLOCATION_DECISION")
            continue
        try:
            units = _number(row["allocated_units"], positive=True)
            _number(row["baseline_total_cost"])
        except (ValueError, TypeError):
            issue("INVALID_ALLOCATION_QUANTITY_OR_COST")
            continue
        allocations_per_line[(row["order_id"], row["item_id"])] += units
        key = (row["item_id"], row["supplier_id"])
        quoted = [q for q in quotes[key] if q[0] <= decision <= q[1]]
        current_capacity = [c for c in capacities[key] if c[0] <= decision <= c[1]]
        if not quoted:
            issue("NO_VALID_DECISION_TIME_QUOTE")
        else:
            latest = max(quoted, key=lambda q: q[0])
            if not latest[3]:
                issue("SUPPLIER_NOT_ELIGIBLE")
            if units < _number(latest[2]["minimum_order_qty"]):
                issue("BELOW_SUPPLIER_MOQ")
        if not current_capacity:
            issue("NO_VALID_DECISION_TIME_CAPACITY")
        else:
            selected = max(current_capacity, key=lambda c: c[0])
            if units > selected[2]:
                issue("ALLOCATION_EXCEEDS_ASOF_CAPACITY")
            snapshot = (key, selected[0], selected[1])
            joint_allocation[snapshot]["sum"] += units
            joint_allocation[snapshot]["available"] = selected[2]

    for quantity in joint_allocation.values():
        if quantity["sum"] > quantity["available"]:
            issue("JOINT_CAPACITY_EXCEEDED_WITHIN_SNAPSHOT")
    for line, required_units in demand_units.items():
        if allocations_per_line[line] != required_units:
            issue("DEMAND_ALLOCATION_UNITS_MISMATCH")

    for row in accepted.get("realized_outcomes", []):
        oid = row["order_id"]
        if oid not in decisions:
            issue("UNMATCHED_OUTCOME_ORDER")
        if not row["actual_delivery_timestamp"].strip():
            # An outcome not yet observed must not be silently classified as on time.
            issue("UNKNOWN_DELIVERY_OUTCOME")
            continue
        try:
            actual = _timestamp(row["actual_delivery_timestamp"])
            recorded = _timestamp(row["outcome_recorded_at"])
            if recorded < actual:
                issue("OUTCOME_RECORDED_BEFORE_DELIVERY")
            if oid in purchases and actual < purchases[oid]:
                issue("DELIVERY_BEFORE_PURCHASE")
            if oid in decisions and actual < decisions[oid]:
                issue("DELIVERY_BEFORE_DECISION")
            if row["realized_total_cost"].strip():
                _number(row["realized_total_cost"])
        except (ValueError, TypeError, OverflowError):
            issue("INVALID_OUTCOME_TIMESTAMP_OR_COST")

    for row in accepted.get("decision_log", []):
        oid = row["order_id"]
        if oid not in decisions:
            issue("UNMATCHED_DECISION_LOG_ORDER")
        try:
            timestamp = _timestamp(row["decision_timestamp"])
            approved = _flag(row["human_approved"])
            executed = _flag(row["action_executed"])
            if executed and not approved:
                issue("EXECUTION_WITHOUT_HUMAN_APPROVAL")
            if executed and not row["execution_timestamp"].strip():
                issue("MISSING_EXECUTION_TIMESTAMP")
            if row["execution_timestamp"].strip() and _timestamp(row["execution_timestamp"]) < timestamp:
                issue("EXECUTION_BEFORE_DECISION")
        except (ValueError, TypeError, OverflowError):
            issue("INVALID_DECISION_LOG_TIMESTAMP_OR_FLAG")

    for row in accepted.get("comparison_assignment", []):
        oid = row["order_id"]
        if oid not in decisions:
            issue("UNMATCHED_COMPARISON_ORDER")
            continue
        try:
            if _timestamp(row["assignment_timestamp"]) > decisions[oid]:
                issue("COMPARISON_ASSIGNED_AFTER_DECISION")
        except (ValueError, TypeError, OverflowError):
            issue("INVALID_COMPARISON_TIMESTAMP")

    return {
        "product": "AEGIS",
        "study": "STEP_192_DECISION_TIME_INPUT_GATE",
        "status": "STRUCTURE_AND_ASOF_CONSISTENT_UNATTESTED" if not issues else "BLOCKED_FOR_REVIEW",
        "table_status": table_summary,
        "issue_counts": dict(sorted(issues.items())),
        "issues_total": sum(issues.values()),
        "source_system_independently_attested": False,
        "supplier_capacity_jointly_certified": False,
        "currency_and_delivery_semantics_certified": False,
        "predictive_calibration_certified": False,
        "real_world_intervention_effect_established": False,
        "operational_approval": "NOT_GRANTED",
        "automatic_business_action": "DISABLED",
        "original_models_modified": False,
        "source_data_written": False,
        "interpretation": (
            "Passing only means supplied CSV rows meet selected mechanical as-of "
            "checks. Unobserved source revisions, genuine availability times, "
            "shared capacity reservations, currency and promise meaning, causal "
            "effects and operational security remain unverified."
        ),
    }


def _fixture():
    """Entirely invented rows for testing the validator, never business evidence."""
    purchase = "2025-07-01T09:00:00+00:00"
    decision = "2025-07-01T10:00:00+00:00"
    quote_time = "2025-06-30T09:00:00+00:00"
    expiry = "2025-07-15T00:00:00+00:00"
    rows = {
        "orders_at_decision": [{"order_id": "FIXTURE-1", "purchase_timestamp": purchase,
            "promised_delivery_date": "2025-07-10", "destination_state": "TEST",
            "decision_timestamp": decision, "purchase_known_at": purchase,
            "promise_known_at": purchase, "destination_known_at": purchase}],
        "demand_lines": [{"order_id": "FIXTURE-1", "item_id": "ITEM-1",
                          "required_units": "10", "required_by_date": "2025-07-10"}],
        "supplier_quotes": [{"item_id": "ITEM-1", "supplier_id": "TEST-SUP-1",
            "unit_cost": "20", "quoted_lead_days": "5", "minimum_order_qty": "5",
            "eligible_for_item": "true", "quote_recorded_at": quote_time,
            "quote_valid_until": expiry}],
        "supplier_capacity": [{"item_id": "ITEM-1", "supplier_id": "TEST-SUP-1",
            "available_units": "100", "capacity_asof": quote_time,
            "capacity_valid_until": expiry}],
        "baseline_allocations": [{"order_id": "FIXTURE-1", "item_id": "ITEM-1",
            "supplier_id": "TEST-SUP-1", "allocated_units": "10", "baseline_total_cost": "200"}],
        "realized_outcomes": [{"order_id": "FIXTURE-1", "actual_delivery_timestamp":
            "2025-07-10T11:00:00+00:00", "realized_total_cost": "200",
            "outcome_recorded_at": "2025-07-11T09:00:00+00:00"}],
        "decision_log": [{"order_id": "FIXTURE-1", "decision_timestamp": decision,
            "recommended_action": "NONE", "human_approved": "false",
            "action_executed": "false", "execution_timestamp": ""}],
        "comparison_assignment": [{"order_id": "FIXTURE-1", "evaluation_group": "TEST",
            "assignment_timestamp": purchase, "assignment_method": "SOFTWARE_FIXTURE"}],
    }
    return {name: (list(CONTRACTS[name][1]), records) for name, records in rows.items()}


def self_test():
    tests = {}
    baseline = _fixture()
    tests["valid_test_fixture_only"] = validate(baseline)["issues_total"] == 0
    future = copy.deepcopy(baseline)
    future["orders_at_decision"][1][0]["promise_known_at"] = "2025-07-02T10:00:00+00:00"
    tests["future_known_feature_blocked"] = bool(validate(future)["issue_counts"].get("FUTURE_KNOWN_ORDER_FEATURE"))
    stale_quote = copy.deepcopy(baseline)
    stale_quote["supplier_quotes"][1][0]["quote_valid_until"] = "2025-06-30T12:00:00+00:00"
    tests["expired_quote_blocked"] = bool(validate(stale_quote)["issue_counts"].get("NO_VALID_DECISION_TIME_QUOTE"))
    capacity = copy.deepcopy(baseline)
    capacity["supplier_capacity"][1][0]["capacity_asof"] = "2025-07-02T10:00:00+00:00"
    tests["future_capacity_blocked"] = bool(validate(capacity)["issue_counts"].get("NO_VALID_DECISION_TIME_CAPACITY"))
    execution = copy.deepcopy(baseline)
    execution["decision_log"][1][0]["action_executed"] = "true"
    execution["decision_log"][1][0]["execution_timestamp"] = "2025-07-01T11:00:00+00:00"
    tests["unapproved_execution_detected"] = bool(validate(execution)["issue_counts"].get("EXECUTION_WITHOUT_HUMAN_APPROVAL"))
    missing = copy.deepcopy(baseline)
    del missing["supplier_quotes"]
    tests["missing_table_blocked"] = validate(missing)["status"] == "BLOCKED_FOR_REVIEW"
    no_offset = copy.deepcopy(baseline)
    no_offset["orders_at_decision"][1][0]["decision_timestamp"] = "2025-07-01T10:00:00"
    tests["timezone_naive_rejected"] = bool(validate(no_offset)["issue_counts"].get("INVALID_ORDER_TIMESTAMP_OR_DATE"))
    joint = copy.deepcopy(baseline)
    second = copy.deepcopy(joint["orders_at_decision"][1][0])
    second["order_id"] = "FIXTURE-2"
    joint["orders_at_decision"][1].append(second)
    second_line = copy.deepcopy(joint["demand_lines"][1][0])
    second_line["order_id"] = "FIXTURE-2"
    joint["demand_lines"][1].append(second_line)
    joint["baseline_allocations"][1][0]["allocated_units"] = "80"
    second_allocation = copy.deepcopy(joint["baseline_allocations"][1][0])
    second_allocation["order_id"] = "FIXTURE-2"
    joint["baseline_allocations"][1].append(second_allocation)
    tests["joint_capacity_overbooking_blocked"] = bool(
        validate(joint)["issue_counts"].get("JOINT_CAPACITY_EXCEEDED_WITHIN_SNAPSHOT")
    )
    shortfall = copy.deepcopy(baseline)
    shortfall["baseline_allocations"][1][0]["allocated_units"] = "9"
    tests["demand_shortfall_blocked"] = bool(
        validate(shortfall)["issue_counts"].get("DEMAND_ALLOCATION_UNITS_MISMATCH")
    )
    return {"product": "AEGIS", "step": 192, "fixture": "SOFTWARE_ONLY_NO_REAL_BUSINESS_RECORDS",
            "checks": tests, "all_pass": all(tests.values()), "operational_approval": "NOT_GRANTED",
            "automatic_business_action": "DISABLED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true", help="Run synthetic positive/negative checks; no files written")
    group.add_argument("--source-dir", type=Path, help="Directory of eight authorized canonical CSV files")
    parser.add_argument("--report", type=Path, help="Unused new output path for local JSON report")
    options = parser.parse_args(argv)
    if options.self_test:
        report = self_test()
        print(json.dumps(report, indent=2))
        return 0 if report["all_pass"] else 1
    if options.report is None:
        parser.error("--report is required with --source-dir")
    if options.report.exists():
        parser.error("Report already exists; AEGIS never overwrites earlier evidence")
    report = validate(load_csv_folder(options.source_dir))
    options.report.parent.mkdir(parents=True, exist_ok=True)
    options.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["issues_total"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
