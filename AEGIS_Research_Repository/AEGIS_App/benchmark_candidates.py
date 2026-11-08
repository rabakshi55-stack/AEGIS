"""Research-only reproducible broad classification benchmark; no deployment.

Output is strictly post-hoc historical comparisons. March and Apr-Jul cannot be
used as a pristine holdout or a source of hyperparameter selection.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time, traceback, warnings
from pathlib import Path
import numpy as np
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.naive_bayes import GaussianNB
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier,ExtraTreesClassifier,HistGradientBoostingClassifier,GradientBoostingClassifier,AdaBoostClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score,average_precision_score, brier_score_loss,log_loss
from historical_challenger import load_rows,feature_frame,SPLITS
warnings.filterwarnings('ignore',category=FutureWarning)

SEED=20261107

def candidates():
  ans=[
   ('prior_baseline', DummyClassifier(strategy='prior'),False),
   ('logistic_l2',LogisticRegression(C=.1,max_iter=650,random_state=SEED),True),
   ('logistic_balanced',LogisticRegression(C=.15,max_iter=650,class_weight='balanced',random_state=SEED),True),
   ('sgd_logistic',SGDClassifier(loss='log_loss',alpha=.002, max_iter=1200,random_state=SEED),True),
   ('gaussian_naive_bayes',GaussianNB(var_smoothing=.0001),True),
   ('linear_discriminant',LinearDiscriminantAnalysis(solver='lsqr',shrinkage=.25),True),
   ('quadratic_discriminant',QuadraticDiscriminantAnalysis(reg_param=.9),True),
   ('decision_tree',DecisionTreeClassifier(max_depth=7,min_samples_leaf=120,random_state=SEED),False),
   ('random_forest',RandomForestClassifier(n_estimators=140,max_depth=10,min_samples_leaf=55,max_features=.8,n_jobs=4,random_state=SEED),False),
   ('extra_trees',ExtraTreesClassifier(n_estimators=140,max_depth=12,min_samples_leaf=50,max_features=.8,n_jobs=4,random_state=SEED),False),
   ('hist_gradient_boosting',HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=15,min_samples_leaf=100,learning_rate=.055,l2_regularization=20,early_stopping=False,random_state=SEED),False),
   ('gradient_boosting',GradientBoostingClassifier(n_estimators=110,learning_rate=.055,max_depth=2,min_samples_leaf=100,random_state=SEED),False),
   ('adaboost',AdaBoostClassifier(n_estimators=120,learning_rate=.08,random_state=SEED),False),
   ('mlp_neural_net',MLPClassifier(hidden_layer_sizes=(32,12),alpha=10,max_iter=100,early_stopping=True,validation_fraction=.15,n_iter_no_change=10,random_state=SEED),True),
  ]
  try:
   from lightgbm import LGBMClassifier
   ans.append(('lightgbm',LGBMClassifier(n_estimators=180,learning_rate=.05,num_leaves=15,max_depth=5,min_child_samples=130,reg_lambda=30,reg_alpha=2,verbosity=-1,n_jobs=4,random_state=SEED),False))
  except ImportError:pass
  try:
   from xgboost import XGBClassifier
   ans.append(('xgboost',XGBClassifier(n_estimators=200,max_depth=4,learning_rate=.05,min_child_weight=40,reg_lambda=30,reg_alpha=2,subsample=.9,colsample_bytree=.9,tree_method='hist',n_jobs=4,random_state=SEED,eval_metric='logloss'),False))
  except ImportError:pass
  try:
   from catboost import CatBoostClassifier
   ans.append(('catboost',CatBoostClassifier(iterations=210,depth=5,learning_rate=.055,l2_leaf_reg=22,loss_function='Logloss',verbose=False,thread_count=4,random_seed=SEED,allow_writing_files=False),False))
  except ImportError:pass
  return ans

def run(source, output):
  df,sha=load_rows(source)
  p=df.order_purchase_timestamp
  masks={n:(((p>=a)&(p<b))&df.label_mature).to_numpy() for n,(a,b) in SPLITS.items()}
  y=df.label_late.to_numpy(dtype=np.int8)
  features=feature_frame(df,'extended_checkout_unattested')
  f_names=list(features.columns)
  all_x=features.to_numpy(dtype=np.float32)
  tr=masks['development_training']; sel=masks['development_selection']
  cal=masks['development_calibration']; march=masks['historical_stress_inspected']; late=masks['historical_audit_inspected']
  print('Rows',len(df),'features',len(f_names),'train',sum(tr),'January selection',sum(sel),'Feb calibration',sum(cal),'March',sum(march),'later',sum(late),flush=True)
  # Standardize training and other folds only with 2017 data; deterministic, unsupervised.
  scale=StandardScaler().fit(all_x[tr]); x_scaled=scale.transform(all_x)
  ans=[]
  for name,model,scaled in candidates():
   start=time.monotonic()
   try:
    xx=x_scaled if scaled else all_x
    with warnings.catch_warnings():
     warnings.simplefilter('ignore')
     model.fit(xx[tr],y[tr])
    if hasattr(model,'predict_proba'):
     prob=model.predict_proba(xx[sel])[:,1]
    else:
     z=model.decision_function(xx[sel]);prob=1/(1+np.exp(-np.clip(z,-50,50)))
    ap=average_precision_score(y[sel],prob);auc=roc_auc_score(y[sel],prob)
    ans.append({'algorithm':name,'january_ap':round(float(ap),6),'january_roc_auc':round(float(auc),6),'fit_seconds':round(time.monotonic()-start,2),'status':'OK'})
    print('%-24s AP %.6f AUC %.6f time %.1fs'%(name,ap,auc,time.monotonic()-start),flush=True)
   except Exception as e:
    ans.append({'algorithm':name,'status':'ERROR','error':str(e)[:250]})
    print('ERROR',name,str(e)[:150],flush=True)
  best=max((a for a in ans if a['status']=='OK' and a['algorithm']!='prior_baseline'),key=lambda t:(t['january_ap'],t['january_roc_auc']))
  rep={'product':'AEGIS','status':'POSTHOC_HISTORICAL_RESEARCH_NOT_PROSPECTIVE','selected_by':'2018-01 average precision then AUC on extended checkout candidate features; fixed predeclared hyperparameters','source_sha256':sha,'feature_names':f_names,'feature_availability_independently_proved':False,'selection_results':ans,'winner':best,'hypothesis_test_warning':'January and later 2018 history already analyzed; this is not a pristine out-of-sample test','live_operational_authorization':False}
  output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(rep,indent=2),encoding='utf-8')
  print('WINNER',best,flush=True)
  return rep

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--olist-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 run(args.olist_dir,args.output)
