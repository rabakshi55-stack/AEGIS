"""AEGIS 4.0 v0.2: causal-forward, fully SYNTHETIC replenishment benchmark.
Run: python generate_v02.py
Needs pandas and numpy. Input seed_data assets are also synthetic, copied from v0.1.
No future customer demand or realized delivery outcomes enter order-time decisions.
"""
from collections import defaultdict, deque
from datetime import date, timedelta
from pathlib import Path
import csv, json, math, shutil
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SEED = 4202602
rng = np.random.default_rng(SEED)
SRC, DEST = ROOT / 'seed_data', ROOT / 'data'
DEST.mkdir(exist_ok=True)
START, END = date(2024,1,1),date(2026,6,30)

def load(name): return pd.read_csv(SRC/name)
def toiso(d): return d.isoformat()
def logistic(z): return 1/(1+math.exp(-z))
def capped(z, lo, hi): return max(lo,min(hi,z))
def write(name, rows, columns):
    with (DEST/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=columns);w.writeheader();w.writerows(rows)

supplier = load('suppliers.csv')
options = load('supplier_component_options.csv')
parts = load('components.csv')
plants= load('plants.csv')
warehouses = load('warehouses.csv')
products = load('finished_products.csv')
bom = load('bill_of_materials.csv')
demand = load('customer_demand_daily.csv')
events = load('disruption_events.csv')
lanes=load('transport_lanes.csv')

# Preserve unchanged synthetic provenance and master tables.
for f in SRC.glob('*.csv'):
    shutil.copyfile(f,DEST/f.name)

supplier_region = dict(zip(supplier.supplier_id,supplier.region))
plant_keys=list(plants.plant_id)
components=list(parts.component_id)
combos=[(p,c) for p in plant_keys for c in components]
cat=defaultdict(list)
for r in options.itertuples(index=False): cat[r.component_id].append(r)
lane_ref={ (r.origin_id,r.destination_id): r for r in lanes.itertuples(index=False) if r.origin_type=='supplier'}
wh_to_plant=dict(zip(warehouses.warehouse_id,warehouses.primary_plant_id))
bom_by_sku=defaultdict(list)
for b in bom.itertuples(index=False):bom_by_sku[b.sku_id].append((b.component_id,int(b.units_per_finished_unit)))

# Fully synthetic observed daily demand; builder only reads each date at decision time.
daily_req=defaultdict(lambda:defaultdict(int))
for r in demand.itertuples(index=False):
    key=(wh_to_plant[r.warehouse_id], r.demand_date)
    for comp,n in bom_by_sku[r.sku_id]:
        daily_req[key][comp]+=int(r.requested_units)*n
# Ex-ante prior: 10 daily SKU units per warehouse (not fitted to future realized demand).
prior=defaultdict(float)
for sku,wh in [(s,w) for s in products.sku_id for w in warehouses.warehouse_id]:
    pl=wh_to_plant[wh]
    for comp,n in bom_by_sku[sku]: prior[(pl,comp)]+=10*n

# Synthetic advisories are visible only from publication through a fixed, disclosed 10-day validity period.
# NOTE: this deliberately never uses realized event_end_date to decide observability.
ev_by_region=defaultdict(list)
for e in events.itertuples(index=False):ev_by_region[e.region].append(e)

def published_alert(region,today):
    count=sum(1 for e in ev_by_region[region]
              if date.fromisoformat(e.alert_published_date)<=today<=date.fromisoformat(e.alert_published_date)+timedelta(days=10))
    return int(count>0),int(min(3,count))

def future_shock(region,due):
    severity=[int(e.realized_severity) for e in ev_by_region[region]
        if date.fromisoformat(e.event_start_date)<=due<=date.fromisoformat(e.event_end_date)]
    return max(severity,default=0)

# Supplier unobserved reliability, distinct from observed contract target.
latent={r.supplier_id:float(rng.normal(0,0.23)) for r in supplier.itertuples(index=False)}

