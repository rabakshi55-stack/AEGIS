"""Checked cohort metrics. Delivery eligibility never changes financial scope.

Grouping is read-only over the full active snapshot; no currency is inferred,
no causal or sourcing decision is certified. Rows are orders only when the
mapped order identifiers are complete and unique.
"""
from collections import defaultdict
from decimal import Decimal, localcontext
from fractions import Fraction
import re
from intake import _date, ROLE_ALIASES, _normalized_header
from dataset_queries import numeric

GROUPS={'supplier':'supplier_id','region':'destination_state','item':'item_id'}
MAX_GROUPS=20

def _roles(ds):
    # Explicit mappings take precedence. Otherwise use only unambiguous exact
    # header aliases for a provisional description, never modify the dataset.
    roles={k:v for k,v in ds.mapping.items() if v in ds.col_indexes}
    extra={'supplier_id':('supplier','vendor'),'destination_state':('region',),'item_id':('item','product')}
    for role in ('supplier_id','destination_state','item_id','order_id','required_units','unit_cost','actual_delivery_timestamp','promised_delivery_date'):
        if role in roles: continue
        names=set(ROLE_ALIASES.get(role,()))|set(extra.get(role,()))
        matches=[c for c in ds.columns if _normalized_header(c) in names and c not in roles.values()]
        if len(matches)==1: roles[role]=matches[0]
    return roles


def _currency(ds,roles):
    columns=[c for c in ds.columns if _normalized_header(c) in {'currency','currency_code','currency_iso','purchase_currency','unit_cost_currency','cost_currency'}]
    if not columns: return 'unspecified',True
    if len(columns)!=1: return 'ambiguous currency fields',False
    i=ds.col_indexes[columns[0]]
    codes={r[i].strip().upper() for r in ds.rows}
    if len(codes)==1 and next(iter(codes)) and re.fullmatch(r'[A-Z]{3}',next(iter(codes))):
        return 'recorded '+next(iter(codes)),True
    return 'mixed, missing or unrecognized currencies',False

def _number(value):
    # Existing numeric parser accepts thousands separators; do not invent zeros.
    # Bound magnitude before arithmetic to keep processing and display finite.
    n=numeric(value)
    return n if n is not None and abs(n)<=Decimal('1e15') else None

def _money(n):
    return format(n,',.2f') if n is not None else 'n/a'

def _label(value):
    s=re.sub(r'[\x00-\x1f\x7f]',' ',str(value))[:100]
    return re.sub(r'([\\`*{}\[\]()<>|_#])',r'\\\1',s)

def _group(ds,dimension):
    roles=_roles(ds)
    col=roles.get(GROUPS[dimension]); actual=roles.get('actual_delivery_timestamp'); promise=roles.get('promised_delivery_date')
    if not col or not actual or not promise: return None
    qcol=roles.get('required_units'); ccol=roles.get('unit_cost'); oid=roles.get('order_id')
    ix=ds.col_indexes
    currency,cost_comparable=_currency(ds,roles)
    ids=[r[ix[oid]] for r in ds.rows] if oid else []
    unit='orders' if ids and all(ids) and len(set(ids))==len(ids) else 'source rows'
    groups=defaultdict(lambda: {'rows':0,'comparable':0,'late':0,'early':0,'on_date':0,'missing_pair':0,'invalid_pair':0,'quantity':Decimal(0),'quantity_rows':0,'cost':Decimal(0),'cost_rows':0})
    missing=0
    with localcontext() as ctx:
        ctx.prec=50
        for row in ds.rows:
            key=row[ix[col]]
            if not key: missing+=1; continue
            g=groups[key];g['rows']+=1
            # Financial and volume eligibility is independent of delivery dates.
            q=_number(row[ix[qcol]]) if qcol else None
            c=_number(row[ix[ccol]]) if ccol else None
            if q is not None: g['quantity']+=q;g['quantity_rows']+=1
            if q is not None and c is not None: g['cost']+=q*c;g['cost_rows']+=1
            av,pv=row[ix[actual]],row[ix[promise]]
            if not av or not pv: g['missing_pair']+=1;continue
            a,p=_date(av),_date(pv)
            if not a or not p: g['invalid_pair']+=1;continue
            g['comparable']+=1
            g['late' if a.date()>p.date() else 'early' if a.date()<p.date() else 'on_date']+=1
    if not groups: return None
    return {'dimension':dimension,'field':col,'unit':unit,'source_rows':len(ds.rows),'excluded_blank_group':missing,'quantity_mapped':bool(qcol),'cost_mapped':bool(qcol and ccol),'groups':dict(groups),'currency':currency,'cost_comparable':cost_comparable,'provisional_roles':{k:v for k,v in roles.items() if k not in ds.mapping}}

