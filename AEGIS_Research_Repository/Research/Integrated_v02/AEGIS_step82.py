# AEGIS 4.0 | Step 82 — Rolling stochastic proof of concept
# Run in existing notebook as a cell, or use %run -i AEGIS_step82.py
import numpy as np
import pandas as pd
from pathlib import Path
from itertools import product
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import lil_matrix
import hashlib

print('=' * 70)
print('AEGIS 4.0 — STEP 82: REPEATED STOCHASTIC DECISION PILOT')
print('=' * 70)

# Fixed design: same development scenario and three hypothetical planning paths
scenario_82 = 'combined_shock__r02__CMP-004'
paths_82 = [1, 2, 3]
n_decisions_82 = 3
allowance_82 = 0.01
assert scenario_78 == scenario_82
assert hashlib.sha256(corrected_file_75.read_bytes()).hexdigest() == hash_75
assert callable(solve_rolling_batch_50)

actual_82 = orders_70.loc[orders_70['scenario_id'] == scenario_82].copy()
options_82 = choices_70.loc[choices_70['scenario_id'] == scenario_82].copy()
actual_82['order_date'] = pd.to_datetime(actual_82['order_date'])
options_82['order_date'] = pd.to_datetime(options_82['order_date'])

future_82 = future_all_80.loc[future_all_80['Path_ID'].isin(paths_82)].copy()
future_options_82 = options_all_80.loc[options_all_80['Path_ID'].isin(paths_82)].copy()
future_82['order_date'] = pd.to_datetime(future_82['order_date'])
future_options_82['order_date'] = pd.to_datetime(future_options_82['order_date'])
assert all(future_82['order_date'] > actual_82['order_date'].min())
assert set(future_82['Future_Order_ID']) == set(future_options_82['Future_Order_ID'])

dates_82 = sorted(actual_82['order_date'].unique())[:n_decisions_82]
assert len(dates_82) == n_decisions_82
initial_82 = capacity_70.loc[capacity_70['scenario_id'] == scenario_82].set_index('supplier_id')['Stressed_Capacity'].astype(int).to_dict()
suppliers_82 = sorted(initial_82)

print('\n1. FIXED CONFIGURATION')
print('Scenario:', scenario_82)
print('Decision dates:', [str(pd.Timestamp(d).date()) for d in dates_82])
print('Hypothetical paths:', paths_82)
print('Original capacity:', initial_82)
print('Daily premium allowance:', allowance_82)
print('No test or reserved holdout used')

# Exact full-path recourse at each decision state: planning approximation only.
# Important: future_82 contains *simulated* orders, not true later actual_82 orders.
def recourse_82(path_id, as_of, residual):
    fo = future_82.loc[(future_82['Path_ID'] == path_id) & (future_82['order_date'] > as_of)].reset_index(drop=True)
    if len(fo) == 0:
        return 0, 0.0
    fc = future_options_82.loc[
        (future_options_82['Path_ID'] == path_id) & (future_options_82['order_date'] > as_of)
    ].reset_index(drop=True)
    assert set(fo['Future_Order_ID']) == set(fc['Future_Order_ID'])
    assert not fc.duplicated(['Future_Order_ID', 'supplier_id']).any()

    n, k = len(fo), len(fc)
    orders_map = {v: i for i, v in enumerate(fo['Future_Order_ID'])}
    supplier_map = {s: i for i, s in enumerate(suppliers_82)}
    A = lil_matrix((n + len(suppliers_82), k + n), dtype=float)
    for j, r in enumerate(fc.itertuples(index=False)):
        A[orders_map[r.Future_Order_ID], j] = 1
        A[n + supplier_map[r.supplier_id], j] = r.order_quantity_units
    for i in range(n):
        A[i, k + i] = 1

    q = fo['order_quantity_units'].to_numpy(dtype=float)
    obj_service = np.r_[np.zeros(k), q]
    obj_cost = np.r_[fc['landed_cost_usd'].to_numpy(dtype=float) / 1000.0, np.zeros(n)]
    ub = np.r_[
        (fc['order_quantity_units'].to_numpy() <= fc['supplier_id'].map(residual).to_numpy()).astype(float),
        np.ones(n)
    ]
    common = LinearConstraint(
        A.tocsr(),
        np.r_[np.ones(n), np.zeros(len(suppliers_82))],
        np.r_[np.ones(n), [residual[s] for s in suppliers_82]]
    )
    kw = dict(integrality=np.ones(k + n, dtype=int), bounds=Bounds(np.zeros(k + n), ub),
              options={'time_limit': 90, 'mip_rel_gap': 1e-8, 'presolve': True})
    s1 = milp(c=obj_service, constraints=[common], **kw)
    if s1.status != 0 or s1.mip_gap is None or s1.mip_gap > 1e-6:
        raise RuntimeError(f'Path {path_id} service did not certify optimality: {s1.message}')
    missed = int(round(s1.fun))
    assert np.isclose(s1.fun, missed, atol=1e-5)
    s2 = milp(c=obj_cost, constraints=[common, LinearConstraint(obj_service.reshape(1,-1), missed, missed)], **kw)
    if s2.status != 0 or s2.mip_gap is None or s2.mip_gap > 1e-6:
        raise RuntimeError(f'Path {path_id} cost did not certify optimality: {s2.message}')
    selected = fc.loc[s2.x[:k] > 0.5]
    missed_from_rows = int(fo.loc[~fo['Future_Order_ID'].isin(selected['Future_Order_ID']), 'order_quantity_units'].sum())
    assert missed_from_rows == missed
    for s in suppliers_82:
        assert selected.loc[selected['supplier_id'].eq(s), 'order_quantity_units'].sum() <= residual[s]
    expected_cost = float(selected['landed_cost_usd'].sum())
    assert np.isclose(s2.fun * 1000, expected_cost, atol=0.05)
    return missed, expected_cost

