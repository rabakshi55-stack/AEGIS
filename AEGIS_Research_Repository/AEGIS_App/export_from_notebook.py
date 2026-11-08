"""One-time, read-only AEGIS research export. Run with %run -i in Jupyter.

Reads existing validated in-memory notebook objects. Does not train, optimize,
change source tables, or authorize business actions.
"""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

import pandas as pd


def _aegis_export_records(frame):
    return json.loads(pd.DataFrame(frame).to_json(orient="records", date_format="iso"))


def export_aegis_research_bundle(namespace=None):
    ns = namespace if namespace is not None else globals()
    required = (
        "olist_tables_163", "aegis_research_catalog_187",
        "headroom_reference_189", "policy_evidence_129",
        "aegis_olist_readiness_182",
    )
    missing = [key for key in required if key not in ns]
    if missing:
        raise RuntimeError(
            "Required existing notebook results are not in memory: "
            + ", ".join(missing)
            + ". Open the saved validation notebook in its working environment."
        )

    original = ns["olist_tables_163"]["orders"]
    registry = original["order_id"].dropna().astype(str)
    if len(original) != 99441 or len(registry) != 99441 or not registry.is_unique:
        raise AssertionError("Original Olist order registry verification failed.")

    catalog = pd.DataFrame(ns["aegis_research_catalog_187"]).copy()
    research_fields = [
        "order_id", "Phase", "Purchase_Time", "Destination_State",
        "Promise_Days", "Promise_Band", "Research_Score_Uncalibrated",
    ]
    if not set(research_fields).issubset(catalog.columns):
        raise AssertionError("The historical research catalog schema has changed.")
    if len(catalog) != 58911 or not catalog["order_id"].is_unique:
        raise AssertionError("Expected 58,911 unique, frozen model prediction rows.")
    if not set(catalog["order_id"].astype(str)).issubset(set(registry)):
        raise AssertionError("Research predictions contain unknown original order IDs.")

    source_ids = registry.reset_index(drop=True)
    shorts = source_ids.str[:8].copy()
    for length in range(9, 33):
        duplicated = shorts.duplicated(keep=False)
        if not duplicated.any():
            break
        shorts.loc[duplicated] = source_ids.loc[duplicated].str[:length]
    if not shorts.is_unique:
        raise AssertionError("Short order references are not unique.")
    short_by_source = dict(zip(source_ids.tolist(), shorts.tolist()))

    frozen_rows = catalog[research_fields].copy()
    frozen_rows["order_id"] = frozen_rows["order_id"].astype(str)
    frozen_rows["Short_Reference"] = frozen_rows["order_id"].map(short_by_source)
    frozen_rows["Purchase_Time"] = pd.to_datetime(
        frozen_rows["Purchase_Time"], errors="raise"
    )
    if frozen_rows["Research_Score_Uncalibrated"].isna().any():
        raise AssertionError("Missing model research scores cannot be exported.")

    scenarios = pd.DataFrame(ns["headroom_reference_189"]).copy()
    required_scenarios = [
        "Scenario", "Rank", "Actual_Reserve_Pct", "Minimum_Allowance_Pct",
        "Landed_Cost", "Supplier_HHI", "Balanced_Score",
    ]
    if len(scenarios) != 10 or not set(required_scenarios).issubset(scenarios.columns):
        raise AssertionError("The frozen synthetic scenario frontier has changed.")
    if scenarios["Scenario"].duplicated().any():
        raise AssertionError("Synthetic scenario identifiers are duplicated.")

    policies = pd.DataFrame(ns["policy_evidence_129"]).copy()
    readiness = pd.DataFrame(ns["aegis_olist_readiness_182"]).copy()
    if len(policies) != 6:
        raise AssertionError("Expected the six existing legacy policies.")
    if not {"Table", "Module", "Status"}.issubset(readiness.columns):
        raise AssertionError("Readiness schema has changed.")

    bundle = {
        "schema_version": 1,
        "product": "AEGIS",
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "RETROSPECTIVE_RESEARCH_ONLY",
        "source_counts": {
            "original_olist_orders": 99441,
            "scored_research_orders": 58911,
            "synthetic_scenarios": 10,
            "synthetic_policies": 6,
        },
        "source_boundaries": {
            "orders": "REAL_OLIST_HISTORICAL_RESEARCH",
            "scenarios": "SYNTHETIC_CAPACITY_FRONTIER_STEPS_155_156",
            "policies": "SYNTHETIC_SOURCING_PILOT_STEPS_126_139",
            "readiness": "BUSINESS_DATA_CONTRACT_STEP_182",
        },
        "original_order_ids": source_ids.tolist(),
        "research_orders": _aegis_export_records(frozen_rows),
        "scenarios": _aegis_export_records(scenarios[required_scenarios]),
        "policies": _aegis_export_records(policies),
        "readiness": _aegis_export_records(readiness),
        "safety": {
            "operational_approval": "NOT_GRANTED",
            "permitted_action": "NONE",
            "human_review": "REQUIRED",
            "calibrated_probability": False,
            "supplier_intervention_effects": False,
            "prospective_validation": False,
        },
    }

    canonical = json.dumps(bundle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    bundle["content_sha256"] = sha256(canonical.encode("utf-8")).hexdigest()

    destination = Path(__file__).resolve().parent / "data" / "aegis_bundle.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    temporary.replace(destination)

    print("AEGIS — LOCAL APPLICATION RESEARCH EXPORT")
    print("Original Olist orders:", len(source_ids))
    print("Historical scored orders:", len(frozen_rows))
    print("Synthetic optimization scenarios:", len(scenarios))
    print("Synthetic sourcing policies:", len(policies))
    print("Operational readiness tables:", len(readiness))
    print("Original models and data modified: NO")
    print("Model training and optimization: NONE")
    print("Business actions: DISABLED")
    print("Saved:", destination)
    return destination


if __name__ == "__main__":
    export_aegis_research_bundle(globals())
