"""Conservative, source-structured DAILY multi-resource planning integrity gate.

Pure stdlib; entirely research-only and does not import Olist forecasts, make causal
claims, infer missing route calendars, or certify quotes/capacities. Inputs are
explicit hypothetical/unaudited snapshots. All resource claims are per-day,
per-component and per-route as specified in the input; missing evidence fails
closed. Every order is indivisible. No procurement execution API exists.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal
import hashlib
import json

ALLOWED_KINDS = {"SUPPLIER_ITEM_DAY", "ROUTE_DAY", "SHARED_COMPONENT_POOL_DAY"}

def _timestamp(raw, name):
    if not isinstance(raw,str):
        raise ValueError(f"{name} must contain a timezone-aware ISO timestamp")
    try:
        val=datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError as e:
        raise ValueError(f"{name} must contain a timezone-aware ISO timestamp") from e
    if val.tzinfo is None or val.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone offset")
    return val

def _day(raw, name):
    if type(raw) is not str or len(raw)!=10:
        raise ValueError(f"{name} must be an ISO calendar date")
    try:
        val=date.fromisoformat(raw)
        if val.isoformat()!=raw: raise ValueError
    except ValueError as e:
        raise ValueError(f"{name} must be an ISO calendar date") from e
    return val

def _int(raw, name, minimum=0):
    if type(raw) is not int or raw<minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return raw

def _string(raw,name):
    if type(raw) is not str or not raw.strip() or len(raw)>120:
        raise ValueError(f"{name} must contain a non-empty identifier")
    return raw

def verify_and_optimize_plan(snapshot, max_nodes=300_000):
    """Exactly solve a finite indivisible order assignment if search completes.

    No guarantee of feasibility/optimality if truncated. All values supplied
    by caller; these are *not* evidence of actual operational conditions.
    """
    _int(max_nodes,'max_nodes',1)
    if type(snapshot) is not dict:
        raise ValueError('Planning snapshot must be an object')
    at=_timestamp(snapshot.get('decision_at'),'decision_at')
    orders=snapshot.get('orders'); resources=snapshot.get('resources'); options=snapshot.get('options')
    if not all(type(x) is list and x for x in (orders,resources,options)):
        raise ValueError('Nonempty orders, resources and options lists are required')
    if len(orders)>100 or len(options)>1000 or len(resources)>1500:
        raise ValueError('Planning instance exceeds the explicit computational safety limit')
    currency=_string(snapshot.get('currency'),'currency')
    if len(currency)!=3 or not currency.isalpha() or currency.upper()!=currency:
        raise ValueError('Currency must be one uniform uppercase ISO-style three-letter code; no conversions inferred')
    parsed_orders={}
    for x in orders:
        oid=_string(x.get('order_id'),'order_id')
        if oid in parsed_orders: raise ValueError('Duplicate order_id')
        item=_string(x.get('item_id'),'item_id')
        plant=_string(x.get('plant_id'),'plant_id')
        units=_int(x.get('units'),'order units',1)
        due=_day(x.get('required_by'),'required_by')
        if due<at.date():raise ValueError('Order required_by predates decision date')
        parsed_orders[oid]={'item_id':item,'plant_id':plant,'units':units,'due':due}
    resource_map={}
    for r in resources:
        rid=_string(r.get('resource_id'),'resource_id')
        if rid in resource_map:raise ValueError('Duplicate capacity resource')
        kind=r.get('kind')
        if kind not in ALLOWED_KINDS:raise ValueError('Resource kind must specify supplier/item, route, or shared pool daily capacity')
        day=_day(r.get('date'),'resource date')
        quantity=_int(r.get('available_units'),'available_units')
        committed=_int(r.get('already_committed_units'),'already_committed_units')
        if committed>quantity:raise ValueError('Recorded commitments exceed available resource capacity')
        known=_timestamp(r.get('recorded_at'),'resource recorded_at')
        valid=_timestamp(r.get('valid_until'),'resource valid_until')
        if not known<=at<=valid:raise ValueError('Stale or late-known capacity snapshot')
        if day<at.date():raise ValueError('Planning resource date is before decision date')
        owner=_string(r.get('owner_id'),'resource owner_id')
        resource_map[rid]={'kind':kind,'day':day,'owner':owner,'capacity':quantity-committed,'committed':committed}
    candidates=defaultdict(list);seen_options=set();excluded=defaultdict(int)
    for opt in options:
        xid=_string(opt.get('option_id'),'option_id')
        if xid in seen_options:raise ValueError('Duplicate option_id')
        seen_options.add(xid)
        oid=_string(opt.get('order_id'),'option order_id')
        if oid not in parsed_orders:raise ValueError('Option refers to unknown order')
        order=parsed_orders[oid]
        supplier=_string(opt.get('supplier_id'),'supplier_id')
        route=_string(opt.get('route_id'),'route_id')
        ship=_day(opt.get('ship_date'),'ship_date')
        arrival=_day(opt.get('arrival_date'),'arrival_date')
        if opt.get('item_id')!=order['item_id'] or opt.get('plant_id')!=order['plant_id']:
            raise ValueError('Supplier option mismatches item or destination plant')
        if opt.get('currency')!=currency:raise ValueError('Cross-currency costs are not comparable without audited conversion')
        cost=_int(opt.get('cost_cents'),'cost_cents')
        quote_at=_timestamp(opt.get('quote_recorded_at'),'quote_recorded_at')
        expires=_timestamp(opt.get('quote_valid_until'),'quote_valid_until')
        if not quote_at<=at<=expires:
            excluded['expired_or_late_quote']+=1;continue
        if opt.get('eligible') is not True or opt.get('route_eligible') is not True:
            excluded['eligibility_unverified_or_false']+=1;continue
        if ship<at.date() or arrival<ship or arrival>order['due']:
            excluded['schedule_infeasible']+=1;continue
        reqs=opt.get('resource_requirements')
        if type(reqs) is not list or not reqs:
            raise ValueError('Each option needs explicit resource requirements')
        usage=defaultdict(int);kinds=set()
        for req in reqs:
            rid=_string(req.get('resource_id'),'requirement resource_id')
            units=_int(req.get('units_per_order_unit'),'units_per_order_unit',1)
            if rid not in resource_map:raise ValueError('Option relies on missing daily capacity/route commitment record')
            resource=resource_map[rid]
            if resource['day']!=ship:raise ValueError('Option resource is not assigned to its shipping day')
            kind=resource['kind'];kinds.add(kind)
            if kind=='SUPPLIER_ITEM_DAY' and resource['owner'] != f"{supplier}|{order['item_id']}":
                raise ValueError('Supplier/component resource does not match the proposed supplier and item')
            if kind=='ROUTE_DAY' and resource['owner']!=route:
                raise ValueError('Route capacity owner does not match proposed route')
            usage[rid]+=order['units']*units
        if not {'SUPPLIER_ITEM_DAY','ROUTE_DAY'}.issubset(kinds):
            raise ValueError('Missing supplier/component daily capacity or transport route daily capacity')
        if any(quantity>resource_map[rid]['capacity'] for rid,quantity in usage.items()):
            excluded['individual_capacity_infeasible']+=1;continue
        candidates[oid].append({'id':xid,'cost':cost,'usage':dict(usage)})
    if set(candidates)!=set(parsed_orders):
        return {'status':'INFEASIBLE_NO_VALID_OPTIONS','uncovered_orders':sorted(set(parsed_orders)-set(candidates)),
            'excluded_options':dict(excluded),'exact_optimal':False,'assignment':None,
            'operational_approval':'NOT_GRANTED','evidence_level':'STRUCTURE_CHECK_ONLY_UNATTESTED'}
    # Search all allowed assignments; realistic instances require a specialist MIP solver.
    order_ids=sorted(parsed_orders,key=lambda oid:(len(candidates[oid]),-parsed_orders[oid]['units'],oid))
    candidates={oid:sorted(candidates[oid],key=lambda r:(r['cost'],r['id'])) for oid in order_ids}
    remaining={rid:r['capacity'] for rid,r in resource_map.items()}
    cheapest=[min(r['cost'] for r in candidates[oid]) for oid in order_ids]
    suffix=[0]*(len(order_ids)+1)
    for idx in range(len(order_ids)-1,-1,-1):suffix[idx]=suffix[idx+1]+cheapest[idx]
    nodes=0;truncated=False;best=None;best_cost=None;current={}
    def search(idx,cost):
        nonlocal nodes,truncated,best,best_cost
        if nodes>=max_nodes:
            truncated=True;return
        nodes+=1
        if best_cost is not None and cost+suffix[idx]>=best_cost:return
        if idx==len(order_ids):
            best=current.copy();best_cost=cost;return
        oid=order_ids[idx]
        for option in candidates[oid]:
            if any(remaining[rid]<qty for rid,qty in option['usage'].items()):continue
            for rid,qty in option['usage'].items():remaining[rid]-=qty
            current[oid]=option['id']
            search(idx+1,cost+option['cost'])
            del current[oid]
            for rid,qty in option['usage'].items():remaining[rid]+=qty
            if truncated:return
    search(0,0)
    # Independent post-solve reconciliation of all resources, including previous commitments.
    used=defaultdict(int)
    if best:
        for oid,option_id in best.items():
            opt=next(o for o in candidates[oid] if o['id']==option_id)
            for rid,qty in opt['usage'].items():used[rid]+=qty
        if any(used[rid]>r['capacity'] for rid,r in resource_map.items()):raise AssertionError('Capacity conservation failed')
        if len(best)!=len(parsed_orders):raise AssertionError('Order coverage failed')
    status=(('EXACT_MIN_COST_UNATTESTED' if not truncated else 'FEASIBLE_NOT_PROVEN_OPTIMAL') if best else
            ('NOT_PROVEN_FEASIBLE' if truncated else 'INFEASIBLE_WITH_RECORDED_CONSTRAINTS'))
    digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'status':status,'exact_optimal':best is not None and not truncated,'nodes':nodes,
        'truncated':truncated,'assignment':best,'cost_cents':best_cost,'currency':currency,
        'source_snapshot_sha256':digest,'excluded_options':dict(excluded),
        'resource_usage':{rid:{'used_units':used[rid],'already_committed_units':r['committed'],
                          'available_after_commitments':r['capacity']}
                          for rid,r in resource_map.items()},
        'orders_covered':len(best) if best else 0,'orders_total':len(parsed_orders),
        'evidence_level':'SOURCE_DECLARED_STRUCTURE_CHECK_ONLY_UNATTESTED',
        'operational_approval':'NOT_GRANTED','permitted_action':'NONE',
        'warnings':['Source timestamps and actual external commitments are NOT independently attested.',
                    'Calendar cutoffs, currency basis, contractual rights, true causality and realized savings are not certified.',
                    'Objective optimizes stated cents only, not disruption resilience or actual commercial outcomes.']}


def main(argv=None):
    """Analyst-only, optional offline check: python daily_feasibility.py snapshot.json"""
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description='AEGIS fictional/unattested daily planning integrity check. No business action.')
    parser.add_argument('snapshot',help='Local JSON snapshot following the documented resource contract')
    parser.add_argument('--max-nodes',type=int,default=300_000)
    args=parser.parse_args(argv)
    data=json.loads(Path(args.snapshot).read_text(encoding='utf-8'))
    result=verify_and_optimize_plan(data,max_nodes=args.max_nodes)
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
    return 0 if result['status'] in {'EXACT_MIN_COST_UNATTESTED','FEASIBLE_NOT_PROVEN_OPTIMAL'} else 2

if __name__=='__main__':
    raise SystemExit(main())