def _rate(g):
    return f"{g['late']}/{g['comparable']} ({float(Fraction(g['late'],g['comparable'])*100):.1f}%)" if g['comparable'] else 'n/a (no comparable dates)'

def _scope_is_broad(ds,q,dimension):
    # Precomputed profile must never replace a filtered analysis. Named group
    # values, specific time periods, conditions, or chart requests go to SQL.
    if re.search(r'\b(chart|plot|graph|visuali[sz]e|scatter|correlation|where|excluding|except|only|between|since|during|before|after|from|in)\b',q):
        # Allow common harmless phrases describing the full dataset.
        remainder=re.sub(r'\b(?:in|from) (?:the |this |our |my )?(?:uploaded )?(?:dataset|data|file|records)\b','',q)
        if re.search(r'\b(chart|plot|graph|visuali[sz]e|scatter|correlation|where|excluding|except|only|between|since|during|before|after|from|in)\b',remainder): return False
    if re.search(r'\b(above|below|under|greater|less|at least|at most|filter(?:ed)?|last|previous|monthly|quarterly|yearly|quarter|lead time|delay duration|average delay|maximum delay|forecast|predict|trend)\b',q): return False
    if re.search(r'\b(?:20\d{2}|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b',q): return False
    # Do not silently discard a named group or filter on a different dimension.
    for role in ('supplier_id','destination_state','item_id'):
        c=_roles(ds).get(role)
        if c not in ds.col_indexes: continue
        for value in {r[ds.col_indexes[c]] for r in ds.rows if r[ds.col_indexes[c]]}:
            if len(value)>=2 and value.casefold() in q and re.search(r'(?<!\w)'+re.escape(value.casefold())+r'(?!\w)',q): return False
    return True

def requested_cohort(ds,question,history=()):
    q=' '.join(str(question).casefold().split())
    # Follow-up has an explicit action intent and prior checked cohort context.
    if history and re.search(r'\b(avoid|precautions?|next transaction|next order|next purchase|mitigate|what should (?:we|i|management) do)\b',q) and not re.search(r'\b(chart|graph|plot|forecast|predict)\b',q):
        last=history[-1]
        dim=last.get('cohort_dimension')
        if dim in GROUPS and not re.search(r'\b(?:only|excluding|except|between|where|in 20\d{2})\b',q):
            if _scope_is_broad(ds,re.sub(r'\b(?:from|for|before|in) (?:the )?next (?:transaction|order|purchase)\b','',q),dim): return dim,'next_action'
    # Direct multi-metric group comparison is a domain tool, not a phrase-specific answer.
    matches=[d for d,pattern in [('supplier',r'\b(suppliers?|vendors?)\b'),('region',r'\b(regions?|destinations?)\b'),('item',r'\b(items?|products?|skus?)\b')] if re.search(pattern,q)]
    if len(matches)!=1:return None
    dim=matches[0]
    if not _scope_is_broad(ds,q,dim): return None
    delivery=bool(re.search(r'\b(delivery|deliveries|late|lateness|on.time|reliability)\b',q))
    comparison=bool(re.search(r'\b(compare|comparison|each|per|by|across|performance|investigate|worst|best|risk)\b',q))
    mixed=bool(re.search(r'\b(quantity|quantities|units|cost|costs|spend|spending|volume|purchase)\b',q))
    # Single rankings and chart requests remain in the existing AI SQL engine.
    if delivery and comparison and (mixed or re.search(r'\b(compare|each|across|performance|investigate)\b',q)):
        return dim,'comparison'
    return None

