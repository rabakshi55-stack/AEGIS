"""Read-only focused descriptions: field profiles and mapped delivery comparisons.

No model-generated figures, source row exposure, mutation or causal inference.
Narrow unqualified requests only; filters/group comparisons belong to the planner.
"""
from collections import Counter, defaultdict
from statistics import median
import re


def _norm(s):
    return re.sub(r'[^\w]+', ' ', str(s).casefold().replace('_',' ')).strip()


def _label(s):
    return re.sub(r'[\x00-\x1f\x7f]+',' ',str(s))[:100]


def _fmt(x):
    return f'{x:,.2f}'.rstrip('0').rstrip('.') if x % 1 else f'{int(x):,}'


def _pct(n,d):
    return f'{100*n/d:.1f}%' if d else 'not available'


def _unique_order_rows(ds):
    col = ds.mapping.get('order_id')
    if col not in ds.col_indexes:
        return False
    ids = [r[ds.col_indexes[col]] for r in ds.rows]
    return all(ids) and len(set(ids)) == len(ids)


def _delivery(ds, trend=False, requested="within"):
    from intake import _date
    actual = ds.mapping.get('actual_delivery_timestamp')
    promise = ds.mapping.get('promised_delivery_date')
    purchase = ds.mapping.get('purchase_timestamp')
    if actual not in ds.col_indexes or promise not in ds.col_indexes:
        return {'kind':'delivery','answer':'To compare delivery performance, map the actual and promised delivery date fields in Data. Missing delivery dates cannot be classified as early, on time or late.'}
    ai, pi = ds.col_indexes[actual], ds.col_indexes[promise]
    oi = ds.col_indexes.get(purchase)
    counts=Counter(); months=defaultdict(Counter); actual_months=Counter(); dates=[]
    undated_order=0
    for row in ds.rows:
        a,p = _date(row[ai]), _date(row[pi])
        o = _date(row[oi]) if oi is not None else None
        if a:
            dates.append(a.date()); actual_months[a.strftime('%Y-%m')] += 1
        if not row[ai]: status='missing_actual'
        elif not row[pi]: status='missing_promise'
        elif a is None or p is None: status='invalid_pair'
        elif a.date() < p.date(): status='early'
        elif a.date() > p.date(): status='late'
        else: status='on_date'
        counts[status]+=1
        if o: months[o.strftime('%Y-%m')][status]+=1
        else: undated_order+=1
    unit='orders' if _unique_order_rows(ds) else 'source rows'
    early,ontime,late=(counts[k] for k in ('early','on_date','late'))
    comp=early+ontime+late; n=len(ds.rows)
    # The two explicit business meanings of "according to promised date".
    if comp:
        intro=(f'{early+ontime:,} of {comp:,} comparable {unit} ({_pct(early+ontime,comp)}) were delivered on or before the promised date: '
               f'{early:,} early and {ontime:,} on the exact promised calendar date. '
               f'{late:,} were late ({_pct(late,comp)}).')
    else:
        intro='No comparable recorded actual/promised date pairs are available; delivery performance cannot be calculated.'
    if comp and requested == 'exact':
        intro=f'{ontime:,} of {comp:,} comparable {unit} ({_pct(ontime,comp)}) were delivered on the exact promised calendar date. '+intro
    elif comp and requested == 'late':
        intro=f'{late:,} of {comp:,} comparable {unit} ({_pct(late,comp)}) were delivered after the promised date. '+intro
    lines=[intro, f'Coverage: {n:,} {unit}; {sum(not row[ai] for row in ds.rows):,} missing actual delivery dates; '
           f'{sum(not row[pi] for row in ds.rows):,} missing promised dates; {counts["invalid_pair"]:,} nonblank but invalid date pairs. Missing or invalid pairs are excluded from the rate, not counted as on time.']
    if dates:
        lines.append(f'Actual delivery dates span {min(dates).isoformat()} to {max(dates).isoformat()} ({len(dates):,} valid recorded actual dates).')
    if trend:
        if months:
            shown=sorted(months)[-24:]
            lines.append(f'Delivery performance by order month (grouped by {_label(purchase)}; last {len(shown)} observed months):')
            rates=[]
            for month in shown:
                c=months[month]; k=c['early']+c['on_date']+c['late']; unknown=sum(c.values())-k
                lines.append(f'{month}: {sum(c.values()):,} {unit}; {c["early"]:,} early, {c["on_date"]:,} exactly on date, {c["late"]:,} late; {k:,} comparable; {unknown:,} not comparable. Late rate: {_pct(c["late"],k)}.')
                rates.append((month,c['late'],k,unknown))
            if len(shown)<len(months): lines.append('Earlier observed months are not displayed; overall counts above cover the full dataset.')
            if undated_order: lines.append(f'{undated_order:,} {unit} lack a usable order date and cannot be assigned to a month.')
            comparable=[(m,l,k,u) for m,l,k,u in rates if k]
            if len(comparable)>=2:
                from fractions import Fraction
                values=[Fraction(l,k) for m,l,k,u in comparable]
                if all(v==values[0] for v in values): movement='The observed late rate is unchanged across comparable displayed months.'
                elif all(x<=y for x,y in zip(values,values[1:])): movement='The observed late rate is non-decreasing across comparable displayed months.'
                elif all(x>=y for x,y in zip(values,values[1:])): movement='The observed late rate is non-increasing across comparable displayed months.'
                else: movement='The observed late rate fluctuates across comparable displayed months.'
                lines.append(movement)
                if any(k<5 or u for m,l,k,u in rates): lines.append('At least one displayed month has fewer than five comparable records or incomplete date pairs. Treat this as descriptive variation, not reliable evidence of improved or worsening performance.')
            else: lines.append('There are fewer than two comparable months; no delivery-performance trend can be assessed.')
        else:
            lines.append('A usable mapped order date is required for a performance trend by order month.')
        if actual_months:
            shown=sorted(actual_months)[-24:]
            lines.append('Recorded deliveries by actual delivery month (observed dates only): '+ '; '.join(f'{m}: {actual_months[m]:,}' for m in shown)+'.')
            if len(shown)<len(actual_months): lines.append('Only the last 24 observed actual-delivery months are displayed.')
        lines.append('Unobserved months are not assumed to have zero deliveries.')
    lines.append('Calendar-date comparisons use the mapped source fields. They are descriptive, not independently verified contractual KPIs or proof of supplier causality.')
    return {'kind':'delivery_trend' if trend else 'delivery','answer':'\n\n'.join(lines),'comparable':comp,'early':early,'on_date':ontime,'late':late,'months':{m:dict(months[m]) for m in sorted(months)[-24:]}}


