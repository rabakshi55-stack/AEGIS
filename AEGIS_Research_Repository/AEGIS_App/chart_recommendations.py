"""Question-driven recommendations for *current uploaded* AEGIS charts.

All decisions are advisory. Proposed specifications are checked and calculated
with custom_charts.build_chart, which scans accepted rows read-only.  Neither
browser values nor local-model descriptions are treated as measurements.
"""
import re
from dataset_queries import schema
from custom_charts import build_chart
from adaptive_charts import recommend

LIMIT = 20
ROLE_ALIASES = {
    'supplier': ('supplier','vendor','seller','source','manufacturer'),
    'region': ('region','state','province','country','city','territory','location','market'),
    'warehouse': ('warehouse','depot','storage','plant','facility','distribution center'),
    'product': ('product','sku','item','category','material','component','commodity','part'),
    'customer': ('customer','client','buyer','account'),
    'date': ('date','day','month','quarter','year','time','timestamp','period','calendar'),
    'quantity': ('quantity','qty','units','volume','stock','inventory','pieces','count'),
    'amount': ('expenditure','expenditures','amount','revenue','sales','spend','spending','cost','value','price','freight','charges','expense','money','budget'),
    'status': ('status','state','stage','outcome','result','type','classification'),
    'orders': ('orders','order','deliveries','shipments','transactions','records'),
}
# Do not automatically turn a monetary field into profit, margin, or savings.
SPECIAL_UNSUPPORTED = {
    'profit': ('profit','profitability','gross margin','net margin','contribution margin'),
    'causal': ('caused the','causal','responsible for','fault of','why exactly did'),
    'forecast': ('forecast','predict next','next month prediction','what will happen'),
}


def _words(s):
    return re.findall(r'[a-z0-9]+', str(s or '').casefold())


def _norm(s):
    return ' '.join(_words(s))


def is_recommendation_question(question, history=None):
    """Route *requests for a visual design*, not existing-chart interpretation."""
    q = _norm(question)
    if not q:
        return False
    visual = bool(re.search(r'\b(chart|charts|plot|plots|graph|graphs|visual|visualize|visualise|visualization|visualisation|diagram|axes|axis|x axis|y axis)\b', q))
    design = bool(re.search(r'\b(suggest|recommend|choose|select|create|make|build|draw|design|generate|pick|best|suitable|ideal|combination|combinations|change to|switch to|turn into|which chart|what chart|which graph|what graph|x axis|y axis|show me a|show as a)\b', q))
    # 'What does this chart show' should be handled by the chart interpreter.
    interpretation = bool(re.search(r'\b(what does (this|that|the) (chart|graph|plot)|explain (this|that|the) (chart|graph)|interpret (this|that|the) (chart|graph)|how (is|was) (this|that) (chart|graph) calculated)\b', q))
    if interpretation and not re.search(r'\b(instead|better|change|switch|other|alternative|new|recommend)\b', q):
        return False
    if visual and design:
        return True
    if re.search(r'\b(how (could|can|should) (i|we) (compare|see|display)|what fields would show|which combination would)\b',q) and any(w in q for w in ('compare','display','view','fields','visual')):
        return True
    if any(phrase in q for phrase in ('which variables should', 'which fields should', 'what variables should',
                                      'best way to display', 'how to visualize', 'how to visualise',
                                      'what should i put on x', 'what should i put on y',
                                      'what x and y', 'which combination of fields', 'what variable combination', 'which variable combination',
                                      'turn that into a chart', 'show that as a chart')):
        return True
    if history and re.search(r'\b(instead|as a (line|bar|pie|scatter|table)|by (month|year|quarter|week)|swap (the )?axes|same chart)\b',q):
        if any(is_recommendation_question(str(h.get('question',''))) for h in history[-3:]):
            return True
    return False


def _semantic_intents(question):
    q = _norm(question)
    hits = set()
    for role, aliases in ROLE_ALIASES.items():
        if any(re.search(r'(?<!\w)'+re.escape(a)+r's?(?!\w)', q) for a in aliases):
            hits.add(role)
    return hits


