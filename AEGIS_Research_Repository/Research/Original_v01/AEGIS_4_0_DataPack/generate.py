"""AEGIS 4.0 synthetic multi-table data generator.
All entities and events are fictitious; not derived from a real company's operational records.
Reproduce: python generate.py  (requires numpy)."""
import csv, json, math, bisect, hashlib
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict, Counter
import numpy as np

SEED = 4012026
rng = np.random.default_rng(SEED)
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data'
OUT.mkdir(exist_ok=True)
START, END = date(2024,1,1), date(2026,6,30)
N_DAYS = (END - START).days + 1
REGIONS=['Northeast','Southeast','Midwest','Southwest','West','Gulf']

def write_csv(name, rows, cols):
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=cols); writer.writeheader();writer.writerows(rows)
    return len(rows)

def iso(d):return d.isoformat()
def rnd(*args): return float(rng.uniform(*args))
def choice(seq):return seq[int(rng.integers(len(seq)))]
def clamp(x,a,b):return max(a,min(b,x))
def sigmoid(x):return 1/(1+math.exp(-x))

# Fictional industrial electronics company, not EV charging supplier project.
suppliers=[]; latent={}
for i in range(1,61):
    sid=f'SUP-{i:03d}'; region=REGIONS[(i*7+int(rng.integers(6)))%6]
    quality=round(rnd(0.89,0.995),3); base_reliability=round(rnd(0.74,0.97),3)
    latent[sid]=float(clamp((0.92-base_reliability)*2+rnd(-0.16,0.16),-0.17,0.53))
    suppliers.append(dict(supplier_id=sid,supplier_name=f'Fictional Supplier {i:03d}',region=region,
                          contract_on_time_target=base_reliability,quality_acceptance_target=quality,
                          financial_risk_band=choice(['Low','Low','Medium','Medium','High']),
                          qualified_flag=1))
write_csv('suppliers.csv',suppliers,list(suppliers[0]))
s_by_id={s['supplier_id']:s for s in suppliers}

parts=[]
for i in range(1,31):
    parts.append(dict(component_id=f'CMP-{i:03d}',component_family=['Microcontroller','Sensor','Power module','Board','Housing','Connector'][((i-1)%6)],
          criticality=choice(['High','High','Medium','Medium','Low']),standard_unit_cost_usd=round(rnd(8,220),2),
          annual_holding_rate=round(rnd(0.15,0.29),3),safety_stock_days=int(rng.integers(10,31))))
write_csv('components.csv',parts,list(parts[0])); part_ids=[p['component_id'] for p in parts]

plants=[dict(plant_id=f'PLT-{i}',plant_name=f'Fictional Assembly Plant {i}',region=REGIONS[(i*2)%6],
             daily_capacity_finished_units=int(rng.integers(500,1100))) for i in range(1,5)]
write_csv('plants.csv',plants,list(plants[0]))
warehouses=[dict(warehouse_id=f'WH-{i}',region=REGIONS[i-1],primary_plant_id=plants[(i-1)%4]['plant_id']) for i in range(1,7)]
write_csv('warehouses.csv',warehouses,list(warehouses[0]))
skus=[]
for i in range(1,13):
    skus.append(dict(sku_id=f'SKU-{i:03d}',product_family=['Industrial controller','Process sensor','Control interface'][((i-1)%3)],
                     selling_price_usd=round(rnd(500,2400),2),priority_tier=['A','B','C'][((i-1)%3)]))
write_csv('finished_products.csv',skus,list(skus[0]))

bom=[]
for s in skus:
    included=rng.choice(part_ids,size=int(rng.integers(5,9)),replace=False)
    for comp in included:
        bom.append(dict(sku_id=s['sku_id'],component_id=str(comp),units_per_finished_unit=int(rng.integers(1,4))))
write_csv('bill_of_materials.csv',bom,list(bom[0]))

# Each component has 5 alternative suppliers; all suppliers can provide several components.
catalog=[]; supplier_load=Counter()
for p in parts:
    picks=list(rng.choice([s['supplier_id'] for s in suppliers],size=5,replace=False))
    for sid in picks:
        supplier_load[sid]+=1
        catalog.append(dict(supplier_id=sid,component_id=p['component_id'],
            quoted_unit_cost_usd=round(p['standard_unit_cost_usd']*rnd(0.81,1.22),2),
            promised_lead_days=int(rng.integers(6,26)),
            minimum_order_qty=int(rng.integers(60,201)),
            monthly_capacity_units=int(rng.integers(8500,24001)),
            approved_for_sourcing=1))