def _field(ds,col):
    from intake import _date
    from dataset_queries import numeric
    values=[r[ds.col_indexes[col]] for r in ds.rows]; present=[v for v in values if v]; n=len(values)
    lines=[f"'{_label(col)}': {len(present):,} populated of {n:,} source rows; {n-len(present):,} blanks ({_pct(n-len(present),n)})."]
    if not present: return {'kind':'field_profile','answer':lines[0]+' No nonblank values are available to analyze.'}
    dates=[_date(v) for v in present]
    numbers=[numeric(v) for v in present]
    # Mapped identifiers are not numeric measures even if their text consists of digits.
    identifier=col in {ds.mapping.get(k) for k in ('order_id','supplier_id','item_id')} or bool(re.search(r'\b(id|code|reference|identifier)\b',_norm(col)))
    if all(d is not None for d in dates):
        days=[d.date() for d in dates]; counts=Counter(d.strftime('%Y-%m') for d in dates); shown=sorted(counts)[-24:]
        lines.append(f'Valid recorded dates range from {min(days).isoformat()} to {max(days).isoformat()}.')
        lines.append('Records by this date field’s observed month: '+ '; '.join(f'{m}: {counts[m]:,}' for m in shown)+'. Missing months are not inferred to be zero.')
        if len(shown)<len(counts): lines.append('Only the last 24 observed months are shown.')
    elif not identifier and all(v is not None for v in numbers):
        lines.append(f'Numeric values: minimum {_fmt(min(numbers))}; maximum {_fmt(max(numbers))}; mean {_fmt(sum(numbers)/len(numbers))}; median {_fmt(median(numbers))}. Units and business meaning are not independently verified.')
    else:
        counts=Counter(present); high=max(counts.values()); leaders=sorted(k for k,v in counts.items() if v==high)
        lines.append(f'{len(counts):,} distinct nonblank recorded values. Highest frequency: {high:,} each, shared by {len(leaders):,} value(s). '+ '; '.join(_label(v) for v in leaders[:8])+('. Additional tied values are not displayed.' if len(leaders)>8 else '.'))
    return {'kind':'field_profile','answer':'\n\n'.join(lines)}


