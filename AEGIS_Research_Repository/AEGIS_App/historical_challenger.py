"""AEGIS historical-only model challenger for Olist.

Never certifies as-of feature availability, a pristine holdout or procurement value.
All purchased opportunities in each time window are counted BEFORE label joins;
undelivered/unknown outcomes are never silently counted as on time.
Optional free dependencies: pandas, numpy, scikit-learn.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

SPLITS = {
    "development_training": ("2017-01-01", "2018-01-01"),
    "development_selection": ("2018-01-01", "2018-02-01"),
    "development_calibration": ("2018-02-01", "2018-03-01"),
    "historical_stress_inspected": ("2018-03-01", "2018-04-01"),
    "historical_audit_inspected": ("2018-04-01", "2018-08-01"),
}


def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""):h.update(c)
    return h.hexdigest()


def load_rows(source):
    source=Path(source)
    order_path=source/'olist_orders_dataset.csv'
    customer_path=source/'olist_customers_dataset.csv'
    orders=pd.read_csv(order_path, low_memory=False)
    customers=pd.read_csv(customer_path, usecols=['customer_id','customer_state'])
    if not {'order_id','customer_id','order_status','order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date'} <= set(orders):
        raise ValueError('Olist orders required columns missing')
    if orders['order_id'].isna().any() or orders['order_id'].duplicated().any():
        raise ValueError('Blank or duplicate order ids')
    if customers['customer_id'].isna().any() or customers['customer_id'].duplicated().any():
        raise ValueError('Blank or duplicate customer ids')
    # NEVER use order_status as a predictive feature. It is used only to assess label maturity.
    df=orders.merge(customers, on='customer_id',how='left',validate='many_to_one')
    # Supplementary *research candidate* information, not independently certified
    # at checkout. No post-delivery, reviews, shipping or cancellation status used.
    lines_path=source/'olist_order_items_dataset.csv'
    sellers_path=source/'olist_sellers_dataset.csv'
    lines=pd.read_csv(lines_path,usecols=['order_id','order_item_id','seller_id','price','freight_value'])
    sellers=pd.read_csv(sellers_path,usecols=['seller_id','seller_state'])
    if sellers['seller_id'].duplicated().any():raise ValueError('Duplicate seller identifiers')
    lines=lines.merge(sellers,on='seller_id',how='left',validate='many_to_one')
    lines=lines.sort_values(['order_id','order_item_id','seller_id'])
    summary=lines.groupby('order_id',sort=False).agg(
        item_count=('order_item_id','count'),unique_sellers=('seller_id','nunique'),
        quoted_price_sum=('price','sum'),quoted_freight_sum=('freight_value','sum'),
        first_seller_state=('seller_state','first')).reset_index()
    df=df.merge(summary,on='order_id',how='left',validate='one_to_one')
    for col in ['order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date']:
        df[col]=pd.to_datetime(df[col], errors='coerce')
    purchase=df['order_purchase_timestamp']
    delivered=(df['order_status'].astype('string').str.lower()=='delivered') & df['order_delivered_customer_date'].notna()
    valid=delivered & purchase.notna() & (df['order_delivered_customer_date']>=purchase) & df['order_estimated_delivery_date'].notna()
    # Compare calendar day only; these are historical research labels, not SLA compliance.
    df['label_mature']=valid
    df['label_late']=((df['order_delivered_customer_date'].dt.normalize()>df['order_estimated_delivery_date'].dt.normalize()) & valid).astype('int8')
    df['hour']=purchase.dt.hour
    df['weekday']=purchase.dt.dayofweek
    df['month']=purchase.dt.month
    df['day_of_month']=purchase.dt.day
    df['week_of_year']=purchase.dt.isocalendar().week.astype('float')
    df['promise_days']=(df['order_estimated_delivery_date'].dt.normalize()-purchase.dt.normalize()).dt.days
    return df, {'orders_csv_sha256':digest(order_path),'customers_csv_sha256':digest(customer_path),'items_csv_sha256':digest(lines_path),'sellers_csv_sha256':digest(sellers_path)}


def feature_frame(df, arm):
    cols=['hour','weekday','month','day_of_month','week_of_year']
    if arm in ('candidate_checkout_unattested','extended_checkout_unattested'):
        cols+=['promise_days']
    if arm=='extended_checkout_unattested':
        cols+=['item_count','unique_sellers','quoted_price_sum','quoted_freight_sum']
    result=df[cols].apply(pd.to_numeric,errors='coerce').astype(float).copy()
    if arm in ('candidate_checkout_unattested','extended_checkout_unattested'):
        # Categorical schema is known ahead of time (Brazil state abbreviations), no outcome info.
        states=df['customer_state'].fillna('UNKNOWN').astype(str)
        for state in ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']:
            result['state_'+state]=(states==state).astype(int)
    if arm=='extended_checkout_unattested':
        first_state=df['first_seller_state'].fillna('UNKNOWN').astype(str)
        customer_state=df['customer_state'].fillna('UNKNOWN').astype(str)
        result['supplier_customer_same_state']=(first_state==customer_state).astype(int)
        for state in ['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']:
            result['seller_state_'+state]=(first_state==state).astype(int)
    return result.replace([np.inf,-np.inf],np.nan).fillna(-999).clip(-999,10000)


def metrics(labels, scores, calibrated=None):
    labels=np.asarray(labels).astype(int); scores=np.asarray(scores)
    n=len(labels)
    if n==0: return {'mature_rows':0}
    rate=float(labels.mean())
    out={'mature_rows':n,'late_count':int(labels.sum()),'late_rate':round(rate,6),
         'auc':round(float(roc_auc_score(labels,scores)),6) if len(set(labels))>1 else None,
         'average_precision':round(float(average_precision_score(labels,scores)),6) if labels.sum() else None,
         'base_rate_average_precision':round(rate,6),
         'mean_uncalibrated_score':round(float(scores.mean()),6)}
    if calibrated is not None:
        probs=np.clip(np.asarray(calibrated),1e-8,1-1e-8)
        out['mean_calibrated_score']=round(float(probs.mean()),6)
        out['brier_calibrated_descriptive']=round(float(brier_score_loss(labels,probs)),6)
        out['absolute_mean_calibration_gap']=round(float(abs(probs.mean()-rate)),6)
        # equal-width descriptive calibration buckets; no certification.
        buckets=[]
        for lo,hi in zip(np.linspace(0,1,11)[:-1],np.linspace(0,1,11)[1:]):
            mask=(probs>=lo)&(probs<(hi if hi<1 else 1.0001))
            if mask.sum(): buckets.append({'low':round(float(lo),1),'high':round(float(hi),1),
                                           'n':int(mask.sum()),'mean_score':round(float(probs[mask].mean()),5),
                                           'late_rate':round(float(labels[mask].mean()),5)})
        out['calibration_buckets']=buckets
    return out


def run(source, artifact_output=None):
    df,sha=load_rows(source)
    df['partition']='OUTSIDE_PREDECLARED_STUDY'
    purchase=df['order_purchase_timestamp']
    population={}
    for name,(start,end) in SPLITS.items():
        mask=(purchase>=pd.Timestamp(start)) & (purchase<pd.Timestamp(end))
        df.loc[mask,'partition']=name
        population[name]={'all_purchased_opportunities':int(mask.sum()),
                         'mature_comparable_outcomes':int((mask&df['label_mature']).sum()),
                         'unknown_or_noncomparable_outcomes':int((mask&~df['label_mature']).sum())}
    masks={name:(df['partition']==name)&df['label_mature'] for name in SPLITS}
    train,selection,calibration=(masks[name].to_numpy() for name in
                               ('development_training','development_selection','development_calibration'))
    if min(train.sum(),selection.sum(),calibration.sum())<500:raise ValueError('Insufficient mature rows in development partitions')
    labels=df['label_late'].to_numpy()
    experiments=[]
    for arm in ['timestamp_only','candidate_checkout_unattested','extended_checkout_unattested']:
        data=feature_frame(df,arm).to_numpy(dtype=float)
        # Candidate algorithms and fixed hyperparameters declared before inspection of stress/audit periods.
        scaler=StandardScaler()
        xtrain=scaler.fit_transform(data[train]); xsel=scaler.transform(data[selection])
        models=[('logistic',LogisticRegression(C=0.1,max_iter=700,random_state=2026,class_weight=None),xtrain,xsel),
                ('hist_gradient_boosting',HistGradientBoostingClassifier(max_iter=120,max_leaf_nodes=15,
                     min_samples_leaf=100,l2_regularization=20,learning_rate=0.06,early_stopping=False,
                     random_state=2026),data[train],data[selection])]
        for model_name,model,a,b in models:
            model.fit(a,labels[train]); scores=model.predict_proba(b)[:,1]
            experiments.append({'arm':arm,'algorithm':model_name,
                                'selection_ap':float(average_precision_score(labels[selection],scores)),
                                'selection_auc':float(roc_auc_score(labels[selection],scores)),
                                'model':model,'scaler':scaler if model_name=='logistic' else None,
                                'data':data})
    # Algorithmic selection on January only. The human research process has already
    # inspected March and later windows; none is an untouched test set.
    winner=max(experiments,key=lambda e:(e['selection_ap'],e['selection_auc']))
    model=winner['model']; scaler=winner['scaler']; x=winner['data']
    def raw(mask):
        a=x[mask]
        return model.predict_proba(scaler.transform(a) if scaler is not None else a)[:,1]
    # Fit a 1D sigmoid calibrator on the February development cohort ONLY.
    pcal=np.clip(raw(calibration),1e-6,1-1e-6)
    logits=np.log(pcal/(1-pcal)).reshape(-1,1)
    calibrator=LogisticRegression(C=1.0,max_iter=600,random_state=2026)
    calibrator.fit(logits,labels[calibration])
    output={}
    for name,mask_series in masks.items():
        mask=mask_series.to_numpy(); scores=raw(mask)
        logits=np.log(np.clip(scores,1e-6,1-1e-6)/(1-np.clip(scores,1e-6,1-1e-6))).reshape(-1,1)
        probabilities=calibrator.predict_proba(logits)[:,1]
        output[name]=metrics(labels[mask],scores,probabilities)
    candidates=[{'arm':e['arm'],'algorithm':e['algorithm'],
                 'selection_ap':round(e['selection_ap'],6),'selection_auc':round(e['selection_auc'],6)} for e in experiments]
    stress=output['historical_stress_inspected']
    audit=output['historical_audit_inspected']
    # Plain JSON artifact (no pickles); shadow/research-only, never loaded by production app.
    artifact=None
    if winner['algorithm']=='logistic' and artifact_output is not None:
        features=feature_frame(df,winner['arm']).columns.tolist()
        artifact={
            'product':'AEGIS','model_version':'AEGIS_HISTORICAL_CHALLENGER_RESEARCH_2026_11_07',
            'model_family':'LOGISTIC_REGRESSION_JSON_SHADOW_ONLY',
            'feature_names_in_order':features,
            'standard_scaler_mean':scaler.mean_.astype(float).tolist(),
            'standard_scaler_scale':scaler.scale_.astype(float).tolist(),
            'linear_coefficients':model.coef_.ravel().astype(float).tolist(),
            'linear_intercept':float(model.intercept_[0]),
            'calibration_logit_coefficient':float(calibrator.coef_[0][0]),
            'calibration_intercept':float(calibrator.intercept_[0]),
            'training_partition':'development_training','selection_partition':'development_selection',
            'calibration_partition':'development_calibration',
            'source_sha256':sha,'proven_asof':False,'pristine_future_holdout':False,
            'live_scoring_authorized':False,'operational_approval':'NOT_GRANTED',
            'meaning':'Research-only ranking challenger. Requires prospectively witnessed feature snapshots, a frozen evaluation plan, and later independent outcome verification.'}
        # Verify lossless arithmetic equivalence before calling the JSON model frozen.
        probe=data[selection][:64]
        original=model.predict_proba(scaler.transform(probe))[:,1]
        z=((probe-scaler.mean_)/scaler.scale_) @ model.coef_.ravel() + model.intercept_[0]
        replica=1/(1+np.exp(-z))
        if float(np.max(np.abs(original-replica)))>1e-10:
            raise RuntimeError('Frozen JSON coefficients disagree with sklearn scorer')
        blob=json.dumps(artifact,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        artifact['self_hash_excluding_this_field']=hashlib.sha256(blob).hexdigest()
        with Path(artifact_output).open('x',encoding='utf-8') as f:json.dump(artifact,f,indent=2,sort_keys=True,allow_nan=False)
    # Explicit no-certification gate. Numerical score gates are illustrative diagnostics only.
    stress_quality=(stress['auc'] is not None and stress['auc']>=0.65 and
                    stress['absolute_mean_calibration_gap']<=0.03)
    audit_quality=(audit['auc'] is not None and audit['auc']>=0.65 and
                   audit['absolute_mean_calibration_gap']<=0.03)
    return {'product':'AEGIS','study':'REPRODUCIBLE_HISTORICAL_CHALLENGER_NOT_PROSPECTIVE',
            'source_sha256':sha,'total_original_orders':int(len(df)),
            'split_contract':SPLITS,'population_before_label_join':population,
            'feature_sets':{'timestamp_only':'Purchase timestamp calendar features only; independent ingestion time not provable.',
                            'candidate_checkout_unattested':'Adds destination state and estimated-delivery horizon; as-of availability NOT proved.',
                            'extended_checkout_unattested':'Adds item count, seller origin, booked price/freight and seller-location relationship; no independently proven as-of timestamps.'},
            'candidate_models':candidates,
            'model_selection_rule':'Highest January-2018 average precision (then AUC); no stress/audit data in selection.',
            'selected_arm':winner['arm'],'selected_algorithm':winner['algorithm'],
            'calibration_window':'February 2018; sigmoid on frozen raw scores; no later refit.',
            'partitions':output,
            'historical_diagnostic_thresholds_met_both_later_periods':bool(stress_quality and audit_quality),
            'historical_reference_auc_0_558705_not_directly_comparable':True,
            'posthoc_feature_development_after_historical_inspection':True,
            'frozen_shadow_model_artifact_sha256':(artifact['self_hash_excluding_this_field'] if artifact else None),
            'frozen_shadow_model_deployed_to_manager':False,
            'frozen_json_shadow_score_arithmetic_parity_verified':bool(artifact),
            'model_artifact_deployed_to_aegis':False,'prospective_cohort_untouched':False,
            'features_independently_verified_asof':False,
            'probabilities_certified':False,'business_action':'DISABLED',
            'interpretation':'Retrospective historical experiment with posthoc feature iteration: target and cohort differ from frozen 58,911-score model. Later windows have already been seen by researchers and are NOT pristine tests. Scores do not establish prospective accuracy or availability of checkout candidate fields.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--olist-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--shadow-artifact',type=Path,help='Optional plain JSON shadow model; must not already exist')
    args=p.parse_args()
    result=run(args.olist_dir,args.shadow_artifact)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,sort_keys=True)
    print('Historical challenger:',result['selected_arm'],result['selected_algorithm'],
          'March AUC:',result['partitions']['historical_stress_inspected']['auc'],
          'later audit AUC:',result['partitions']['historical_audit_inspected']['auc'],
          '| Prospective certified: NO')
if __name__=='__main__': main()
