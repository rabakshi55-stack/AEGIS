# AEGIS 4.0 — Step 84: Full-horizon policy cost and capacity attribution
# Run from the same live notebook with: %run -i AEGIS_step84.py
# Diagnostic only. Does NOT retrain, retune, reoptimize or inspect any holdout.

from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

print('=' * 72)
print('AEGIS 4.0 - STEP 84: FULL-HORIZON COST AND CAPACITY DIAGNOSTIC')
print('=' * 72)

# 1. Verify the frozen previous experiment
assert scenario_82 == 'combined_shock__r02__CMP-004'
assert hashlib.sha256(corrected_file_75.read_bytes()).hexdigest() == hash_75
assert len(orders_83) == 16 and orders_83['purchase_order_id'].is_unique
assert len(allocations_83) == 32
assert len(results_83) == 14
assert len(summary_83) == 2

policies_84 = ['Cost-Only', 'Rolling-Stochastic']
alloc_84 = allocations_83.copy()
alloc_84['Date'] = pd.to_datetime(alloc_84['Date'])
alloc_84['order_quantity_units'] = alloc_84['order_quantity_units'].astype(int)
assert not alloc_84.duplicated(['Policy','purchase_order_id']).any()

for policy in policies_84:
    ids = set(alloc_84.loc[alloc_84['Policy'].eq(policy),'purchase_order_id'])
    assert ids == set(orders_83['purchase_order_id'])

cost_84 = (alloc_84.groupby('Policy')['landed_cost_usd'].sum()
           .reindex(policies_84))
assert np.isclose(cost_84['Cost-Only'],465535.75,atol=.02)
assert np.isclose(cost_84['Rolling-Stochastic'],468245.01,atol=.02)
net_84 = float(cost_84['Cost-Only']-cost_84['Rolling-Stochastic'])
assert np.isclose(net_84,-2709.26,atol=.02)

print('\n1. FROZEN EXPERIMENT RECONCILIATION')
print('Scenario:',scenario_82)
print('Orders served by both policies:',len(orders_83))
print('Required and served units:',int(orders_83['order_quantity_units'].sum()))
print('Cost-Only total ($):',round(cost_84['Cost-Only'],2))
print('Rolling-Stochastic total ($):',round(cost_84['Rolling-Stochastic'],2))
print('Cost-Only minus stochastic ($):',round(net_84,2))

# 2. Exact same-order cost and supplier attribution
base_84 = alloc_84.loc[alloc_84['Policy'].eq('Cost-Only')].drop(columns='Policy')
stoch_84 = alloc_84.loc[alloc_84['Policy'].eq('Rolling-Stochastic')].drop(columns='Policy')
paired_84 = base_84.merge(stoch_84,on='purchase_order_id',
                          suffixes=('_Cost','_Stochastic'),validate='one_to_one')
assert len(paired_84) == 16
assert (paired_84['Date_Cost'] == paired_84['Date_Stochastic']).all()
assert (paired_84['order_quantity_units_Cost'] == paired_84['order_quantity_units_Stochastic']).all()
paired_84['Date'] = paired_84['Date_Cost']
paired_84['Supplier_Changed'] = (paired_84['supplier_id_Cost'] != paired_84['supplier_id_Stochastic'])
paired_84['Cost_Only_Minus_Stochastic_USD'] = (
    paired_84['landed_cost_usd_Cost'] - paired_84['landed_cost_usd_Stochastic']
)
assert np.isclose(paired_84['Cost_Only_Minus_Stochastic_USD'].sum(),net_84,atol=.02)

print('\n2. MATCHED-ORDER PROCUREMENT ATTRIBUTION')
print('Different supplier assignments:',int(paired_84['Supplier_Changed'].sum()))
print('Same supplier assignments:',int((~paired_84['Supplier_Changed']).sum()))
print('Largest disadvantages for rolling stochastic:')
print(paired_84.nsmallest(7,'Cost_Only_Minus_Stochastic_USD')[
    ['Date','purchase_order_id','supplier_id_Cost','supplier_id_Stochastic',
     'order_quantity_units_Cost','Cost_Only_Minus_Stochastic_USD']
].to_string(index=False,float_format=lambda x:f'{x:.2f}'))

# 3. Date-level difference and cumulative advantage
daily_84 = paired_84.groupby('Date',as_index=False).agg(
    Orders=('purchase_order_id','size'),
    Changed_Assignments=('Supplier_Changed','sum'),
    Cost_Only_Minus_Stochastic_USD=('Cost_Only_Minus_Stochastic_USD','sum')
).sort_values('Date')
daily_84['Cumulative_Advantage_USD'] = daily_84['Cost_Only_Minus_Stochastic_USD'].cumsum()
assert len(daily_84)==7
assert np.isclose(daily_84['Cumulative_Advantage_USD'].iloc[2],289.74,atol=.02)
assert np.isclose(daily_84['Cumulative_Advantage_USD'].iloc[-1],net_84,atol=.02)
assert np.isclose(daily_84['Cost_Only_Minus_Stochastic_USD'].iloc[3:].sum(),-2999.,atol=.02)

print('\n3. DECISION-DATE COST DECOMPOSITION')
print(daily_84.to_string(index=False,float_format=lambda x:f'{x:.2f}'))