def focused_analysis(ds,question):
    """Recognize unqualified descriptive intent, never swallow filters or comparisons.

    Hosted mode still uses the LLM for interpretation and other analytical plans.
    """
    q=_norm(question)
    if not q: return None
    # Restrict the precomputed delivery tool to unqualified descriptions.
    # Other questions (e.g. "delivery trend in West") go to the planner; a
    # full-dataset answer must not silently discard a subgroup or date filter.
    delivery_topic=r'(?:delivery(?: data| dates?| performance| delays?| lateness| column| field)?|deliveries|late deliveries|on time deliveries)'
    prefix=r'(?:can (?:you|u) |could (?:you|u) |please |tell me )?'
    trend_forms=(
        prefix+r'(?:analy[sz]e|describe|explain|show|summari[sz]e) (?:the )?(?:trend(?:s)? (?:in|of) (?:the )?'+delivery_topic+'|'+delivery_topic+r' trend(?:s)?|'+delivery_topic+r' over time)',
        r'what (?:is|are) (?:the )?(?:trend(?:s)? (?:in|of) (?:the )?'+delivery_topic+'|'+delivery_topic+r' trend(?:s)?)',
        r'what (?:does|do) (?:the )?'+delivery_topic+r' trend(?:s)? (?:say|show|mean)',
        r'(?:'+delivery_topic+r') (?:by|per) month',
        r'how (?:has|have|is|are) (?:the )?'+delivery_topic+r' (?:changed|changing|trending)(?: over time)?',
    )
    tail=r'(?: in (?:the|this|my|our) (?:data|dataset|upload|file))?'
    if any(re.fullmatch(form+tail,q) for form in trend_forms):
        return _delivery(ds,True)
    count_match=re.fullmatch(r'(?:tell me |can (?:you|u) tell me )?(?:how many|number of|what percentage of) (?:orders|deliveries|records|rows) (?:were |are )?(?:fulfilled|delivered|completed) (according to|on|on or before|before or on|by|after) (?:the )?(?:promised|promise|expected) (?:delivery )?date'+tail,q)
    if count_match:
        relation=count_match.group(1)
        return _delivery(ds, requested='exact' if relation=='on' else 'late' if relation=='after' else 'within')
    if re.fullmatch(r'(?:what (?:does|do) (?:the )?|tell me about (?:the )?|describe (?:the )?|analy[sz]e (?:the )?|explain (?:the )?)'+delivery_topic+r'(?: (?:say|show|mean|tell me))?'+tail,q):
        return _delivery(ds)
    # Exact, single-field descriptions: do not interpret a list of headers as a data question.
    m=re.fullmatch(r'(?:what does (?:the )?(.+?) (?:column|field) (?:say|show|mean)|(?:describe|summari[sz]e|profile|explain|analy[sz]e) (?:the )?(.+?) (?:column|field)|(?:describe|summari[sz]e|profile) (?:the )?(?:column|field) (.+))',q)
    if m:
        target=next(g for g in m.groups() if g is not None)
        matches=[c for c in ds.columns if _norm(c)==target]
        if len(matches)==1: return _field(ds,matches[0])
    return None
