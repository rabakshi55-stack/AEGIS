"""AEGIS: predeclared, outcome-independent scoring eligibility research gate.

No feature is assumed to be genuinely available merely because the supplied
recorded timestamp says so. Only an independent, immutable source audit can
attest source truth. This offline gate never trains, scores, or takes actions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

# Conservative deny list; user-defined allowlists are mandatory too.
OUTCOME_TOKENS = re.compile(r"(?:actual_?deliver|delivered|outcome|late_?flag|cancell|refund|return_?date|review_?score|post_?receipt|delivery_?status)", re.I)
MAX_RECORDS = 100_000
MAX_FEATURES = 100


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError("A timezone-aware ISO timestamp is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timezone offset is required")
    return result


def audit_eligibility(records, contract):
    """Inspect an entire declared opportunity population, before label joining.

    Contract and clocks are caller declarations, not independent provenance.
    The return contains no order IDs or raw feature values.
    """
    if not isinstance(contract, dict) or not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ValueError("Invalid contract or record population")
    if not records:
        raise ValueError("Empty eligible population is not auditable")
    allowed = contract.get("predeclared_feature_names")
    if not isinstance(allowed, list) or not allowed or len(allowed) > MAX_FEATURES or any(
        not isinstance(n, str) or not n or OUTCOME_TOKENS.search(n) for n in allowed
    ) or len(set(allowed)) != len(allowed):
        raise ValueError("Predeclared features must be distinct and outcome-independent")
    registered = _stamp(contract.get("registered_at"))
    start = _stamp(contract.get("decision_window_start"))
    end = _stamp(contract.get("decision_window_end"))
    if not registered <= start <= end:
        raise ValueError("Contract must predate the evaluation window")
    if set(contract) != {"registered_at", "decision_window_start", "decision_window_end", "predeclared_feature_names"}:
        raise ValueError("Unexpected contract fields or missing mandatory fields")
    rejects = Counter()
    ids = set()
    selected = 0
    for entry in records:
        if not isinstance(entry, dict) or set(entry) != {"order_id", "decision_at", "features"}:
            raise ValueError("Unexpected record fields: no outcome/label is permitted in eligibility records")
        oid = entry["order_id"]
        if not isinstance(oid, str) or not oid or oid in ids:
            raise ValueError("Duplicate or blank opportunity identifier")
        ids.add(oid)
        try:
            decision = _stamp(entry["decision_at"])
        except ValueError:
            rejects["INVALID_DECISION_CLOCK"] += 1
            continue
        if not start <= decision <= end:
            rejects["OUTSIDE_PREDECLARED_WINDOW"] += 1
            continue
        features = entry["features"]
        if not isinstance(features, dict) or set(features) != set(allowed):
            rejects["FEATURE_SCHEMA_MISSING_OR_EXTRA"] += 1
            continue
        reason = None
        for name in allowed:
            value = features[name]
            if not isinstance(value, dict) or set(value) != {"value", "known_at", "source_recorded_at"}:
                reason = "FEATURE_PROVENANCE_MISSING"
                break
            if value["value"] is None:
                reason = "FEATURE_VALUE_MISSING"
                break
            try:
                known = _stamp(value["known_at"])
                recorded = _stamp(value["source_recorded_at"])
            except ValueError:
                reason = "FEATURE_CLOCK_INVALID"
                break
            if max(known, recorded) > decision:
                reason = "FEATURE_RECORDED_AFTER_DECISION"
                break
        if reason:
            rejects[reason] += 1
        else:
            selected += 1
    digest = hashlib.sha256(json.dumps({"contract": contract, "records": records}, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {
        "product": "AEGIS", "study": "PREDECLARED_OUTCOME_INDEPENDENT_ELIGIBILITY_SOFTWARE_GATE",
        "status": "ELIGIBILITY_SOFTWARE_AUDIT_UNATTESTED", "population_count": len(records),
        "eligible_count": selected, "ineligible_count": len(records) - selected,
        "exclusion_counts": dict(sorted(rejects.items())),
        "no_label_joins_used": True, "contract_independently_preregistered": False,
        "feature_timestamps_independently_attested": False, "future_predictive_accuracy_certified": False,
        "input_snapshot_sha256": digest, "business_action": "DISABLED",
        "interpretation": "Eligibility used only predeclared features and declared feature timestamps; no delivery outcome was read. All records must be present in the submitted opportunity population. The gate cannot attest source timestamps or completeness of source records."
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="JSON object containing contract and the complete opportunities array")
    p.add_argument("--output", type=Path, help="New report path (must not exist)")
    args = p.parse_args(argv)
    if args.input.stat().st_size > 30_000_000:
        raise ValueError("Oversized eligibility audit")
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"contract", "opportunities"}:
        raise ValueError("Expected exactly contract and opportunities")
    report = audit_eligibility(data["opportunities"], data["contract"])
    output = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        with args.output.open("x", encoding="utf-8") as file:
            file.write(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
