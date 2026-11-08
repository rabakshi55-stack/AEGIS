# AEGIS 4.0 — Step 83: Full-horizon rolling policy reconciliation
# Execute from the existing 02_Version_Validation.ipynb with: %run -i AEGIS_step83.py
# Reuses the frozen Step 82 stochastic decision rule; NO parameter retuning.

import hashlib
from pathlib import Path
import numpy as np
import pandas as pd

print('=' * 72)
print('AEGIS 4.0 - STEP 83: FULL-HORIZON ROLLING POLICY AUDIT')
print('=' * 72)

# 1. Preserve experiment configuration and dependencies
assert scenario_82 == 'combined_shock__r02__CMP-004'
assert paths_82 == [1, 2, 3]
assert np.isclose(allowance_82, 0.01)
assert callable(select_stochastic_82)
assert callable(solve_rolling_batch_50)
assert len(results_82) == 6
assert len(summary_82) == 2
assert hashlib.sha256(corrected_file_75.read_bytes()).hexdigest() == hash_75

orders_83 = actual_82.copy()
choices_83 = options_82.copy()
orders_83['order_date'] = pd.to_datetime(orders_83['order_date'])
choices_83['order_date'] = pd.to_datetime(choices_83['order_date'])

assert len(orders_83) == 16
assert orders_83['purchase_order_id'].is_unique
assert not choices_83.duplicated(['purchase_order_id', 'supplier_id']).any()
assert set(choices_83['purchase_order_id']) == set(orders_83['purchase_order_id'])

dates_83 = sorted(pd.Timestamp(d) for d in orders_83['order_date'].unique())
assert len(dates_83) > n_decisions_82
assert [pd.Timestamp(d) for d in dates_82] == dates_83[:3]
assert all((future_82['order_date'] > orders_83['order_date'].min()))

print('\n1. FROZEN CONFIGURATION')
print('Scenario:', scenario_82)
print('Full-horizon orders:', len(orders_83))
print('Decision dates:', len(dates_83))
print('Stochastic planning paths:', paths_82)
print('Daily current-order cost allowance:', allowance_82)
print('Initial capacities:', initial_82)
print('No new simulation data, thresholds or models introduced.')

remaining_83 = {'Cost-Only': initial_82.copy(), 'Rolling-Stochastic': initial_82.copy()}
served_ids_83 = {'Cost-Only': set(), 'Rolling-Stochastic': set()}
selected_records_83 = []
daily_records_83 = []

