"""Source-recomputed descriptions of automatic and manager-created charts.

Never trust chart measurements, titles or data sent by the browser: an accepted
catalog contains only selectors/specifications, re-evaluated against the active
in-memory dataset. Neither the offline answer nor optional Qwen may claim
causality or certified operational performance from descriptive visualizations.
"""
from math import isfinite
import re

MAX_CHARTS = 17


def is_chart_question(question, focus=None, history=None):
    q = str(question or '').casefold().strip()
    if re.search(r'\b(chart|charts|plot|plots|visuali[sz]ation|visual|graph|graphs|figures?|depictions?|bars?|line|trend|axis|axes|donut|pie|scatter|histogram|depict|dashboard)\b', q):
        return True
    if focus and re.search(r'\b(this|that|these|those|it|shown|showing|highest|lowest|peak|dip|drop|rise|why|compare|explain|interpret|meaning|figure|pattern|difference|change|what do you make|what stands out|how did you calculate)\b', q):
        if re.search(r'\b(this|that|these|those)\b', q) and re.search(
            r'\b(dataset|data file|file|rows|records|spreadsheet|upload)\b', q
        ) and not re.search(r'\b(chart|figure|graph|plot|visuali[sz]ation)\b', q):
            return False
        return True
    if history and any(re.search(r'\b(chart|visuali[sz]ation|plot|graph)\b', str(h.get('question','')).casefold()) for h in history[-2:]):
        return bool(re.search(r'\b(?:this|that|the previous|the same) (?:chart|graph|plot|figure|visual|axis|bar|line)\b|\b(?:explain|interpret|describe) (?:it|that|this)\b|^(?:why|how)\s+(?:is|does|was|did)\s+(?:it|that|this)\b|^(?:what|how) about (?:it|that|this)\b', q))
    return False


def _load_catalog(dataset, catalog):
    from adaptive_charts import recommend
    from custom_charts import build_chart
    if not isinstance(catalog, list) or len(catalog) > MAX_CHARTS:
        raise ValueError('Chart references must be a list of at most 17 currently visible charts.')
    recommended = {c['id']: c for c in recommend(dataset)['charts']}
    seen = set()
    charts = []
    for entry in catalog:
        if not isinstance(entry, dict) or set(entry) - {'key','kind','id','options'}:
            raise ValueError('Invalid chart reference.')
        key = entry.get('key')
        kind = entry.get('kind')
        if not isinstance(key, str) or not 1 <= len(key) <= 80 or key in seen:
            raise ValueError('Duplicate or invalid chart reference.')
        seen.add(key)
        if kind == 'automatic':
            if set(entry) - {'key','kind','id'}:
                raise ValueError('Automatic chart references accept an ID only.')
            ident = entry.get('id')
            if not isinstance(ident, str) or ident not in recommended:
                raise ValueError('The recommended chart is not available for this upload.')
            source = recommended[ident]
            item = {'key':key, 'kind':'automatic', 'title':source['title'], 'type':source['type'],
                    'x':list(source['source_columns']), 'y':source['value_label'],
                    'reason':source['reason'], 'caution':source['caution'],
                    'selection_basis':source['selection_basis'],
                    'values':[{'label':str(v['label']), 'value':v['count'],
                               **({'comparable_rows':v['comparable_rows']} if 'comparable_rows' in v else {}),
                               **({'after_date_rows':v['after_date_rows']} if 'after_date_rows' in v else {}),
                               **({'remainder':True} if v.get('remainder') else {}),
                               **({'exact_value':v['exact_value']} if 'exact_value' in v else {})}
                              for v in source['values']],
                    'source_rows':len(dataset.rows), 'truncated': False,
                    'source_note':'This chart is a bounded, automatically selected display; category grouping and time windows can omit other groups.',
                    'is_percent': '(%)' in source.get('value_label', '')}
        elif kind == 'custom':
            if set(entry) - {'key','kind','options'}:
                raise ValueError('Custom chart references accept a specification only.')
            data = build_chart(dataset, entry.get('options'))
            item = {'key':key, 'kind':'custom', 'title': f"{data['y'] or 'Record count'} by {data['x']}",
                    'type':data['chart_type'], 'x':[data['x']],
                    'y':data['y'] or 'record count', 'aggregation':data['aggregation'],
                    'date_grain':data['date_grain'], 'sort':data['sort'],
                    'caution':data['caution'], 'source_note':data['note'],
                    'values':data.get('values',[]), 'points':data.get('points',[]),
                    'source_rows':data['source_rows'], 'valid_rows':data.get('valid_rows',0),
                    'excluded_x_rows':data.get('excluded_x_rows',0),
                    'excluded_y_rows':data.get('excluded_y_rows',0),
                    'truncated':data.get('truncated',False), 'is_percent':False}
        elif kind == 'cohort_scatter':
            if set(entry) - {'key','kind','options'}: raise ValueError('Derived chart references accept a specification only.')
            from cohort_analysis import build_cohort_scatter
            data=build_cohort_scatter(dataset,entry.get('options'))
            item={'key':key,'kind':kind,'title':data['title'],'type':'scatter','x':[data['x']], 'y':data['y'],'aggregation':'grouped measures','points':data['points'],'values':[],'source_rows':data['source_rows'],'source_note':data['note'],'caution':data['caution'],'truncated':False,'is_percent':False}
        else:
            raise ValueError('Unsupported chart reference.')
        charts.append(item)
    return charts


