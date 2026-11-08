"""Independent verification of AEGIS v0.2 outputs; no generated values assumed correct."""
from pathlib import Path
from datetime import timedelta
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
D=ROOT/'data'
read=lambda name: pd.read_csv(D/name)
orders=read('purchase_orders.csv')
stock=read('component_inventory_monthly.csv')
options=read('supplier_component_options.csv')
lanes=read('transport_lanes.csv')
demand=read('customer_demand_daily.csv')
bom=read('bill_of_materials.csv')
wh=read('warehouses.csv')
sup=read('suppliers.csv')
print('AEGIS 4.0 v0.2 -- INDEPENDENT DATA VERIFICATION')
print('='*61)

# Identity, links, source capacity and economic terms.
assert orders.purchase_order_id.is_unique
assert stock[['month','plant_id','component_id']].duplicated().sum()==0
assert orders.notna().all().all()
assert ((orders.late_receipt_flag==0)|(orders.late_receipt_flag==1)).all()
assert set(orders.supplier_id).issubset(set(sup.supplier_id))
opts=options[['supplier_id','component_id','minimum_order_qty','monthly_capacity_units','quoted_unit_cost_usd','promised_lead_days']]
m=orders.merge(opts,how='left',on=['supplier_id','component_id'],validate='many_to_one',suffixes=('','_catalog'),indicator=True)
assert m._merge.eq('both').all()
assert (m.order_quantity_units>=m.minimum_order_qty).all()
assert (m.quoted_unit_cost_usd==m.quoted_unit_cost_usd_catalog).all()
lan=lanes[lanes.origin_type.eq('supplier')][['lane_id','origin_id','destination_id','transit_days']]
m=m.merge(lan,on='lane_id',validate='many_to_one')
assert (m.origin_id==m.supplier_id).all() and (m.destination_id==m.plant_id).all()
assert (m.promised_lead_days==m.promised_lead_days_catalog+m.transit_days).all()
orders['order_month']=orders.order_date.str[:7]
cap=m.assign(order_month=m.order_date.str[:7]).groupby(['supplier_id','component_id','order_month'],as_index=False).agg(
        monthly_booked=('order_quantity_units','sum'),monthly_capacity=('monthly_capacity_units','first'))
assert (cap.monthly_booked<=cap.monthly_capacity).all()
print('PASS: Uniqueness, catalog, supplier-lane relationships, MOQ, price, lead, monthly order capacity')

# Outcome label and strictly order-time state.
for c in ['order_date','promised_receipt_date','actual_receipt_date']:
    orders[c]=pd.to_datetime(orders[c])
assert (orders.order_date<orders.actual_receipt_date).all()
assert (orders.order_date<orders.promised_receipt_date).all()
computed_late=(orders.actual_receipt_date-orders.promised_receipt_date).dt.days
assert (orders.days_late==computed_late.clip(lower=0)).all()
assert (orders.late_receipt_flag==computed_late.gt(0).astype(int)).all()
assert (orders.actual_lead_days==(orders.actual_receipt_date-orders.order_date).dt.days).all()
assert (orders.inventory_position_at_order == orders.inventory_on_hand_at_order + orders.inventory_on_order_at_order).all()
assert (orders.inventory_on_hand_at_order>=0).all()
assert (orders.inventory_on_order_at_order>=0).all()
assert (orders.reorder_target_units_at_order>orders.inventory_position_at_order).all()
assert (orders.forecast_daily_requirements_at_order>0).all()
print('PASS: Delay labels, dates, inventory-position identity, positive replenishment triggers')

# Independently reconstruct historical supplier data with *completed* deliveries only.
by_sid={sid:g.sort_values('actual_receipt_date') for sid,g in orders.groupby('supplier_id')}
mismatches=0
for sid, group in by_sid.items():
    completed=group.actual_receipt_date.to_numpy(dtype='datetime64[ns]')
    flags=group.late_receipt_flag.to_numpy(dtype=int)
    prefix=np.r_[0,flags.cumsum()]
    for o in group.itertuples(index=False):
        day=np.datetime64(o.order_date)
        l=int(np.searchsorted(completed,day-np.timedelta64(90,'D'),'left'))
        r=int(np.searchsorted(completed,day,'left'))
        expected_n=r-l
        expected_rate=round((int(prefix[r]-prefix[l])+2)/(expected_n+10),4)
        if expected_n!=o.supplier_completed_orders_past_90d or abs(expected_rate-o.supplier_late_rate_past_90d)>1e-8:
            mismatches+=1
