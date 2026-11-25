import argparse,hashlib,json,zipfile,sys,platform
from pathlib import Path
import numpy as np,pandas as pd,sklearn,scipy
from scipy.special import expit
from sklearn.metrics import average_precision_score,roc_auc_score,brier_score_loss,log_loss
H=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def read(n): return json.loads((H/n).read_text())
def metrics(y,p,w=None):
 return dict(average_precision=float(average_precision_score(y,p,sample_weight=w)),roc_auc=float(roc_auc_score(y,p,sample_weight=w)),brier=float(brier_score_loss(y,p,sample_weight=w)),log_loss=float(log_loss(y,p,sample_weight=w,labels=[0,1])),signed_calibration_gap=float(np.average(p-y,weights=w)))
def main():
 a=argparse.ArgumentParser();a.add_argument('archive',type=Path);a.add_argument('--out',type=Path,required=True);args=a.parse_args()
 manifest=read('freeze_manifest.json')
 for n,h in manifest.items():
  if sha((H/n).read_bytes())!=h: raise ValueError('Frozen file changed: '+n)
 pr=read('protocol.json'); m=read('fitted_model.json'); r=read('prediction_report.json'); assert sha((H/'feature_contract.json').read_bytes())==m['contract_sha256']==r['contract_sha256']
 with zipfile.ZipFile(args.archive) as z:
  assert z.testzip() is None
  def load(name,hashkey,cols):
   names=[n for n in z.namelist() if Path(n).name==name]; assert len(names)==1
   b=z.read(names[0]); assert sha(b)==pr[hashkey]
   import io
   return pd.read_csv(io.BytesIO(b),usecols=cols,dtype={'order_ID':'string','package_ID':'string'})
  o=load('JD_order_data.csv','order_sha256',['order_ID','order_date','order_time','type','promise']); d=load('JD_delivery_data.csv','delivery_sha256',['order_ID','package_ID','type','arr_time'])
 counts={'order_lines':len(o),'delivery_rows':len(d),'missing_order_id_lines':int(o.order_ID.isna().sum()),'missing_delivery_order_id_rows':int(d.order_ID.isna().sum())}
 o['p']=pd.to_datetime(o.order_time,errors='coerce',format='mixed'); o['date']=pd.to_datetime(o.order_date,errors='coerce',format='mixed'); o['promise']=pd.to_numeric(o.promise,errors='coerce'); o['type']=pd.to_numeric(o.type,errors='coerce')
 o['valid']=(o.p.notna()&o.date.notna()&(o.p.dt.normalize()==o.date)&(o.type==1)&(o.promise>=1)&(o.promise%1==0)).fillna(False)
 g=o.groupby('order_ID').agg(p=('p','first'),promise=('promise','first'),valid=('valid','all'),p_n=('p','nunique'),promise_n=('promise','nunique'))
 counts['unique_orders']=len(g)
 def filt(mask,name):
  nonlocal g
  mask=mask.fillna(False);counts[name]=int((~mask).sum());g=g.loc[mask].copy()
 filt(g.valid&(g.p_n==1)&(g.promise_n==1),'excluded_inconsistent_or_non_1p_order')
 filt((g.p>=pd.Timestamp('2018-03-01'))&(g.p<pd.Timestamp('2018-03-25')),'excluded_outside_purchase_window')
 filt(~((g.promise==1)&(g.p.dt.hour>=23)),'excluded_ambiguous_late_evening_promise')
 days=np.where((g.promise==1)&(g.p.dt.hour<11),0,g.promise)
 g['deadline']=g.p.dt.normalize()+pd.to_timedelta(days,unit='D',errors='coerce'); cutoff=pd.Timestamp('2018-04-01')
 filt(g.deadline.notna()&(g.deadline<cutoff),'excluded_deadline_not_mature')
 d['arr']=pd.to_datetime(d.arr_time,format='mixed',errors='coerce');d['type']=pd.to_numeric(d.type,errors='coerce');d['full']=(d.package_ID==d.order_ID)&(d.type==1)
 dg=d.groupby('order_ID').agg(rows=('order_ID','size'),full=('full','all'),arr=('arr','first'))
 g=g.join(dg);filt(g.rows.notna(),'excluded_no_delivery_match');filt((g.rows==1)&g.full,'excluded_not_single_full_order_package');filt(g.arr.notna()&(g.arr>=g.p)&(g.arr<cutoff),'excluded_invalid_or_unmature_arrival')
 y=(g.arr.dt.normalize()>g.deadline).astype(int).to_numpy();counts['eligible_orders']=len(g);counts['late_orders']=int(y.sum());assert len(np.unique(y))==2
 p=g.p;x=pd.DataFrame({'hour':p.dt.hour,'weekday':p.dt.dayofweek,'month':p.dt.month,'day_of_month':p.dt.day,'iso_week':p.dt.isocalendar().week.astype(float)})
 assert list(x)==m['features'];z=((x.to_numpy(float)-m['scale_mean'])/m['scale_std'])@np.array(m['coefficients'])+m['intercept']; raw=expit(z);cal=expit(m['calibration_coefficient']*z+m['calibration_intercept']);prior=r['training']['late']/r['training']['mature_comparable']
 # Collapse equal day/score/label combinations for exact weighted cluster bootstrap.
 tab=pd.DataFrame({'day':p.dt.normalize().to_numpy(),'y':y,'raw':raw,'cal':cal}).groupby(['day','y','raw','cal'],as_index=False).size()
 codes,dates=pd.factorize(tab.day,sort=True);n=len(dates);rng=np.random.default_rng(20261125); draws={k:[] for k in ['raw','calibrated']}
 for _ in range(500):
  w=np.bincount(rng.integers(0,n,size=n),minlength=n)[codes]*tab['size'].to_numpy();keep=w>0
  yy=tab.y.to_numpy()[keep];ww=w[keep]
  if len(np.unique(yy))<2: continue
  for name,col in [('raw','raw'),('calibrated','cal')]: draws[name].append(metrics(yy,tab[col].to_numpy()[keep],ww))
 ci={name:{k:[float(v) for v in np.quantile([a[k] for a in ds],[.025,.975])] for k in ds[0]} for name,ds in draws.items()}
 def reliability(probs):
  b=[0,.02,.04,.06,.08,.1,.15,.2,.3,.5,1];out=[]
  for lo,hi in zip(b[:-1],b[1:]):
   ix=(probs>=lo)&((probs<hi) if hi<1 else (probs<=1))
   if ix.any():out.append(dict(lo=lo,hi=hi,n=int(ix.sum()),mean_prediction=float(probs[ix].mean()),observed=float(y[ix].mean())))
  return out
 report={'status':'CONDITIONAL_EXTERNAL_HISTORICAL_VALIDATION','counts':counts,'prevalence':float(y.mean()),'raw_mean':float(raw.mean()),'calibrated_mean':float(cal.mean()),'training_prior':prior,'raw':metrics(y,raw),'calibrated':metrics(y,cal),'training_prior_baseline':metrics(y,np.full(len(y),prior)),'uncertainty':{'clusters':n,'replicates':500,'valid':len(draws['raw']),'intervals_95':ci},'reliability':{'raw':reliability(raw),'calibrated':reliability(cal)},'model_unchanged':True,'untouched_team_attestation':False,'original_license_verified':False,'operational_approval':False,'supplier_causal_effect_established':False,'freeze_manifest':manifest,'runtime':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'sklearn':sklearn.__version__,'scipy':scipy.__version__}}
 with args.out.open('x') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({k:report[k] for k in ['counts','prevalence','raw_mean','calibrated_mean','training_prior','raw','calibrated','training_prior_baseline','uncertainty']},indent=2))
if __name__=='__main__':main()
