"""Source-grounded managerial overviews for any accepted local dataset.

A descriptive, bounded summary is always computed BEFORE optional Qwen wording.
All figures originate in the current read-only in-memory dataset; no source
rows are exposed in the answer and no causal/supplier action is inferred.
"""
import re

from adaptive_charts import recommend


OVERVIEW_RE = (
    r'\b(?:summari[sz]e|summary|overview|insights?|takeaways?|highlights?|'
    r'patterns?|trends?|findings?|analyse|analyze|interpret|describe)\b',
    r'\b(?:what(?:\s+is|\s+does|\s+are|\s+can)?|tell|show|explain|walk)\b.{0,85}'
    r'\b(?:data|dataset|spreadsheet|file|records|figures|numbers|upload|table)\b',
    r'\b(?:data|dataset|spreadsheet|file|records|figures|numbers|upload|table)\b.{0,85}'
    r'\b(?:tell|say|show|mean|indicat|reveal|suggest|happen|going\s+on)\b',
    r'\b(?:big\s+picture|overall\s+picture|main\s+points|stand\s+out|going\s+on|'
    r'worth\s+notic|happening\s+here)\b',
)


def asks_for_overview(question):
    """Identify broad description requests; leave directed calculations to planner.

    These are broad intent patterns, not a required sentence structure.
    """
    q = re.sub(r'\s+', ' ', str(question or '').casefold()).strip()
    if not q:
        return False
    # A request for a particular field, chart, grouping or calculation should
    # stay with the more specific data/chart engine, not this overview.
    directed = (r'\b(?:by month|by year|by week|by supplier|by vendor|by region|by warehouse|'
                r'by category|how many|what percentage|which five|top five|top 5|'
                r'average|median|total cost|sum of|x.axis|y.axis|chart type|'
                r'field mapping|map the field|column mapping)\b')
    if re.search(directed, q):
        return False
    # Field-specific and delivery-specific analyses need their own evidence,
    # not an overall activity summary. The focused analysis tool handles
    # unqualified descriptions; the AI planner handles additional qualifiers.
    if re.search(r'\b(?:delivery|deliveries|lateness|column|field|chart|plot|scatter|correlation|forecast|predict|supplier|suppliers|region|regions|product|products|quantity|quantities|cost|costs|revenue|profit|price|prices|inventory|stock|where|excluding|except|only|between|since|during|before|after|filtered|filter)\b', q):
        return False
    # Overview verbs alone must not swallow a conceptual question.
    return (bool(re.search(r'\b(?:data|dataset|spreadsheet|file|records|figures|numbers|upload|table|results|here)\b',q)) and any(re.search(p,q) for p in OVERVIEW_RE)) or bool(re.fullmatch(r'(?:(?:please|just) )?(?:give me (?:the )?|any (?:interesting )?)?(?:summari[sz]e|overview|insights|highlights|main findings|findings|big picture|overall picture|what stands out|what is going on|what is happening)[?.!]*',q))


def _format_count(value):
    try:
        number = float(value)
        if abs(number) >= 1e14:
            return f'{number:.3g}'
        if number.is_integer():
            return f'{int(number):,}'
        return f'{number:,.2f}'
    except (TypeError, ValueError, OverflowError):
        return str(value)[:65]


def _safe(value, limit=85):
    """Restrict source label length/control characters (they are data only)."""
    return re.sub(r'[\x00-\x1f\x7f]+', ' ', str(value or '')).strip()[:limit]