def _column_candidates(ds):
    types = schema(ds)['columns']
    mapped = ds.mapping
    out=[]
    for field in types:
        name = field['name']
        n = _norm(name)
        tokens = set(_words(name))
        roles = set()
        for role, aliases in ROLE_ALIASES.items():
            if any(a in n or a.replace(' ','') in n.replace(' ','') for a in aliases):
                roles.add(role)
        for role, col in mapped.items():
            if col == name:
                for label in (role, 'date' if ('date' in role or 'timestamp' in role) else ''):
                    if label:
                        roles.add(label)
                if 'supplier' in role:roles.add('supplier')
                if 'quantity' in role:roles.add('quantity')
                if 'amount' in role or 'price' in role:roles.add('amount')
        out.append({**field,'roles':roles,'tokens':tokens})
    return out


def _explicit_columns(question, fields):
    """Prefer actual field-name mentions, avoiding vague one-word aliases."""
    q = ' '+_norm(question)+' '
    matched=[]
    for f in fields:
        n=_norm(f['name'])
        if n and len(n)>=3 and ((' '+n+' ') in q or (' '+n+'s ') in q):
            matched.append(f['name'])
    return matched


def _pick(fields, roles, *, require=None, question='', avoid=None):
    q=set(_words(question))
    best=None
    for f in fields:
        if require and f['kind'] != require:continue
        if f['present']==0:continue
        if avoid and f['name'] in avoid:continue
        matched = f['roles'] & set(roles)
        if roles and not matched:continue
        score = 10*len(matched) + 3*len(f['tokens'] & q)
        if f['kind']=='date' and 'date' in roles:score+=6
        if f['kind']=='numeric' and ('amount' in roles or 'quantity' in roles):score+=5
        if f['estimated_cardinality']==1 and f['kind']=='text':score-=30
        if f['estimated_cardinality']>100 and f['kind']=='text':score-=4
        score += min(f['present']/(max(1,len(fields))*1000), 1)
        if best is None or score>best[0]:best=(score,f)
    return best[1] if best else None


def has_specific_chart_objective(ds, question):
    q=_norm(question)
    return bool(_explicit_columns(question,_column_candidates(ds)) or _semantic_intents(question) or re.search(r'\b(average|mean|sum|total|distinct|unique|count|trend|monthly|weekly|yearly|distribution|relationship|correlation)\b',q))