write_csv('supplier_component_options.csv',catalog,list(catalog[0]))
cat_index={(x['supplier_id'],x['component_id']):x for x in catalog}

lanes=[]; lane_index={}
for s in suppliers:
    for p in plants:
        d=int(rng.integers(2,11))+(2 if s['region']!=p['region'] else 0)
        lane=dict(lane_id=f'LN-SP-{s["supplier_id"]}-{p["plant_id"]}',origin_type='supplier',
                  origin_id=s['supplier_id'],destination_type='plant',destination_id=p['plant_id'],
                  transit_days=d,freight_cost_per_unit_usd=round(rnd(0.4,6.5)+d*.15,2),
                  route_region=s['region'])
        lanes.append(lane);lane_index[(s['supplier_id'],p['plant_id'])]=lane
for p in plants:
    for w in warehouses:
        lanes.append(dict(lane_id=f'LN-PW-{p["plant_id"]}-{w["warehouse_id"]}',origin_type='plant',
                  origin_id=p['plant_id'],destination_type='warehouse',destination_id=w['warehouse_id'],
                  transit_days=int(rng.integers(2,9)),freight_cost_per_unit_usd=round(rnd(1,9),2),route_region=p['region']))
write_csv('transport_lanes.csv',lanes,list(lanes[0]))

# Regional hazards are synthetic; warning availability is time stamped for point-in-time integrity.
raw_events=[]
for i in range(1,221):
    start=START+timedelta(days=int(rng.integers(14,N_DAYS-10)))
    end=start+timedelta(days=int(rng.integers(2,11)))
    lead=int(rng.integers(0,11))
    raw_events.append(dict(event_id=f'EVT-{i:04d}',region=choice(REGIONS),event_type=choice(['Extreme weather','Port congestion','Labor disruption','Power outage','Infrastructure failure']),
        alert_published_date=iso(start-timedelta(days=lead)),event_start_date=iso(start),event_end_date=iso(end),
        realized_severity=int(rng.integers(1,6)),source_type='synthetic_simulation'))
write_csv('disruption_events.csv',raw_events,list(raw_events[0]))
events_by_region=defaultdict(list)
for e in raw_events:events_by_region[e['region']].append(e)

def at_order_alert(region,day):
    """Whether a regional alert was published on/before the order date and still applicable."""
    flagged=[e for e in events_by_region[region]
            if e['alert_published_date']<=iso(day)<=e['event_end_date']]
    if not flagged:return 0,0
    # Only expose a public ordinal warning level, not future realized severity.
    return 1, min(3,1+int(len(flagged)>1)+int(len(flagged)>2))

def realized_shock(region,day):
    ev=[e for e in events_by_region[region] if e['event_start_date']<=iso(day)<=e['event_end_date']]
    return max([e['realized_severity'] for e in ev],default=0)

