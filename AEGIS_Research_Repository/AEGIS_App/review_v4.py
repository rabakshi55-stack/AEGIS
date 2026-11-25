"""Read-only final review evidence; deliberately never exposes operational scores."""
from pathlib import Path
import hashlib,json,math
ROOT=Path(__file__).resolve().parents[1]/'Review_V4'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get_final_evidence(directory=ROOT):
    result={'available':False,'operational_approval':'NOT_GRANTED','permitted_action':'NONE'}
    try:
        p=Path(directory);manifest=json.loads((p/'evidence_manifest.json').read_text(encoding='utf-8'))
        required={'JD/result.json','JD/protocol.json','JD/freeze_manifest.json','JD/feature_contract.json','JD/fitted_model.json','JD/prediction_report.json','JD/evaluate_jd.py','challenger_protocol.json','challenger.py','evidence/challenger.json'}
        if set(manifest)!=required:raise ValueError('Incomplete evidence manifest')
        for name,h in manifest.items():
            if digest(p/name)!=h:raise ValueError('Evidence digest mismatch: '+name)
        j=json.loads((p/'JD/result.json').read_text()); c=json.loads((p/'evidence/challenger.json').read_text()); frozen=json.loads((p/'JD/freeze_manifest.json').read_text())
        if j['freeze_manifest']!=frozen or any(digest(p/'JD'/n)!=h for n,h in frozen.items()):raise ValueError('JD frozen evidence mismatch')
        if c['protocol_sha256']!=digest(p/'challenger_protocol.json'):raise ValueError('Challenger protocol mismatch')
        for k in ('untouched_team_attestation','original_license_verified','operational_approval','supplier_causal_effect_established'):
            if j[k] is not False:raise ValueError('Unsupported external certification')
        if j['model_unchanged'] is not True or any(c[k] is not False for k in ('jd_used','feature_availability_attested','untouched_holdout','operational_approval')):raise ValueError('Unexpected challenger certification')
        n=j['counts']['eligible_orders']; late=j['counts']['late_orders']; rate=j['prevalence']
        if not 0<late<n or not math.isclose(rate,late/n,abs_tol=1e-10):raise ValueError('External population mismatch')
        if sum(v for k,v in j['counts'].items() if k.startswith('excluded_'))+n!=j['counts']['unique_orders']:raise ValueError('External exclusions do not reconcile')
        for key in ('raw','calibrated','training_prior_baseline'):
            m=j[key]
            for field in ('average_precision','roc_auc','brier'):
                if not math.isfinite(m[field]) or not 0<=m[field]<=1:raise ValueError('Invalid metric')
        if not math.isclose(j['calibrated']['signed_calibration_gap'],j['calibrated_mean']-rate,abs_tol=1e-10):raise ValueError('Calibration gap mismatch')
        result.update(available=True,external=j,challenger=c,scope='CONDITIONAL_EXTERNAL_HISTORICAL_VALIDATION_AND_RETROSPECTIVE_CHALLENGERS',limitations=['JD.com now inspected; no new untouched test for challengers. Team non-exposure and original data-use terms unverified.','Olist promise availability not independently attested; challengers are not operational models.','No supplier-switch causality or autonomous procurement.'])
    except (OSError,ValueError,TypeError,KeyError,ZeroDivisionError) as exc:result['error']=str(exc)
    return result