def _basic_plan(ds, question, history=None):
    # A short follow-up should inherit the previous business objective, not
    # silently choose another field just because the current turn says 'it'.
    current=_norm(question)
    if history and re.search(r'\b(it|that|instead|same|them|those|by month|by year|by quarter)\b',current):
        for previous in reversed(history[-3:]):
            prior=str(previous.get('question',''))
            if is_recommendation_question(prior):
                question=prior+'; '+str(question)
                break
    # The ordinary chart builder has no row-filter parameter. Never substitute
    # a whole-source chart when the question specifies a filter or threshold.
    if re.search(r'\b(where|excluding|except|only|filtered|filter by|at least|at most|greater than|less than|above|below|last month|last year|last quarter|this month|this year|this quarter|since|during|before|after|20\d{2}|january|february|march|april|june|july|august|september|october|november|december)\b',_norm(question)):
        return None, 'This chart requires a filtered dataset. The current chart builder cannot apply that row filter; no whole-dataset chart has been substituted.'
    fields=_column_candidates(ds)
    intent=_semantic_intents(question)
    q=_norm(question)
    explicit=_explicit_columns(question,fields)
    by_time = ('date' in intent and bool(re.search(r'\b(over time|trend|monthly|weekly|yearly|by month|by year|by quarter|over months|over years|time series|through time|month|quarter)\b',q)))
    if any(term in q for term in ('trend','over time','through time','monthly')):by_time=True
    distribution=bool(re.search(r'\b(distribution|spread|frequency|histogram|range of|how are .*distributed)\b',q))
    relationship=bool(re.search(r'\b(relationship|correlation|associated|association|correlated|scatter|vs|versus|against|between .* and )\b',q))
    average=bool(re.search(r'\b(average|mean|typical|avg)\b',q))
    distinct=bool(re.search(r'\b(unique|distinct)\b',q))
    count=bool(re.search(r'\b(number of|how many|count|frequency|volume of orders|most orders|fewest orders)\b',q))
    share=bool(re.search(r'\b(share|portion|percentage|proportion|contribution|breakdown)\b',q))
    minimum=bool(re.search(r'\b(minimum|smallest value|lowest value)\b',q))
    maximum=bool(re.search(r'\b(maximum|largest value|highest value)\b',q))
    amount_requested = 'amount' in intent or any(t in q for t in ('financial','monetary','total cost','total revenue','total sales','how much spent'))
    quantity_requested = 'quantity' in intent
    # A question asking for profit/margin cannot be substituted with sales or cost.
    if re.search(r'\b(margins?|profitability|profits?)\b',q):
        required='margin' if 'margin' in q else 'profit'
        if not any(required in _norm(f['name']) for f in fields):
            return None, f'This file has no confirmed {required} field. Sales or spending alone cannot answer a {required} question.' 
    if any(a in q for a in SPECIAL_UNSUPPORTED['causal']):
        return None, 'A chart alone cannot establish supplier fault or causal effects; a descriptive comparison may help identify records to investigate.'
    # Unit prices are not total expenditure; duration and on-time metrics
    # are not interchangeable with the late-delivery percentage.
    if re.search(r'\b(?:on time|early|average (?:delivery )?delay|mean (?:delivery )?delay|lead time|delivery time|delay duration|days late)\b',q) and re.search(r'\b(delivery|deliveries|delay|late|supplier|suppliers|vendor|vendors|lead time|on time)\b',q):
        return None, 'The requested delivery metric needs a separately calculated measure. The current chart builder cannot derive that exact metric; a late-rate or record-count chart would not answer it.'
    totals=[]
    if re.search(r'\b(?:total (?:purchase |purchasing )?(?:cost|spend|expenditure|value)|purchase value|purchasing expenditure|purchase expenditure|total spending|how much spent)\b',q):
        totals=[f for f in fields if f['kind']=='numeric' and re.search(r'\b(?:total cost|total purchase cost|total amount|purchase value|order total|line total|extended cost|purchase amount|spend|expenditure|invoice amount)\b',_norm(f['name']))]
        if not totals:
            return None, 'Total purchasing expenditure requires summing quantity × unit cost (or an explicit recorded line-total field). A sum of unit prices is not total expenditure; no misleading chart was created.'
        if len(totals)==1: explicit=[n for n in explicit if n!=totals[0]['name']]+[totals[0]['name']]
    # Distinct supplier late-rate views are special derived metrics that the custom
    # chart builder cannot reconstruct from one arbitrary X/Y aggregation.
    if re.search(r'\b(late|delayed|delays?|delay rates?|on time|on time rates?|punctual|reliable|reliability)\b',q) and ('supplier' in intent or 'vendor' in q):
        auto={a['id']:a for a in recommend(ds)['charts']}
        if 'recorded_date_exceptions_by_supplier' in auto:
            return {'kind':'automatic','id':'recorded_date_exceptions_by_supplier'}, None
        return None, ('A reliable supplier delay-rate chart needs supplier, promised date and actual date fields '
                      'with enough comparable records. No validated ready-made percentage chart is available for this upload.')
    # A requested forecast is not a historical visualization.
    if any(a in q for a in SPECIAL_UNSUPPORTED['forecast']):
        return None, 'Historical charts cannot predict future values without a separately validated forecasting model.'
    # Field names explicitly present in the question get priority; ambiguous
    # generic terms are resolved by types and dataset profile.
    explicit_fields=[next(f for f in fields if f['name']==name) for name in explicit]
    if by_time:
        x=next((f for f in explicit_fields if f['kind']=='date'),None) or _pick(fields, {'date'},require='date',question=question)
        # May be ISO date text recognized as date by schema; don't invent date values.
        if not x:
            return None,'No usable date column exists for a chronological chart. Map or upload an ISO date field first.'
    else:
        x=None
        grouping_role = ({'supplier','warehouse','product','region','customer','status'} & intent)
        for f in explicit_fields:
            if f['kind']=='text' and (not grouping_role or f['roles']&grouping_role):x=f;break
        if x is None and grouping_role:x=_pick(fields,grouping_role,question=question)
        if x is None and distribution:
            x=next((f for f in explicit_fields if f['kind']=='numeric'),None)
        if x is None:
            x=next((f for f in explicit_fields if f['kind'] in {'text','date'}),None)
        if x is None:
            x=_pick(fields,{'supplier','region','warehouse','product','status','date'},question=question)
        if x is None:x=next((f for f in fields if f['kind']=='text' and 2<=f['estimated_cardinality']<=20),None)
        if x is None:x=next((f for f in fields if f['kind']=='date'),None)
        if x is None:x=next((f for f in fields if f['kind']=='numeric'),None)
    if x is None:return None, 'No suitable column was found for a chart. The dataset may need valid nonblank fields.'
    if any(t in q for t in ('revenue','sales')) and not any(any(t in _norm(f['name']) for t in ('revenue','sales','order amount','total amount','line total')) for f in fields):
        return None, 'No identifiable revenue or sales amount field is available. A cost or price column cannot automatically stand in for revenue.' 
    y=None
    numeric=[f for f in explicit_fields if f['kind']=='numeric' and f['name']!=x['name']]
    if numeric:y=numeric[0]
    if totals:
        eligible=[f for f in totals if f['name']!=x['name']]
        if len(eligible)!=1:
            return None, 'Choose the exact recorded total field and a separate grouping field; expenditure fields are ambiguous.'
        y=eligible[0]
    if y is None and amount_requested:y=_pick(fields, {'amount'},require='numeric',question=question, avoid={x['name']})
    if y is None and quantity_requested:y=_pick(fields, {'quantity'},require='numeric',question=question, avoid={x['name']})
    if y is None and (average or minimum or maximum or 'total' in q or 'sum' in q):
        y=_pick(fields, {'amount','quantity'},require='numeric',question=question,avoid={x['name']})
    if y is None and not count:
        numeric_other=[f for f in fields if f['kind']=='numeric' and f['name']!=x['name']]
        if len(numeric_other)==1 and (by_time or relationship):y=numeric_other[0]
    if (amount_requested or quantity_requested) and y is None:
        return None, 'The dataset has no verified numeric field that matches the requested amount or quantity. A row-count chart would not answer that question.'
    if relationship and len(explicit_fields)>=2:
        pair=[f for f in explicit_fields if f['kind']=='numeric']
        if len(pair)>=2:
            return {'kind':'custom','options':dict(chart_type='scatter',x=pair[0]['name'],y=pair[1]['name'],aggregation='count',date_grain='none',sort='x_asc',limit=20)},None
    if relationship:
        return None, 'A relationship chart needs two identifiable numeric measures at the same grain. Specify the two variables; a record-count chart would not answer the question.'
    if distribution and x['kind']=='numeric' and not y:
        return {'kind':'custom','options':dict(chart_type='histogram',x=x['name'],y=None,aggregation='count',date_grain='none',sort='x_asc',limit=20)},None
    if distinct:
        split=re.split(r'\b(?:by|per|for each)\b',q,maxsplit=1)
        if len(split)==2:
            left=[f for f in explicit_fields if f['name'] in _explicit_columns(split[0],fields)]
            right=[f for f in explicit_fields if f['name'] in _explicit_columns(split[1],fields)]
            if len(left)==1 and len(right)==1 and left[0]['name']!=right[0]['name']:
                x=right[0]; y=left[0]
        target=y if y and y['name']!=x['name'] and len(split)==2 and len(left)==1 and len(right)==1 else next((f for f in explicit_fields if f['name']!=x['name']),None)
        if target is None:
            return None, 'A distinct-count chart needs an identifiable field to count uniquely and a separate grouping field; no record-count chart was substituted.'
        y=target
    if y is None:agg='count'
    elif average:agg='average'
    elif distinct:agg='distinct_count'
    elif minimum:agg='minimum'
    elif maximum:agg='maximum'
    else:agg='sum'
    if count and not (amount_requested or quantity_requested or average or distinct):agg='count';y=None
    typ='line' if by_time else 'bar'
    if share and not by_time:typ='donut'
    if re.search(r'\b(horizontal|horizontally|horizontal bar)\b',q):typ='horizontal_bar'
    if re.search(r'\b(line chart|line graph|as a line)\b',q):typ='line'
    if re.search(r'\b(bar chart|bar graph|as a bar)\b',q):typ='bar'
    if re.search(r'\b(pie chart|pie graph|as a pie)\b',q):typ='pie'
    if re.search(r'\b(donut chart|as a donut)\b',q):typ='donut'
    if re.search(r'\b(table|tabular)\b',q):typ='table'
    grain='month' if by_time else 'none'
    if by_time:
        if re.search(r'\b(by year|yearly|annual|annually)\b',q):grain='year'
        elif re.search(r'\b(weekly|by week)\b',q):grain='week'
        elif re.search(r'\b(by quarter|quarterly)\b',q):grain='quarter'
        elif re.search(r'\b(daily|by day)\b',q):grain='day'
    if typ=='donut' and x['estimated_cardinality']>12:typ='bar'
    return {'kind':'custom','options':dict(chart_type=typ,x=x['name'],y=y['name'] if y else None,aggregation=agg,
                                            date_grain=grain,sort='x_asc' if by_time else 'value_desc',limit=LIMIT)},None


