"""AEGIS offline supplementary SVM/ML model-family benchmark. NEVER authorizes live procurement.
Selection on January 2018 only; all data post hoc and historical.
"""
import argparse, json, time, warnings
from pathlib import Path
import numpy as np
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.svm import LinearSVC, SVC
from sklearn.linear_model import SGDClassifier, RidgeClassifier, LogisticRegression
from sklearn.neighbors import KNeighborsClassifier, NearestCentroid
from sklearn.naive_bayes import BernoulliNB, ComplementNB
from sklearn.kernel_approximation import Nystroem, RBFSampler
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import BaggingClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.neural_network import MLPClassifier
from historical_challenger import load_rows, feature_frame, SPLITS
SEED=20261107

def models():
 return [
 ('linear_svm_c001',LinearSVC(C=.01,max_iter=4500,random_state=SEED),'scaled'),
 ('linear_svm_c01',LinearSVC(C=.1,max_iter=4500,random_state=SEED),'scaled'),
 ('linear_svm_balanced',LinearSVC(C=.01,class_weight='balanced',max_iter=4500,random_state=SEED),'scaled'),
 ('sgd_svm_hinge',SGDClassifier(loss='hinge',alpha=.0003,max_iter=1200,random_state=SEED),'scaled'),
 ('sgd_modified_huber',SGDClassifier(loss='modified_huber',alpha=.001,max_iter=1200,random_state=SEED),'scaled'),
 ('ridge_classifier',RidgeClassifier(alpha=50.0),'scaled'),
 ('rbf_svm_c05',SVC(C=.5,kernel='rbf',gamma='scale',cache_size=512),'scaled'),
 ('rbf_svm_c2',SVC(C=2,kernel='rbf',gamma='scale',cache_size=512),'scaled'),
 ('poly_svm_degree2',SVC(C=.5,kernel='poly',degree=2,gamma='scale',coef0=1,cache_size=512),'scaled'),
 ('sigmoid_svm',SVC(C=.3,kernel='sigmoid',gamma='scale',cache_size=512),'scaled'),
 ('knn_101',KNeighborsClassifier(n_neighbors=101,weights='distance',n_jobs=4),'scaled'),
 ('knn_301',KNeighborsClassifier(n_neighbors=301,weights='uniform',n_jobs=4),'scaled'),
 ('nearest_centroid',NearestCentroid(),'scaled'),
 ('bernoulli_nb',BernoulliNB(alpha=10,binarize=0.0),'scaled'),
 ('complement_nb',ComplementNB(alpha=5),'nonnegative'),
 ('rbf_fourier_logistic',make_pipeline(RBFSampler(gamma=.015,n_components=900,random_state=SEED),LogisticRegression(C=.1,max_iter=500,random_state=SEED)),'scaled'),
 ('nystroem_rbf_logistic',make_pipeline(Nystroem(kernel='rbf',gamma=.015,n_components=650,random_state=SEED),LogisticRegression(C=1,max_iter=500,random_state=SEED)),'scaled'),
 ('logistic_elasticnet',LogisticRegression(penalty='elasticnet',solver='saga',l1_ratio=.2,C=.1,max_iter=600,random_state=SEED,n_jobs=4),'scaled'),
 ('logistic_l1',LogisticRegression(penalty='l1',solver='saga',C=.1,max_iter=600,random_state=SEED,n_jobs=4),'scaled'),
 ('mlp_small',MLPClassifier(hidden_layer_sizes=(16,),alpha=20,max_iter=120,early_stopping=True,random_state=SEED),'scaled'),
 ('bagged_shallow_trees',BaggingClassifier(estimator=DecisionTreeClassifier(max_depth=5,min_samples_leaf=160),n_estimators=60,n_jobs=4,random_state=SEED),'raw'),
 ]

def run(source,output):
 start=time.monotonic();df,hashes=load_rows(source);p=df.order_purchase_timestamp
 masks={n:(((p>=a)&(p<b))&df.label_mature).to_numpy() for n,(a,b) in SPLITS.items()};tr=masks['development_training'];sel=masks['development_selection'];y=df.label_late.to_numpy(dtype=np.int8)
 frame=feature_frame(df,'extended_checkout_unattested');raw=frame.to_numpy(dtype=np.float32)
 scaled=StandardScaler().fit(raw[tr]).transform(raw).astype(np.float32)
 nonnegative=MinMaxScaler().fit(raw[tr]).transform(raw).clip(0).astype(np.float32)
 matrices={'raw':raw,'scaled':scaled,'nonnegative':nonnegative};results=[]
 print('Expanded AEGIS benchmark:',sum(tr),'train',sum(sel),'selection',raw.shape[1],'features',flush=True)
 for name,model,rep in models():
  now=time.monotonic();x=matrices[rep]
  try:
   with warnings.catch_warnings():
    warnings.simplefilter('ignore');model.fit(x[tr],y[tr])
   if hasattr(model,'decision_function'):scores=np.asarray(model.decision_function(x[sel])).reshape(-1)
   elif hasattr(model,'predict_proba'):scores=model.predict_proba(x[sel])[:,1]
   else:scores=np.asarray(model.predict(x[sel])).reshape(-1)
   if not np.isfinite(scores).all():raise ValueError('nonfinite scores')
   ap=float(average_precision_score(y[sel],scores));auc=float(roc_auc_score(y[sel],scores))
   row={'algorithm':name,'selection_ap':round(ap,6),'selection_auc':round(auc,6),'fit_eval_seconds':round(time.monotonic()-now,2),'status':'OK','train_rows':int(sum(tr))}
   print(f'{name:26} AP={ap:.6f} AUC={auc:.6f} seconds={row["fit_eval_seconds"]}',flush=True)
  except Exception as exc:
   row={'algorithm':name,'status':'FAILED','reason':repr(exc)[:200],'train_rows':int(sum(tr))};print('FAILED',name,repr(exc),flush=True)
  results.append(row)
 report={'study':'AEGIS_EXPANDED_BENCHMARK_RESEARCH_ONLY','original_source_hashes':hashes,'seed':SEED,'feature_set':'extended_checkout_unattested', 'feature_names':frame.columns.tolist(),'selection':'January 2018 AP; AUC as tiebreak','train_rows':int(sum(tr)),'selection_rows':int(sum(sel)),'feature_availability_independently_verified':False,'pristine_holdout':False,'business_execution':'DISABLED','all_candidates_trained_on_same_rows':True,'results':results,'seconds':round(time.monotonic()-start,2)}
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--olist-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();run(args.olist_dir,args.output)
