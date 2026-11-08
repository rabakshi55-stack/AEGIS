"""Run with: python verify_dataset.py. Uses Python standard library only."""
import csv
from pathlib import Path
from collections import Counter
root = Path(__file__).resolve().parent / 'data'

def records(name):
    with (root/name).open(newline='', encoding='utf-8') as stream:
        yield from csv.DictReader(stream)

orders = list(records('purchase_orders.csv'))
options = {(r['supplier_id'], r['component_id']) for r in records('supplier_component_options.csv')}
assert len(orders) == len({r['purchase_order_id'] for r in orders}), 'Duplicate PO ID'
assert all((r['supplier_id'],r['component_id']) in options for r in orders), 'Invalid sourcing join'
assert all(r['order_date'] < r['promised_receipt_date'] for r in orders), 'Impossible due date'
assert all(r['actual_receipt_date'] >= r['order_date'] for r in orders), 'Impossible receipt date'
inventory = list(records('component_inventory_monthly.csv'))
assert all(int(r['opening_inventory_units'])+int(r['receipts_units'])-int(r['consumed_units']) == int(r['closing_inventory_units']) for r in inventory), 'Inventory does not reconcile'
assert all(int(r['planned_requirements_units'])-int(r['consumed_units']) == int(r['unmet_component_requirements_units']) for r in inventory), 'Shortages do not reconcile'
assert all(int(r['closing_inventory_units']) >= 0 for r in inventory), 'Negative inventory'
print('AEGIS 4.0 SYNTHETIC DATASET: VERIFIED CORE INTEGRITY')
print('Purchase orders:', len(orders))
print('Late receipt rate:', f"{sum(int(r['late_receipt_flag']) for r in orders)/len(orders):.2%}")
print('Years:', dict(Counter(r['order_date'][:4] for r in orders)))
print('Monthly component inventory records:',len(inventory))
print('Inventory records with shortages:',sum(int(r['unmet_component_requirements_units'])>0 for r in inventory))
print('PASS: Primary-key uniqueness, sourcing options, temporal sanity, component inventory conservation')
print('Reminder: Integrity checks do NOT establish real-world validity or forecast performance.')
