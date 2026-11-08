"""Research gates: outcome-blind eligibility and scenario-specific paired feasibility."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eligibility_gate import audit_eligibility
from joint_resilience import run_paired_daily_stress


class EligibilityAuditTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"registered_at":"2026-01-01T00:00:00Z",
                     "decision_window_start":"2026-01-02T00:00:00Z",
                     "decision_window_end":"2026-01-31T23:00:00Z",
                     "predeclared_feature_names":["supplier_region","quoted_price"]}
        self.entry = {"order_id":"1", "decision_at":"2026-01-03T12:00:00Z",
                      "features":{name:{"value":value,"known_at":"2026-01-03T09:00:00Z",
                                        "source_recorded_at":"2026-01-03T10:00:00Z"}
                                  for name,value in (("supplier_region","West"),("quoted_price",100))}}
    def test_predeclared_outcome_blind_eligibility(self):
        result = audit_eligibility([self.entry], self.plan)
        self.assertEqual(result['eligible_count'], 1)
        self.assertEqual(result['ineligible_count'], 0)
        self.assertFalse(result['feature_timestamps_independently_attested'])
        self.assertNotIn('1', result['exclusion_counts'])
    def test_future_source_recording_is_ineligible(self):
        x=copy.deepcopy(self.entry)
        x['features']['quoted_price']['source_recorded_at']='2026-01-04T10:00:00Z'
        self.assertEqual(audit_eligibility([x],self.plan)['exclusion_counts']['FEATURE_RECORDED_AFTER_DECISION'],1)
    def test_after_decision_known_at_is_ineligible(self):
        x=copy.deepcopy(self.entry)
        x['features']['quoted_price']['known_at']='2026-01-04T10:00:00Z'
        self.assertEqual(audit_eligibility([x],self.plan)['eligible_count'],0)
    def test_past_or_outside_window_is_not_scored(self):
        x=copy.deepcopy(self.entry);x['decision_at']='2025-12-31T12:00:00Z'
        self.assertEqual(audit_eligibility([x],self.plan)['exclusion_counts']['OUTSIDE_PREDECLARED_WINDOW'],1)
    def test_reject_outcome_as_feature_or_top_level_label(self):
        p=copy.deepcopy(self.plan);p['predeclared_feature_names'].append('actual_delivery_date')
        with self.assertRaises(ValueError):audit_eligibility([self.entry],p)
        x=copy.deepcopy(self.entry);x['outcome']='late'
        with self.assertRaises(ValueError):audit_eligibility([x],self.plan)
    def test_reject_duplicate_and_unknown_feature(self):
        with self.assertRaises(ValueError):audit_eligibility([self.entry,self.entry],self.plan)
        x=copy.deepcopy(self.entry);x['features']['random_posthoc']=1
        self.assertEqual(audit_eligibility([x],self.plan)['exclusion_counts']['FEATURE_SCHEMA_MISSING_OR_EXTRA'],1)
    def test_reject_invalid_registration(self):
        p=copy.deepcopy(self.plan);p['registered_at']='2026-03-01T00:00:00Z'
        with self.assertRaises(ValueError):audit_eligibility([self.entry],p)

class JointStressTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=json.loads((Path(__file__).parent/'fixtures'/'FICTIONAL_DAILY_MULTICOMPONENT_PLAN.json').read_text(encoding='utf-8'))
        self.baseline={'O1':'O1-S2','O2':'O2-S2'}
    def test_paired_exact_same_shocks_and_reproducibility(self):
        a=run_paired_daily_stress(self.snapshot,self.baseline,scenarios=20,seed=9)
        self.assertEqual(a,run_paired_daily_stress(self.snapshot,self.baseline,scenarios=20,seed=9))
        self.assertEqual(len(a['paired_results']),20)
        self.assertFalse(a['supplier_switch_effect_causal'])
        self.assertEqual(a['operational_approval'],'NOT_GRANTED')
        self.assertTrue(all(r['conditional_model_cost_difference_cents'] is None or
                            r['conditional_model_cost_difference_cents']>=0 for r in a['paired_results']))
    def test_bad_baseline_rejected(self):
        with self.assertRaisesRegex(ValueError,'Baseline'):
            run_paired_daily_stress(self.snapshot, {'O1':'O1-S1'},scenarios=4)
        with self.assertRaisesRegex(ValueError,'Baseline'):
            run_paired_daily_stress(self.snapshot, {'O1':'O2-S1','O2':'O2-S2'},scenarios=4)
    def test_counted_only_comparable_exact_pairs(self):
        r=run_paired_daily_stress(self.snapshot,self.baseline,scenarios=25,seed=4)
        self.assertLessEqual(r['comparable_exact_pairs'],r['fixed_baseline_exact_feasible_count'])
        self.assertLessEqual(r['comparable_exact_pairs'],r['reoptimized_exact_feasible_count'])
        self.assertEqual(r['hypothetical_cost_delta_cents_on_comparable_pairs'],sum(
            x['conditional_model_cost_difference_cents'] or 0 for x in r['paired_results']))
    def test_no_snapshot_mutation(self):
        x=copy.deepcopy(self.snapshot)
        run_paired_daily_stress(x,self.baseline,scenarios=2)
        self.assertEqual(x,self.snapshot)
    def test_invalid_scenario_count_rejected(self):
        with self.assertRaises(ValueError):run_paired_daily_stress(self.snapshot,self.baseline,scenarios=0)
        with self.assertRaises(ValueError):run_paired_daily_stress(self.snapshot,self.baseline,scenarios=501)

if __name__=='__main__':unittest.main()