def _fmt(value):
    n = float(value)
    if not isfinite(n):
        raise ValueError('Chart contains invalid numeric values.')
    from dataset_queries import display_number
    return display_number(value)


def _measure(chart):
    if chart['kind'] == 'automatic':
        return str(chart['y'])
    if chart['kind']=='cohort_scatter': return str(chart['y'])
    agg = str(chart['aggregation']).replace('_',' ')
    y = chart['y']
    return f'{agg} of {y}' if y != 'record count' else 'count of source records'


def _overview(chart, question):
    title, typ = chart['title'], chart['type']
    q = str(question).casefold()
    axis = ', '.join(chart['x'])
    prelude = (f'**{title}** is a {typ.replace("_"," ")} chart of {_measure(chart)} '
               f'grouped or plotted using {axis}. It is computed from the current uploaded dataset, not the archived Olist research.')
    source = chart.get('source_note','')
    caution = chart['caution']
    if typ == 'scatter':
        coords = chart.get('points',[])
        if not coords:
            return prelude + ' No numeric coordinates could be displayed. ' + source + ' ' + caution
        xs = [float(p['x']) for p in coords]
        ys = [float(p['y']) for p in coords]
        detail = (f'The {len(coords):,} displayed numeric pairs range from {_fmt(min(xs))} to {_fmt(max(xs))} on X '
                  f'and {_fmt(min(ys))} to {_fmt(max(ys))} on Y. ')
        if chart['kind']=='cohort_scatter':
            detail += 'Each point represents a group, not a source row. ' + '; '.join(f"{p['label']}: X={_fmt(p['x'])}, late={p['late']}/{p['comparable']}, total records={p['total']}" for p in coords[:12]) + ('. Additional groups not listed. ' if len(coords)>12 else '. ')
        if chart['truncated']:
            detail += 'These are the first bounded valid pairs, not a random sample; do not infer a dataset-wide relationship. '
        return prelude + ' ' + detail + source + ' ' + caution
    values = chart.get('values') or []
    if not values:
        return prelude + ' No displayable groups are present. ' + source + ' ' + caution
    from decimal import Decimal
    points = [(str(v['label']),Decimal(str(v.get('exact_value',v['value'])))) for v in values if not v.get('remainder')]
    if not points: return prelude + ' No individually displayed groups. ' + source + ' ' + caution
    high=max(v for _,v in points); low=min(v for _,v in points)
    highs=[k for k,v in points if v==high]; lows=[k for k,v in points if v==low]
    high_label=', '.join(highs[:8])+(' and additional tied groups' if len(highs)>8 else '')
    low_label=', '.join(lows[:8])+(' and additional tied groups' if len(lows)>8 else '')
    vals = {key.casefold():(key,value) for key,value in points}
    explicit = next(((key,val) for key,val in points if key.casefold() in q and len(key) >= 2), None)
    if explicit:
        group_detail = f'The displayed group **{explicit[0]}** is {_fmt(explicit[1])}. '
    else:
        group_detail = ''
    if chart['is_percent']:
        detail = (f'The highest displayed share is **{high_label}** at {_fmt(high)}%; '
                  f'the lowest is **{low_label}** at {_fmt(low)}%. ')
    else:
        detail = (f'Of the {len(points)} displayed groups, **{high_label}** is highest at {_fmt(high)} '
                  f'and **{low_label}** lowest at {_fmt(low)}. ')
    if any(v.get('remainder') for v in values):
        detail += 'The remainder bar combines multiple categories; it is not a single group and is excluded from the individual extrema. '
    if len(points) > 1:
        detail += (f'The difference between those displayed values is {_fmt(high-low)} ' + ('percentage points' if chart['is_percent'] else 'in the displayed measure') + '. ')
    if chart['type'] in {'line','area'} and len(points)>1:
        first, last=points[0],points[-1]
        delta=last[1]-first[1]
        detail += (f'In chart display order, {first[0]} is {_fmt(first[1])} and '
                   f'{last[0]} is {_fmt(last[1])} (change {_fmt(delta)}). ')
        if chart['kind']=='custom' and chart.get('sort') not in ('x_asc','x_desc'):
            detail += 'This chart is not sorted by date; do not interpret that change as a chronological trend. '
    if chart['kind']=='automatic' and chart['is_percent'] and len(highs)==1:
        high_record=next((v for v in values if v['label']==high_label),{})
        if 'comparable_rows' in high_record and 'after_date_rows' in high_record:
            detail+=(f'That largest displayed percentage represents {_fmt(high_record["after_date_rows"])} '
                     f'out of {_fmt(high_record["comparable_rows"])} comparable source records. ')
    if 'percent' in q or 'share' in q:
        if not chart['is_percent'] and chart.get('aggregation') in ('count','sum','count_nonblank') and all(v >= 0 for _,v in points):
            visible_sum = sum(Decimal(str(v.get('exact_value',v['value']))) for v in values)
            if visible_sum:
                detail += (f'{high_label} '+('each account' if len(highs)>1 else 'accounts')+f' for {_fmt(100*high/visible_sum)}% of the sum of *displayed* values; '
                           'that is not necessarily the whole dataset share. ')
    if chart.get('truncated'):
        detail += 'Some chart groups or rows are not displayed; do not treat the visible extremes as full-dataset extremes. '
    if re.search(r'\b(why|cause|reason|responsib|fault|predict|recommend|best supplier)\b',q):
        detail += ('The chart describes a pattern; it cannot establish its cause, forecast a future outcome, '
                   'or prove which supplier is responsible. Investigate the original records and possible confounders before acting. ')
    if re.search(r'\b(how|calculated|formula|axis|axes|field|source|method|aggregate)\b',q):
        detail += f'The displayed measure is {_measure(chart)}; source columns: {axis}. '
        if chart.get('date_grain') and chart['date_grain']!='none':
            detail+=f'Dates are grouped by {chart["date_grain"]}. '
    if re.search(r'\b(each|every|all values|all bars|list|underlying|data points|exact values|table of values)\b',q):
        subset=points[:20]
        detail+='Displayed values: '+ '; '.join(f'{k}: {_fmt(v)}'+('%' if chart['is_percent'] else '') for k,v in subset)+'. '
        if len(points)>len(subset):
            detail+=f'Only the first {len(subset)} of {len(points)} displayed groups are listed here. '
    if explicit:
        detail=group_detail+detail
    if chart['kind']=='custom':
        detail += (f'The chart used {chart.get("valid_rows",0):,} contributing records out of '
                   f'{chart["source_rows"]:,}; excluded X rows: {chart.get("excluded_x_rows",0):,}; '
                   f'excluded Y rows: {chart.get("excluded_y_rows",0):,}. ')
    return prelude + ' ' + detail + source + ' ' + caution