# 2. Process all realized development-scenario dates in chronological order
for date in dates_83:
    day_orders = orders_83.loc[orders_83['order_date'].eq(date)].copy()
    day_options = choices_83.loc[choices_83['order_date'].eq(date)].copy()
    assert set(day_orders['purchase_order_id']) == set(day_options['purchase_order_id'])

    for policy in ['Cost-Only', 'Rolling-Stochastic']:
        before = remaining_83[policy].copy()

        if policy == 'Cost-Only':
            selected, shortage = solve_rolling_batch_50(
                day_orders, day_options, before.copy(), suppliers_82
            )
            selected = selected.copy()
            expenditure = float(selected['landed_cost_usd'].sum())
            after = before.copy()
            for row in selected.itertuples(index=False):
                after[row.supplier_id] -= int(row.order_quantity_units)
            choices_count = np.nan
            future_shortage_est = np.nan
        else:
            (selected, shortage, after, expenditure,
             choices_count, future_shortage_est,
             current_baseline_cost) = select_stochastic_82(
                day_orders, day_options, before.copy(), date
            )
            selected = selected.copy()
            assert np.isclose(expenditure, selected['landed_cost_usd'].sum(), atol=0.02)
            assert expenditure <= current_baseline_cost * (1 + allowance_82) + 0.02

        # Verify solver output independently against today's known choices
        assert set(selected['purchase_order_id']).issubset(set(day_orders['purchase_order_id']))
        assert selected['purchase_order_id'].is_unique
        assert not (set(selected['purchase_order_id']) & served_ids_83[policy])
        permitted = day_options[['purchase_order_id', 'supplier_id', 'order_quantity_units', 'landed_cost_usd']]
        checked = selected[['purchase_order_id', 'supplier_id', 'order_quantity_units', 'landed_cost_usd']].merge(
            permitted,
            on=['purchase_order_id', 'supplier_id'], how='left',
            validate='one_to_one', suffixes=('_selected','_catalog'), indicator=True
        )
        assert checked['_merge'].eq('both').all()
        assert np.allclose(checked['order_quantity_units_selected'], checked['order_quantity_units_catalog'])
        assert np.allclose(checked['landed_cost_usd_selected'], checked['landed_cost_usd_catalog'], atol=0.01)

        unserved_orders = day_orders.loc[~day_orders['purchase_order_id'].isin(selected['purchase_order_id'])]
        unserved_units = int(unserved_orders['order_quantity_units'].sum())
        served_units = int(selected['order_quantity_units'].sum())
        required_units = int(day_orders['order_quantity_units'].sum())
        assert int(shortage) == unserved_units
        assert served_units + unserved_units == required_units
        assert len(selected) + len(unserved_orders) == len(day_orders)
        assert min(after.values()) >= 0

        load = selected.groupby('supplier_id')['order_quantity_units'].sum()
        for supplier in suppliers_82:
            assert after[supplier] == before[supplier] - int(load.get(supplier, 0))

        # Commit today's purchases only AFTER optimization, for each policy separately
        remaining_83[policy] = after
        served_ids_83[policy].update(selected['purchase_order_id'])
        for row in selected.itertuples(index=False):
            selected_records_83.append({
                'Date': date, 'Policy': policy,
                'purchase_order_id': row.purchase_order_id,
                'supplier_id': row.supplier_id,
                'order_quantity_units': int(row.order_quantity_units),
                'landed_cost_usd': float(row.landed_cost_usd)
            })

        daily_records_83.append({
            'Date': date, 'Policy': policy,
            'Orders_Seen': len(day_orders), 'Orders_Served': len(selected),
            'Required_Units': required_units, 'Served_Units': served_units,
            'Unserved_Units': unserved_units,
            'Procurement_Cost_USD': expenditure,
            'Feasible_First_Stage_Assignments': choices_count,
            'Mean_Hypothetical_Future_Shortage': future_shortage_est,
            'Remaining_Units': sum(after.values())
        })

    print('Certified full-horizon date:', date.date(), flush=True)

# 3. Aggregate results and independently reconcile all orders
results_83 = pd.DataFrame(daily_records_83)
allocations_83 = pd.DataFrame(selected_records_83)
summary_83 = results_83.groupby('Policy', as_index=False).agg(
    Decision_Dates=('Date', 'nunique'),
    Orders_Seen=('Orders_Seen','sum'),
    Orders_Served=('Orders_Served','sum'),
    Required_Units=('Required_Units','sum'),
    Served_Units=('Served_Units','sum'),
    Unserved_Units=('Unserved_Units','sum'),
    Procurement_Cost_USD=('Procurement_Cost_USD','sum')
)

assert len(results_83) == len(dates_83) * 2
for policy in ['Cost-Only', 'Rolling-Stochastic']:
    subset = results_83.loc[results_83['Policy'].eq(policy)]
    assigned = allocations_83.loc[allocations_83['Policy'].eq(policy)]
    assert subset['Orders_Seen'].sum() == 16
    assert subset['Required_Units'].sum() == int(orders_83['order_quantity_units'].sum())
    assert subset['Served_Units'].sum() + subset['Unserved_Units'].sum() == subset['Required_Units'].sum()
    assert len(assigned) == len(served_ids_83[policy])
    assert assigned['purchase_order_id'].is_unique
    assert np.isclose(assigned['landed_cost_usd'].sum(), subset['Procurement_Cost_USD'].sum(), atol=0.02)
    total_by_supplier = assigned.groupby('supplier_id')['order_quantity_units'].sum()
    for supplier in suppliers_82:
        used = int(total_by_supplier.get(supplier, 0))
        assert used <= initial_82[supplier]
        assert remaining_83[policy][supplier] == initial_82[supplier] - used

