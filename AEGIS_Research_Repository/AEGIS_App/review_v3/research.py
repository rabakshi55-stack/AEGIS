"""Review V3: strict retrospective diagnostics, not a deployed model."""
import hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss

HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def protocol():
    p=HERE/'protocol.json'
    if sha(p)!=(HERE/'protocol.sha256').read_text().strip():
        raise ValueError('Frozen protocol digest mismatch')
    return json.loads(p.read_text(encoding='utf-8'))

def load_orders(source):
    p=Path(source)/'olist_orders_dataset.csv'
    cols=['order_id','order_purchase_timestamp','order_estimated_delivery_date','order_delivered_customer_date','order_status']
    d=pd.read_csv(p,usecols=cols)
    if d.order_id.isna().any() or d.order_id.duplicated().any(): raise ValueError('Invalid order identifiers')
    for c in cols[1:4]: d[c]=pd.to_datetime(d[c],errors='coerce')
    if d.order_purchase_timestamp.isna().any(): raise ValueError('Unparseable purchase timestamp')
    return d,sha(p)

def features(purchase):
    return pd.DataFrame({'hour':purchase.dt.hour,'weekday':purchase.dt.dayofweek,'month':purchase.dt.month,'day_of_month':purchase.dt.day,'week_of_year':purchase.dt.isocalendar().week.astype(float)},index=purchase.index).astype(float)

def cohort(d, spec):
    p=d.order_purchase_timestamp; a=d.order_delivered_customer_date; e=d.order_estimated_delivery_date
    cutoff=pd.Timestamp(spec['label_cutoff']); mask=p.ge(pd.Timestamp(spec['start'])) & p.lt(pd.Timestamp(spec['end']))
    valid=d.order_status.eq('delivered') & a.notna() & e.notna() & a.ge(p) & e.dt.normalize().ge(p.dt.normalize())
    mature=valid & a.lt(cutoff) & (e.dt.normalize()+pd.Timedelta(days=1)).le(cutoff)
    keep=mask & mature
    y=(a.dt.normalize()>e.dt.normalize()).loc[keep].astype(int)
    counts={'all_purchases':int(mask.sum()),'mature_comparable':int(keep.sum()),'noncomparable_or_unknown':int((mask&~valid).sum()),'comparable_but_not_mature_at_cutoff':int((mask&valid&~mature).sum()),'late':int(y.sum())}
    assert counts['all_purchases']==counts['mature_comparable']+counts['noncomparable_or_unknown']+counts['comparable_but_not_mature_at_cutoff']
    return keep,y.to_numpy(),counts

def logit(p):
    p=np.clip(p,1e-8,1-1e-8); return np.log(p/(1-p)).reshape(-1,1)

def metrics(y,p):
    if len(np.unique(y))!=2: raise ValueError('Need both outcome classes')
    return {'average_precision':float(average_precision_score(y,p)), 'roc_auc':float(roc_auc_score(y,p)), 'brier':float(brier_score_loss(y,p)), 'log_loss':float(log_loss(y,p,labels=[0,1])), 'mean_score':float(np.mean(p)), 'late_rate':float(np.mean(y)), 'signed_calibration_gap':float(np.mean(p)-np.mean(y))}

def reliability(y,p):
    rows=[]
    for lo,hi in zip(np.linspace(0,1,11)[:-1],np.linspace(0,1,11)[1:]):
        m=(p>=lo)&((p<hi) if hi<1 else (p<=hi))
        if m.any(): rows.append({'low':float(lo),'high':float(hi),'n':int(m.sum()),'mean_prediction':float(p[m].mean()),'observed_rate':float(y[m].mean())})
    return rows

def intervals(y,p,week,replicates,seed):
    groups=[np.flatnonzero(week==w) for w in np.unique(week)]
    rng=np.random.default_rng(seed); draws=[]
    for _ in range(replicates):
        idx=np.concatenate([groups[i] for i in rng.integers(0,len(groups),len(groups))])
        if len(np.unique(y[idx]))==2: draws.append(metrics(y[idx],p[idx]))
    if len(draws)<int(replicates*.9): raise ValueError('Too few valid bootstrap replicates')
    return {'weeks':len(groups),'valid_replicates':len(draws),'intervals_95pct':{k:[float(x) for x in np.quantile([r[k] for r in draws],[.025,.975])] for k in draws[0]}}

def run(source):
    cfg=protocol(); d,source_hash=load_orders(source); x=features(d.order_purchase_timestamp)
    if list(x.columns)!=cfg['features']: raise ValueError('Feature contract mismatch')
    phases={k:cohort(d,cfg[k]) for k in ['train','calibration','diagnostic']}
    tr,yt,_=phases['train']; ca,yc,_=phases['calibration']; te,ye,_=phases['diagnostic']
    assert not ((tr&ca)|(tr&te)|(ca&te)).any()
    scaler=StandardScaler().fit(x.loc[tr]); model=LogisticRegression(C=cfg['model']['C'],max_iter=cfg['model']['max_iter'],random_state=cfg['model']['seed']).fit(scaler.transform(x.loc[tr]),yt)
    if model.n_iter_.max()>=cfg['model']['max_iter']: raise RuntimeError('Model convergence not established')
    def raw(mask): return model.predict_proba(scaler.transform(x.loc[mask]))[:,1]
    cal=LogisticRegression(C=cfg['calibrator']['C'],max_iter=cfg['calibrator']['max_iter'],random_state=cfg['model']['seed']).fit(logit(raw(ca)),yc)
    def calibrated(p): return cal.predict_proba(logit(p))[:,1]
    outcomes={}
    for k,(mask,y,counts) in phases.items():
        r=raw(mask); c=calibrated(r); baseline=np.full(len(y),yt.mean()); outcomes[k]={'population':counts,'raw':metrics(y,r),'calibrated':metrics(y,c),'training_prevalence_baseline':metrics(y,baseline),'calibration_bins_raw':reliability(y,r),'calibration_bins_calibrated':reliability(y,c)}
    week=d.loc[te,'order_purchase_timestamp'].dt.to_period('W').astype(str).to_numpy()
    r=raw(te); c=calibrated(r); u=cfg['uncertainty']; outcomes['diagnostic']['uncertainty_raw']=intervals(ye,r,week,u['replicates'],u['seed']); outcomes['diagnostic']['uncertainty_calibrated']=intervals(ye,c,week,u['replicates'],u['seed'])
    artifact={'feature_names':cfg['features'],'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'coef':model.coef_[0].tolist(),'intercept':float(model.intercept_[0]),'calibrator_coef':float(cal.coef_[0,0]),'calibrator_intercept':float(cal.intercept_[0])}
    return {'status':cfg['status'],'protocol_sha256':sha(HERE/'protocol.json'),'source_orders_sha256':source_hash,'source_orders':len(d),'cohorts':outcomes,'frozen_model_research_only':artifact,'untouched_holdout_certified':False,'feature_availability_independently_attested':False,'operational_probability_authorized':False,'operational_approval':'NOT_GRANTED','limitations':[cfg['holdout']['reason'],'Label maturity based on retrospective recorded fields, not event-history attestation. Delivered-only outcome is conditional and excludes other orders.','Bootstrap intervals are descriptive, conditional on fixed fitted model and historical cohort.','Previous 18 percentage point calibration bias remains part of V2 evidence; this experiment cannot establish live calibration.']}
