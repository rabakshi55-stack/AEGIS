"""Research-only, dependency-free scoring for frozen JSON AEGIS challenger.

Not wired into a manager recommendation or business execution. Feature values
must arrive with a timezone-aware asserted recorded-at clock; that assertion
is NOT independent provenance. Caller must satisfy future_holdout_gate.
"""
from __future__ import annotations
import hashlib,json,math
from asof_validation import _timestamp


def verify_artifact(artifact):
    if not isinstance(artifact,dict):raise ValueError('Artifact must be an object')
    claimed=artifact.get('self_hash_excluding_this_field')
    if not isinstance(claimed,str) or len(claimed)!=64:raise ValueError('Missing frozen digest')
    x={k:v for k,v in artifact.items() if k!='self_hash_excluding_this_field'}
    actual=hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if claimed!=actual:raise ValueError('Shadow artifact changed after freezing')
    if artifact.get('model_family')!='LOGISTIC_REGRESSION_JSON_SHADOW_ONLY' or artifact.get('live_scoring_authorized') is not False:
        raise ValueError('No live models or unsupported model families')
    n=len(artifact['feature_names_in_order'])
    if n<1 or len(set(artifact['feature_names_in_order']))!=n or any(len(artifact[k])!=n for k in
              ('standard_scaler_mean','standard_scaler_scale','linear_coefficients')):
        raise ValueError('Invalid frozen feature schema')
    for k in ('standard_scaler_mean','standard_scaler_scale','linear_coefficients'):
        if not all(isinstance(i,(int,float)) and math.isfinite(i) for i in artifact[k]):
            raise ValueError('Nonfinite coefficient or scale')
    if not all(i>0 for i in artifact['standard_scaler_scale']):raise ValueError('Invalid scaling factors')
    for k in ('linear_intercept','calibration_logit_coefficient','calibration_intercept'):
        v=artifact[k]
        if not isinstance(v,(float,int)) or not math.isfinite(v):raise ValueError('Invalid intercept')
    return claimed


def sigmoid(z):
    # Overflow-safe logistic response, preserving finite probabilities.
    if z>=0:return 1/(1+math.exp(-z))
    e=math.exp(z)
    return e/(1+e)


def score_frozen_shadow(artifact,snapshot):
    artifact_digest=verify_artifact(artifact)
    if not isinstance(snapshot,dict) or set(snapshot)!={'order_id','decision_at','score_recorded_at','features','feature_recorded_at'}:
        raise ValueError('Only an exact decision-time scoring snapshot is allowed')
    oid=snapshot['order_id']
    if not isinstance(oid,str) or not oid:raise ValueError('Blank order ID')
    decision=_timestamp(snapshot['decision_at']); saved=_timestamp(snapshot['score_recorded_at'])
    known=_timestamp(snapshot['feature_recorded_at'])
    if known>saved or saved>decision:
        raise ValueError('Feature and score must be recorded at or before the decision')
    features=snapshot['features']
    names=artifact['feature_names_in_order']
    if not isinstance(features,dict) or set(features)!=set(names):
        raise ValueError('Missing/extra predictive feature names or outcome leakage')
    vector=[]
    for k in names:
        n=features[k]
        if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n):
            raise ValueError('All shadow features must be finite numeric values')
        vector.append(float(n))
    raw_logit=artifact['linear_intercept']+sum(
        ((value-mean)/scale)*coef for value,mean,scale,coef in zip(vector,
        artifact['standard_scaler_mean'],artifact['standard_scaler_scale'],artifact['linear_coefficients']))
    raw=sigmoid(raw_logit)
    calibrated=sigmoid(artifact['calibration_logit_coefficient']*raw_logit+artifact['calibration_intercept'])
    return {'product':'AEGIS','status':'RESEARCH_SHADOW_SCORE_UNATTESTED',
        'score_type':'HISTORICAL_CHALLENGER_NOT_CALIBRATED_FOR_LIVE_DECISIONS',
        'uncalibrated_ranking_score':round(raw,8),'development_window_calibrated_score':round(calibrated,8),
        'model_sha256':artifact_digest,'features_independently_verified_asof':False,
        'probability_certified':False,'business_action':'DISABLED',
        'interpretation':'The model is an offline retrospective challenger only. The supplied feature recorded-at clock is an assertion, not independent source proof. Do not use this score for supplier procurement.'}