def build_overview(dataset):
    """Create a useful overview even with zero confirmed business mappings."""
    n, cols = len(dataset.rows), len(dataset.columns)
    blanks = sum(dataset.blank_counts)
    total_cells = n * cols
    complete = 100 * (total_cells - blanks) / total_cells
    missing = sorted(((dataset.columns[i], count) for i, count in enumerate(dataset.blank_counts) if count),
                     key=lambda item: (-item[1], item[0]))
    dashboard = recommend(dataset)
    output = [
        f"Here's what the uploaded dataset '{_safe(dataset.filename, 90)}' shows from {n:,} rows and {cols:,} columns. "
        "These are recorded source rows, not necessarily distinct orders or customers.",
        f"Data completeness: {complete:.1f}% of cells are populated. " + (
            f"{len(missing)} {'column contains' if len(missing) == 1 else 'columns contain'} blanks; the largest gaps are " +
            "; ".join(f"'{_safe(col)}' ({count:,} blank, {100*count/n:.1f}% of rows)" for col, count in missing[:3]) + "."
            if missing else "No empty cells were detected; placeholder codes such as N/A were not automatically counted as missing."
        ),
    ]
    facts = []
    for chart in dashboard.get('charts', []):
        if chart['id'] in {'records_overview', 'field_completeness'}:
            continue
        values = chart.get('values', [])
        if not values:
            continue
        title = _safe(chart.get('title'), 90)
        metric = _safe(chart.get('value_label', 'Recorded values'), 65)
        original = [v for v in values if not v.get('remainder')]
        if not original:
            continue
        # Describe all visible periods, and do not invent a unique peak.
        # Charts can be bounded: conclusions apply only to the displayed groups.
        peak = max(v['count'] for v in original)
        leaders = [v for v in original if v['count'] == peak]
        lead_labels = ', '.join(_safe(v['label']) for v in leaders)
        if chart['id'] in {'activity_over_time', 'recorded_amount_trend'}:
            series = [v['count'] for v in original]
            first, last = series[0], series[-1]
            if len(series) == 1:
                movement = 'Only one displayed period; no trend can be assessed.'
            elif all(x == first for x in series):
                movement = 'Flat across all displayed periods; no increase or decrease is observed.'
            elif all(x <= y for x,y in zip(series,series[1:])):
                movement = 'Non-decreasing across the displayed periods.'
            elif all(x >= y for x,y in zip(series,series[1:])):
                movement = 'Non-increasing across the displayed periods.'
            else:
                movement = ('Fluctuates; the last displayed value is '+('higher' if last>first else 'lower' if last<first else 'equal to the first')+'.')
            peak_note = (f"Highest displayed period: {lead_labels} ({_format_count(peak)})." if len(leaders)==1 else
                         f"{len(leaders)} displayed periods tie for the highest value ({_format_count(peak)}): {lead_labels}.")
            text = (f"{title}: " + '; '.join(f"{_safe(v['label'])}: {_format_count(v['count'])}" for v in original)
                    + f" ({metric.lower()}). {movement} {peak_note} Periods without usable records are not inferred to be zero.")
        elif chart['id'] == 'numeric_distribution':
            text = (f"{title}: " + (f"the most populated displayed numeric range is {lead_labels}" if len(leaders)==1 else
                    f"{len(leaders)} displayed ranges tie for most populated: {lead_labels}") + f" with {_format_count(peak)} rows each.")
        elif chart['id'] == 'date_comparison':
            pairs = sum(float(v.get('count', 0)) for v in original)
            after = next((v['count'] for v in original if 'after' in str(v.get('label','')).lower()), 0)
            text = (f"{title}: {_format_count(after)} of {_format_count(pairs)} comparable rows "
                    f"({_format_count(100 * after / pairs if pairs else 0)}%) have delivery dates after the mapped comparison date.")
        else:
            runner = sorted((v for v in original if v['count'] != peak), key=lambda v: (-v['count'], str(v['label'])))[:3]
            text = (f"{title}: " + (f"highest displayed category is '{lead_labels}'" if len(leaders)==1 else
                    f"{len(leaders)} displayed categories tie for highest: {lead_labels}") +
                    f" with {_format_count(peak)} {metric.lower()}" + (" each. " if len(leaders)>1 else ". ") +
                    ("Other leading categories: " + "; ".join(f"{_safe(v['label'])} ({_format_count(v['count'])})" for v in runner) + "." if runner else ""))
        facts.append(text)
        if len(facts) >= 3:
            break
    if facts:
        output.append("Patterns worth examining in the recorded data:\n" +
                      "\n".join(f"- {f}" for f in facts))
    else:
        output.append("The current fields do not support a reliable specialized trend or category comparison yet. "
                      "The record counts and data-quality checks above are still valid.")
    if not dataset.mapping:
        output.append("No business meanings have been confirmed through field mapping yet. "
                      "The chart patterns use inferred source fields; confirm their definitions and units before relying on them.")
    else:
        output.append(f"{len(dataset.mapping)} business-field roles are manager-mapped; mapping alone does not verify the source values.")
    output.append("These are descriptive findings, not evidence of causes, reliable forecasts, or verified supplier performance. "
                  "Business definitions and source provenance are not verified. "
                  "A useful next step is to check the largest gap or trend against the relevant source records.")
    answer = "\n\n".join(output)
    return {"answer": answer[:6500], "rows": n, "columns": cols,
            "patterns": facts, "completeness_pct": round(complete, 2),
            "source_columns": list(dataset.columns), "source": "CURRENT_UPLOADED_DATASET"}


def is_adequate_overview_reply(reply, overview):
    """Reject vague model paraphrases that omit the actual uploaded findings."""
    s = str(reply or '').lower().replace(',', '')
    if str(overview['rows']) not in s:
        return False
    if not overview['patterns']:
        return 'column' in s or 'missing' in s or 'complete' in s
    # The answer should actually discuss a chart-backed observation, not merely
    # echo the row count and generic business advice.
    return any(tok in s for tok in ('trend', 'month', 'supplier', 'category', 'delivery',
                                    'sales', 'recorded', 'range', 'highest', 'units',
                                    'amount', 'warehouse', 'stock', 'date', 'order'))