def validate_proposal(ds, proposal):
    if not isinstance(proposal,dict) or set(proposal)-{'kind','options','id'}:
        raise ValueError('Chart proposal has unsupported fields.')
    if proposal.get('kind')=='automatic':
        ident=proposal.get('id')
        available={r['id']:r for r in recommend(ds)['charts']}
        if ident not in available:
            raise ValueError('That ready-made metric is not available from this dataset.')
        return {'kind':'automatic','id':ident,'automatic_chart':available[ident]}
    if proposal.get('kind')!='custom' or set(proposal)!={'kind','options'}:
        raise ValueError('Expected an approved chart specification.')
    computed=build_chart(ds,proposal['options'])
    types={x['name']:x['kind'] for x in schema(ds)['columns']}
    opts=proposal['options']
    if computed['chart_type'] == 'scatter' and (types[computed['x']]!='numeric' or types[computed['y']]!='numeric'):
        raise ValueError('Scatter requires two columns with predominantly numeric values.')
    if computed['chart_type'] == 'histogram' and types[computed['x']]!='numeric':
        raise ValueError('Histogram requires a numeric variable.')
    if computed['aggregation'] in {'sum','average','minimum','maximum','median'} and types[computed['y']]!='numeric':
        raise ValueError('The chosen measure is not reliably numeric for this aggregation.')
    if computed['date_grain']!='none' and types[computed['x']]!='date':
        raise ValueError('A time-series chart requires parseable dates.')
    return {'kind':'custom','options':{k:computed[k] for k in ('chart_type','x','y','aggregation','date_grain','sort','limit')},
            'computed':computed}


