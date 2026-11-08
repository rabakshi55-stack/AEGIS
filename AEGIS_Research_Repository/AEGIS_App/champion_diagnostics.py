"""AEGIS retrospective paired comparison for final selected research classifiers.

NEVER use inspected March/April-Jul 2018 cohorts for model selection.
No test is pristine; feature availability and actual procurement remain unverified.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import average_precision_score,roc_auc_score,brier_score_loss
from historical_challenger import load_rows,feature_frame,SPLITS

def run(source,output):
    df, hashes=load_rows(source);p=df.order_purchase_timestamp
    masks={k:(((p>=a)&(p<b))&df.label_mature).to_numpy() for k,(a,b) in SPLITS.items()}
    y=df.label_late.to_numpy(dtype=np.int8); X=feature_frame(df,'extended_checkout_unattested').to_numpy(dtype=np.float32)
    tr=masks['development_training']; scale=StandardScaler().fit(X[tr]);xx=scale.transform(X)
    models={
       'logistic_l2':LogisticRegression(C=.1,max_iter=600,random_state=20261107),
       'logistic_l1':LogisticRegression(penalty='l1',solver='saga',C=.1,max_iter=600,random_state=20261107),
       'linear_svm_balanced':LinearSVC(C=.01,class_weight='balanced',max_iter=4500,random_state=20261107),
       'mlp_neural_net':MLPClassifier(hidden_layer_sizes=(32,12),alpha=10,max_iter=100,early_stopping=True,validation_fraction=.15,n_iter_no_change=10,random_state=20261107),
    }
    results={};jan_scores={}
    with __import__('warnings').catch_warnings():
      __import__('warnings').simplefilter('ignore')
      for name,model in models.items():
        model.fit(xx[tr],y[tr]);scores={}
        for k,mask in masks.items():
          if hasattr(model,'decision_function'):sc=model.decision_function(xx[mask])
          else:sc=model.predict_proba(xx[mask])[:,1]
          scores[k]=np.asarray(sc,dtype=float)
        jan_scores[name]=scores['development_selection']
        results[name]={}
        for k,sc in scores.items():
          yy=y[masks[k]]
          results[name][k]={'rows':int(len(yy)),
                            'late_count':int(yy.sum()),
                            'average_precision':round(float(average_precision_score(yy,sc)),6),
                            'roc_auc':round(float(roc_auc_score(yy,sc)),6)}
        # Independently fit only February development logits as monotone sigmoid calibration.
        feb=scores['development_calibration'].reshape(-1,1)
        cal=LogisticRegression(C=1.0,max_iter=550,random_state=20261107).fit(feb,y[masks['development_calibration']])
        for k in ['historical_stress_inspected','historical_audit_inspected']:
          yy=y[masks[k]];pr=cal.predict_proba(scores[k].reshape(-1,1))[:,1]
          results[name][k]['february_calibration_brier']=round(float(brier_score_loss(yy,pr)),6)
          results[name][k]['mean_calibrated_score']=round(float(pr.mean()),6)
          results[name][k]['observed_late_rate']=round(float(yy.mean()),6)
          results[name][k]['absolute_mean_calibration_gap']=round(float(abs(pr.mean()-yy.mean())),6)
    # Stratified paired bootstrap for descriptive difference in Jan AP, NOT independent inference.
    rng=np.random.default_rng(20261107);ys=y[masks['development_selection']]
    pos=np.flatnonzero(ys==1);neg=np.flatnonzero(ys==0)
    bootstrap={}
    baseline=jan_scores['logistic_l2']
    for name,challenge in jan_scores.items():
      if name=='logistic_l2':continue
      diffs=[]
      for _ in range(300):
        ids=np.concatenate([rng.choice(pos,len(pos),replace=True),rng.choice(neg,len(neg),replace=True)])
        diffs.append(float(average_precision_score(ys[ids],baseline[ids])-average_precision_score(ys[ids],challenge[ids])))
      lo,hi=np.quantile(diffs,[.025,.975]);bootstrap[name]={'l2_minus_competitor_ap':round(float(average_precision_score(ys,baseline)-average_precision_score(ys,challenge)),6),
         'stratified_bootstrap_95pct_interval':[round(float(lo),6),round(float(hi),6)],
         'interval_caveat':'Selection data already reused to choose leader; not a claim of new independent statistical significance'}
    report={'product':'AEGIS','study':'RESEARCH_CHAMPION_TEMPORAL_DIAGNOSTICS_NON_PROSPECTIVE',
     'source_hashes':hashes,'features_independently_available_asof':False,
     'model_choice':'logistic_l2 by January 2018 development-selection average precision',
     'periods':SPLITS,'models':results,'paired_january_ap_uncertainty':bootstrap,
     'later_months_used_to_choose_model':False,'later_months_have_been_inspected_by_researcher':True,
     'operational_approval':'NOT_GRANTED','business_execution':'DISABLED'}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report
if __name__=='__main__':
  ap=argparse.ArgumentParser();ap.add_argument('--olist-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
  args=ap.parse_args();run(args.olist_dir,args.output)
