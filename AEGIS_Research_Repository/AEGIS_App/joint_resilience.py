"""AEGIS: paired, synthetic capacity shocks with a reoptimized DAILY planner.

This is not the original Step 191 study; its results are separate and cannot
replace its outputs. It compares an explicitly fixed baseline and the best
modelled cost assignment under identical shocks and constraints. Causality,
real supplier availability and measured recovery remain unverified.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from daily_feasibility import verify_and_optimize_plan


def _digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def run_paired_daily_stress(snapshot, baseline, *, scenarios=100, seed=191, max_nodes=100_000):
    if type(scenarios) is not int or not 2 <= scenarios <= 500:
        raise ValueError("scenarios must be an integer from 2 to 500")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be a nonnegative 32-bit integer")
    if type(baseline) is not dict or not isinstance(snapshot, dict):
        raise ValueError("Baseline and snapshot must be structured objects")
    order_ids = [o["order_id"] for o in snapshot["orders"]]
    if len(set(order_ids)) != len(order_ids) or set(baseline) != set(order_ids):
        raise ValueError("Baseline must cover each distinct order exactly once")
    options = {o["option_id"]: o for o in snapshot["options"]}
    if len(options) != len(snapshot["options"]):
        raise ValueError("Duplicate option IDs")
    for order_id, option_id in baseline.items():
        if option_id not in options or options[option_id]["order_id"] != order_id:
            raise ValueError("Baseline option missing or assigned to wrong order")
    original_hash = _digest(snapshot)
    rng = random.Random(seed)
    levels = (0, 0, 0, 1, 1, 2)  # synthetic loss levels 0%, 25%, 50%
    rows = []
    for i in range(scenarios):
        shocked = deepcopy(snapshot)
        applied = {}
        for res in shocked["resources"]:
            reduction = rng.choice(levels)
            # Retain pre-existing commitments, stress only remaining slack.
            free = res["available_units"] - res["already_committed_units"]
            if type(free) is not int or free < 0:
                raise ValueError("Invalid declared resource commitments")
            remaining_free = free * (4 - reduction) // 4 if reduction else free
            res["available_units"] = res["already_committed_units"] + remaining_free
            applied[res["resource_id"]] = reduction * 25
        fixed = deepcopy(shocked)
        fixed["options"] = [opt for opt in fixed["options"] if opt["option_id"] in set(baseline.values())]
        baseline_result = verify_and_optimize_plan(fixed, max_nodes=max_nodes)
        optimized_result = verify_and_optimize_plan(shocked, max_nodes=max_nodes)
        baseline_exact = baseline_result["status"] == "EXACT_MIN_COST_UNATTESTED"
        optimized_exact = optimized_result["status"] == "EXACT_MIN_COST_UNATTESTED"
        comparison_valid = baseline_exact and optimized_exact
        delta = (baseline_result["cost_cents"] - optimized_result["cost_cents"] if comparison_valid else None)
        if delta is not None and delta < 0:
            raise AssertionError("Exact optimizer worse than fixed baseline under identical shock")
        rows.append({
            "scenario": i+1, "shock_resource_loss_percent": applied, "shock_sha256": _digest(applied),
            "baseline_status": baseline_result["status"], "optimized_status": optimized_result["status"],
            "baseline_feasible_exact": baseline_exact, "optimized_feasible_exact": optimized_exact,
            "baseline_cost_cents": baseline_result["cost_cents"] if baseline_exact else None,
            "optimized_cost_cents": optimized_result["cost_cents"] if optimized_exact else None,
            "conditional_model_cost_difference_cents": delta,
            "comparison_valid": comparison_valid,
        })
    comparison = [r for r in rows if r["comparison_valid"]]
    optim = sum(r["optimized_feasible_exact"] for r in rows)
    base = sum(r["baseline_feasible_exact"] for r in rows)
    return {
        "product": "AEGIS", "experiment": "PAIRED_DAILY_JOINT_CAPACITY_REOPTIMIZATION_SYNTHETIC",
        "research_only": True, "not_the_original_step191_experiment": True,
        "input_sha256": original_hash, "baseline_assignment_sha256": _digest(baseline),
        "seed": seed, "scenarios": scenarios, "currency": snapshot["currency"],
        "fixed_baseline_exact_feasible_count": base, "reoptimized_exact_feasible_count": optim,
        "comparable_exact_pairs": len(comparison),
        "baseline_infeasible_or_unproven_count": scenarios - base,
        "reoptimization_infeasible_or_unproven_count": scenarios - optim,
        "hypothetical_cost_delta_cents_on_comparable_pairs": sum(r["conditional_model_cost_difference_cents"] for r in comparison),
        "paired_results": rows, "source_or_scenario_attested": False,
        "shock_distribution_calibrated_to_real_events": False,
        "recovery_duration_measured": False, "supplier_switch_effect_causal": False,
        "operational_approval": "NOT_GRANTED", "permitted_business_action": "NONE",
        "interpretation": "Both policies faced identical resource reductions and all declared daily constraints per scenario. Cost differences apply only to pairs where both could be solved exactly. Infeasible cases are not counted as savings. All losses, quotations, capacity and baseline assignments are synthetic or caller-declared; no realized improvement is established.",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    p.add_argument("baseline", type=Path, help="JSON map order_id to fixed baseline option_id")
    p.add_argument("--scenarios", type=int, default=100)
    p.add_argument("--seed", type=int, default=191)
    p.add_argument("--report", type=Path, help="New report path; never overwrite historical evidence")
    args = p.parse_args(argv)
    result = run_paired_daily_stress(json.loads(args.snapshot.read_text(encoding="utf-8")),
                                      json.loads(args.baseline.read_text(encoding="utf-8")),
                                      scenarios=args.scenarios, seed=args.seed)
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.report:
        with args.report.open("x", encoding="utf-8") as f:
            f.write(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
