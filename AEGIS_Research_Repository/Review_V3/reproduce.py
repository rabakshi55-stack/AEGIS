"""AEGIS V3 review supplement. Fit from raw Olist and reproduce synthetic allocation checks.
Run in pinned research environment; does not alter original application or archives.
"""
import argparse, hashlib, json, sys, os, platform, importlib.metadata as md
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss, log_loss
from threadpoolctl import threadpool_limits
from scipy.optimize import milp, Bounds, LinearConstraint
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'AEGIS_App'))
from joint_capacity import run as monthly_run, _get_problem
from paired_stress import _source_bytes, build_candidate_menu
from joint_resilience import run_paired_daily_stress

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,obj):
    with path.open('x',encoding='utf-8') as f: json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False); f.write('\n')
def contract():
    p=HERE/'feature_contract.json'; h=digest(p)
    if h!=(HERE/'feature_contract.sha256').read_text().strip(): raise ValueError('Frozen contract digest mismatch')
    return json.loads(p.read_text()),h

def prepare(path):
    df=pd.read_csv(path,usecols=['order_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date'])
    if df.order_id.isna().any() or df.order_id.duplicated().any(): raise ValueError('Missing/duplicate IDs')
    for c in ['order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date']: df[c]=pd.to_datetime(df[c],errors='coerce')
    return df

def features(df):
    p=df.order_purchase_timestamp
    return pd.DataFrame({'hour':p.dt.hour,'weekday':p.dt.dayofweek,'month':p.dt.month,'day_of_month':p.dt.day,'iso_week':p.dt.isocalendar().week.astype(float)},index=df.index)

def cohort(df, rule):
    p=df.order_purchase_timestamp; d=df.order_delivered_customer_date; e=df.order_estimated_delivery_date
    start,end,cut=[pd.Timestamp(rule[k]) for k in ('start','end_exclusive','label_cutoff_exclusive')]
    population=(p>=start)&(p<end)
    valid=(df.order_status=='delivered') & d.notna() & e.notna() & (d>=p) & (e.dt.normalize()>=p.dt.normalize()) & (d<cut) & (e.dt.normalize()<cut.normalize())
    m=population&valid
    y=(d[m].dt.normalize()>e[m].dt.normalize()).astype(int).to_numpy()
    counts={'purchased':int(population.sum()),'mature_comparable':int(m.sum()),'excluded_or_unresolved':int((population&~valid).sum()),'late':int(y.sum())}
    return m,y,counts

def metric(y,p):
    if len(np.unique(y))<2: raise ValueError('Both classes required')
    return {'average_precision':float(average_precision_score(y,p)),'roc_auc':float(roc_auc_score(y,p)),'brier':float(brier_score_loss(y,p)),'log_loss':float(log_loss(y,p,labels=[0,1])),'signed_calibration_gap':float(p.mean()-y.mean())}

def describe(y,p,raw,dates,prior,boot):
    result={'prevalence':float(y.mean()),'mean_calibrated_probability':float(p.mean()),'mean_raw_probability':float(raw.mean()),'raw':metric(y,raw),'calibrated':metric(y,p),'training_prior_baseline':metric(y,np.full(len(y),prior))}
    wk=dates.dt.to_period('W').astype(str).to_numpy(); groups=[np.flatnonzero(wk==v) for v in sorted(set(wk))]
    rng=np.random.default_rng(20261125); draws=defaultdict(list)
    for _ in range(boot):
        ix=np.concatenate([groups[i] for i in rng.integers(0,len(groups),size=len(groups))]); yy=y[ix]
        if len(np.unique(yy))<2: continue
        for key,val in metric(yy,p[ix]).items(): draws[key].append(val)
    result['uncertainty']={'method':'calendar-week cluster percentile bootstrap; fitted model fixed; descriptive only','weeks':len(groups),'replicates':boot,'valid_replicates':len(draws['roc_auc']),'interval_95':{k:[float(x) for x in np.quantile(v,[.025,.975])] for k,v in draws.items()}}
    result['reliability_bins']=[]
    for lo,hi in zip(np.arange(0,1,.1),np.arange(.1,1.01,.1)):
        mask=(p>=lo)&((p<hi) if hi<.999 else (p<=1))
        if mask.any(): result['reliability_bins'].append({'lower':round(float(lo),1),'upper':round(float(hi),1),'n':int(mask.sum()),'predicted':float(p[mask].mean()),'observed':float(y[mask].mean())})
    return result

