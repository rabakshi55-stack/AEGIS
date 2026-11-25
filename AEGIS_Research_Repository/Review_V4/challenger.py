"""Frozen Olist-only challenger experiment. Does not read JD.com."""
import argparse,json,hashlib,sys,platform,importlib.metadata as md
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from scipy.special import logit
from threadpoolctl import threadpool_limits
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'Review_V3'))
from reproduce import prepare,features,cohort,describe,metric

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def make(kind):
    if kind=='logistic':return make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=700,random_state=20261125))
    return HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,min_samples_leaf=100,learning_rate=.05,l2_regularization=10,early_stopping=False,random_state=20261125)
def logodds(p):return logit(np.clip(p,1e-9,1-1e-9)).reshape(-1,1)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--olist-orders',type=Path,default=ROOT/'Research/Public_Data/Olist_Raw/archive/olist_orders_dataset.csv');ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    expected=dict(line.split('==') for line in (ROOT/'requirements-review.lock.txt').read_text().splitlines() if line.strip())
    if platform.python_version()!='3.13.5' or any(md.version(k)!=v for k,v in expected.items()):raise SystemExit('Use pinned V3 research environment')
    cp=HERE/'challenger_protocol.json'; ph=digest(cp)
    if ph!=(HERE/'challenger_protocol.sha256').read_text().strip():raise ValueError('Frozen protocol mismatch')
    protocol=json.loads(cp.read_text());df=prepare(args.olist_orders); X=features(df); X['promise_days']=(df.order_estimated_delivery_date.dt.normalize()-df.order_purchase_timestamp.dt.normalize()).dt.days
    folds={k:cohort(df,v) for k,v in protocol['cohorts'].items()};tr,yt,_=folds['train'];se,ys,_=folds['selection'];ca,yc,_=folds['calibration'];prior=float(yt.mean())
    report={'status':'RETROSPECTIVE_CHALLENGER_ONLY','protocol_sha256':ph,'source_sha256':digest(args.olist_orders),'cohorts':{k:v[2] for k,v in folds.items()},'training_prior':prior,'selection':{},'selected':{},'diagnostics':{},'jd_used':False,'feature_availability_attested':False,'untouched_holdout':False,'operational_approval':False}
    with threadpool_limits(limits=1):
        for group,cols in protocol['features'].items():
            x=X[cols];models={}
            for kind in ('logistic','hgb'):
                model=make(kind);model.fit(x.loc[tr],yt);score=model.predict_proba(x.loc[se])[:,1];name=group+'_'+kind;report['selection'][name]=metric(ys,score);models[name]=model
            winner=max(models,key=lambda n:(report['selection'][n]['average_precision'],report['selection'][n]['roc_auc']));report['selected'][group]=winner;model=models[winner]
            raw_ca=model.predict_proba(x.loc[ca])[:,1];cal=LogisticRegression(C=1e6,max_iter=700,random_state=20261125).fit(logodds(raw_ca),yc)
            report['diagnostics'][group]={}
            for k in ('march_inspected','april_july_inspected'):
                m,y,counts=folds[k];raw=model.predict_proba(x.loc[m])[:,1];p=cal.predict_proba(logodds(raw))[:,1];r=describe(y,p,raw,df.loc[m,'order_purchase_timestamp'],prior,500);r['counts']=counts;r['cohort_prevalence_reference']=metric(y,np.full(len(y),y.mean()));report['diagnostics'][group][k]=r
            print(group,winner,report['diagnostics'][group]['april_july_inspected']['calibrated'],flush=True)
    with args.out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
if __name__=='__main__':main()
