"""Stdlib-only verified V3 evidence for the existing manager UI; no model fitting."""
from pathlib import Path
import hashlib,json,math
HERE=Path(__file__).resolve().parent

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def get_review_evidence(directory=HERE/'evidence'):
    result={'available':False,'operational_approval':'NOT_GRANTED','permitted_action':'NONE','untouched_holdout_certified':False}
    try:
        directory=Path(directory)
        checks=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
        if set(checks)!={'predictive_review.json','allocation_review.json'}: raise ValueError('Incomplete review manifest')
        for name,h in checks.items():
            if digest(directory/name)!=h: raise ValueError('Review evidence digest mismatch')
        p=json.loads((directory/'predictive_review.json').read_text(encoding='utf-8')); a=json.loads((directory/'allocation_review.json').read_text(encoding='utf-8'))
        if p['protocol_sha256']!=digest(HERE/'protocol.json') or p['protocol_sha256']!=(HERE/'protocol.sha256').read_text().strip(): raise ValueError('Protocol does not match review evidence')
        if p['untouched_holdout_certified'] is not False or p['operational_probability_authorized'] is not False or p['operational_approval']!='NOT_GRANTED' or a['status']!='SYNTHETIC_RESEARCH_ONLY': raise ValueError('Unexpected certification claim')
        d=p['cohorts']['diagnostic']; counts=d['population']; raw=d['raw']; cal=d['calibrated']; u=d['uncertainty_calibrated']['intervals_95pct']
        if counts['all_purchases']!=counts['mature_comparable']+counts['noncomparable_or_unknown']+counts['comparable_but_not_mature_at_cutoff'] or not 0<counts['late']<counts['mature_comparable']: raise ValueError('Review population inconsistent')
        for metrics in (raw,cal):
            for k in ['average_precision','roc_auc','brier','late_rate','mean_score']:
                if type(metrics[k]) not in (int,float) or not math.isfinite(metrics[k]) or not 0<=metrics[k]<=1: raise ValueError('Invalid review metric')
            if abs(metrics['late_rate']-counts['late']/counts['mature_comparable'])>1e-9 or abs(metrics['signed_calibration_gap']-(metrics['mean_score']-metrics['late_rate']))>1e-9: raise ValueError('Metric reconciliation failed')
        if a['risk_lock_changes_assignment'] is not False or a['sequential']!=a['risk_locked_sequential']: raise ValueError('Risk lock reconciliation failed')
        result.update({'available':True,'scope':'POST_HOC_HISTORICAL_DIAGNOSTIC_AND_SEPARATE_FICTIONAL_OPTIMIZATION','period':'April–July 2018; already inspected','population':counts,'raw':raw,'calibrated':cal,'uncertainty_95pct':u,'baseline':d['training_prevalence_baseline'],'calibration_bins':d['calibration_bins_calibrated'],'monthly_common_cost_usd':a['monthly_common_cost_usd'],'sequential_common_cost_usd':a['sequential_common_cost_usd'],'archived_daily_quoted_cost_usd':a['prior_step126']['Cost_Only']['archived_quoted_cost_usd'],'risk_lock_changes_assignment':False,'limitations':p['limitations']+a['limitations']})
    except (OSError,ValueError,KeyError,TypeError,ZeroDivisionError) as exc: result['error']=str(exc)
    return result