# 4. Independently rebuild capacities before AND after each date
caps_84 = []
trace_84 = []
for policy in policies_84:
    remaining = {s:int(initial_82[s]) for s in suppliers_82}
    for date in sorted(daily_84['Date'].unique()):
        selected = alloc_84.loc[alloc_84['Policy'].eq(policy) & alloc_84['Date'].eq(date)]
        loads = selected.groupby('supplier_id')['order_quantity_units'].sum().to_dict()
        for supplier in suppliers_82:
            before = remaining[supplier]
            allocated = int(loads.get(supplier,0))
            remaining[supplier] -= allocated
            assert remaining[supplier] >= 0
            caps_84.append({
                'Date':date,'Policy':policy,'Supplier':supplier,
                'Capacity_Before':before,'Allocated_Today':allocated,
                'Capacity_After':remaining[supplier]
            })
        trace_84.append({'Date':date,'Policy':policy,
                         'Remaining_Total_After':sum(remaining.values())})
    assert remaining == remaining_83[policy]

capacity_trace_84 = pd.DataFrame(caps_84)

# 5. Capacity availability on the final decision day
last_date_84 = daily_84['Date'].max()
last_cap_84 = capacity_trace_84.loc[capacity_trace_84['Date'].eq(last_date_84)]
capacity_compare_84 = last_cap_84.pivot(index='Supplier',columns='Policy',
                                         values=['Capacity_Before','Allocated_Today','Capacity_After'])
capacity_compare_84.columns = [f'{metric}_{policy}' for metric,policy in capacity_compare_84.columns]
capacity_compare_84 = capacity_compare_84.reset_index()
capacity_compare_84['Before_Cost_Minus_Stochastic'] = (
    capacity_compare_84['Capacity_Before_Cost-Only'] -
    capacity_compare_84['Capacity_Before_Rolling-Stochastic']
)

print('\n4. SUPPLIER CAPACITY ENTERING FINAL DECISION')
print('Last decision:',pd.Timestamp(last_date_84).date())
print(capacity_compare_84[
    ['Supplier','Capacity_Before_Cost-Only','Capacity_Before_Rolling-Stochastic',
     'Before_Cost_Minus_Stochastic','Allocated_Today_Cost-Only',
     'Allocated_Today_Rolling-Stochastic']
].to_string(index=False))

# 6. Compare individually feasible choices at last decision, based ONLY on
# supplier capacity before that day; simultaneous feasibility is not implied.
final_orders_84 = orders_83.loc[pd.to_datetime(orders_83['order_date']).eq(last_date_84)]
final_options_84 = choices_83.loc[pd.to_datetime(choices_83['order_date']).eq(last_date_84)].copy()
assert len(final_orders_84)==3
option_diagnostics_84=[]
for row in final_options_84.itertuples(index=False):
    for policy in policies_84:
        before = capacity_trace_84.loc[
            capacity_trace_84['Date'].eq(last_date_84) &
            capacity_trace_84['Supplier'].eq(row.supplier_id) &
            capacity_trace_84['Policy'].eq(policy), 'Capacity_Before'
        ]
        assert len(before)==1
        option_diagnostics_84.append({
            'purchase_order_id':row.purchase_order_id,'Policy':policy,
            'Supplier':row.supplier_id,'Order_Units':int(row.order_quantity_units),
            'Capacity_Before':int(before.iloc[0]),
            'Individually_Fits':bool(row.order_quantity_units<=int(before.iloc[0])),
            'Landed_Cost_USD':float(row.landed_cost_usd)
        })
option_df_84=pd.DataFrame(option_diagnostics_84)
print('\n5. FINAL-DATE INDIVIDUAL OPTION AVAILABILITY')
print('These options are checked individually, not as a joint allocation.')
print(option_df_84.sort_values(['purchase_order_id','Policy','Landed_Cost_USD'])
      .to_string(index=False,float_format=lambda x:f'{x:.2f}'))

# 7. Integrity + reproducible outputs
assert np.isclose(daily_84['Cost_Only_Minus_Stochastic_USD'].sum(),-2709.26,atol=.02)
assert len(capacity_trace_84)==2*7*len(suppliers_82)
assert (capacity_trace_84['Allocated_Today']>=0).all()
assert (capacity_trace_84['Capacity_Before']>=capacity_trace_84['Allocated_Today']).all()
assert (capacity_trace_84['Capacity_After']>=0).all()
assert not option_df_84.duplicated(['purchase_order_id','Policy','Supplier']).any()
assert hashlib.sha256(corrected_file_75.read_bytes()).hexdigest()==hash_75

output_84=Path('outputs')
output_84.mkdir(exist_ok=True)
paired_84.to_csv(output_84/'AEGIS_step84_order_cost_attribution.csv',index=False)
daily_84.to_csv(output_84/'AEGIS_step84_daily_cost_attribution.csv',index=False)
capacity_trace_84.to_csv(output_84/'AEGIS_step84_supplier_capacity_trace.csv',index=False)
option_df_84.to_csv(output_84/'AEGIS_step84_final_date_options.csv',index=False)

print('\n6. FINAL VERIFICATION')
print('PASS: All 16 purchase orders matched exactly.')
print('PASS: Full-horizon cost difference reconciled.')
print('PASS: First-three-date and last-four-date changes reconciled.')
print('PASS: Supplier capacity reconstructed chronologically.')
print('PASS: Final-date option and capacity snapshots prepared.')
print('PASS: No new supplier allocations optimized.')
print('PASS: Original planning bank unchanged.')
print('PASS: No reserved holdout or final ML test accessed.')
print('\nLIMITATIONS')
print('This is a retrospective synthetic development-case attribution.')
print('Different capacity states can change daily feasible allocations.')
print('Individual option feasibility does not imply joint feasibility.')
print('Attribution does not establish causal policy superiority.')
print('No stochastic probabilities, constraints or policies retuned.')
print('\nSTEP 84 COMPLETE')