# Use cache because multiple assignments can leave identical residual capacity.
recourse_cache_82 = {}
def cached_recourse_82(path_id, as_of, residual):
    key = (path_id, pd.Timestamp(as_of).isoformat(), tuple(int(residual[s]) for s in suppliers_82))
    if key not in recourse_cache_82:
        recourse_cache_82[key] = recourse_82(path_id, pd.Timestamp(as_of), residual)
    return recourse_cache_82[key]

def select_stochastic_82(today, options, remaining, as_of):
    baseline, min_shortage = solve_rolling_batch_50(today, options, remaining.copy(), suppliers_82)
    baseline_cost = float(baseline['landed_cost_usd'].sum())
    budget = baseline_cost * (1 + allowance_82) + 0.01

    today = today.sort_values('purchase_order_id')
    options = options.reset_index(drop=True)
    ids = today['purchase_order_id'].tolist()
    q_map = today.set_index('purchase_order_id')['order_quantity_units'].to_dict()
    choices = [options.index[options['purchase_order_id'].eq(oid)].tolist() + [None] for oid in ids]
    valid = []
    for combo in product(*choices):
        shortage = sum(int(q_map[oid]) for oid, ix in zip(ids, combo) if ix is None)
        if shortage != int(min_shortage):
            continue
        indices = [ix for ix in combo if ix is not None]
        picked = options.loc[indices].copy()
        cost = float(picked['landed_cost_usd'].sum())
        if cost > budget + 1e-7:
            continue
        load = picked.groupby('supplier_id')['order_quantity_units'].sum().to_dict()
        remaining_after = {s: remaining[s] - int(load.get(s, 0)) for s in suppliers_82}
        if min(remaining_after.values()) < 0:
            continue
        path_outcomes = [cached_recourse_82(pid, as_of, remaining_after) for pid in paths_82]
        future_missed = sum(out[0] for out in path_outcomes)
        future_cost = sum(out[1] for out in path_outcomes) / len(paths_82)
        signature = tuple('UNSERVED' if ix is None else str(options.loc[ix, 'supplier_id']) for ix in combo)
        valid.append((future_missed, cost + future_cost, signature, picked, remaining_after, cost))
    assert valid, 'No feasible candidate preserving current service and budget'
    valid.sort(key=lambda c: (c[0], c[1], c[2]))
    winner = valid[0]
    assert winner[5] <= budget + 0.01
    return winner[3], min_shortage, winner[4], winner[5], len(valid), winner[0] / len(paths_82), baseline_cost

remaining_by_policy_82 = {'Cost-Only': initial_82.copy(), 'Rolling-Stochastic': initial_82.copy()}
records_82 = []
served_ids_82 = {'Cost-Only': set(), 'Rolling-Stochastic': set()}

