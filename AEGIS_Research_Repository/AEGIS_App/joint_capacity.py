"""AEGIS — source-derived SYNTHETIC monthly joint-capacity assignment.

Every order is indivisible and assigned to one eligible supplier.  Monthly
supplier/component quotas are hard constraints. This does NOT certify daily
commitments, concurrent components, contract validity, service outcomes,
causality or a real-world supplier switching benefit.

Stdlib only. No training, no real procurement, no writes to source data.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from paired_stress import _source_bytes, _rows, _amount, build_candidate_menu

SOURCE_NAMES = ("purchase_orders.csv", "supplier_component_options.csv", "transport_lanes.csv", "suppliers.csv")


def _units(value):
    result = _amount(value)
    if result != result.to_integral_value() or result <= 0:
        raise ValueError("Source quantities and capacities must be positive whole units")
    return int(result)


def _money_cents(value):
    cents = _amount(value) * 100
    if cents != cents.to_integral_value():
        raise ValueError("Landed cost must resolve to integer cents")
    return int(cents)


def _get_problem(raw, component, month):
    menu = build_candidate_menu(raw, component, month)
    orders = _rows(raw["purchase_orders.csv"], "purchase_orders.csv")
    options = _rows(raw["supplier_component_options.csv"], "supplier_component_options.csv")
    quantities = {}
    for r in orders:
        if r["component_id"] == component and r["order_date"][:7] == month:
            key = r["purchase_order_id"]
            if key in quantities:
                raise ValueError("Duplicate month purchase order")
            quantities[key] = _units(r["order_quantity_units"])
    suppliers = {r["supplier_id"] for r in menu}
    caps = {}
    for r in options:
        if r["component_id"] == component and r["supplier_id"] in suppliers:
            key = r["supplier_id"]
            if key in caps:
                raise ValueError("Duplicate supplier component capacity")
            caps[key] = _units(r["monthly_capacity_units"])
    if set(caps) != suppliers:
        raise ValueError("Missing supplier/component monthly capacity")
    candidates = defaultdict(list)
    for m in menu:
        key = m["order_id"]
        if key not in quantities:
            raise ValueError("Candidate not in purchased cohort")
        candidates[key].append({"supplier":m["supplier_id"],"cost":_money_cents(m["landed_cost_usd"]), "baseline":m["baseline"]})
    if set(candidates) != set(quantities):
        raise ValueError("Every order must have at least one candidate")
    return quantities, caps, candidates


def solve_whole_order_assignment(quantities, capacities, candidates, max_nodes=2_000_000):
    """Finite B&B. Claims exact optimality only if full search completes.

    A node limit is always explicit: any truncated result is a feasible
    incumbent, NEVER an optimality certificate.
    """
    if not isinstance(max_nodes,int) or isinstance(max_nodes,bool) or max_nodes < 1:
        raise ValueError("max_nodes must be a positive integer")
    if not quantities or not capacities or set(candidates) != set(quantities):
        raise ValueError("Invalid assignment problem")
    q = {o:_units(v) for o,v in quantities.items()}
    caps = {s:_units(v) for s,v in capacities.items()}
    normalized = {}
    for order, entries in candidates.items():
        got={}
        for r in entries:
            supplier=r["supplier"]
            if supplier not in caps or supplier in got or type(r["cost"]) is not int or r["cost"] < 0:
                raise ValueError("Invalid or duplicated supplier option")
            got[supplier]=int(r["cost"])
        if not got:
            raise ValueError("No options for an order")
        normalized[order]=got
    # High-regret orders first. Deterministic tie-breaking, independent of source row ordering.
    def priority(order):
        sorted_cost=sorted(normalized[order].values())
        second=sorted_cost[1] if len(sorted_cost)>1 else sorted_cost[0] + 1_000_000_000
        return (-(second-sorted_cost[0]),-q[order],str(order))
    order_ids=sorted(q,key=priority)
    options={o:sorted(normalized[o].items(),key=lambda p:(p[1],p[0])) for o in order_ids}
    baseline={}
    for o in order_ids:
        entries=[r for r in candidates[o] if r.get('baseline') is True]
        if len(entries)!=1:raise ValueError("Exactly one baseline per order is required")
        baseline[o]=entries[0]['supplier']
    def cost_of(selection):return sum(normalized[o][s] for o,s in selection.items())
    def feasible(selection):
        consumed=defaultdict(int)
        for o,s in selection.items():
            if s not in normalized[o]:return False
            consumed[s]+=q[o]
        return all(consumed[s] <= caps[s] for s in consumed)
    # Baseline is only a valid incumbent if it obeys ALL joint capacity constraints.
    incumbent=baseline.copy() if feasible(baseline) else None
    incumbent_cost=cost_of(incumbent) if incumbent is not None else float('inf')
    # A cheap greedy assignment sometimes provides a tighter initial bound.
    remaining=caps.copy(); greedy={}
    for o in order_ids:
        choices=[(s,c) for s,c in options[o] if remaining[s]>=q[o]]
        if not choices:break
        supplier,_=choices[0];greedy[o]=supplier;remaining[supplier]-=q[o]
    if len(greedy)==len(order_ids):
        g_cost=cost_of(greedy)
        if g_cost<incumbent_cost:
            incumbent,incumbent_cost=greedy,g_cost
    remaining=caps.copy();selected={};nodes=0;truncated=False
    def optimistic_bound(index,total):
        # Relax shared capacity consumption for the unassigned orders. Safe LB.
        result=total
        for o in order_ids[index:]:
            available=[cost for supplier,cost in options[o] if remaining[supplier]>=q[o]]
            if not available:return float('inf')
            result+=available[0] # already sorted by cost
        return result
    def visit(index,total):
        nonlocal nodes, truncated, incumbent, incumbent_cost
        if nodes>=max_nodes:
            truncated=True
            return
        nodes+=1
        if index==len(order_ids):
            if total<incumbent_cost:
                incumbent,incumbent_cost=selected.copy(),total
            return
        if optimistic_bound(index,total)>=incumbent_cost:
            return
        order=order_ids[index]; qty=q[order]
        for supplier,cost in options[order]:
            if remaining[supplier]<qty:continue
            if total+cost>=incumbent_cost:continue
            remaining[supplier]-=qty;selected[order]=supplier
            visit(index+1,total+cost)
            del selected[order];remaining[supplier]+=qty
            if truncated:return
    visit(0,0)
    if incumbent is None:
        status="NOT_PROVEN_FEASIBLE" if truncated else "INFEASIBLE_WITH_CURRENT_MONTHLY_CONSTRAINTS"
        return {"status":status,"exact_optimal":False,"nodes":nodes,"truncated":truncated,"assignment":None,
                "baseline_feasible":feasible(baseline),"baseline_cost_cents":cost_of(baseline),"solution_cost_cents":None}
    status="EXACT_MIN_COST_MONTHLY_SYNTHETIC" if not truncated else "FEASIBLE_NOT_PROVEN_OPTIMAL"
    by_supplier=defaultdict(int)
    for order,supplier in incumbent.items():by_supplier[supplier]+=q[order]
    if not feasible(incumbent) or len(incumbent)!=len(order_ids):
        raise AssertionError("Joint assignment fails capacity or coverage")
    return {"status":status,"exact_optimal":not truncated,"nodes":nodes,"truncated":truncated,"assignment":incumbent,
            "capacity_by_supplier":{s:{"monthly_capacity_units":caps[s],"assigned_units":by_supplier[s],"remaining_units":caps[s]-by_supplier[s]} for s in sorted(caps)},
            "baseline_feasible":feasible(baseline),"baseline_cost_cents":cost_of(baseline),"solution_cost_cents":incumbent_cost,
            "difference_from_baseline_cents":cost_of(baseline)-incumbent_cost}


def _independent_two_supplier_reference(quantities, capacities, candidates):
    """Independent 0/1 knapsack proof for dominated two-supplier instances.

    Applicable only where one supplier is least-cost for EVERY order, a
    second is next-cheapest for EVERY order, and the second can absorb all
    units. Every other supplier is then dominated for this monthly problem.
    """
    suppliers = sorted(capacities)
    total_units = sum(quantities.values())
    by_order = {o:{c['supplier']:c['cost'] for c in options} for o,options in candidates.items()}
    for low in suppliers:
        for backup in suppliers:
            if low==backup or capacities[backup]<total_units:continue
            if not all(low in opts and backup in opts and opts[low] <= opts[backup] <= min(v for s,v in opts.items() if s!=low) for opts in by_order.values()):
                continue
            cap=capacities[low]
            dp=[None]*(cap+1)
            dp[0]=0
            for order in sorted(quantities):
                quantity=quantities[order]
                gain=by_order[order][backup]-by_order[order][low]
                for amount in range(cap,quantity-1,-1):
                    previous=dp[amount-quantity]
                    if previous is not None:
                        new=previous+gain
                        if dp[amount] is None or new>dp[amount]:dp[amount]=new
            if max(x for x in dp if x is not None) < 0:
                raise AssertionError('Reference knapsack failed baseline feasibility')
            return {"method":"INDEPENDENT_EXACT_0_1_KNAPSACK", "dominating_supplier":low,
                    "unconstrained_backup_supplier":backup,
                    "reference_optimal_cents":sum(by_order[o][backup] for o in quantities)-max(x for x in dp if x is not None),
                    "all_other_supplier_options_dominated":True}
    return {"method":"NOT_APPLICABLE", "reason":"No provable all-order dominant supplier pair with unlimited backup capacity"}


def run(source, *, component="CMP-007", month="2025-07", max_nodes=2_000_000):
    raw=_source_bytes(Path(source))
    hashes={k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}
    quantities, capacities, candidates=_get_problem(raw,component,month)
    result=solve_whole_order_assignment(quantities,capacities,candidates,max_nodes=max_nodes)
    reference=_independent_two_supplier_reference(quantities,capacities,candidates)
    if reference['method']=='INDEPENDENT_EXACT_0_1_KNAPSACK' and result['exact_optimal']:
        if reference['reference_optimal_cents']!=result['solution_cost_cents']:
            raise AssertionError('Independent capacity-aware reference disproves optimizer result')
        reference['matches_solver']=True
    # Independent recomputation of assignment from source menu and shared capacities.
    checks={"all_order_assignments":False,"only_eligible_source_candidates":False,"all_monthly_capacities_respected":False,"candidate_cost_reconciles":False,"baseline_joint_capacity_feasible":result['baseline_feasible']}
    if result['assignment'] is not None:
        assignment=result['assignment']
        checks['all_order_assignments']=set(assignment)==set(quantities)
        checks['only_eligible_source_candidates']=all(assignment[o] in {v['supplier'] for v in candidates[o]} for o in assignment)
        usage=defaultdict(int)
        costs=0
        for order,supplier in assignment.items():
            usage[supplier]+=quantities[order]
            costs+=next(x['cost'] for x in candidates[order] if x['supplier']==supplier)
        checks['all_monthly_capacities_respected']=all(usage[s]<=cap for s,cap in capacities.items() for cap in [capacities[s]])
        checks['candidate_cost_reconciles']=costs==result['solution_cost_cents']
        if not all(v for k,v in checks.items() if k!='baseline_joint_capacity_feasible'):
            raise AssertionError('Synthetic assignment failed independent consistency controls')
    assignment_details=([{"order_id":o,"quantity_units":quantities[o],"supplier_id":result['assignment'][o],
                          "synthetic_landed_cost_usd":next(v['cost'] for v in candidates[o] if v['supplier']==result['assignment'][o])/100}
                         for o in sorted(quantities)] if result['assignment'] else [])
    return {"product":"AEGIS","experiment":"SYNTHETIC_COMPONENT_MONTH_JOINT_CAPACITY",
            "status":result['status'],"scope":{"component":component,"month":month,"orders":len(quantities),"eligible_pairs":sum(len(v) for v in candidates),"suppliers":len(capacities),"total_order_units":sum(quantities.values())},
            "source_sha256":hashes,"solver_nodes":result['nodes'],"exact_cost_optimum_certified_for_synthetic_problem":result['exact_optimal'],
            "synthetic_baseline_joint_feasible":result['baseline_feasible'],"baseline_landed_cost_usd":round(result['baseline_cost_cents']/100,2),
            "result_landed_cost_usd":None if result['solution_cost_cents'] is None else round(result['solution_cost_cents']/100,2),
            "hypothetical_cost_difference_usd":None if result['assignment'] is None else round(result['difference_from_baseline_cents']/100,2),
            "assignment":result['assignment'],"assignment_details":assignment_details,"capacity_by_supplier":result.get('capacity_by_supplier'),"checks":checks, "independent_exact_reference":reference,
            "monthly_component_capacity_modeled":True,"daily_or_concurrent_other_component_capacity_proven":False,
            "quotes_certified_real_asof":False,"contractual_supplier_eligibility_certified":False,"delivery_risk_model_used":False,
            "real_causal_supplier_benefits":False,"automatic_procurement":"DISABLED","operational_approval":"NOT_GRANTED",
            "interpretation":"Illustrative whole-order supplier assignment within synthetic component-month capacities only. Costs are source-derived synthetic quoted plus freight. No measured intervention effect or operational approval."}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-nodes',type=int,default=2_000_000)
    args=p.parse_args(argv)
    if args.output.exists():p.error('Output already exists; preserving all prior evidence')
    report=run(args.source,max_nodes=args.max_nodes)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('assignment','source_sha256')},indent=2))

if __name__=='__main__':main()