def checked_cohort(ds,dimension,mode='comparison'):
    p=_group(ds,dimension)
    if p is None: return None
    groups=p['groups']; unit=p['unit']; shown=sorted(groups,key=lambda k:(-groups[k]['rows'],k))[:MAX_GROUPS]
    if mode=='next_action':
        lines=['**Before the next transaction:**',
               '- Avoid changing allocation, cancelling orders, or excluding a supplier solely because of a small historical sample.',
               '- Avoid assuming that a missing delivery date means the order was on time or late. Reconcile the outstanding or missing status first.',
               '- Avoid treating purchase cost as the financial loss from delays. Verify current capacity, lead times, price/currency and the actual cost of a delay before committing.',
               '- Request updated delivery commitments and investigate recorded delays; obtain human approval for any sourcing decision.']
    else:
        lines=[f'**{dimension.title()} comparison — verified calculations**',f'Coverage: {p["source_rows"]:,} source rows. Totals use all rows with the group recorded; delivery rates use only valid actual/promised calendar-date pairs. {p["excluded_blank_group"]:,} rows with blank group values are excluded from the grouped table.',
               f'| {dimension.title()} | {unit.title()} | Comparable deliveries | Late rate | Ordered units (valid rows) | Quantity × unit cost (valid rows) |', '|---|---:|---:|---:|---:|---:|']
        for k in shown:
            g=groups[k];qty=_money(g['quantity'])+f" ({g['quantity_rows']})" if g['quantity_rows'] else 'n/a';cost=_money(g['cost'])+f" ({g['cost_rows']})" if g['cost_rows'] and p['cost_comparable'] else 'n/a'
            lines.append(f"| {_label(k)} | {g['rows']} | {g['comparable']} | {_rate(g)} | {qty} | {cost} |")
        lines.extend(['','Currency: '+p['currency']+'. '+('Cost totals are not combined across ambiguous currencies. ' if not p['cost_comparable'] else '')+'Cost is the sum of valid quantity × unit-cost products, not observed financial loss from delay. Missing or invalid date pairs do not remove otherwise valid units or costs. Valid-row counts expose incomplete measures; partial sums are not complete totals.'])
        if unit!='orders': lines.append('Order identifiers are missing or repeated; these are record-level counts and sums, not deduplicated order-level KPIs. Confirm row grain before using them as order totals.')
    if p['provisional_roles']: lines.append('Field meanings are provisional where inferred from unambiguous headers; confirm mappings and units before business use.')
    if len(groups)>MAX_GROUPS: lines.append(f'Only {MAX_GROUPS} of {len(groups)} groups are shown; all eligible rows were aggregated. No overall unique priority is inferred from the bounded display.')
    else:
        eligible=[(k,g) for k,g in groups.items() if g['comparable']]
        if eligible:
            highest=max(Fraction(g['late'],g['comparable']) for k,g in eligible)
            leaders=[(k,g) for k,g in eligible if Fraction(g['late'],g['comparable'])==highest]
            if highest==0: lines.append('No late deliveries were observed among the comparable groups; missing outcomes still need review.')
            lines.append('**Highest observed late rate:** '+ '; '.join(f"{_label(k)}: {_rate(g)} late, {g['rows']-g['comparable']} of {g['rows']} {unit} without comparable dates" for k,g in leaders[:8])+('. Additional tied groups not listed.' if len(leaders)>8 else '.'))
            if any(g['comparable']<5 or g['comparable']<g['rows'] for k,g in leaders): lines.append('The highest observed rate is based on limited or incomplete comparable deliveries; it is not evidence of a systematic reliability problem. Review the missing records and gather more observations before drawing a supplier-performance conclusion.')
            else: lines.append('These observed rates are descriptive; even a high rate does not establish the cause of delays or future performance.')
        exposure=[(k,g) for k,g in groups.items() if g['cost_rows'] and g['cost_rows']==g['rows']]
        if p['cost_comparable'] and exposure and len(exposure)==len(groups):
            high=max(g['cost'] for k,g in exposure); names=[_label(k) for k,g in exposure if g['cost']==high]
            lines.append('**Recorded purchase exposure:** '+', '.join(names[:8])+' '+('share' if len(names)>1 else 'has')+' the highest recorded quantity × unit-cost total ('+_money(high)+', currency '+p['currency']+'). This is potential exposure, not measured delay loss.')
        if mode!='next_action': lines.append('**Management priority:** Review groups with recorded delays and high purchase exposure, reconcile incomplete delivery records, and verify delay causes and current commitments. Do not suspend or reallocate orders based on these descriptive figures alone.')
    # JSON-safe bounded numeric evidence; model never needs full source rows.
    data=[{'group':k[:100],**{a:(None if a=='cost' and not p['cost_comparable'] else str(v) if isinstance(v,Decimal) else v) for a,v in groups[k].items()}} for k in shown]
    return {'kind':'cohort_analysis','dimension':dimension,'mode':mode,'answer':'\n\n'.join(lines[:2])+ '\n\n'+'\n'.join(lines[2:]) if mode=='comparison' else '\n'.join(lines),'groups':data,'source_rows':p['source_rows'],'group_count':len(groups),'excluded_blank_group':p['excluded_blank_group'],'unit':unit,'currency':p['currency'],'cost_comparable':p['cost_comparable']}
