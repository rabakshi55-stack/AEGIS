"""Independent reference for the fictional AEGIS demo CSV; Python standard library only."""
import csv, sys, json
from pathlib import Path
from datetime import date
from decimal import Decimal
from collections import defaultdict
p=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).with_name("AEGIS_Sample_Supply_Chain.csv")
rows=list(csv.DictReader(p.open(newline="",encoding="utf-8")))
groups=defaultdict(list)
for r in rows: groups[r["supplier"]].append(r)
assert len({r["order_id"] for r in rows})==len(rows)
assert {r["currency"] for r in rows}=={"INR"}
def summary(rs):
    delays=[(date.fromisoformat(r["actual_delivery_date"])-date.fromisoformat(r["promised_delivery_date"])).days for r in rs if r["actual_delivery_date"]]
    late=[d for d in delays if d>0]
    return dict(orders=len(rs),quantity=sum(int(r["quantity"]) for r in rs),purchase_value_INR=str(sum(Decimal(r["quantity"])*Decimal(r["unit_cost"]) for r in rs)),comparable=len(delays),late=len(late),missing=len(rs)-len(delays),on_or_before=len(delays)-len(late),late_rate_pct=round(100*len(late)/len(delays),6) if delays else None,mean_signed_delay_days=round(sum(delays)/len(delays),6) if delays else None,mean_late_only_days=round(sum(late)/len(late),6) if late else None)
print(json.dumps({"suppliers":{s:summary(rs) for s,rs in sorted(groups.items())},"overall":summary(rows)},indent=2))
