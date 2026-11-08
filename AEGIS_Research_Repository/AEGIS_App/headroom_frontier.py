"""AEGIS research: optimizer-selected *hypothetical* resource reserve frontier.

This is not the legacy "AI +5%" daily QUOTED-COST allowance. Here, reserve
percentage explicitly constrains uncommitted resource capacity. A cost budget
is supplied by the analyst; no causal resilience benefit is assumed.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from daily_feasibility import verify_and_optimize_plan


def evaluate_reserve_frontier(snapshot, *, reserve_levels=(0, 10, 20, 30),
                              maximum_extra_modeled_cost_cents=0, max_nodes=300_000):
    if type(maximum_extra_modeled_cost_cents) is not int or maximum_extra_modeled_cost_cents < 0:
        raise ValueError("Cost budget must be nonnegative integer cents")
    if not isinstance(reserve_levels, (list, tuple)) or not 1 <= len(reserve_levels) <= 25 or 0 not in reserve_levels:
        raise ValueError("Reserve grid must include 0 and contain 1–25 levels")
    if any(type(h) is not int or h < 0 or h > 90 for h in reserve_levels) or len(set(reserve_levels)) != len(reserve_levels):
        raise ValueError("Reserve levels must be unique whole percentages from 0 to 90")
    frontier=[]
    for reserve in sorted(reserve_levels):
        proposed=deepcopy(snapshot)
        for resource in proposed["resources"]:
            committed=resource["already_committed_units"]
            uncommitted=resource["available_units"]-committed
            if type(uncommitted) is not int or uncommitted<0:
                raise ValueError("Invalid resource commitment")
            resource["available_units"]=committed+(uncommitted*(100-reserve))//100
        result=verify_and_optimize_plan(proposed,max_nodes=max_nodes)
        frontier.append({"minimum_unused_capacity_percent_declared":reserve,
                         "status":result["status"],"exact_optimal":result["exact_optimal"],
                         "modeled_cost_cents":result.get("cost_cents") if result["exact_optimal"] else None,
                         "assignment":result.get("assignment") if result["exact_optimal"] else None})
    zero=next(r for r in frontier if r["minimum_unused_capacity_percent_declared"]==0)
    if not zero["exact_optimal"]:
        return {"status":"NO_EXACT_REFERENCE","frontier":frontier,"selected":None,
                "operational_approval":"NOT_GRANTED","permitted_business_action":"NONE",
                "legacy_ai_plus_five_quoted_cost_allowance_is_capacity":False}
    ceiling=zero["modeled_cost_cents"]+maximum_extra_modeled_cost_cents
    feasible=[r for r in frontier if r["exact_optimal"] and r["modeled_cost_cents"]<=ceiling]
    selected=max(feasible,key=lambda r:(r["minimum_unused_capacity_percent_declared"],-r["modeled_cost_cents"]))
    return {"status":"EXACT_GRID_CONSTRAINED_RESEARCH_ONLY",
            "baseline_modeled_cost_cents":zero["modeled_cost_cents"],
            "maximum_extra_modeled_cost_cents":maximum_extra_modeled_cost_cents,
            "declared_cost_ceiling_cents":ceiling,
            "frontier":frontier,"selected":selected,"operational_approval":"NOT_GRANTED",
            "permitted_business_action":"NONE",
            "legacy_ai_plus_five_quoted_cost_allowance_is_capacity":False,
            "actual_resilience_benefit_proven":False,
            "interpretation":"The program chooses a reserve level from a predeclared finite grid by maximizing unused declared capacity within an analyst-specified cost ceiling. Each candidate is re-solved jointly across all declared daily resources; no risk reduction, actual capacity, supplier causality or real savings is established."}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot",type=Path)
    p.add_argument("--reserve-levels",default="0,10,20,30")
    p.add_argument("--max-extra-cost-cents",type=int,default=0)
    p.add_argument("--report",type=Path)
    a=p.parse_args(argv)
    levels=tuple(int(x) for x in a.reserve_levels.split(','))
    result=evaluate_reserve_frontier(json.loads(a.snapshot.read_text(encoding='utf-8')),
                        reserve_levels=levels,maximum_extra_modeled_cost_cents=a.max_extra_cost_cents)
    data=json.dumps(result,indent=2,sort_keys=True)
    if a.report:
        with a.report.open('x',encoding='utf-8') as f:f.write(data+'\n')
    else:print(data)

if __name__=='__main__':main()
