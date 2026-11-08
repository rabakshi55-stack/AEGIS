"""AEGIS future holdout contract/read-only gate.

Build a *new*, timestamped scoring plan before future outcomes. This code
catches chronological violations and reused historic order IDs, but does not
claim that a self-declared local time is independently witnessed.
"""
from __future__ import annotations
from collections import Counter
import hashlib,json
from asof_validation import _timestamp

SCORE_FIELDS={'order_id','decision_at','score_recorded_at','feature_latest_recorded_at',
              'model_sha256','research_score'}


def validate_future_holdout(plan,score_rows,previously_seen_ids=()):
    expected={'registered_at','model_training_ended_at','evaluation_start',
              'evaluation_end','model_sha256','eligibility_rule_sha256','feature_contract_sha256'}
    if not isinstance(plan,dict) or set(plan)!=expected:
        raise ValueError('Exactly the immutable study registration contract is required')
    times={k:_timestamp(plan[k]) for k in ('registered_at','model_training_ended_at','evaluation_start','evaluation_end')}
    if not times['model_training_ended_at']<times['registered_at']<times['evaluation_start']<times['evaluation_end']:
        raise ValueError('Freeze the model and declare future period before evaluation begins')
    for name in ('model_sha256','eligibility_rule_sha256','feature_contract_sha256'):
        x=plan[name]
        if not isinstance(x,str) or len(x)!=64 or any(c not in '0123456789abcdef' for c in x):
            raise ValueError('Model, eligibility and feature contracts require SHA256 hashes')
    if not isinstance(score_rows,list) or len(score_rows)>250000:
        raise ValueError('Invalid opportunity list')
    historical_ids=tuple(previously_seen_ids)
    seen=set(historical_ids)
    if len(seen)!=len(historical_ids):
        raise ValueError('Duplicated IDs in exclusion registry')
    included=set();issues=Counter()
    for row in score_rows:
        if not isinstance(row,dict) or set(row)!=SCORE_FIELDS:
            issues['UNAPPROVED_FIELDS_OR_OUTCOME_LEAKAGE']+=1;continue
        oid=row['order_id']
        if not isinstance(oid,str) or not oid or oid in included:
            issues['DUPLICATED_OR_BLANK_OPPORTUNITY']+=1;continue
        included.add(oid)
        if oid in seen:
            issues['HISTORICAL_ID_REUSED']+=1;continue
        try:
            at=_timestamp(row['decision_at'])
            saved=_timestamp(row['score_recorded_at'])
            feature=_timestamp(row['feature_latest_recorded_at'])
            score=float(row['research_score'])
            import math
            if not math.isfinite(score) or score<0 or score>1:raise ValueError('Invalid score')
        except (ValueError,TypeError,OverflowError):
            issues['INVALID_SCORE_OR_CLOCK']+=1;continue
        if not times['evaluation_start']<=at<=times['evaluation_end']:
            issues['DECISION_OUTSIDE_FROZEN_WINDOW']+=1
        if row['model_sha256']!=plan['model_sha256']:
            issues['MODEL_DIGEST_NOT_FROZEN']+=1
        if feature>saved or saved>at or saved<times['registered_at']:
            issues['CLAIMED_ASOF_OR_SCORE_TIME_VIOLATION']+=1
    digest=hashlib.sha256(json.dumps({'plan':plan,'rows':score_rows},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return {'product':'AEGIS','study':'PROSPECTIVE_HOLDOUT_PREREGISTRATION_GATE',
            'status':'BLOCKED_REUSED_OR_INVALID_FUTURE_COHORT' if issues else 'LOCAL_FROZEN_CONTRACT_UNATTESTED',
            'score_rows_checked':len(score_rows),'issue_counts':dict(sorted(issues.items())),
            'registered_contract_and_scoring_digest_sha256':digest,
            'no_label_or_outcome_fields_in_scores':not any(k=='UNAPPROVED_FIELDS_OR_OUTCOME_LEAKAGE' for k in issues),
            'independent_preregistration_attested':False,
            'independent_feature_time_attested':False,
            'untouched_future_holdout_certified':False,
            'prospective_model_performance_certified':False,
            'business_actions':'DISABLED',
            'interpretation':'A locally frozen plan can detect reuse of known past IDs, label fields and obvious chronology errors. Only independently time-witnessed registration, complete source logs and future matured labels can establish truly untouched prospective evaluation.'}


def main():
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',required=True,type=Path)
    p.add_argument('--scores',required=True,type=Path)
    p.add_argument('--known-historical-ids',type=Path,help='One historical order ID per line, never embedded in report')
    p.add_argument('--report',required=True,type=Path)
    a=p.parse_args()
    known=a.known_historical_ids.read_text(encoding='utf-8').splitlines() if a.known_historical_ids else []
    result=validate_future_holdout(json.loads(a.plan.read_text(encoding="utf-8")),json.loads(a.scores.read_text(encoding="utf-8")),known)
    with a.report.open('x') as f:json.dump(result,f,indent=2)
    print(result['status'])
    return 2 if result['status'].startswith('BLOCKED') else 0
if __name__=='__main__':raise SystemExit(main())