def predictive(out, raw):
    c,h=contract(); df=prepare(raw); x=features(df)
    assert list(x)==c['features']
    tr,ytr,tc=cohort(df,c['training']); ca,yca,cc=cohort(df,c['calibration'])
    assert not (tr&ca).any() and len(set(ytr))==2 and len(set(yca))==2
    scale=StandardScaler().fit(x.loc[tr]); model=LogisticRegression(C=.1,max_iter=700,random_state=20261125).fit(scale.transform(x.loc[tr]),ytr)
    raw_cal=model.decision_function(scale.transform(x.loc[ca])); cal=LogisticRegression(C=1,max_iter=700,random_state=20261125).fit(raw_cal.reshape(-1,1),yca)
    artifact={'contract_sha256':h,'source_sha256':digest(raw),'features':list(x),'scale_mean':scale.mean_.tolist(),'scale_std':scale.scale_.tolist(),'coefficients':model.coef_[0].tolist(),'intercept':float(model.intercept_[0]),'calibration_coefficient':float(cal.coef_[0,0]),'calibration_intercept':float(cal.intercept_[0]),'operational_approval':False}
    dump(out/'fitted_model.json',artifact)
    rep={'status':'RETROSPECTIVE_DIAGNOSTICS_ONLY','contract_sha256':h,'source_sha256':digest(raw),'source_rows':len(df),'invalid_purchase_timestamp':int(df.order_purchase_timestamp.isna().sum()),'training':tc,'calibration':cc,'holdout_independence_established':False,'feature_ingestion_independently_attested':False,'operational_probability_certified':False,'supplier_causal_effect_established':False,'historical_negative_findings_retained':True,'diagnostics':{}}
    for rule in c['diagnostics']:
        m,y,count=cohort(df,rule); assert not (m&(tr|ca)).any()
        z=model.decision_function(scale.transform(x.loc[m])); p=cal.predict_proba(z.reshape(-1,1))[:,1]; raw_p=model.predict_proba(scale.transform(x.loc[m]))[:,1]
        rep['diagnostics'][rule['name']]={'counts':count,**describe(y,p,raw_p,df.loc[m,'order_purchase_timestamp'],float(ytr.mean()),500)}
    dump(out/'prediction_report.json',rep); return rep

def solve_menu(menu, caps, objective='cost', budget=None):
    # Same eligible menu, cost units, hard capacity and whole-order constraints.
    n=len(menu); orders=sorted({r['order_id'] for r in menu}); suppliers=sorted(caps)
    cost=np.array([r['cost_cents'] for r in menu],float); risk=np.array([r['stress_proxy'] for r in menu],float)
    rows=[]; lower=[]; upper=[]
    for o in orders: rows.append([int(r['order_id']==o) for r in menu]);lower.append(1);upper.append(1)
    for s in suppliers: rows.append([r['quantity'] if r['supplier_id']==s else 0 for r in menu]);lower.append(0);upper.append(caps[s])
    if budget is not None: rows.append(cost);lower.append(0);upper.append(budget)
    obj=cost if objective=='cost' else risk
    result=milp(c=obj,integrality=np.ones(n),bounds=Bounds(np.zeros(n),np.ones(n)),constraints=LinearConstraint(np.asarray(rows,float),lower,upper),options={'mip_rel_gap':0.0})
    if result.status!=0: return {'status':str(result.message),'feasible_exact':False}
    chosen=[r for r,z in zip(menu,result.x) if z>.5]; usage={s:sum(r['quantity'] for r in chosen if r['supplier_id']==s) for s in suppliers}
    assert len(chosen)==len(orders) and len({r['order_id'] for r in chosen})==len(orders) and all(usage[s]<=caps[s] for s in suppliers)
    total=sum(r['cost_cents'] for r in chosen); assert budget is None or total<=budget
    return {'feasible_exact':True,'cost_cents':total,'mean_assumed_stress_proxy':float(np.mean([r['stress_proxy'] for r in chosen])),'assignment':{r['order_id']:r['supplier_id'] for r in chosen},'capacity_usage':usage}