# PO data: order-time fields are separate from future outcomes.
orders=[]; launch_pairs=list(cat_index.keys())
for i in range(1,26001):
    order_day=START+timedelta(days=int(rng.integers(0,N_DAYS-17)))
    sid,comp=launch_pairs[int(rng.integers(len(launch_pairs)))]; plant=choice(plants)
    option=cat_index[(sid,comp)]; lane=lane_index[(sid,plant['plant_id'])]
    quantity=int(rng.integers(max(100,option['minimum_order_qty']),max(201,min(750,option['monthly_capacity_units']//19))))
    lead=option['promised_lead_days']+lane['transit_days']; due=order_day+timedelta(days=lead)
    alert,level=at_order_alert(s_by_id[sid]['region'],order_day)
    season=math.sin(2*math.pi*order_day.timetuple().tm_yday/365.25)
    utilization=round(clamp(.66+.19*season+rnd(-.3,.37)+(0.08 if order_day.year==2026 else 0),.16,1.30),3)
    congestion=round(clamp(.25+.18*season+rnd(-.24,.31)+.13*alert,.02,1.0),3)
    urgent=int(rng.random()<0.19)
    shock=realized_shock(s_by_id[sid]['region'],due)
    # True unobserved disturbances cannot be used as model features.
    linear=-1.80+latent[sid]*2.0+1.3*(utilization-.65)+1.3*(congestion-.35)+.28*urgent+.6*alert+.25*(shock>0)+.25*(shock>=4)
    delayed=int(rng.random()<sigmoid(linear))
    delay_days=int(rng.integers(1,4))+int(rng.poisson(2.5+2*(shock>=4))) if delayed else -int(rng.choice([0,0,0,0,1,2]))
    actual=due+timedelta(days=delay_days)
    orders.append(dict(purchase_order_id=f'PO-{i:07d}',order_date=iso(order_day),supplier_id=sid,
        component_id=comp,plant_id=plant['plant_id'],lane_id=lane['lane_id'],
        order_quantity_units=quantity,quoted_unit_cost_usd=option['quoted_unit_cost_usd'],
        promised_lead_days=lead,promised_receipt_date=iso(due),
        urgent_order_flag=urgent,regional_alert_available_at_order=alert,
        regional_alert_level_at_order=level,capacity_utilization_at_order=utilization,
        logistics_congestion_at_order=congestion,
        actual_receipt_date=iso(actual),actual_lead_days=(actual-order_day).days,
        days_late=max(0,delay_days),late_receipt_flag=delayed))
orders.sort(key=lambda r:(r['order_date'],r['purchase_order_id']))

# Legitimate historical features: include ONLY deliveries completed prior to new order.
completion=defaultdict(list)
for r in orders:completion[r['supplier_id']].append((r['actual_receipt_date'],r['late_receipt_flag']))
completion_arrays={}
for sid, vals in completion.items():
    vals.sort(key=lambda z:z[0]); ds=[z[0] for z in vals]; ps=[0]
    for z in vals:ps.append(ps[-1]+z[1])
    completion_arrays[sid]=(ds,ps)
for r in orders:
    dates,prefix=completion_arrays[r['supplier_id']]; d=r['order_date']; lo=iso(date.fromisoformat(d)-timedelta(days=90))
    left=bisect.bisect_left(dates,lo);right=bisect.bisect_left(dates,d)
    n=right-left;late_n=prefix[right]-prefix[left]
    r['supplier_completed_orders_past_90d']=n
    r['supplier_late_rate_past_90d']=round((late_n+2)/(n+10),4)  # smoothed prior 20%
write_csv('purchase_orders.csv',orders,list(orders[0]))

# Daily independent end-market demand; not past customer project data.
daily=[]; sku_base={s['sku_id']:rnd(3,15) for s in skus}; wh_mult={w['warehouse_id']:rnd(.75,1.28) for w in warehouses}
for day_idx in range(N_DAYS):
    dt=START+timedelta(days=day_idx); d=dt.timetuple().tm_yday
    cyc=1+.22*math.sin(2*math.pi*d/365.25)+.08*math.sin(4*math.pi*d/365.25)
    weekend=int(dt.weekday()>=5)
    for s in skus:
        for w in warehouses:
            promo=int(rng.random()<.045)
            mu=sku_base[s['sku_id']]*wh_mult[w['warehouse_id']]*cyc*(.86 if weekend else 1)*(1+.4*promo)
            if dt.year==2026 and s['priority_tier']=='A':mu*=1.17
            if dt.year==2025 and w['region']=='West':mu*=.93
            mu=max(0.3,mu)
            qty=int(rng.negative_binomial(n=10,p=10/(10+mu)))
            daily.append(dict(demand_date=iso(dt),warehouse_id=w['warehouse_id'],sku_id=s['sku_id'],
                         promotion_announced_flag=promo,weekend_flag=weekend,requested_units=qty))
write_csv('customer_demand_daily.csv',daily,list(daily[0]))

# Inventory snapshots conserve receipts and component usage at monthly granularity.
# Simplified: planned component requirements are allocated from downstream demand to primary plant.
months=[];cur=date(START.year,START.month,1)
while cur<=END:
    months.append(cur);cur=date(cur.year+1,1,1) if cur.month==12 else date(cur.year,cur.month+1,1)
monthly_required=defaultdict(int); bom_idx=defaultdict(list)
for b in bom:bom_idx[b['sku_id']].append((b['component_id'],b['units_per_finished_unit']))
wh_idx={w['warehouse_id']:w['primary_plant_id'] for w in warehouses}
for d in daily:
    period=d['demand_date'][:7]; pid=wh_idx[d['warehouse_id']]
    for comp,units in bom_idx[d['sku_id']]:monthly_required[(period,pid,comp)]+=d['requested_units']*units
monthly_receipts=defaultdict(int)
for o in orders:
    dt=o['actual_receipt_date']
    if iso(START)<=dt<=iso(END):monthly_receipts[(dt[:7],o['plant_id'],o['component_id'])]+=o['order_quantity_units']
stock={(p['plant_id'],part['component_id']):int(rng.integers(1000,5001)) for p in plants for part in parts}
snaps=[]
for m in months:
    period=iso(m)[:7]
    for p in plants:
        for part in parts:
            k=(p['plant_id'],part['component_id']); opening=stock[k]
            received=monthly_receipts[(period,*k)]; required=monthly_required[(period,*k)]
            consumed=min(opening+received,required); short=required-consumed
            closing=opening+received-consumed;stock[k]=closing
            snaps.append(dict(month=period,plant_id=k[0],component_id=k[1],opening_inventory_units=opening,
                     receipts_units=received,planned_requirements_units=required,
                     consumed_units=consumed,unmet_component_requirements_units=short,closing_inventory_units=closing))
write_csv('component_inventory_monthly.csv',snaps,list(snaps[0]))

# Data dictionary: includes provenance and availability metadata for leakage review.
spec={
'suppliers.csv':'Synthetic supplier master. Targets describe contract expectations, not observed actual delivery performance.',
'components.csv':'Synthetic raw-material master and holding cost assumptions.',
'plants.csv':'Synthetic assembly plants with approximate daily capacity.',
'warehouses.csv':'Synthetic distribution centers and primary plant relationships.',
'finished_products.csv':'Synthetic end-product catalog and selling prices.',
'bill_of_materials.csv':'Synthetic SKU-component quantity requirements.',
'supplier_component_options.csv':'Synthetic supplier qualification, quotes, MOQ and per-option capacity.',
'transport_lanes.csv':'Synthetic supplier-to-plant and plant-to-warehouse lanes.',
'disruption_events.csv':'Synthetic regional shock events and published warning dates.',
'purchase_orders.csv':'Synthetic procurement orders with order-time signals and realized receipt outcomes.',
'customer_demand_daily.csv':'Synthetic daily market demand by SKU and distribution center.',
'component_inventory_monthly.csv':'Derived monthly component ledger from recorded receipts and BOM-based planned requirements.'}
# all files and column names read back from CSV for no dictionary omissions
fieldinfo=[]
for filename,description in spec.items():
    with (OUT/filename).open(encoding='utf-8') as f:cols=next(csv.reader(f))
    for c in cols:
        avail='static master/reference'
        if filename=='purchase_orders.csv':
            avail='outcome / ONLY after actual receipt' if c in {'actual_receipt_date','actual_lead_days','days_late','late_receipt_flag'} else 'known at order creation / point-in-time'
        elif filename=='disruption_events.csv':
            avail='known only at or after event end' if c in {'event_end_date','realized_severity'} else 'published at alert date / scheduled or actual event'
        elif filename=='customer_demand_daily.csv':
            avail='realized at end of demand day' if c=='requested_units' else 'known by or during demand day'
        elif filename=='component_inventory_monthly.csv':avail='known at month close (not at month start)'
        fieldinfo.append(dict(file=filename,column=c,availability=avail,description=description))
write_csv('data_dictionary.csv',fieldinfo,list(fieldinfo[0]))

# Invariants: relationships, ledger balance, past-only risk history, chronological target split.
assert len(orders)==26000
assert len({p['purchase_order_id'] for p in orders})==len(orders)
assert all((o['supplier_id'],o['component_id']) in cat_index for o in orders)
assert all(o['order_date']<o['promised_receipt_date'] for o in orders)
assert all(o['days_late']==max(0,(date.fromisoformat(o['actual_receipt_date'])-date.fromisoformat(o['promised_receipt_date'])).days) for o in orders)
assert all(v['opening_inventory_units']+v['receipts_units']-v['consumed_units']==v['closing_inventory_units'] for v in snaps)
assert all(v['planned_requirements_units']-v['consumed_units']==v['unmet_component_requirements_units'] for v in snaps)
assert all(v['closing_inventory_units']>=0 for v in snaps)
assert min(Counter(o['late_receipt_flag'] for o in orders).values())>0
counts={fn:sum(1 for _ in (OUT/fn).open(encoding='utf-8'))-1 for fn in [*spec.keys(),'data_dictionary.csv']}
ycounts=dict(Counter(o['order_date'][:4] for o in orders));rates={year:round(sum(x['late_receipt_flag'] for x in orders if x['order_date'][:4]==year)/n,4) for year,n in ycounts.items()}
report=dict(dataset='AEGIS 4.0 - industrial electronics resilience benchmark (SYNTHETIC)',seed=SEED,
            start=iso(START),end=iso(END),table_row_counts=counts,
            delivery_label_distribution=dict(Counter(o['late_receipt_flag'] for o in orders)),
            late_receipt_rate_by_order_year=rates,
            inventory_conservation_check='PASS',unique_po_check='PASS',catalog_join_check='PASS',
            temporal_outcome_separation='Outcome columns must not enter order-time ML features',
            recommended_split=dict(train='order_date < 2025-07-01',validation='2025-07-01 <= order_date < 2026-01-01',test='order_date >= 2026-01-01'))
(ROOT/'validation_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(ROOT/'README.md').write_text('''# AEGIS 4.0 — Synthetic Relational Supply Chain Benchmark (v0.1)\n\n**SYNTHETIC DATA ONLY.** All companies, events, facilities, prices, contracts, shipments, and observed labels in this archive are generated for a hypothetical industrial electronics manufacturer. They are **not** actual corporate records and **not** independently measured business outcomes. Do not claim otherwise in a report or CV.\n\n## Research use\nEvaluate whether risk prediction combined with cost-sensitive/robust optimization improves *simulated* operational outcomes compared with static and standard ML baselines. Financial parameters are illustrative. This benchmark can demonstrate engineering and algorithmic differences, but cannot establish real-world ROI, causal effectiveness, or external validity.\n\n## Tables and joins\n- `suppliers.csv` ↔ `purchase_orders.csv` on `supplier_id`\n- `components.csv` ↔ `purchase_orders.csv` and `bill_of_materials.csv` on `component_id`\n- `supplier_component_options.csv` ↔ `purchase_orders.csv` on `(supplier_id, component_id)`\n- `transport_lanes.csv` ↔ `purchase_orders.csv` on `lane_id`\n- `plants.csv` ↔ `purchase_orders.csv` and `component_inventory_monthly.csv` on `plant_id`\n- `warehouses.csv` ↔ `customer_demand_daily.csv` on `warehouse_id`\n- `finished_products.csv` ↔ `customer_demand_daily.csv` and `bill_of_materials.csv` on `sku_id`\n- `disruption_events.csv` is joined by `region` and event/alert dates, **not** by future realized severity.\n- `component_inventory_monthly.csv` is a **derived component balance** using BOM-projected consumption; it is NOT a full production, transportation or customer-fulfillment ledger.\n\n## Important modelling safeguards\n1. **Temporal split**: train before 2025-07-01, validate 2025-07-01 through 2025-12-31, test from 2026-01-01. Later data must not inform features, scaling, training, model selection or business assumptions tuned against test.\n2. `purchase_orders.csv`: `actual_receipt_date`, `actual_lead_days`, `days_late`, and `late_receipt_flag` are **post-outcome variables**. Only the label may be used as target; the other three must be removed from model input. `promised_receipt_date` is known at order time but redundant with promised lead.\n3. `supplier_late_rate_past_90d` and `supplier_completed_orders_past_90d` are historical point-in-time features computed from receipts strictly earlier than each order date; no future outcomes used.\n4. `disruption_events.csv` contains `realized_severity` and event end information which is NOT available before events resolve. Use only published alert details at event time, and do not join future events.\n5. Historical demand values are observable only **after** the respective demand day. Avoid using same-day future demand in forecasts.\n6. Month-close inventory snapshots must **not** be used as month-opening predictive features. Inventory values are reconciled within the simple component ledger only.\n7. Beware of shared-simulation assumptions: benchmark comparisons must use identical disruption scenarios and prevent simulator access to oracle labels. Performance on generated data may reflect the generator's assumptions.\n\n## Synthetic design\n- Period: 2024-01-01 to 2026-06-30\n- Entity master: 60 suppliers, 30 components, 12 finished SKUs, 4 assembly plants, 6 distribution centers\n- Procurement decisions and realized receipts (26,000 orders)\n- Daily end-market demand (per SKU / warehouse) and supplier alternatives\n- Synthetic disruptions: regional weather/logistics/power incidents, with publication timestamps\n- Simulated forecast covariates include congestion, capacity utilization, alert information, order urgency and supplier performance history\n- Downstream monthly component inventory ledger balances are exactly conserved\n\n## Reproduce\nInstall `numpy` and run `python generate.py` from this folder. The generator has a deterministic seed, and `validation_report.json` records integrity checks and split windows. Files are plain UTF-8 CSV.\n\n## Next step\nAudit each table, inspect target and time splits, assess geographic/event realism, then benchmark baselines. For additional credibility, calibrate selected assumptions against separately cited public datasets (e.g. US BTS FAF freight-flow aggregates and NOAA Storm Events) without falsely suggesting the synthetic rows are real measurements.\n\n## License / source\nGenerated solely for this conversation, with Python and NumPy. Public dataset links mentioned as optional validation sources are **not ingested** into this package.\n''',encoding='utf-8')
print(json.dumps(report,indent=2))
