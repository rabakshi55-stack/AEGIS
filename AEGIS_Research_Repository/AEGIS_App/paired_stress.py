"""AEGIS: complete, explicitly hypothetical paired sourcing stress experiment.

This module is independent of AEGIS's historical risk model and frozen research
outputs. It NEVER estimates real-world delivery probabilities, recommends a
supplier, changes a source file, or authorizes business activity.

The experiment varies a disclosed *dimensionless* stress index across the
full eligible menu under reproducible shared synthetic shock scenarios.
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import random
import statistics
import zipfile


SOURCES = (
    "purchase_orders.csv",
    "supplier_component_options.csv",
    "transport_lanes.csv",
    "suppliers.csv",
)
SHOCK_WEIGHTS = (0.25, 0.60, 0.85)
MODEL_STATEMENT = (
    "Illustrative dimensionless stress index = "
    "(global_weight * common_shock + (1-global_weight) * region_shock) "
    "* (2 - synthetic_contract_on_time_target). "
    "The formula and weights are assumptions, not fitted or validated effects."
)


def _source_bytes(source: Path) -> dict[str, bytes]:
    """Read required files from a directory or archive, without extracting."""
    if source.is_file() and source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            paths = [name for name in archive.namelist() if not name.endswith("/")]
            resolved = {}
            for filename in SOURCES:
                found = [
                    name for name in paths
                    if name.replace("\\", "/").endswith("/data/" + filename)
                ]
                if len(found) != 1:
                    raise ValueError(f"Expected exactly one data/{filename} in ZIP.")
                resolved[filename] = archive.read(found[0])
            return resolved

    if source.is_dir():
        dirs = (source / "data", source)
        matches = [d for d in dirs if all((d / name).is_file() for name in SOURCES)]
        if len(matches) != 1:
            raise ValueError("Source directory must contain a single complete data/ folder.")
        return {name: (matches[0] / name).read_bytes() for name in SOURCES}
    raise ValueError("Source must be the original integrated dataset ZIP or data directory.")


def _rows(raw: bytes, filename: str) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError(f"Missing or duplicate CSV headers in {filename}.")
    records = list(reader)
    if not records or any(None in r for r in records):
        raise ValueError(f"Empty or malformed CSV: {filename}.")
    return records


def _index_unique(rows, key, label):
    result = {}
    for item in rows:
        value = key(item)
        if value in result:
            raise ValueError(f"Duplicate {label}: {value}.")
        result[value] = item
    return result


def _amount(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid negative or non-finite numeric source value.")
    return result


def build_candidate_menu(raw_sources, component="CMP-007", month="2025-07"):
    """Rebuild source-derived eligible order/supplier pairs without outcome fields."""
    orders = _rows(raw_sources["purchase_orders.csv"], "purchase_orders.csv")
    options = _rows(raw_sources["supplier_component_options.csv"], "supplier_component_options.csv")
    lanes = _rows(raw_sources["transport_lanes.csv"], "transport_lanes.csv")
    suppliers = _rows(raw_sources["suppliers.csv"], "suppliers.csv")

    selected = sorted(
        (r for r in orders if r["component_id"] == component and r["order_date"][:7] == month),
        key=lambda r: r["purchase_order_id"],
    )
    if not selected:
        raise ValueError("No orders match the selected synthetic pilot month and component.")
    _index_unique(selected, lambda r: r["purchase_order_id"], "purchase order")
    option_map = _index_unique(
        options, lambda r: (r["component_id"], r["supplier_id"]), "supplier option"
    )
    lane_map = _index_unique(
        (r for r in lanes if r["origin_type"] == "supplier" and r["destination_type"] == "plant"),
        lambda r: (r["origin_id"], r["destination_id"]), "sourcing lane"
    )
    supplier_map = _index_unique(suppliers, lambda r: r["supplier_id"], "supplier")
    menu = []
    for order in selected:
        count = 0
        for (comp, supplier_id), option in sorted(option_map.items()):
            if comp != component or option["approved_for_sourcing"] != "1":
                continue
            supplier = supplier_map.get(supplier_id)
            lane = lane_map.get((supplier_id, order["plant_id"]))
            if supplier is None or lane is None:
                continue
            if supplier["qualified_flag"] != "1":
                continue
            units = _amount(order["order_quantity_units"])
            if units < _amount(option["minimum_order_qty"]):
                continue
            target = float(_amount(supplier["contract_on_time_target"]))
            if not 0 <= target <= 1:
                raise ValueError("Invalid synthetic contract-on-time target.")
            landed = units * (_amount(option["quoted_unit_cost_usd"]) + _amount(lane["freight_cost_per_unit_usd"]))
            menu.append({
                "order_id": order["purchase_order_id"],
                "supplier_id": supplier_id,
                "baseline_supplier_id": order["supplier_id"],
                "region": supplier["region"],
                "synthetic_contract_on_time_target": target,
                "landed_cost_usd": f"{landed:.2f}",
                "baseline": supplier_id == order["supplier_id"],
            })
            count += 1
        if not count:
            raise ValueError("An order has no eligible sourcing options.")

    baselines = {}
    for row in menu:
        if row["baseline"]:
            if row["order_id"] in baselines:
                raise ValueError("Multiple baseline suppliers for one order.")
            baselines[row["order_id"]] = row
    if len(baselines) != len(selected):
        raise ValueError("Source baseline not present in eligible candidate menu.")
    if len(menu) != len({(r["order_id"], r["supplier_id"]) for r in menu}):
        raise ValueError("Duplicate order/supplier pairs.")
    return menu


def run_experiment(source, *, scenarios=500, seed=191, component="CMP-007", month="2025-07"):
    """Return an immutable-source, fully paired synthetic stress experiment."""
    if not isinstance(scenarios, int) or scenarios < 2 or scenarios > 10_000:
        raise ValueError("scenarios must be an integer between 2 and 10,000.")
    raw = _source_bytes(Path(source))
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
    menu = build_candidate_menu(raw, component=component, month=month)
    by_order = {}
    for row in menu:
        by_order.setdefault(row["order_id"], []).append(row)
    baselines = {o: next(x for x in entries if x["baseline"]) for o, entries in by_order.items()}
    regions = sorted({r["region"] for r in menu})
    rng = random.Random(seed)
    shocks = []
    exposures = []
    deltas = {(r["order_id"], r["supplier_id"], w): [] for r in menu for w in SHOCK_WEIGHTS}

    # Every candidate for a given order and scenario receives the same complete
    # exogenous shock vector: one global draw and one draw per supplier region.
    for scenario_id in range(1, scenarios + 1):
        global_draw = rng.random()
        regional = {region: rng.random() for region in regions}
        shocks.append({"scenario_id": scenario_id, "global_shock": round(global_draw, 8),
                       "regional_shocks": {key: round(val, 8) for key, val in regional.items()}})

        def exposure(candidate, weight):
            return (weight * global_draw + (1 - weight) * regional[candidate["region"]]) * (
                2 - candidate["synthetic_contract_on_time_target"]
            )

        for order_id, entries in sorted(by_order.items()):
            baseline = baselines[order_id]
            for row in entries:
                pair = (order_id, row["supplier_id"])
                for weight in SHOCK_WEIGHTS:
                    deltas[(*pair, weight)].append(exposure(row, weight) - exposure(baseline, weight))
                exposures.append({
                    "scenario_id": scenario_id,
                    "order_id": order_id,
                    "candidate_supplier_id": row["supplier_id"],
                    "baseline_supplier_id": baseline["supplier_id"],
                    "global_shock": round(global_draw, 8),
                    "candidate_region_shock": round(regional[row["region"]], 8),
                    "baseline_region_shock": round(regional[baseline["region"]], 8),
                    "candidate_stress_index": round(exposure(row, 0.60), 8),
                    "baseline_stress_index": round(exposure(baseline, 0.60), 8),
                    "paired_difference_index": round(exposure(row, 0.60) - exposure(baseline, 0.60), 8),
                })

    results = []
    for row in menu:
        key = (row["order_id"], row["supplier_id"])
        results.append({
            "order_id": key[0],
            "candidate_supplier_id": key[1],
            "baseline_supplier_id": row["baseline_supplier_id"],
            "mean_paired_index_difference": round(statistics.mean(deltas[(*key, 0.60)]), 8),
            "sensitivity_weight_025": round(statistics.mean(deltas[(*key, 0.25)]), 8),
            "sensitivity_weight_085": round(statistics.mean(deltas[(*key, 0.85)]), 8),
            "baseline": row["baseline"],
        })

    pairs = {(r["order_id"], r["candidate_supplier_id"]) for r in exposures}
    unique_grain = {(r["scenario_id"], r["order_id"], r["candidate_supplier_id"]) for r in exposures}
    expected = scenarios * len(menu)
    counts = {}
    for r in exposures:
        k = (r["order_id"], r["candidate_supplier_id"])
        counts[k] = counts.get(k, 0) + 1
    baselines_zero = all(
        r["mean_paired_index_difference"] == 0
        and r["sensitivity_weight_025"] == 0
        and r["sensitivity_weight_085"] == 0
        for r in results if r["baseline"]
    )
    checks = {
        "all_menu_pairs_covered": len(pairs) == len(menu),
        "unique_scenario_order_supplier_rows": len(unique_grain) == expected,
        "identical_scenario_count_per_pair": all(v == scenarios for v in counts.values()),
        "one_baseline_per_order": sum(r["baseline"] for r in menu) == len(by_order),
        "baseline_compares_to_itself_exactly": baselines_zero,
        "all_scenarios_have_common_shock_vector": len(shocks) == scenarios,
    }
    if not all(checks.values()):
        raise AssertionError(f"Paired stress verification failed: {checks}")
    report = {
        "product": "AEGIS",
        "experiment": "FULL_MENU_SHARED_SHOCK_SYNTHETIC_STRESS",
        "research_only": True,
        "historical_risk_model_used": False,
        "model_trained_or_modified": False,
        "real_supplier_causality_established": False,
        "real_intervention_effect_established": False,
        "joint_capacity_feasibility_retested": False,
        "real_quotes_or_contracts_verified": False,
        "late_delivery_probabilities_estimated": False,
        "operational_approval": "NOT_GRANTED",
        "permitted_business_action": "NONE",
        "original_experiment_replaced": False,
        "scenario_count": scenarios,
        "seed": seed,
        "order_count": len(by_order),
        "candidate_pair_count": len(menu),
        "paired_rows": len(exposures),
        "coverage_percent": 100.0 * len(pairs) / len(menu),
        "component": component,
        "month": month,
        "formula": MODEL_STATEMENT,
        "sensitivity_global_weights": list(SHOCK_WEIGHTS),
        "source_sha256": hashes,
        "independent_checks": checks,
        "interpretation": (
            "This repairs the candidate-coverage gap only for a NEW illustrative "
            "stress experiment. It does not complete the original frozen-model "
            "simulation, provide observed delivery outcomes, calibrate predictions, "
            "prove causal supplier benefits, or justify procurement."
        ),
    }
    return {"report": report, "candidate_menu": menu, "scenarios": shocks,
            "paired_exposures": exposures, "pair_summary": results}


def export_experiment(result, output: Path):
    """Write only new evidence files to a separate, explicit output folder."""
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Output directory is not empty; existing reports will not be overwritten.")
    output.mkdir(parents=True, exist_ok=True)
    for name in ("candidate_menu", "paired_exposures", "pair_summary"):
        records = result[name]
        with (output / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    (output / "synthetic_shared_shocks.json").write_text(
        json.dumps(result["scenarios"], indent=2), encoding="utf-8"
    )
    (output / "audit_report.json").write_text(
        json.dumps(result["report"], indent=2), encoding="utf-8"
    )
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Integrated dataset ZIP or its extracted root")
    parser.add_argument("--output", required=True, type=Path, help="A new, empty report folder")
    parser.add_argument("--scenarios", default=500, type=int)
    parser.add_argument("--seed", default=191, type=int)
    args = parser.parse_args(argv)
    result = run_experiment(args.source, scenarios=args.scenarios, seed=args.seed)
    export_experiment(result, args.output)
    print(json.dumps(result["report"], indent=2))


if __name__ == "__main__":
    main()
