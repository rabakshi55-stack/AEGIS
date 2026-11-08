"""Exact synthetic joint-capacity assignment tests; no real-world claims."""
import itertools
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from joint_capacity import solve_whole_order_assignment


def toy():
    quantities={'A':4,'B':3,'C':5}
    capacities={'X':7,'Y':10}
    candidates={
        'A':[{'supplier':'X','cost':40,'baseline':True},{'supplier':'Y','cost':49,'baseline':False}],
        'B':[{'supplier':'X','cost':25,'baseline':False},{'supplier':'Y','cost':37,'baseline':True}],
        'C':[{'supplier':'X','cost':42,'baseline':False},{'supplier':'Y','cost':56,'baseline':True}],
    }
    return quantities,capacities,candidates

class JointCapacityTests(unittest.TestCase):
    def test_exact_matches_bruteforce_and_capacity(self):
        quantities,capacities,candidates=toy()
        result=solve_whole_order_assignment(quantities,capacities,candidates)
        possible=[]
        for values in itertools.product(('X','Y'),repeat=3):
            selection=dict(zip(('A','B','C'),values))
            usage={s:sum(quantities[o] for o,v in selection.items() if v==s) for s in capacities}
            if all(usage[s]<=capacities[s] for s in capacities):
                possible.append(sum(next(r['cost'] for r in candidates[o] if r['supplier']==s) for o,s in selection.items()))
        self.assertTrue(result['exact_optimal'])
        self.assertEqual(result['solution_cost_cents'],min(possible))
        self.assertEqual(sum(row['assigned_units'] for row in result['capacity_by_supplier'].values()),12)

    def test_baseline_overcapacity_not_used_as_incumbent(self):
        quantities, capacities, candidates=toy()
        for entries in candidates.values():
            for r in entries:r['baseline']=r['supplier']=='X'
        result=solve_whole_order_assignment(quantities,capacities,candidates)
        self.assertFalse(result['baseline_feasible'])
        self.assertTrue(result['exact_optimal'])

    def test_infeasible_reports_no_solution(self):
        quantities,capacities,candidates=toy()
        capacities={'X':3,'Y':4}
        result=solve_whole_order_assignment(quantities,capacities,candidates)
        self.assertFalse(result['exact_optimal'])
        self.assertIsNone(result['assignment'])
        self.assertEqual(result['status'],'INFEASIBLE_WITH_CURRENT_MONTHLY_CONSTRAINTS')

    def test_truncated_run_never_claims_optimality(self):
        quantities,capacities,candidates=toy()
        result=solve_whole_order_assignment(quantities,capacities,candidates,max_nodes=1)
        self.assertFalse(result['exact_optimal'])
        self.assertTrue(result['truncated'])

    def test_reject_invalid_inputs(self):
        quantities,capacities,candidates=toy()
        with self.assertRaises(ValueError):
            solve_whole_order_assignment({'A':float('nan')},capacities,{'A':candidates['A']})
        with self.assertRaises(ValueError):
            solve_whole_order_assignment(quantities,capacities,candidates,max_nodes=0)
        bad={k:[r.copy() for r in v] for k,v in candidates.items()}
        bad['A'][0]['cost']=-1
        with self.assertRaises(ValueError):
            solve_whole_order_assignment(quantities,capacities,bad)

if __name__=='__main__':unittest.main()
