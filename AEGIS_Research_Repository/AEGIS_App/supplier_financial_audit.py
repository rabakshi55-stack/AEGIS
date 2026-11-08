"""Conservative evidence gate for documented supplier intervention costs.

No invented quotations, causal estimates, material benefit or business approval.
All cost components required; complete observed outcomes compared by *item* only.
No cross-currency aggregation, no implicit allocation of fixed overheads.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib,json
from asof_validation import _timestamp

COMPONENTS=('purchase','freight','duties','switching','quality','expedite','penalties')
REQUIRED={'order_id','item_id','supplier_id','evaluation_group','assignment_at',
          'decision_at','outcome_at','outcome_recorded_at','source_record_id',
          'source_system','source_recorded_at','currency','units','cost_components_cents'}

def audit_financial_outcomes(events,plan):
    if not isinstance(events,list) or not 0<len(events)<=100000:
        raise ValueError('Expected a finite, nonempty observed intervention population')
    if not isinstance(plan,dict) or set(plan)!={'registered_at','evaluation_start','evaluation_end','outcome_freeze_at','currency'}:
        raise ValueError('A predeclared group comparison plan is mandatory')
    times={k:_timestamp(plan[k]) for k in ('registered_at','evaluation_start','evaluation_end','outcome_freeze_at')}
    if not times['registered_at']<times['evaluation_start']<=times['evaluation_end']<times['outcome_freeze_at']:
        raise ValueError('Invalid plan chronology')
    if plan['currency'] not in ('USD','INR','EUR','GBP'):
        raise ValueError('Cost inputs require one supported 1/100 minor-unit currency: USD, INR, EUR, GBP')
    errors=Counter();seen_ids=set();seen_sources=set();bygroup=defaultdict(lambda:defaultdict(lambda:{'units':0,'cost_cents':0,'orders':0}))
    for e in events:
        if not isinstance(e,dict) or set(e)!=REQUIRED:
            errors['INCOMPLETE_OR_UNEXPECTED_EVENT_SCHEMA']+=1;continue
        oid=e['order_id'];source=e['source_record_id']
        if not isinstance(oid,str) or not oid or oid in seen_ids:
            errors['DUPLICATE_OR_BLANK_ORDER_ID']+=1;continue
        seen_ids.add(oid)
        if not isinstance(source,str) or not source or source in seen_sources:
            errors['DUPLICATE_OR_BLANK_SOURCE_RECORD']+=1;continue
        seen_sources.add(source)
        group=e['evaluation_group']
        if group not in ('CONTROL','TREATMENT') or not all(isinstance(e[k],str) and e[k].strip() for k in ('item_id','supplier_id','source_system')):
            errors['INVALID_GROUP_OR_SOURCE_IDENTIFIERS']+=1;continue
        if e['currency']!=plan['currency']:
            errors['MIXED_OR_UNKNOWN_CURRENCY']+=1;continue
        units=e['units']
        if type(units) is not int or units<=0:
            errors['INVALID_UNITS']+=1;continue
        parts=e['cost_components_cents']
        if not isinstance(parts,dict) or set(parts)!=set(COMPONENTS) or any(type(v) is not int or v<0 for v in parts.values()):
            errors['MISSING_OR_INVALID_ALL_IN_COST_COMPONENTS']+=1;continue
        try:
            assignment=_timestamp(e['assignment_at']);decision=_timestamp(e['decision_at'])
            realized=_timestamp(e['outcome_at']);recorded=_timestamp(e['outcome_recorded_at']);source_at=_timestamp(e['source_recorded_at'])
        except (ValueError,TypeError,OverflowError):
            errors['INVALID_EVENT_TIME']+=1;continue
        # Source timestamp for realized cost must not precede actual outcome.
        if not (times['registered_at']<=assignment<=decision<=realized<=recorded<=times['outcome_freeze_at'] and
                times['evaluation_start']<=decision<=times['evaluation_end'] and source_at>=realized and source_at<=times['outcome_freeze_at']):
            errors['EVENT_CHRONOLOGY_OR_MATURITY_VIOLATION']+=1;continue
        record=bygroup[e['item_id']][group]
        record['units']+=units;record['cost_cents']+=sum(parts.values());record['orders']+=1
    matched={}
    for item,groups in sorted(bygroup.items()):
        control=groups['CONTROL'];treat=groups['TREATMENT']
        if not control['units'] or not treat['units']:
            errors['UNMATCHED_ITEM_BETWEEN_GROUPS']+=1
            continue
        c=Decimal(control['cost_cents'])/control['units']
        t=Decimal(treat['cost_cents'])/treat['units']
        matched[item]={'control_orders':control['orders'],'treatment_orders':treat['orders'],
                      'control_units':control['units'],'treatment_units':treat['units'],
                      'control_cost_cents_per_unit':str(c.quantize(Decimal('0.0001'))),
                      'treatment_cost_cents_per_unit':str(t.quantize(Decimal('0.0001'))),
                      'observed_treatment_minus_control_cents_per_unit':str((t-c).quantize(Decimal('0.0001')))}
    if not matched:errors['NO_MATCHED_PRODUCT_ITEMS']+=1
    return {'product':'AEGIS','study':'REALIZED_SUPPLIER_COST_READINESS_NOT_CAUSAL',
            'status':'BLOCKED_INCOMPLETE_OR_INCOMPARABLE_EVIDENCE' if errors else 'DESCRIPTIVE_RECORDED_COST_ONLY_UNATTESTED',
            'input_event_rows':len(events),'accepted_rows':sum(v['orders'] for g in bygroup.values() for v in g.values()),
            'matched_item_count':len(matched),'matched_item_descriptive_comparison':matched if not errors else {},
            'issues':dict(sorted(errors.items())),'declared_currency':plan['currency'],
            'money_unit':'Currency minor unit (USD/EUR/GBP cents; INR paise); factor=100 per major currency unit',
            'specified_cost_components_only_not_all_business_economics':True,
            'fully_landed_cost_accounting_independently_certified':False,
            'source_records_independently_attested':False,
            'supplier_assignment_randomization_verified':False,
            'unobserved_confounding_ruled_out':False,'causal_supplier_switch_benefit_established':False,
            'realized_net_savings_certified':False,'operational_approval':'NOT_GRANTED',
            'automatic_business_action':'DISABLED',
            'interpretation':'The seven specified cost components are included in the descriptive item-level averages; this is not a comprehensive business cost accounting standard. Source completeness, cash settlement, counterfactual identification, trade terms, group comparability, and actual causal benefit require independent external review.'}


def main():
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--events',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    data=json.loads(args.events.read_text(encoding='utf-8'))
    report=audit_financial_outcomes(data,json.loads(args.plan.read_text(encoding='utf-8')))
    with args.report.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(report['status'])
    return 2 if report['status'].startswith('BLOCKED') else 0
if __name__=='__main__':raise SystemExit(main())