def recommend_for_question(ds, question, *, revision, history=None, llm_proposal=None):
    """Return an actionable, server-recomputed recommendation or a grounded refusal."""
    from cohort_analysis import cohort_relationship
    checked=cohort_relationship(ds,question,online_chart=True)
    if checked is not None:
        text=checked['answer'] if isinstance(checked,dict) else checked
        result={'answer':text,'context':'local_dataset','evidence_source':'VERIFIED_CHART_RECOMMENDATION','routing_mode':'CHECKED_DERIVED_CHART_GUIDANCE','permitted_action':'NONE','operational_approval':'NOT_GRANTED','human_review':'REQUIRED','safety_gate':False}
        if isinstance(checked,dict):
            from cohort_analysis import build_cohort_scatter
            spec=checked['options']; chart=build_cohort_scatter(ds,spec)
            result['chart_suggestion']={'kind':'cohort_scatter','options':spec,'title':chart['title'],'dataset_revision':revision}
        return result, {'dataset_name':ds.filename,'file_rows':len(ds.rows),'verified_description':text,'permitted_business_action':'NONE'}
    plan, reason=_basic_plan(ds,question,history)
    mode='LOCAL_RULES'
    if llm_proposal is not None and reason is None:
        try:
            candidate=validate_proposal(ds,llm_proposal)
            # LLM plans cannot replace the trusted automatically derived delay-rate
            # metric with a misleading raw-count chart.
            if plan and plan['kind'] == 'automatic' and candidate['kind']!='automatic':
                raise ValueError('A separately derived ratio is required for this objective.')
            if plan and plan['kind']=='custom' and candidate['kind']=='custom':
                # Explicit fields must not be substituted in local-model plans.
                explicit=_explicit_columns(question,_column_candidates(ds))
                if has_specific_chart_objective(ds,question) and any(candidate['options'][k]!=plan['options'][k] for k in ('x','y','aggregation','date_grain')):
                    raise ValueError('The suggested chart changes the checked measure, grouping or aggregation.')
                if explicit and any(column not in (candidate['options']['x'],candidate['options']['y'])
                                    for column in explicit[:2]):
                    raise ValueError('The suggested axes omit a user-requested field.')
            plan=llm_proposal
            mode='LOCAL_QWEN_SCHEMA_PLAN_VALIDATED'
        except (ValueError, KeyError, TypeError):
            pass
    if not plan:
        explanation=(reason or 'No supported visual measure matches the question and available fields.')
        return ({'answer':explanation+' No chart was created or data changed.',
                 'context':'local_dataset','evidence_source':'VERIFIED_CHART_RECOMMENDATION',
                 'routing_mode':'NO_VALID_CHART_AVAILABLE','permitted_action':'NONE',
                 'operational_approval':'NOT_GRANTED','safety_gate':False},
                {'dataset_name':ds.filename,'file_rows':len(ds.rows),'limitation':explanation,
                 'permitted_business_action':'NONE'})
    try:
        result=validate_proposal(ds,plan)
    except (ValueError, KeyError, TypeError) as error:
        # A comparison with refunds or negative amounts should not become a pie.
        if (plan['kind']=='custom' and plan['options']['chart_type'] in {'pie','donut'}):
            safe_opts={**plan['options'],'chart_type':'bar'}
            try:
                result=validate_proposal(ds,{'kind':'custom','options':safe_opts})
                plan={'kind':'custom','options':safe_opts}
            except (ValueError, KeyError, TypeError):
                result=None
        else:
            result=None
        if result is None:
            return ({'answer':f'I cannot reliably create that comparison from this dataset: {error}. Try choosing a usable field or mapping its business meaning first.',
                     'context':'local_dataset','evidence_source':'VERIFIED_CHART_RECOMMENDATION',
                     'routing_mode':'NO_VALID_CHART_AVAILABLE','permitted_action':'NONE',
                     'operational_approval':'NOT_GRANTED','safety_gate':False},
                    {'dataset_name':ds.filename,'file_rows':len(ds.rows),'limitation':str(error),'permitted_business_action':'NONE'})
    if result['kind']=='automatic':
        a=result['automatic_chart']
        title=a['title']; rationale=a['reason']
        message=(f"For your question, I recommend **{title}**, a {a['type']} chart already available on Visualizations. "
                 f"It uses {', '.join(a['source_columns'])}, and its measure is {a['value_label']}. "
                 f"{rationale} {a['caution']} This does not establish supplier fault or a causal effect.")
        suggestion={'kind':'automatic','chart_id':a['id'],'title':title,'reason':rationale,
                    'dataset_revision':revision}
    else:
        c=result['computed']; conf=result['options']; axis=c['x']; measure=c['y'] or 'record count'
        title=(f'{measure} versus {axis}' if c['chart_type']=='scatter' else
               f'Distribution of {axis}' if c['chart_type']=='histogram' else
               f"{('Record counts' if measure=='record count' else conf['aggregation'].replace('_',' ').title()+' of '+measure)} by {axis}")
        reasons={'line':'A time-ordered line makes recorded changes over periods easier to inspect.',
                 'bar':'A bar chart makes differences among recorded groups easy to compare.',
                 'horizontal_bar':'A horizontal bar chart helps compare labelled groups.',
                 'donut':'A donut chart shows parts of the total of displayed nonnegative groups.',
                 'scatter':'A scatter plot shows individual recorded numeric pairs, not necessarily causality.',
                 'histogram':'A histogram shows the frequency distribution of a numeric field.',
                 'table':'A table shows recorded group values precisely.'}
        rationale=reasons.get(c['chart_type'],'This chart displays the selected source-field measurements.')
        calculation=('Direct numeric pairs' if c['chart_type']=='scatter' else
                     'Histogram frequencies' if c['chart_type']=='histogram' else conf['aggregation'].replace('_',' '))
        message=(f"I suggest a **{c['chart_type'].replace('_',' ')} chart** for this question. "
                 f"X-axis: **{axis}**. Y-axis: **{measure}**; calculation: **{calculation}**. "
                 + (f"Group dates by **{conf['date_grain']}**. " if conf['date_grain']!='none' else '')+
                 f"{rationale} It uses {c['valid_rows']:,} contributing rows out of {c['source_rows']:,}. "
                 f"{c['note']} Business meaning, units and causal interpretation still require review.")
        suggestion={'kind':'custom','options':conf,'title':title,'reason':rationale,'dataset_revision':revision}
    outcome={'answer':message,'chart_suggestion':suggestion,'context':'local_dataset',
             'evidence_source':'VERIFIED_CHART_RECOMMENDATION','routing_mode':mode,
             'permitted_action':'NONE','operational_approval':'NOT_GRANTED','human_review':'REQUIRED',
             'safety_gate':False}
    facts={'dataset_name':ds.filename,'file_rows':len(ds.rows),'chart_suggestion':suggestion,
           'verified_description':message,'permitted_business_action':'NONE'}
    return outcome,facts
