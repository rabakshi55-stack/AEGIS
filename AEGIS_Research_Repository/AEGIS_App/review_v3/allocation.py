"""Comparable fictional allocation rerun using a common frozen cost/capacity menu."""
import csv, hashlib, itertools, json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from paired_stress import _source_bytes, _rows, build_candidate_menu, run_experiment
from joint_capacity import _get_problem, run as monthly_run
from joint_resilience import run_paired_daily_stress


def run(source, fixtures):
    source=Path(source); raw=_source_bytes(source); q,caps,candidates=_get_problem(raw,'CMP-007','2025-07')
    monthly=monthly_run(source); assert monthly['exact_cost_optimum_certified_for_synthetic_problem']
    dates={r['purchase_order_id']:r['order_date'] for r in _rows(raw['purchase_orders.csv'],'purchase_orders.csv') if r['purchase_order_id'] in q}
    if set(dates)!=set(q): raise ValueError('Incomplete date registry')
    # Identical eligible candidates, quantities, cost, starting capacity. Only information horizon differs.
    # For risk lock, one order-level invariant proxy: original baseline candidate target.
    # It is constant over all eligible choices and cannot justify supplier-switch benefits.
    menu=build_candidate_menu(raw); risk={r['order_id']:1-r['synthetic_contract_on_time_target'] for r in menu if r['baseline']}
    def sequential(risk_weight):
        remaining=caps.copy(); assignments={}; cents=0; days=[]
        for day in sorted(set(dates.values())):
            orders=sorted(o for o in q if dates[o]==day); best=None
            for opts in itertools.product(*(sorted(candidates[o],key=lambda x:x['supplier']) for o in orders)):
                use=defaultdict(int)
                for o,r in zip(orders,opts): use[r['supplier']]+=q[o]
                if any(v>remaining[s] for s,v in use.items()): continue
                cost=sum(r['cost'] for r in opts); score=cost+risk_weight*sum(risk[o] for o in orders)
                key=(score,cost,tuple(r['supplier'] for r in opts))
                if best is None or key<best[0]: best=(key,opts,dict(use))
            if best is None: return {'status':'INFEASIBLE_SEQUENTIAL','assignment':assignments,'unserved_day':day,'cost_cents':None}
            key,opts,use=best; cents+=key[1]
            assignments.update({o:r['supplier'] for o,r in zip(orders,opts)})
            for s,v in use.items(): remaining[s]-=v
            days.append({'day':day,'orders':len(orders),'cost_cents':key[1],'remaining_monthly_capacity':remaining.copy()})
        return {'status':'EXACT_EACH_DAY_NOT_GLOBAL_OPTIMUM','assignment':assignments,'cost_cents':cents,'daily_ledger':days,'order_invariant_risk_sum':sum(risk[o] for o in assignments)}
    seq=sequential(0); locked=sequential(1000000)
    assert seq==locked, 'Order-invariant risk cannot change cost optimum or tie breaking'
    if seq['cost_cents'] is not None:
        assert len(seq['assignment'])==len(q) and seq['cost_cents']>=round(monthly['result_landed_cost_usd']*100)
    archived=source/'outputs'/'AEGIS_step126_chronological_allocations.csv'
    rows=list(csv.DictReader(archived.open(encoding='utf-8-sig',newline='')))
    summary=list(csv.DictReader((source/'outputs'/'AEGIS_step126_policy_comparison.csv').open(encoding='utf-8-sig',newline='')))
    prior={}
    for policy in sorted({r['Policy'] for r in rows}):
        selected=[r for r in rows if r['Policy']==policy]; cost=sum(Decimal(r['Cost']) for r in selected); reference=next(r for r in summary if r['Policy']==policy)
        assert cost==Decimal(reference['Total_Quoted_Cost_USD']) and len(selected)==int(reference['Orders_Served']) and len({r['purchase_order_id'] for r in selected})==len(selected)
        prior[policy]={'archived_quoted_cost_usd':float(cost),'orders':len(selected),'archived_mean_predicted_risk':float(reference['Mean_Predicted_Late_Risk']),'causal_effect_established':False}
    f=Path(fixtures); snap=json.loads((f/'FICTIONAL_DAILY_MULTICOMPONENT_PLAN.json').read_text()); baseline=json.loads((f/'FICTIONAL_BASELINE_ASSIGNMENT.json').read_text()); stress=run_paired_daily_stress(snap,baseline,scenarios=500,seed=191)
    return {'status':'SYNTHETIC_RESEARCH_ONLY','common_input_sha256':hashlib.sha256(json.dumps({'q':q,'caps':caps,'candidates':candidates,'dates':dates,'risk':risk},sort_keys=True).encode()).hexdigest(),'scope':monthly['scope'],'monthly_common_cost_usd':monthly['result_landed_cost_usd'],'monthly_exact_reference':monthly['independent_exact_reference'],'monthly_assignment':monthly['assignment'],'sequential_common_cost_usd':None if seq['cost_cents'] is None else seq['cost_cents']/100,'sequential':seq,'risk_locked_sequential':locked,'risk_lock_changes_assignment':False,'prior_step126':prior,'prior_step126_source_sha256':hashlib.sha256(archived.read_bytes()).hexdigest(),'paired_daily_fixture_stress':stress,'comparison_table':[
      {'dimension':'Objective / cost','archived_monthly':'Minimize quoted unit cost plus lane freight','archived_daily_step126':'Minimize quoted order cost or risk subject to daily quoted budget','common_rerun':'Minimize same quoted plus freight cents'},
      {'dimension':'Information horizon','archived_monthly':'Whole component-month visible','archived_daily_step126':'Day batches; same-day commitments assumed known','common_rerun':'Monthly sees all orders; sequential sees only current day; both identical static menu'},
      {'dimension':'Demand and capacity','archived_monthly':'16 whole orders; component-month caps','archived_daily_step126':'16 whole orders; monthly caps tracked sequentially','common_rerun':'Same 16 orders, quantities, monthly caps; no daily resource certification'},
      {'dimension':'Eligibility','archived_monthly':'Approval, qualification, MOQ, documented lane','archived_daily_step126':'Approval, MOQ, monthly caps; route approval unverified','common_rerun':'Identical source-derived menu; documented lanes not real approval'},
      {'dimension':'Risk','archived_monthly':'None','archived_daily_step126':'Supplier-dependent model estimates','common_rerun':'Fixed order-level fictional proxy; invariant over supplier; no causal claim'}], 'limitations':['The two archived totals are not comparable. Common-cost rerun controls cost and eligibility but intentionally differs in information horizon.','Order-invariant risk lock is an illustrative negative control, not a replacement for causal data or the original feature-lock audit.','Fixture stress is a different fictional multi-component example, not the Step126 population.','No operational approval, causal supplier-switch effect, or real savings.']}
