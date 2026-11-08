"""Read-only AEGIS research champion registry; never operational or self-training.

Bundled original benchmark and extended support-vector benchmark must agree on
source hashes and feature schema. The historical, repeatedly inspected January
selection is for research model-family ranking, not prospective certification.
"""
from __future__ import annotations
from pathlib import Path
import json, hashlib
from shadow_model import verify_artifact,score_frozen_shadow

RESEARCH = Path(__file__).resolve().parent.parent / 'Research' / 'Validation_Archive' / 'Current_Validation_2026_11_07'
BROAD = RESEARCH/'BROAD_ALGORITHM_BENCHMARK.json'
EXTENDED = RESEARCH/'EXPANDED_BENCHMARK_REPORT.json'
SHADOW = RESEARCH/'AEGIS_RELEASE_SHADOW_MODEL.json'


def _read_json(path):
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict):raise ValueError('Expected benchmark record')
    return data


def collect_report():
    broad,extended=_read_json(BROAD),_read_json(EXTENDED)
    if broad.get('source_sha256')!=extended.get('original_source_hashes'):
        raise ValueError('Benchmark source hash mismatch')
    if broad.get('feature_names')!=extended.get('feature_names'):
        raise ValueError('Benchmark feature schema mismatch')
    if broad.get('feature_availability_independently_proved') is not False or extended.get('feature_availability_independently_verified') is not False:
        raise ValueError('Unsubstantiated historical source certification')
    if broad.get('live_operational_authorization') is not False or extended.get('business_execution')!='DISABLED':
        raise ValueError('Invalid operational action policy')
    if extended.get('train_rows')!=43426 or extended.get('selection_rows')!=7069:
        raise ValueError('Unreconciled historical cohort counts')
    original=broad.get('selection_results')
    others=extended.get('results')
    if not isinstance(original,list) or not isinstance(others,list):raise ValueError('Incomplete benchmark records')
    rows=[]
    for record,keys in [(r,('january_ap','january_roc_auc')) for r in original]+[(r,('selection_ap','selection_auc')) for r in others]:
        if record.get('status')!='OK':continue
        ap,auc=record[keys[0]],record[keys[1]]
        if not (type(ap) in (int,float) and type(auc) in (int,float) and 0<=ap<=1 and 0<=auc<=1):
            raise ValueError('Non-finite or out of range benchmark metric')
        rows.append({'name':record['algorithm'],'average_precision':ap,'roc_auc':auc,'cohort':'Jan 2018 historical selection'})
    if len(rows)<20 or len({r['name'] for r in rows})!=len(rows):
        raise ValueError('Benchmark incomplete or duplicated')
    rows.sort(key=lambda r:(r['average_precision'],r['roc_auc']),reverse=True)
    chosen=rows[0]
    # Existing portable JSON shadow artifact corresponds only to this previously
    # selected Logistic Regression configuration, NEVER automatically install a
    # different model from a benchmark leaderboard.
    shadow_ok=False
    if chosen['name']=='logistic_l2':
        artifact=_read_json(SHADOW)
        verify_artifact(artifact)
        if artifact.get('source_sha256')!=broad.get('source_sha256') or artifact.get('feature_names_in_order')!=broad.get('feature_names'):
            raise ValueError('Frozen logistic shadow model does not match benchmark inputs')
        shadow_ok=True
    return {
        'available':True,
        'status':'RETROSPECTIVE_RESEARCH_COMPARISON_NOT_DEPLOYMENT',
        'selected_algorithm':chosen,
        'selection_rule':'Highest Jan-2018 average precision; ROC-AUC tie breaker; all historically inspected',
        'models_tested_successfully':len(rows),
        'total_attempts':len(original)+len(others),
        'sorted_candidates':rows,
        'frozen_shadow_score_available':shadow_ok,
        'model_used_for_production_predictions':False,
        'future_feature_availability_certified':False,
        'prospective_performance_certified':False,
        'operational_approval':'NOT_GRANTED','business_execution':'DISABLED',
        'warning':'All results are historical and post-hoc. This winner is not a certified improvement over the old 0.5587 model (different cohort/features), and cannot be automatically used on arbitrary uploads.'}


def score_research_snapshot(request):
    if not isinstance(request,dict) or set(request)!={'research_acknowledgement','snapshot'}:
        raise ValueError('Explicit research acknowledgment and snapshot required')
    if request['research_acknowledgement']!='RESEARCH_ONLY_NO_BUSINESS_ACTION':
        raise ValueError('Research-only scoring must be acknowledged')
    report=collect_report()
    if not report['frozen_shadow_score_available']:
        raise ValueError('No portable frozen scoring artifact for this algorithm')
    return score_frozen_shadow(_read_json(SHADOW),request['snapshot'])


def is_model_selection_question(question):
    """Narrow, audit-friendly routing; never intercept questions about uploaded data."""
    if not isinstance(question,str):return False
    s=' '.join(question.casefold().split())
    return any(phrase in s for phrase in (
        'which algorithm', 'best algorithm', 'which model', 'best model',
        'model selection', 'model benchmark', 'machine learning model',
        'logistic regression', 'support vector', ' svm', 'xgboost', 'lightgbm',
        'catboost', 'neural network', 'classification algorithm', 'predictive algorithm', 'model accuracy',
        'classifier benchmark')) or s.startswith('svm')


def benchmark_copilot_answer(question):
    r=collect_report()
    winner=r['selected_algorithm']
    rows=r['sorted_candidates']
    best_svm=next((x for x in rows if x['name']=='linear_svm_balanced'),None)
    base=(f"AEGIS evaluated {r['models_tested_successfully']} historical classifier configurations. "
          f"The January-2018 development selection favored {winner['name']}: "
          f"average precision {winner['average_precision']:.5f}, ROC-AUC {winner['roc_auc']:.5f}. ")
    if is_model_selection_question(question) and 'svm' in question.casefold() and best_svm:
        base+=(f"The tested class-weighted linear SVM had average precision {best_svm['average_precision']:.5f} "
               f"and ROC-AUC {best_svm['roc_auc']:.5f}; kernel SVMs did not lead by average precision. ")
    base+=("These historical differences are small and not evidence of a reliably better live predictor. "
           "The later inspected cohorts are not pristine holdouts, and checkout-field availability at decision time is unverified. "
           "The selected model is available only for explicitly acknowledged research shadow scoring; "
           "it does not score arbitrary business uploads or authorize supplier actions.")
    return {'answer':base,'context':'historical_order',
      'evidence_source':'AEGIS_HISTORICAL_CLASSIFIER_BENCHMARK_RESEARCH_ONLY',
      'routing_mode':'CHECKED_DETERMINISTIC_BENCHMARK_EVIDENCE',
      'operational_approval':'NOT_GRANTED','permitted_action':'NONE','human_review':'REQUIRED',
      'model_selection_status':r['status']}