# All inventory is updated daily. Receipts are applied at actual receipt date.
stock={(pl,c):int(rng.integers(2500,6001)) for pl,c in combos}
initial_stock=stock.copy()
last28=defaultdict(lambda:deque(maxlen=28))
by_arrival=defaultdict(list) # actual_date -> list of created orders
onorder=defaultdict(int)
monthly_booking=defaultdict(int) # (supplier, component, order_month) for capacity restriction
historical=defaultdict(list) # completed supplier orders by date
orders=[]; today_id=0
monthly=defaultdict(lambda:dict(receipts=0,requirements=0,consumed=0,unmet=0))
# Pilot-designed policy: weekly order review; target = expected consumption during
# replenishment lead plus 14 review/safety days; requirements estimated from trailing
# 28 observed days and a 14-day ex-ante engineering prior.
review_interval=7
for i in range((END-START).days+1):
    today=START+timedelta(days=i)
    curr_month=today.strftime('%Y-%m')
    if i%review_interval==0:
        for pl,comp in combos:
            history=last28[(pl,comp)]
            baseline=prior[(pl,comp)]
            forecast=(sum(history)+14*baseline)/(len(history)+14)
            possible=cat[comp]
            # Ex-ante quotes & published contract targets, not future delivery outcomes.
            ranked=sorted(possible,key=lambda x:(float(x.quoted_unit_cost_usd)
                                  + 1.30*float(x.promised_lead_days)
                                  - 50.0*float(supplier.loc[supplier.supplier_id==x.supplier_id,'contract_on_time_target'].iloc[0])))
            shortest_lead=min(int(o.promised_lead_days)+int(lane_ref[(o.supplier_id,pl)].transit_days) for o in possible)
            planning_horizon=shortest_lead+14
            target=int(math.ceil(forecast*planning_horizon))
            inventory_position=stock[(pl,comp)]+onorder[(pl,comp)]
            required=max(0,target-inventory_position)
            # Disclosed synthetic qualification-rotation policy: rotate the 5 approved
            # suppliers across weeks, to represent contractual diversification.
            # This is a baseline operating policy, NOT the proposed AEGIS optimizer.
            rotation=(i//7 + components.index(comp)) % len(ranked)
            suppliers_to_try=ranked[rotation:]+ranked[:rotation]
            for option in suppliers_to_try:
                if required<=0:break
                sid=option.supplier_id
                cap_key=(sid,comp,curr_month)
                capacity_available=max(0,int(option.monthly_capacity_units)-monthly_booking[cap_key])
                # Prefer not to create order if the remaining quantity is smaller than MOQ.
                moq=int(option.minimum_order_qty)
                if capacity_available <moq:continue
                units=int(math.ceil(required / 25)*25)
                units=max(units,moq)
                units=min(units,capacity_available)
                if units <moq:continue
                lane=lane_ref[(sid,pl)]
                promised_lead=int(option.promised_lead_days)+int(lane.transit_days)
                due=today+timedelta(days=promised_lead)
                alert,level=published_alert(supplier_region[sid],today)
                day_of_year=today.timetuple().tm_yday
                congestion=capped(.27+.14*math.sin(day_of_year*math.pi*2/365.25)
                     +float(rng.normal(0,.085))+.12*alert+(0.10 if today.year==2026 else 0),.01,1.)
                # Supplier commitment load is observable at creation, not generated using future outcomes.
                load=monthly_booking[cap_key]/int(option.monthly_capacity_units)
                utilization=capped(.48+load+.10*(today.year==2026)+float(rng.normal(0,.09)),.05,1.60)
                urgent=int(stock[(pl,comp)] < forecast*max(7,shortest_lead/2))
                # Hidden outcome driver, NEVER part of order-time features.
                shock=future_shock(supplier_region[sid],due)
                lp=(-1.83+1.2*latent[sid]+1.35*(utilization-.6)
                    +1.4*(congestion-.35)+.40*urgent+.48*alert
                    +.30*(shock>0)+.35*(shock>=4))
                is_late=int(rng.random()<logistic(lp))
                drift=int(rng.poisson(2.4+2*(shock>=4)))+1 if is_late else -int(rng.choice([0,0,0,1,2]))
                received=due+timedelta(days=drift)
                assert received>today
                # Strictly previous completions, even if created orders have future outcomes precomputed.
                hist90=[flag for dt,flag in historical[sid]
                          if today-timedelta(days=90)<=dt<today]
                hist_count=len(hist90)
                hist_rate=round((sum(hist90)+2)/(hist_count+10),4)
                today_id+=1
                order={
                    'purchase_order_id':f'PO2-{today_id:07d}',
                    'order_date':toiso(today), 'supplier_id':sid,'component_id':comp,'plant_id':pl,
                    'lane_id':lane.lane_id,'order_quantity_units':units,
                    'quoted_unit_cost_usd':float(option.quoted_unit_cost_usd),
                    'promised_lead_days':promised_lead,'promised_receipt_date':toiso(due),
                    'urgent_order_flag':urgent,'regional_alert_available_at_order':alert,
                    'regional_alert_level_at_order':level,'capacity_utilization_at_order':round(utilization,4),
                    'logistics_congestion_at_order':round(congestion,4),
                    'supplier_completed_orders_past_90d':hist_count,
                    'supplier_late_rate_past_90d':hist_rate,
                    'forecast_daily_requirements_at_order':round(forecast,3),
                    'inventory_on_hand_at_order':stock[(pl,comp)],
                    'inventory_on_order_at_order':onorder[(pl,comp)],
                    'reorder_target_units_at_order':target,
                    'inventory_position_at_order':inventory_position,
                    'actual_receipt_date':toiso(received),
                    'actual_lead_days':(received-today).days,
                    'days_late':max(0,drift),'late_receipt_flag':is_late,
                    'replenishment_policy':'weekly_demand_inventory_position_v02'
                }
                orders.append(order)
                by_arrival[received].append(order)
                onorder[(pl,comp)]+=units
                monthly_booking[cap_key]+=units
                required=max(0,required-units)
    # process receipts observed today, after orders for the day are placed
    for order in by_arrival.get(today,[]):
        key=(order['plant_id'],order['component_id'])
        qty=order['order_quantity_units']
        stock[key]+=qty
        onorder[key]-=qty
        monthly[(curr_month,*key)]['receipts']+=qty
        historical[order['supplier_id']].append((today,order['late_receipt_flag']))
    # realize today's downstream demand (not available to morning decision)
    for pl,comp in combos:
        key=(pl,comp)
        required=daily_req[(pl,toiso(today))].get(comp,0)
        used=min(stock[key],required)
        stock[key]-=used
        unmet=required-used
        row=monthly[(curr_month,*key)]
        row['requirements']+=required
        row['consumed']+=used
        row['unmet']+=unmet
        last28[key].append(required)

# Month-close balances: must reconstruct openings from initial opening and prior closes.
months=sorted({month for month,*_ in monthly})
current_stock=initial_stock.copy()
inv=[]
for month in months:
    for pl,comp in combos:
        k=(pl,comp); row=monthly[(month,*k)]
        opening=current_stock[k]
        closing=opening+row['receipts']-row['consumed']
        assert closing>=0, (month,k,closing)
        assert row['requirements']-row['consumed']==row['unmet']
        current_stock[k]=closing
        inv.append(dict(month=month,plant_id=pl,component_id=comp,
            opening_inventory_units=opening,receipts_units=row['receipts'],
            planned_requirements_units=row['requirements'],consumed_units=row['consumed'],
            unmet_component_requirements_units=row['unmet'],closing_inventory_units=closing))
assert current_stock==stock
assert all(onorder[key]>=0 for key in combos)
assert all(o['actual_receipt_date']>o['order_date'] for o in orders)
assert all(o['days_late']==max(0,(date.fromisoformat(o['actual_receipt_date'])-
                          date.fromisoformat(o['promised_receipt_date'])).days) for o in orders)
write('purchase_orders.csv',orders,list(orders[0]))
write('component_inventory_monthly.csv',inv,list(inv[0]))

# Source availability dictionary (column-level definitions rather than universal vague labels).
post_order={'actual_receipt_date','actual_lead_days','days_late','late_receipt_flag'}
reasoncols={'forecast_daily_requirements_at_order','inventory_on_hand_at_order',
            'inventory_on_order_at_order','reorder_target_units_at_order',
            'inventory_position_at_order'}
rows=[]
for f in sorted(DEST.glob('*.csv')):
    if f.name=='data_dictionary.csv':continue
    with f.open(encoding='utf8') as inp: cols=next(csv.reader(inp))
    for col in cols:
        av='Static/structural reference; provenance synthetic'
        if f.name=='purchase_orders.csv':
            av='Target or outcome; available ONLY on actual receipt' if col in post_order else 'Order-time feature; simulated available at order creation'
        elif f.name=='customer_demand_daily.csv':
            av='Observed at end of demand day' if col=='requested_units' else 'Calendar/planned variable'
        elif f.name=='component_inventory_monthly.csv':av='Available after end of month'
        elif f.name=='disruption_events.csv':
            av=('Future realization, NOT available at order time' if col in {'event_end_date','realized_severity'}
                else 'At or after published/observed date, subject to alert rules')
        rows.append({'file':f.name,'column':col,'availability':av,
             'description':('Derived from trailing observed requirements and previously observed state' if col in reasoncols
                            else 'Synthetic; refer to README for use and caveats')})
write('data_dictionary.csv',rows,['file','column','availability','description'])

from collections import Counter
cnt=Counter(o['late_receipt_flag'] for o in orders)
report={
    'version':'v0.2', 'dataset_type':'100% synthetic', 'seed':SEED,
    'date_start':toiso(START),'date_end':toiso(END),
    'orders':len(orders),'late_receipt_rate':round(cnt[1]/len(orders),5),
    'demand_records':len(demand),'inventory_monthly_records':len(inv),
    'components':len(components),'plants':len(plant_keys),
    'active_suppliers':len(set(x['supplier_id'] for x in orders)),
    'inventories_with_shortages':sum(x['unmet_component_requirements_units']>0 for x in inv),
    'total_requirements':sum(x['planned_requirements_units'] for x in inv),
    'total_receipts':sum(x['receipts_units'] for x in inv),
    'total_unmet':sum(x['unmet_component_requirements_units'] for x in inv),
    'inventory_conservation':'PASS',
    'known_limitations':['No observed corporate data or calibrated business costs',
        'Finished good order fulfillment is not fully simulated',
        'Weekly planning uses assumed prior + trailing realized component requirements',
        'Future disruption realization shapes outcomes but is never order-time feature',
        'Demand simulation and delay generation are synthetic and may bias ML benchmarks']}
(ROOT/'validation_report_v02.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
