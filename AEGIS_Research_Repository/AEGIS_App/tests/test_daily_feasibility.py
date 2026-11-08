"""Fictional daily multi-item, route and capacity tests; not real-world certification."""
from copy import deepcopy
import unittest
from daily_feasibility import verify_and_optimize_plan

NOW='2026-11-07T09:00:00+05:30'
END='2026-11-08T20:00:00+05:30'
DAY='2026-11-08'

def sample():
    resources=[]
    for rid,kind,owner,cap,committed in [
        ('A-S1','SUPPLIER_ITEM_DAY','S1|A',5,0),('B-S1','SUPPLIER_ITEM_DAY','S1|B',5,0),
        ('A-S2','SUPPLIER_ITEM_DAY','S2|A',5,0),('B-S2','SUPPLIER_ITEM_DAY','S2|B',5,0),
        ('ROUTE-S1','ROUTE_DAY','R1',8,0),('ROUTE-S2','ROUTE_DAY','R2',8,0),
        ('SHARED-S1','SHARED_COMPONENT_POOL_DAY','production-line-1',6,2)]:
        resources.append({'resource_id':rid,'kind':kind,'owner_id':owner,'available_units':cap,
            'already_committed_units':committed,'date':DAY,'recorded_at':NOW,'valid_until':END})
    orders=[{'order_id':i,'item_id':item,'plant_id':'PL','units':3,'required_by':'2026-11-09'} for i,item in [('O1','A'),('O2','B')]]
    options=[]
    for i,item in [('O1','A'),('O2','B')]:
        for supplier,route in [('S1','R1'),('S2','R2')]:
            req=[{'resource_id':f'{item}-{supplier}','units_per_order_unit':1},
                 {'resource_id':f'ROUTE-{supplier}','units_per_order_unit':1}]
            if supplier=='S1':req.append({'resource_id':'SHARED-S1','units_per_order_unit':1})
            options.append({'option_id':f'{i}-{supplier}','order_id':i,'item_id':item,'plant_id':'PL',
                'supplier_id':supplier,'route_id':route,'ship_date':DAY,'arrival_date':'2026-11-09',
                'eligible':True,'route_eligible':True,'currency':'USD',
                'quote_recorded_at':NOW,'quote_valid_until':END,
                'cost_cents':300 if supplier=='S1' else 500,'resource_requirements':req})
    return {'decision_at':NOW,'currency':'USD','orders':orders,'resources':resources,'options':options}

class DailyFeasibilityTests(unittest.TestCase):
    def test_multi_item_shared_pool_prevents_cheapest_infeasible_combination(self):
        result=verify_and_optimize_plan(sample())
        self.assertEqual(result['status'],'EXACT_MIN_COST_UNATTESTED')
        self.assertEqual(result['cost_cents'],800)
        self.assertEqual(len(result['assignment']),2)
        self.assertEqual(sum(1 for v in result['assignment'].values() if v.endswith('S1')),1)
        self.assertEqual(result['resource_usage']['SHARED-S1']['used_units'],3)
        self.assertEqual(result['resource_usage']['SHARED-S1']['already_committed_units'],2)
        self.assertEqual(result['operational_approval'],'NOT_GRANTED')
    def test_joint_daily_route_capacity(self):
        value=sample()
        for r in value['resources']:
            if r['resource_id']=='ROUTE-S1': r['available_units']=2
        report=verify_and_optimize_plan(value)
        self.assertEqual(report['cost_cents'],1000)
        self.assertEqual(report['assignment'],{'O1':'O1-S2','O2':'O2-S2'})
    def test_quote_expiry_excludes_candidate_and_no_fabricated_fallback(self):
        value=sample()
        for o in value['options']:
            if o['order_id']=='O1':o['quote_valid_until']='2026-11-06T21:00:00+05:30'
        report=verify_and_optimize_plan(value)
        self.assertEqual(report['status'],'INFEASIBLE_NO_VALID_OPTIONS')
        self.assertIsNone(report['assignment'])
        self.assertEqual(report['uncovered_orders'],['O1'])
    def test_outcome_time_not_accepted_as_quote_or_capacity_known(self):
        value=sample()
        value['resources'][0]['recorded_at']='2026-11-09T09:00:00+05:30'
        with self.assertRaisesRegex(ValueError,'late-known capacity'):
            verify_and_optimize_plan(value)
    def test_reject_missing_route_commitment(self):
        value=sample()
        value['options'][0]['resource_requirements']=[value['options'][0]['resource_requirements'][0]]
        with self.assertRaisesRegex(ValueError,'transport route'):
            verify_and_optimize_plan(value)
    def test_stop_is_not_exact_optimality_claim(self):
        result=verify_and_optimize_plan(sample(),max_nodes=1)
        self.assertTrue(result['truncated'])
        self.assertFalse(result['exact_optimal'])
        self.assertEqual(result['status'],'NOT_PROVEN_FEASIBLE')
    def test_mismatch_supplier_and_item_rejected(self):
        value=sample();value['resources'][0]['owner_id']='S3|A'
        with self.assertRaisesRegex(ValueError,'does not match'):
            verify_and_optimize_plan(value)
    def test_currency_mismatch_rejected_without_conversion(self):
        value=sample();value['options'][0]['currency']='INR'
        with self.assertRaisesRegex(ValueError,'Cross-currency'):
            verify_and_optimize_plan(value)
    def test_deterministic_across_own_input(self):
        first=verify_and_optimize_plan(sample());second=verify_and_optimize_plan(sample())
        self.assertEqual(first,second)

if __name__ == '__main__':unittest.main()