def rerun_daily(source):
    # Recreate the archived Step 126 cost-only daily-batch problem from its frozen
    # candidate quote table and raw purchase orders/catalog. No risk model is refit.
    opts=pd.read_csv(source/'outputs/AEGIS_step126_constrained_options.csv')
    po=pd.read_csv(source/'data/purchase_orders.csv',parse_dates=['order_date'])
    catalog=pd.read_csv(source/'data/supplier_component_options.csv')
    assert not opts.duplicated(['purchase_order_id','supplier_id']).any()
    assert not catalog.duplicated(['supplier_id','component_id']).any()
    assert not po.purchase_order_id.duplicated().any()
    assert opts.component_id.nunique()==1
    comp=opts.component_id.iloc[0]; ids=set(opts.purchase_order_id); assert len(ids)==16
    opts['Order_Date']=pd.to_datetime(opts.Order_Date)
    dates=sorted(opts.Order_Date.unique()); month=pd.Timestamp(dates[0]).to_period('M')
    cat=catalog[catalog.component_id==comp].set_index('supplier_id')
    caps={str(k):int(v) for k,v in cat.monthly_capacity_units.items() if k in set(opts.supplier_id)}
    orig=po.set_index('purchase_order_id')
    eligible=[]
    for r in opts.itertuples():
        o=orig.loc[r.purchase_order_id]; c=cat.loc[r.supplier_id]
        assert o.component_id==comp and o.order_date==r.Order_Date and int(o.order_quantity_units)==int(r.Quantity)
        flag=bool(int(c.approved_for_sourcing)) and int(r.Quantity)>=int(c.minimum_order_qty)
        assert flag==bool(r.Static_Eligible) and caps[r.supplier_id]==int(r.Monthly_Capacity)
        if flag: eligible.append({'order_id':r.purchase_order_id,'supplier_id':r.supplier_id,'quantity':int(r.Quantity),'cost_cents':int(round(r.Cost*100)),'stress_proxy':0.0,'date':r.Order_Date})
    # Same-day external commitments are assumed known, as in Step 126.
    external=po[(po.component_id==comp)&(po.order_date.dt.to_period('M')==month)&(po.order_date<=dates[-1])&(~po.purchase_order_id.isin(ids))]
    booked=defaultdict(int); assignments={}; total=0; daily=[]
    for day in dates:
        ex=external[external.order_date<=day].groupby('supplier_id').order_quantity_units.sum().to_dict()
        remaining={s:cap-int(ex.get(s,0))-booked[s] for s,cap in caps.items()}
        result=solve_menu([r for r in eligible if r['date']==day],remaining)
        if not result['feasible_exact']: raise RuntimeError(f'Daily cost batch infeasible: {day}: {result}')
        for s,n in result['capacity_usage'].items():booked[s]+=n
        assignments.update(result['assignment']);total+=result['cost_cents']
        daily.append({'date':str(pd.Timestamp(day).date()),'external_booked_units':{s:int(ex.get(s,0)) for s in caps},'capacity_remaining_at_decision':remaining,'assignment':result['assignment'],'cost_cents':result['cost_cents']})
    final_ext=external.groupby('supplier_id').order_quantity_units.sum().to_dict()
    final={s:booked[s]+int(final_ext.get(s,0)) for s in caps}
    assert set(assignments)==ids and all(final[s]<=caps[s] for s in caps)
    return {'cost_cents':total,'orders':len(assignments),'candidate_options':len(eligible),'days':daily,'capacity_usage_at_end':final,'capacity_limit':caps,'full_period_capacity_pass':True,'same_day_visibility_assumed_not_attested':True,'quote_table_sha256':digest(source/'outputs/AEGIS_step126_constrained_options.csv'),'interpretation':'Exact daily cost-only replay from archived quote candidates and source commitments, not a replay of upstream ML candidate generation. No real delivery effects.'}

