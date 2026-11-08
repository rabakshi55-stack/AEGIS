"""Read-only presentation of archived, source-reconciled historical validation.

The archived report is not a new test, a cryptographic signature, or a
prospective / real-world certification. This module never scores or trains.
"""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
EVIDENCE_PATH = ROOT / "data" / "model_validation_evidence.json"
BUNDLE_PATH = ROOT / "data" / "aegis_bundle.json"


def get_evidence(bundle_path=BUNDLE_PATH, evidence_path=EVIDENCE_PATH, expected_count=58911):
    baseline = {
        "available": False,
        "scope": "RETROSPECTIVE_RESEARCH_ONLY",
        "operational_approval": "NOT_GRANTED",
        "automatic_business_actions": "DISABLED",
        "prospective_certified": False,
    }
    try:
        snapshot = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
        if snapshot.get("schema") != 1 or snapshot.get("scope") != "RETROSPECTIVE_RESEARCH_ONLY":
            raise ValueError("Unsupported model-evidence schema or scope")
        if snapshot.get("operational_approval") != "NOT_GRANTED" or snapshot.get("automatic_business_actions") != "DISABLED":
            raise ValueError("Model-evidence safety contract is invalid")
        if snapshot.get("pristine_prospective_holdout") is not False or snapshot.get("probability_calibration_certified") is not False:
            raise ValueError("Model-evidence certification flags are invalid")
        bundle_hash = hashlib.sha256(Path(bundle_path).read_bytes()).hexdigest()
        if bundle_hash != snapshot.get("frozen_bundle_sha256"):
            raise ValueError("Frozen research bundle does not match archived validation evidence")
        phases = snapshot["phases"]
        if set(phases) != {"ALL", "TRAIN", "VALIDATION", "TEST"}:
            raise ValueError("Expected all four historical evaluation periods")
        if sum(phases[p]["count"] for p in ("TRAIN", "VALIDATION", "TEST")) != expected_count:
            raise ValueError("Historical research population is inconsistent")
        if phases["ALL"]["count"] != expected_count or sum(phases[p]["late_count"] for p in ("TRAIN", "VALIDATION", "TEST")) != phases["ALL"]["late_count"]:
            raise ValueError("Scored and late-order totals are inconsistent")
        for value in phases.values():
            count, late = value["count"], value["late_count"]
            if type(count) is not int or type(late) is not int or not 0 <= late <= count:
                raise ValueError("Invalid scored-order counts")
            for key in ("observed_late_rate", "mean_frozen_score", "roc_auc", "average_precision"):
                number = value[key]
                if not isinstance(number, (float, int)) or not math.isfinite(number) or not 0 <= number <= 1:
                    raise ValueError("Invalid historical metric")
            if abs(value["observed_late_rate"] - (late / count)) > 1e-9:
                raise ValueError("Late rate is inconsistent with the audited counts")
        if snapshot["report_checks_passed"] != 23 or snapshot["report_checks_total"] != 23:
            raise ValueError("Archived audit was not fully reconciled")
        baseline.update({
            "available": True,
            "source": "ARCHIVED_CONSOLIDATED_HISTORICAL_AUDIT",
            "archive_report_sha256": snapshot["original_report_sha256"],
            "bundle_sha256_matched": True,
            "software_source_checks": 23,
            "phases": phases,
            "long_promise_impact_auc": snapshot["long_promise_impact_auc"],
            "alerts": snapshot["alerts"],
            "disclaimer": ("Read-only archived historical metrics for the exact frozen bundle. "
                "These do not prove model calibration, purchase-time feature availability, "
                "pristine holdout isolation, or prospective operational effectiveness. "
                "The application does not independently recheck original Olist CSVs."),
        })
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, ZeroDivisionError) as exc:
        baseline["error"] = f"Historical validation evidence unavailable: {exc}"
    return baseline