def answer_for_charts(dataset, question, catalog, focus=None, *, dataset_revision=None, current_revision=None, history=None):
    """Return checked answer + bounded facts, or None if a different analysis is requested.

    No source row is ever accepted from or returned to the browser. Chart definitions
    are re-executed on the server. A mismatched dataset revision is a hard failure.
    """
    if dataset_revision != current_revision or type(dataset_revision) is not int:
        raise ValueError('Chart context belongs to another dataset. Reload Visualizations and try again.')
    if focus is not None and (not isinstance(focus,str) or len(focus)>80):
        raise ValueError('Invalid selected chart.')
    if not is_chart_question(question, focus, history):
        return None
    charts = _load_catalog(dataset,catalog)
    if not charts:
        return None
    selected = next((c for c in charts if c['key']==focus),None)
    if focus and not selected:
        raise ValueError('Selected chart is not available for the current dataset. Please choose it again.')
    if selected is None:
        # Respond to a clearly named chart even without the user clicking its Ask button.
        qwords=set(re.findall(r'[a-z0-9]+',str(question).casefold())) - {'what','does','the','this','chart','show','about','that','graph','please','explain'}
        matches=[]
        for c in charts:
            words=set(re.findall(r'[a-z0-9]+',c['title'].casefold()))
            matches.append((len(words & qwords),c))
        if matches and max(score for score,_ in matches)>=2:
            selected=max(matches,key=lambda p:p[0])[1]
    if selected:
        message = _overview(selected,question)
        used=[selected]
        if re.search(r'\b(compare|comparison|versus|vs|against|another chart|other chart)\b',str(question).casefold()):
            others=[c for c in charts if c['key']!=selected['key']]
            if others:
                other=others[0]
                message += ('\n\n**Second chart for context:** ' + _overview(other,question) +
                            '\n\nThese charts may measure different quantities, so do not infer that one is better '
                            'or higher in a comparable business sense without matching units and definitions.')
                used.append(other)
    elif len(charts)==1:
        used=charts
        message=_overview(charts[0],question)
    else:
        used=charts[:MAX_CHARTS]
        summaries=[]
        for item in used:
            vals=[v for v in item.get('values',[]) if not v.get('remainder')]
            if vals:
                from decimal import Decimal
                peak=max(Decimal(str(v.get('exact_value',v['value']))) for v in vals)
                leaders=[str(v['label']) for v in vals if Decimal(str(v.get('exact_value',v['value'])))==peak]
                names=', '.join(leaders[:8])+(' and additional tied groups' if len(leaders)>8 else '')
                summaries.append(f"**{item['title']}** ({item['kind']} {item['type']}): {'tied top displayed groups' if len(leaders)>1 else 'top displayed group'} {names} = {_fmt(peak)}{'%' if item['is_percent'] else ''}")
            else:
                summaries.append(f"**{item['title']}** ({item['kind']} {item['type']}): {len(item.get('points',[]))} displayed points")
        message=(f'Your current uploaded dataset has {len(used)} charts available for discussion. '
                 + '; '.join(summaries) + '. Choose **Ask AEGIS** on a chart or select it in the Copilot to inspect axes, calculations, missing data, and limitations in detail. '
                 'Different measures cannot be compared directly without checking their definitions.')
    trusted_facts={
        'file_rows':len(dataset.rows),'file_columns':len(dataset.columns),
        'dataset_name':dataset.filename,'chart_context':'SERVER_RECOMPUTED_CURRENT_DATASET',
        'selected_chart':selected['key'] if selected else None,
        'chart_source_facts':[{**c, 'values':c.get('values',[])[:25], 'points':c.get('points',[])[:20]} for c in used[:2]] if selected else [{k:v for k,v in c.items() if k not in ('values','points')} for c in used[:5]],
        'no_operational_actions':True, 'chart_information_is_descriptive_not_causal':True,
    }
    result={
        'answer':message,'context':'local_dataset','evidence_source':'VERIFIED_CURRENT_DATASET_CHART',
        'routing_mode':'OFFLINE_VERIFIED_CHART_INTERPRETATION','operational_approval':'NOT_GRANTED',
        'permitted_action':'NONE','human_review':'REQUIRED','safety_gate':False,
        'chart_focus':selected['key'] if selected else None,
        'chart_count':len(charts),
    }
    return result,trusted_facts