def allocation(out):
    source=ROOT/'Research/Integrated_v02'; raw=_source_bytes(source)
    orig=monthly_run(source); dump(out/'monthly_reproduction.json',orig)
    quantities,caps,_=_get_problem(raw,'CMP-007','2025-07')
    menu=build_candidate_menu(raw); rows=[dict(r,quantity=quantities[r['order_id']],cost_cents=int(round(float(r['landed_cost_usd'])*100)),stress_proxy=2-r['synthetic_contract_on_time_target']) for r in menu]
    cost=solve_menu(rows,caps); assert cost['feasible_exact'] and cost['cost_cents']==round(orig['result_landed_cost_usd']*100)
    # Locked, source-derived hypothetical proxy independent of the historical classifier.
    budget=cost['cost_cents']*105//100; stress=solve_menu(rows,caps,'stress',budget)
    lookup={(r['order_id'],r['supplier_id']):r for r in rows}; regions=sorted({r['region'] for r in rows}); rng=np.random.default_rng(191)
    diffs=[]; scenario_rows=[]
    for i in range(500):
        g=float(rng.random()); rs={r:float(rng.random()) for r in regions}
        def exposure(policy): return float(np.mean([(0.6*g+0.4*rs[lookup[o,s]['region']])*lookup[o,s]['stress_proxy'] for o,s in policy['assignment'].items()]))
        a,b=exposure(cost),exposure(stress); diffs.append(b-a); scenario_rows.append({'scenario':i+1,'global':g,'regional':rs,'cost_policy_index':a,'proxy_policy_index':b,'paired_difference':b-a})
    dump(out/'shared_shocks.json',scenario_rows)
    daily=rerun_daily(source); dump(out/'daily_cost_reproduction.json',daily)
    archived=source/'outputs'; old=pd.read_csv(archived/'AEGIS_step126_chronological_allocations.csv'); old=old[old.Policy=='Cost_Only']; locked=pd.read_csv(archived/'AEGIS_step145_feature_sensitivity.csv')
    report={'status':'SYNTHETIC_CONTROLLED_COMPARISON_ONLY','monthly_original_reproduced_usd':orig['result_landed_cost_usd'],'daily_original_archived_sum_usd':float(old.Cost.sum()),'daily_original_orders':int(old.purchase_order_id.nunique()),'daily_original_reoptimized':True,'daily_replayed_cost_usd':daily['cost_cents']/100,'daily_replay_matches_archived_cost':daily['cost_cents']==round(float(old.Cost.sum())*100),'daily_original_source_sha256':digest(archived/'AEGIS_step126_chronological_allocations.csv'),'old_input_lock_sensitivity':locked.to_dict('records'),'same_menu_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'capacity':caps,'eligible_pairs':len(rows),'cost_policy':cost,'proxy_policy':stress,'proxy_cost_ceiling_cents':budget,'scenario_count':500,'paired_mean_index_difference_proxy_minus_cost':float(np.mean(diffs)),'paired_scenario_quantiles_2_5_97_5':[float(v) for v in np.quantile(diffs,[.025,.975])],'interpretation':'Synthetic static monthly comparison, no daily timing or causal benefit. Both policies see same menu, capacity and source-derived assumed stress proxy; proxy has no fitted probability meaning. Same exogenous shocks applied to both fixed plans. Scenario quantiles are not confidence intervals for real-world effects. Original daily formulation remains separate.','operational_approval':False}
    dump(out/'allocation_report.json',report); return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--olist-orders',type=Path,default=ROOT/'Research/Public_Data/Olist_Raw/archive/olist_orders_dataset.csv');args=p.parse_args()
    expected=dict(line.strip().split('==') for line in (HERE/'requirements.lock.txt').read_text().splitlines() if line.strip()); actual={k:md.version(k) for k in expected}
    if actual!=expected or platform.python_version()!='3.13.5': raise SystemExit(f'Pinned research environment required: Python 3.13.5; actual {platform.python_version()}, {actual}')
    args.output.mkdir(parents=True,exist_ok=False)
    with threadpool_limits(limits=1):
        pred=predictive(args.output,args.olist_orders); print('Predictive retrospective fit complete',flush=True); alloc=allocation(args.output);print('Synthetic reconciliation complete',flush=True)
    dump(args.output/'run_manifest.json',{'python':platform.python_version(),'packages':actual,'source_script_sha256':digest(Path(__file__)),'outputs':{p.name:digest(p) for p in sorted(args.output.iterdir())},'holdout_certified':False,'operational_approval':False})
if __name__=='__main__': main()