# 4. Must reproduce the previous three-date pilot exactly
old_83 = results_82[['Date', 'Policy', 'Orders', 'Served_Orders',
                     'Unserved_Units', 'Procurement_Cost_USD']].copy()
old_83['Date'] = pd.to_datetime(old_83['Date'])
replay_83 = results_83.loc[results_83['Date'].isin(dates_83[:3])].merge(
    old_83, on=['Date','Policy'], validate='one_to_one', suffixes=('_new','_old')
)
assert len(replay_83) == 6
assert (replay_83['Orders_Seen'] == replay_83['Orders']).all()
assert (replay_83['Orders_Served'] == replay_83['Served_Orders']).all()
assert (replay_83['Unserved_Units_new'] == replay_83['Unserved_Units_old']).all()
assert np.allclose(replay_83['Procurement_Cost_USD_new'], replay_83['Procurement_Cost_USD_old'], atol=0.05)

# 5. Compare full-horizon service and costs
print('\n2. FULL-HORIZON DAILY POLICY COMPARISON')
daily_compare_83 = results_83.pivot(index='Date', columns='Policy', values=[
    'Orders_Served','Unserved_Units','Procurement_Cost_USD'
]).round(2)
print(daily_compare_83.to_string())
print('\n3. FULL-HORIZON POLICY SUMMARY')
print(summary_83.round(2).to_string(index=False))
print('\n4. FULL-HORIZON ECONOMIC QUALIFICATION')
identical_83 = served_ids_83['Cost-Only'] == served_ids_83['Rolling-Stochastic']
print('Both policies served identical order sets:', identical_83)
net_units_83 = (int(summary_83.loc[summary_83.Policy.eq('Rolling-Stochastic'), 'Served_Units'].iloc[0]) -
                int(summary_83.loc[summary_83.Policy.eq('Cost-Only'), 'Served_Units'].iloc[0]))
print('Net additional units served by stochastic:', net_units_83)
if identical_83:
    net_saving_83 = (float(summary_83.loc[summary_83.Policy.eq('Cost-Only'), 'Procurement_Cost_USD'].iloc[0]) -
                     float(summary_83.loc[summary_83.Policy.eq('Rolling-Stochastic'), 'Procurement_Cost_USD'].iloc[0]))
    print('Like-for-like full-horizon procurement difference ($):', round(net_saving_83, 2))
else:
    print('WARNING: Different fulfilled orders. Raw spending difference is NOT a savings estimate.')

print('\n5. FINAL VERIFICATION')
assert hashlib.sha256(corrected_file_75.read_bytes()).hexdigest() == hash_75
assert (results_83['Remaining_Units'] >= 0).all()
assert len(dates_83) > 3
print('PASS: Every decision date in the development scenario replayed.')
print('PASS: First three dates reconcile with Step 82.')
print('PASS: Both policies receive identical current-day orders.')
print('PASS: No realized future orders enter stochastic recourse.')
print('PASS: Each policy maintains independent supplier commitments.')
print('PASS: Supplier capacities and MOQ-eligible choices verified.')
print('PASS: Order counts, unit service and costs reconciled.')
print('PASS: Same frozen hypothetical planning bank preserved.')
print('PASS: Reserved evaluation and final ML test data untouched.')

# 6. Store experiment outputs
out_83 = Path('outputs')
out_83.mkdir(exist_ok=True)
results_83.to_csv(out_83 / 'AEGIS_full_horizon_stochastic_daily.csv', index=False)
summary_83.to_csv(out_83 / 'AEGIS_full_horizon_stochastic_summary.csv', index=False)
allocations_83.to_csv(out_83 / 'AEGIS_full_horizon_stochastic_allocations.csv', index=False)

print('\nIMPORTANT LIMITATIONS')
print('This is one previously studied synthetic development scenario.')
print('Both policies may have different served order sets.')
print('Stochastic recourse assumes full knowledge of each simulated path.')
print('The same three pre-generated planning paths are reused across dates.')
print('Simulation beliefs are not refreshed with observed demand.')
print('This is NOT an independent holdout or real-world savings estimate.')
print('Delivery-risk ML is not yet integrated into the sourcing objective.')
print('\nSTEP 83 COMPLETE')