for d in dates_82:
    date = pd.Timestamp(d)
    todays = actual_82.loc[actual_82['order_date'].eq(date)].copy()
    todays_opts = options_82.loc[options_82['order_date'].eq(date)].copy()
    assert set(todays_opts['purchase_order_id']) == set(todays['purchase_order_id'])

    for policy in ['Cost-Only', 'Rolling-Stochastic']:
        before = remaining_by_policy_82[policy].copy()
        if policy == 'Cost-Only':
            selected, shortage = solve_rolling_batch_50(todays, todays_opts, before.copy(), suppliers_82)
            cost = float(selected['landed_cost_usd'].sum())
            capacity_after = before.copy()
            for r in selected.itertuples(index=False):
                capacity_after[r.supplier_id] -= int(r.order_quantity_units)
            choices_count, planning_risk = None, None
        else:
            selected, shortage, capacity_after, cost, choices_count, planning_risk, baseline_cost = select_stochastic_82(
                todays, todays_opts, before, date
            )
        assert min(capacity_after.values()) >= 0
        assert int(shortage) == int(todays.loc[~todays['purchase_order_id'].isin(selected['purchase_order_id']), 'order_quantity_units'].sum())
        assert selected['purchase_order_id'].is_unique
        assert not (served_ids_82[policy] & set(selected['purchase_order_id']))
        served_ids_82[policy].update(selected['purchase_order_id'])
        remaining_by_policy_82[policy] = capacity_after
        records_82.append({
            'Date': date, 'Policy': policy, 'Orders': len(todays), 'Served_Orders': len(selected),
            'Unserved_Units': int(shortage), 'Procurement_Cost_USD': cost,
            'Feasible_First_Stage_Assignments': choices_count,
            'Mean_Hypothetical_Future_Shortage': planning_risk,
            'Remaining_Units': sum(capacity_after.values())
        })
    print('Certified decision date:', str(date.date()), flush=True)

results_82 = pd.DataFrame(records_82)
summary_82 = results_82.groupby('Policy', as_index=False).agg(
    Decision_Dates=('Date','nunique'), Orders_Seen=('Orders','sum'),
    Served_Orders=('Served_Orders','sum'), Unserved_Units=('Unserved_Units','sum'),
    Procurement_Cost_USD=('Procurement_Cost_USD','sum')
)
print('\n2. CHRONOLOGICAL PILOT RESULT')
print(results_82.round(3).to_string(index=False))
print('\n3. THREE-DATE POLICY SUMMARY')
print(summary_82.round(2).to_string(index=False))

same_served_82 = served_ids_82['Cost-Only'] == served_ids_82['Rolling-Stochastic']
print('\n4. COST COMPARABILITY')
print('Both policies served identical orders:', same_served_82)
if same_served_82:
    saved = float(summary_82.loc[summary_82.Policy.eq('Cost-Only'), 'Procurement_Cost_USD'].iloc[0] -
                  summary_82.loc[summary_82.Policy.eq('Rolling-Stochastic'), 'Procurement_Cost_USD'].iloc[0])
    print('Cost-Only minus rolling stochastic procurement ($):', round(saved, 2))
else:
    print('Different served-order sets: do not interpret raw cost differences as savings')
assert len(results_82) == n_decisions_82 * 2
assert (results_82['Unserved_Units'] >= 0).all()
assert (results_82['Remaining_Units'] >= 0).all()
assert hashlib.sha256(corrected_file_75.read_bytes()).hexdigest() == hash_75

out_82 = Path('outputs')
out_82.mkdir(exist_ok=True)
results_82.to_csv(out_82 / 'AEGIS_repeated_stochastic_three_dates.csv', index=False)
summary_82.to_csv(out_82 / 'AEGIS_repeated_stochastic_pilot_summary.csv', index=False)
print('\nPASS: First three current-day batches replayed for both policies')
print('PASS: Service-first, budget-constrained stochastic decisions')
print('PASS: Both policies commit capacity chronologically')
print('PASS: Simulated future paths contain no realized future orders')
print('PASS: No reserved evaluation scenarios or ML test data used')
print('LIMITATION: In-sample development pilot; stochastic recourse is full-path informed')
print('LIMITATION: Same pre-generated hypothetical paths are reused at later dates')
print('LIMITATION: Only three dates tested; no delivery-risk ML integrated yet')
print('\nSTEP 82 COMPLETE')
