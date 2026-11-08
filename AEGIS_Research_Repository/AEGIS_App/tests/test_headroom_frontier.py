import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from headroom_frontier import evaluate_reserve_frontier

class HeadroomFrontierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot=json.loads((Path(__file__).parent/'fixtures'/'FICTIONAL_DAILY_MULTICOMPONENT_PLAN.json').read_text(encoding='utf-8'))
    def test_dynamic_policy_not_fixed_ai_five_cost_policy(self):
        r=evaluate_reserve_frontier(self.snapshot,reserve_levels=(0,20,40),maximum_extra_modeled_cost_cents=200)
        self.assertEqual(r['status'],'EXACT_GRID_CONSTRAINED_RESEARCH_ONLY')
        self.assertEqual(r['baseline_modeled_cost_cents'],800)
        self.assertGreater(r['selected']['minimum_unused_capacity_percent_declared'],0)
        self.assertFalse(r['legacy_ai_plus_five_quoted_cost_allowance_is_capacity'])
        self.assertFalse(r['actual_resilience_benefit_proven'])
    def test_cost_ceiling_enforced(self):
        r=evaluate_reserve_frontier(self.snapshot,reserve_levels=(0,20,40),maximum_extra_modeled_cost_cents=0)
        self.assertLessEqual(r['selected']['modeled_cost_cents'],800)
        self.assertEqual(r['permitted_business_action'],'NONE')
    def test_no_exact_reference_fails_closed(self):
        r=evaluate_reserve_frontier(self.snapshot,reserve_levels=(0,10),max_nodes=1)
        self.assertEqual(r['status'],'NO_EXACT_REFERENCE')
        self.assertIsNone(r['selected'])
    def test_reserve_levels_validation(self):
        for invalid in ((20,40),(0,10,10),(-1,0),(0,100)):
            with self.assertRaises(ValueError):evaluate_reserve_frontier(self.snapshot,reserve_levels=invalid)
        with self.assertRaises(ValueError):evaluate_reserve_frontier(self.snapshot,maximum_extra_modeled_cost_cents=-1)

if __name__=='__main__':unittest.main()
