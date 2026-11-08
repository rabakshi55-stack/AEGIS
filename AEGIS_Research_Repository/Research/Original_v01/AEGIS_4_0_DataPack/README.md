# AEGIS 4.0 — Synthetic Relational Supply Chain Benchmark (v0.1)

**SYNTHETIC DATA ONLY.** All companies, events, facilities, prices, contracts, shipments, and observed labels in this archive are generated for a hypothetical industrial electronics manufacturer. They are **not** actual corporate records and **not** independently measured business outcomes. Do not claim otherwise in a report or CV.

## Research use
Evaluate whether risk prediction combined with cost-sensitive/robust optimization improves *simulated* operational outcomes compared with static and standard ML baselines. Financial parameters are illustrative. This benchmark can demonstrate engineering and algorithmic differences, but cannot establish real-world ROI, causal effectiveness, or external validity.

## Tables and joins
- `suppliers.csv` ↔ `purchase_orders.csv` on `supplier_id`
- `components.csv` ↔ `purchase_orders.csv` and `bill_of_materials.csv` on `component_id`
- `supplier_component_options.csv` ↔ `purchase_orders.csv` on `(supplier_id, component_id)`
- `transport_lanes.csv` ↔ `purchase_orders.csv` on `lane_id`
- `plants.csv` ↔ `purchase_orders.csv` and `component_inventory_monthly.csv` on `plant_id`
- `warehouses.csv` ↔ `customer_demand_daily.csv` on `warehouse_id`
- `finished_products.csv` ↔ `customer_demand_daily.csv` and `bill_of_materials.csv` on `sku_id`
- `disruption_events.csv` is joined by `region` and event/alert dates, **not** by future realized severity.
- `component_inventory_monthly.csv` is a **derived component balance** using BOM-projected consumption; it is NOT a full production, transportation or customer-fulfillment ledger.

## Important modelling safeguards
1. **Temporal split**: train before 2025-07-01, validate 2025-07-01 through 2025-12-31, test from 2026-01-01. Later data must not inform features, scaling, training, model selection or business assumptions tuned against test.
2. `purchase_orders.csv`: `actual_receipt_date`, `actual_lead_days`, `days_late`, and `late_receipt_flag` are **post-outcome variables**. Only the label may be used as target; the other three must be removed from model input. `promised_receipt_date` is known at order time but redundant with promised lead.
3. `supplier_late_rate_past_90d` and `supplier_completed_orders_past_90d` are historical point-in-time features computed from receipts strictly earlier than each order date; no future outcomes used.
4. `disruption_events.csv` contains `realized_severity` and event end information which is NOT available before events resolve. Use only published alert details at event time, and do not join future events.
5. Historical demand values are observable only **after** the respective demand day. Avoid using same-day future demand in forecasts.
6. Month-close inventory snapshots must **not** be used as month-opening predictive features. Inventory values are reconciled within the simple component ledger only.
7. Beware of shared-simulation assumptions: benchmark comparisons must use identical disruption scenarios and prevent simulator access to oracle labels. Performance on generated data may reflect the generator's assumptions.

## Synthetic design
- Period: 2024-01-01 to 2026-06-30
- Entity master: 60 suppliers, 30 components, 12 finished SKUs, 4 assembly plants, 6 distribution centers
- Procurement decisions and realized receipts (26,000 orders)
- Daily end-market demand (per SKU / warehouse) and supplier alternatives
- Synthetic disruptions: regional weather/logistics/power incidents, with publication timestamps
- Simulated forecast covariates include congestion, capacity utilization, alert information, order urgency and supplier performance history
- Downstream monthly component inventory ledger balances are exactly conserved

## Reproduce
Install `numpy` and run `python generate.py` from this folder. The generator has a deterministic seed, and `validation_report.json` records integrity checks and split windows. Files are plain UTF-8 CSV.

## Next step
Audit each table, inspect target and time splits, assess geographic/event realism, then benchmark baselines. For additional credibility, calibrate selected assumptions against separately cited public datasets (e.g. US BTS FAF freight-flow aggregates and NOAA Storm Events) without falsely suggesting the synthetic rows are real measurements.

## License / source
Generated solely for this conversation, with Python and NumPy. Public dataset links mentioned as optional validation sources are **not ingested** into this package.