assert mismatches==0, f'Historical point-in-time mismatches: {mismatches}'
print('PASS: Independent point-in-time supplier history reconstruction for all orders')

# Receipts: inventory ledger must equal realized PO arrivals (not order-month quantities).
received=orders.loc[orders.actual_receipt_date<=pd.Timestamp('2026-06-30')].copy()
received['month']=received.actual_receipt_date.dt.strftime('%Y-%m')
r=received.groupby(['month','plant_id','component_id'],as_index=False).order_quantity_units.sum().rename(columns={'order_quantity_units':'receipts_from_orders'})
inv=stock.merge(r,on=['month','plant_id','component_id'],how='left',validate='one_to_one').fillna({'receipts_from_orders':0})
assert (inv.receipts_units==inv.receipts_from_orders).all()
assert (inv.opening_inventory_units+inv.receipts_units-inv.consumed_units==inv.closing_inventory_units).all()
assert (inv.planned_requirements_units-inv.consumed_units==inv.unmet_component_requirements_units).all()
assert (inv.consumed_units<=inv.planned_requirements_units).all()
assert (inv.closing_inventory_units>=0).all()
check=inv.copy(); check['prev_close']=check.groupby(['plant_id','component_id']).closing_inventory_units.shift(1)
assert (check.loc[check.prev_close.notna(),'opening_inventory_units']==check.loc[check.prev_close.notna(),'prev_close']).all()
print('PASS: Every recorded receipt matches actual supplier arrivals; monthly inventory conservation and continuity')

# Independent BOM explosion into component requirements.
d= demand.merge(wh[['warehouse_id','primary_plant_id']],on='warehouse_id',validate='many_to_one')
d=d.merge(bom,on='sku_id',validate='many_to_many')
d['month']=d.demand_date.str[:7]
d['req']=d.requested_units*d.units_per_finished_unit
req=d.groupby(['month','primary_plant_id','component_id'],as_index=False).req.sum()
req=req.rename(columns={'primary_plant_id':'plant_id'})
q=inv.merge(req,on=['month','plant_id','component_id'],how='left',validate='one_to_one').fillna({'req':0})
assert (q.planned_requirements_units==q.req).all()
print('PASS: Independent BOM-based demand-to-component-requirements reconciliation')

# Better relationship not sufficient proof of true corporate validity.
month_orders=orders.assign(month=orders.order_date.dt.strftime('%Y-%m'))
a=month_orders.groupby(['month','plant_id','component_id'],as_index=False).order_quantity_units.sum()
a=a.rename(columns={'order_quantity_units':'ordered_units'})
z=stock.merge(a,on=['month','plant_id','component_id'],how='left').fillna({'ordered_units':0})
corr=z[['ordered_units','planned_requirements_units']].corr().iloc[0,1]
z['group']=z.plant_id+'-'+z.component_id
z['x']=z.ordered_units-z.groupby('group').ordered_units.transform('mean')
z['y']=z.planned_requirements_units-z.groupby('group').planned_requirements_units.transform('mean')
within=z[['x','y']].corr().iloc[0,1]
assert corr>0.5 and within>0.25
assert (stock.month.nunique()==30 and len(stock)==3600)
print('PASS: Replenishment/demand linkage observed (not evidence of causal validation)')
print('  Orders:',f'{len(orders):,}')
print('  Same-month raw correlation:',round(corr,4))
print('  Same-month within plant-component correlation:',round(within,4))
print('  Synthetic late receipt rate:',round(orders.late_receipt_flag.mean()*100,2),'%')
print('  Synthetic unmet component units:',f'{stock.unmet_component_requirements_units.sum():,}')
print('  Master/active/ordered suppliers:',len(sup),'/',len(options.supplier_id.unique()),'/',len(orders.supplier_id.unique()))
print('FINAL RESULT: PASS -- integrity checks. NOT real-world validation.')
