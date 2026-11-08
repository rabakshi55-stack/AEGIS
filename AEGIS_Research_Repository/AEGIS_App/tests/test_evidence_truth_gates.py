"""Research-only negatives: input tampering, impossible dates, missing fees, reused cohorts."""
from __future__ import annotations
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from source_witness_gate import verify_snapshot,canonical_manifest
from future_holdout_gate import validate_future_holdout
from supplier_financial_audit import audit_financial_outcomes,COMPONENTS

class SourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'orders.csv').write_bytes(b'order_id\nexample\n')
        self.manifest={'source_system':'FICTIONAL_ERP','snapshot_id':'S1',
          'claimed_recorded_at':'2026-10-30T10:00:00+00:00','decision_at':'2026-11-01T00:00:00+00:00',
          'files':{'orders.csv':hashlib.sha256((self.root/'orders.csv').read_bytes()).hexdigest()}}
    def test_local_hash_is_not_asof_proof(self):
        x=verify_snapshot(self.root,{'manifest':self.manifest})
        self.assertTrue(x['file_checks_pass']);self.assertFalse(x['historical_feature_availability_certified'])
    def test_tamper_fails(self):
        (self.root/'orders.csv').write_bytes(b'mutated')
        self.assertEqual(verify_snapshot(self.root,{'manifest':self.manifest})['status'],'BLOCKED_INTEGRITY_FAILURE')
    def test_postdecision_claim_fails(self):
        m=deepcopy(self.manifest);m['claimed_recorded_at']='2026-11-02T00:00:00+00:00'
        self.assertEqual(verify_snapshot(self.root,{'manifest':m})['status'],'BLOCKED_INTEGRITY_FAILURE')
    def test_path_traversal_fails(self):
        m=deepcopy(self.manifest);m['files']={'../secret':('0'*64)}
        with self.assertRaises(ValueError):verify_snapshot(self.root,{'manifest':m})
    def test_untrusted_signature_fails(self):
        self.assertEqual(verify_snapshot(self.root,{'manifest':self.manifest,'signature_base64':'abc'})['status'],'BLOCKED_INTEGRITY_FAILURE')
    def test_valid_pinned_signer_still_not_time_attestation(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
        except ImportError:self.skipTest('optional cryptography unavailable')
        key=Ed25519PrivateKey.generate()
        pub=key.public_key().public_bytes(encoding=serialization.Encoding.PEM,format=serialization.PublicFormat.SubjectPublicKeyInfo)
        (self.root/'key.pem').write_bytes(pub)
        raw,_=canonical_manifest(self.manifest)
        envelope={'manifest':self.manifest,'signature_base64':base64.b64encode(key.sign(raw)).decode()}
        x=verify_snapshot(self.root,envelope,self.root/'key.pem')
        self.assertTrue(x['cryptographic_signature_verified_against_pinned_key'])
        self.assertFalse(x['historical_feature_availability_certified'])
        envelope['manifest']['snapshot_id']='TAMPERED'
        self.assertEqual(verify_snapshot(self.root,envelope,self.root/'key.pem')['status'],'BLOCKED_INTEGRITY_FAILURE')

class FutureHoldoutTests(unittest.TestCase):
    def setUp(self):
        self.plan={'model_training_ended_at':'2026-10-20T00:00:00+00:00',
        'registered_at':'2026-11-07T00:00:00+00:00','evaluation_start':'2026-11-08T00:00:00+00:00',
        'evaluation_end':'2026-12-08T00:00:00+00:00','model_sha256':'a'*64,
        'eligibility_rule_sha256':'b'*64,'feature_contract_sha256':'c'*64}
        self.row={'order_id':'FUTURE-O-1','decision_at':'2026-11-09T10:00:00+00:00',
                  'score_recorded_at':'2026-11-09T10:00:00+00:00',
                  'feature_latest_recorded_at':'2026-11-09T09:00:00+00:00',
                  'model_sha256':'a'*64,'research_score':0.2}
    def test_local_contract_not_certified(self):
        x=validate_future_holdout(self.plan,[self.row],['PREVIOUS-1'])
        self.assertEqual(x['status'],'LOCAL_FROZEN_CONTRACT_UNATTESTED')
        self.assertFalse(x['untouched_future_holdout_certified'])
    def test_old_id_blocked(self):
        x=validate_future_holdout(self.plan,[self.row],['FUTURE-O-1'])
        self.assertIn('HISTORICAL_ID_REUSED',x['issue_counts'])
    def test_label_leakage_blocked(self):
        x=dict(self.row,actual_delivery_date='2026-11-10')
        self.assertEqual(validate_future_holdout(self.plan,[x])['status'],'BLOCKED_REUSED_OR_INVALID_FUTURE_COHORT')
    def test_postdecision_feature_blocked(self):
        x=dict(self.row,feature_latest_recorded_at='2026-11-10T00:00:00+00:00')
        self.assertIn('CLAIMED_ASOF_OR_SCORE_TIME_VIOLATION',validate_future_holdout(self.plan,[x])['issue_counts'])
    def test_after_registration_rule(self):
        self.plan['registered_at']='2026-12-09T00:00:00+00:00'
        with self.assertRaises(ValueError):validate_future_holdout(self.plan,[self.row])

class SupplierCostsTests(unittest.TestCase):
    def setUp(self):
        self.plan={'registered_at':'2026-10-28T00:00:00+00:00',
                   'evaluation_start':'2026-11-01T00:00:00+00:00','evaluation_end':'2026-11-30T00:00:00+00:00',
                   'outcome_freeze_at':'2027-01-01T00:00:00+00:00','currency':'INR'}
        self.events=[]
        for idx,group in enumerate(['CONTROL','TREATMENT']):
            self.events.append({'order_id':f'F-{idx}','item_id':'CABLE','supplier_id':f'S-{idx}',
                'evaluation_group':group,'assignment_at':'2026-10-30T00:00:00+00:00',
                'decision_at':'2026-11-02T00:00:00+00:00',
                'outcome_at':'2026-11-20T00:00:00+00:00',
                'outcome_recorded_at':'2026-11-21T00:00:00+00:00',
                'source_record_id':f'RECEIPT-{idx}','source_system':'FICTIONAL_ERP',
                'source_recorded_at':'2026-11-21T00:00:00+00:00','currency':'INR',
                'units':10,'cost_components_cents':{k:(100 if k=='purchase' else 0) for k in COMPONENTS}})
    def test_descriptive_never_causal(self):
        x=audit_financial_outcomes(self.events,self.plan)
        self.assertEqual(x['status'],'DESCRIPTIVE_RECORDED_COST_ONLY_UNATTESTED')
        self.assertFalse(x['causal_supplier_switch_benefit_established'])
    def test_missing_fee_component_rejected(self):
        bad=deepcopy(self.events);bad[0]['cost_components_cents'].pop('quality')
        self.assertEqual(audit_financial_outcomes(bad,self.plan)['status'],'BLOCKED_INCOMPLETE_OR_INCOMPARABLE_EVIDENCE')
    def test_cross_currency_rejected(self):
        bad=deepcopy(self.events);bad[0]['currency']='USD'
        self.assertIn('MIXED_OR_UNKNOWN_CURRENCY',audit_financial_outcomes(bad,self.plan)['issues'])
    def test_unmatched_items_rejected(self):
        bad=deepcopy(self.events);bad[0]['item_id']='CONNECTOR'
        self.assertIn('UNMATCHED_ITEM_BETWEEN_GROUPS',audit_financial_outcomes(bad,self.plan)['issues'])
    def test_postfreeze_settlement_rejected(self):
        bad=deepcopy(self.events);bad[0]['outcome_recorded_at']='2027-02-01T00:00:00+00:00'
        self.assertIn('EVENT_CHRONOLOGY_OR_MATURITY_VIOLATION',audit_financial_outcomes(bad,self.plan)['issues'])

if __name__=='__main__':unittest.main()

class ResearchShadowScoringTests(unittest.TestCase):
    def setUp(self):
        import shadow_model
        self.shadow=shadow_model
        self.artifact={'product':'AEGIS','model_family':'LOGISTIC_REGRESSION_JSON_SHADOW_ONLY',
                       'live_scoring_authorized':False,'feature_names_in_order':['hour','distance'],
                       'standard_scaler_mean':[10.0,100.0],'standard_scaler_scale':[2.0,50.0],
                       'linear_coefficients':[0.5,-0.3],'linear_intercept':-2.0,
                       'calibration_logit_coefficient':0.8,'calibration_intercept':0.1}
        digest=hashlib.sha256(json.dumps(self.artifact,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.artifact['self_hash_excluding_this_field']=digest
        self.snapshot={'order_id':'FIXTURE-ONLY','decision_at':'2026-11-10T10:00:00+00:00',
                       'score_recorded_at':'2026-11-10T09:59:00+00:00',
                       'feature_recorded_at':'2026-11-10T09:58:00+00:00',
                       'features':{'hour':12,'distance':150}}
    def test_frozen_math_and_uncertainty(self):
        import math
        result=self.shadow.score_frozen_shadow(self.artifact,self.snapshot)
        expected=1/(1+math.exp(1.8))
        self.assertAlmostEqual(result['uncalibrated_ranking_score'],expected,places=7)
        self.assertFalse(result['probability_certified'])
    def test_tampered_model_refused(self):
        bad=deepcopy(self.artifact);bad['linear_coefficients'][0]=42
        with self.assertRaises(ValueError):self.shadow.score_frozen_shadow(bad,self.snapshot)
    def test_future_feature_refused(self):
        bad=deepcopy(self.snapshot);bad['feature_recorded_at']='2026-11-11T10:00:00+00:00'
        with self.assertRaises(ValueError):self.shadow.score_frozen_shadow(self.artifact,bad)
    def test_postreceipt_feature_name_refused(self):
        bad=deepcopy(self.snapshot);bad['features']['actual_delivery_timestamp']=1
        with self.assertRaises(ValueError):self.shadow.score_frozen_shadow(self.artifact,bad)
