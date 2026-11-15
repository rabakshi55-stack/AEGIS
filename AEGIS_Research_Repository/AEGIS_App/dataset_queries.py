"""Restricted, read-only analytical queries over an uploaded LocalDataset.

No eval, SQL, Python execution, filesystem reads or mutations. All uploaded rows
may be inspected for calculating a result, but only a bounded number of matched
records are ever included in a model response. This is local research analysis,
not a supplier-decision or prediction certification engine.
"""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
import re

MAX_FILTERS = 6
MAX_GROUPS = 2
MAX_OUTPUT_GROUPS = 30
MAX_RECORD_PREVIEW = 12
MAX_PLANS = 3
MAX_RESPONSE_CHARS = 12_000


def numeric(value):
    text = str(value if value is not None else "").strip()
    # Never reinterpret a locale decimal comma or malformed grouping as a
    # larger number. Accept conventional thousands grouping only.
    if "," in text:
        if not re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?",text): return None
        text=text.replace(",", "")
    if not text or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,2})?", text):
        return None
    try:
        n = Decimal(text)
        return n if n.is_finite() and abs(n)<=Decimal("1e15") else None
    except InvalidOperation:
        return None


def date_key(value, grain="day"):
    text = str(value or "").strip()
    from intake import _date
    if _date(text) is None:
        return None
    return text[:4] if grain == "year" else text[:7] if grain == "month" else text[:10]


def _resolve(column, names):
    if not isinstance(column, str):
        raise ValueError("A query column must be a name from the uploaded dataset.")
    if column in names:
        return column
    matches = [x for x in names if x.casefold() == column.casefold()]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"Unknown or ambiguous field: {column[:80]!r}.")


def schema(dataset):
    """Tell the model about every column, without copying the full dataset."""
    specs = []
    for i, name in enumerate(dataset.columns):
        present = [row[i] for row in dataset.rows if row[i]]
        count = len(present)
        nnum = sum(numeric(x) is not None for x in present)
        ndate = sum(date_key(x) is not None for x in present)
        data_type = ("numeric" if count and nnum / count >= .95 else
                     "date" if count and ndate / count >= .95 else "text")
        entries = {x for x in present[:3000]}
        specs.append({"name": name, "kind": data_type, "present": count,
                      "missing": len(dataset.rows) - count,
                      "estimated_cardinality": min(len(entries), 3000),
                      "cardinality_sampled": count > 3000})
    return {"filename": dataset.filename, "rows": len(dataset.rows),
            "columns": specs, "mapped_roles": dict(dataset.mapping),
            "records_fully_available_to_read_only_query_engine": True,
            "automatic_business_action": False}


def _require_keys(obj, allowed):
    unknown = set(obj) - set(allowed)
    if unknown:
        raise ValueError("Unsupported query options: " + ", ".join(sorted(map(str, unknown))))


def _compile_filters(filters, names):
    if not isinstance(filters, list) or len(filters) > MAX_FILTERS:
        raise ValueError("Supply up to six read-only filters.")
    supported = {"eq", "ne", "contains", "in", "gt", "gte", "lt", "lte", "between", "missing", "present", "date_between"}
    compiled = []
    for filt in filters:
        if not isinstance(filt, dict):
            raise ValueError("Filters must be objects.")
        _require_keys(filt, {"column", "op", "value", "value2"})
        col = _resolve(filt.get("column"), names)
        op = filt.get("op")
        if op not in supported:
            raise ValueError("Unsupported comparison operation.")
        val = filt.get("value")
        second = filt.get("value2")
        if op in {"gt", "gte", "lt", "lte", "between"} and numeric(val) is None:
            raise ValueError("Numeric comparisons require a valid numeric value.")
        if op == "between" and numeric(second) is None:
            raise ValueError("Between requires two valid numeric bounds.")
        if op == "in" and (not isinstance(val, list) or len(val) > 25 or not all(isinstance(v, (str,int,float)) for v in val)):
            raise ValueError("A list filter requires at most 25 scalar values.")
        if op == "date_between" and (date_key(val) is None or date_key(second) is None):
            raise ValueError("A date range requires ISO dates.")
        compiled.append((names.index(col), op, val, second))
    return compiled


def _matched(raw, compiled):
    for i, op, val, val2 in compiled:
        value = raw[i]
        if op == "missing":
            good = not value
        elif op == "present":
            good = bool(value)
        elif op == "contains":
            good = str(val).casefold() in value.casefold() if val is not None else False
        elif op == "in":
            good = value.casefold() in {str(v).casefold() for v in val}
        elif op in {"eq", "ne"}:
            good = value.casefold() == str(val if val is not None else "").casefold()
            if op == "ne":
                good = not good
        elif op == "date_between":
            d = date_key(value)
            good = d is not None and date_key(val) <= d <= date_key(val2)
        else:
            n = numeric(value)
            bound = numeric(val)
            good = n is not None and (n > bound if op == "gt" else
                                     n >= bound if op == "gte" else
                                     n < bound if op == "lt" else
                                     n <= bound if op == "lte" else
                                     bound <= n <= numeric(val2))
        if not good:
            return False
    return True


def _formatted(x):
    if isinstance(x, Decimal):
        return float(round(x, 6)) if abs(x) < Decimal("1E15") else str(x)
    return x


def execute(dataset, plan):
    """Execute a validated plan over all dataset rows, with bounded output."""
    if not isinstance(plan, dict):
        raise ValueError("Analysis plan must be a JSON object.")
    _require_keys(plan, {"operation", "column", "group_by", "filters", "order", "limit", "date_grain", "columns"})
    op = plan.get("operation")
    allowed_ops = {"schema", "count", "count_distinct", "sum", "average", "min", "max", "median", "stddev",
                   "group_count", "group_sum", "group_average", "preview"}
    if op not in allowed_ops:
        raise ValueError("Query operation is not supported by the safe local analysis engine.")
    names = dataset.columns
    filt = _compile_filters(plan.get("filters", []), names)
    cols = plan.get("columns", [])
    if not isinstance(cols, list) or len(cols) > 12:
        raise ValueError("Preview can select up to 12 columns.")
    cols = [_resolve(c, names) for c in cols]
    group_by = plan.get("group_by", [])
    if not isinstance(group_by, list) or len(group_by) > MAX_GROUPS:
        raise ValueError("Use up to two grouping fields.")
    group_by = [_resolve(c, names) for c in group_by]
    if len(set(group_by)) != len(group_by):
        raise ValueError("Grouping fields must be unique.")
    date_grain = plan.get("date_grain", "raw")
    if date_grain not in {"raw", "day", "month", "year"}:
        raise ValueError("Unsupported date grouping interval.")
    if date_grain != "raw" and len(group_by) != 1:
        raise ValueError("Date grouping requires one date column.")
    col = plan.get("column")
    if op in {"count_distinct", "sum", "average", "min", "max", "median", "stddev", "group_sum", "group_average"}:
        col = _resolve(col, names)
    elif col is not None:
        col = _resolve(col, names)
    if op.startswith("group_") and not group_by:
        raise ValueError("Grouped analysis requires group_by fields.")
    if not op.startswith("group_") and group_by:
        raise ValueError("Grouping is only allowed for grouped operations.")
    limit = plan.get("limit", 10)
    if type(limit) is not int or not 1 <= limit <= MAX_OUTPUT_GROUPS:
        raise ValueError("Result limit must be 1–30.")
    order = plan.get("order", "desc")
    if order not in {"asc", "desc", "key_asc", "key_desc"}:
        raise ValueError("Unsupported sort order.")
    if op == "schema":
        return {"operation": "schema", "source": dataset.filename, "result": schema(dataset), "business_action": "NONE"}
    hit = 0
    preview = []
    count_distinct = set()
    numeric_values = []
    invalid_numeric = 0
    groups = defaultdict(lambda: {"rows": 0, "numeric_sum": Decimal(0), "numeric_count": 0, "invalid_numeric": 0})
    selected_col = names.index(col) if col is not None else None
    group_indices = [names.index(c) for c in group_by]
    out_cols = cols if cols else names[:min(len(names), 12)]
    out_indices = [names.index(c) for c in out_cols]
    for row in dataset.rows:
        if not _matched(row, filt):
            continue
        hit += 1
        if op == "preview" and len(preview) < min(limit, MAX_RECORD_PREVIEW):
            preview.append({c: row[i][:500] for c, i in zip(out_cols, out_indices)})
        if op == "count_distinct":
            if row[selected_col]:
                count_distinct.add(row[selected_col])
        if op in {"sum", "average", "min", "max", "median", "stddev", "group_sum", "group_average"}:
            number = numeric(row[selected_col])
            if number is None:
                invalid_numeric += 1
            else:
                if op in {"sum", "average", "min", "max", "median", "stddev"}:
                    numeric_values.append(number)
        if op.startswith("group_"):
            key = tuple((date_key(row[i], date_grain) if date_grain != "raw" else row[i]) or None
                        for i in group_indices)
            info = groups[key]
            info["rows"] += 1
            if op in {"group_sum", "group_average"}:
                if number is None:
                    info["invalid_numeric"] += 1
                else:
                    info["numeric_sum"] += number
                    info["numeric_count"] += 1
    evidence = {"source": dataset.filename, "operation": op,
                "matched_rows": hit, "total_rows": len(dataset.rows),
                "all_rows_considered": True, "filters": plan.get("filters", []),
                "result_is_descriptive_not_causal": True, "business_action": "NONE"}
    if op == "preview":
        evidence["result"] = preview
        evidence["displayed_rows"] = len(preview)
        evidence["limited_preview"] = hit > len(preview)
    elif op == "count":
        evidence["result"] = hit
    elif op == "count_distinct":
        evidence.update({"field": col, "result": len(count_distinct), "missing_values_excluded": True,
                         "missing_count": sum(1 for row in dataset.rows if _matched(row, filt) and not row[selected_col])})
    elif op in {"sum", "average", "min", "max", "median", "stddev"}:
        n = len(numeric_values)
        evidence.update({"field": col, "valid_numeric_rows": n, "non_numeric_or_missing_rows": invalid_numeric})
        if not n:
            evidence["result"] = None
        elif op == "sum":
            evidence["result"] = _formatted(sum(numeric_values, Decimal(0)))
        elif op == "average":
            evidence["result"] = _formatted(sum(numeric_values, Decimal(0)) / n)
        elif op == "min":
            evidence["result"] = _formatted(min(numeric_values))
        elif op == "max":
            evidence["result"] = _formatted(max(numeric_values))
        elif op == "median":
            vals = sorted(numeric_values)
            evidence["result"] = _formatted(vals[n//2] if n%2 else (vals[n//2-1] + vals[n//2])/2)
        else:
            avg = float(sum(numeric_values, Decimal(0)) / n)
            evidence["result"] = round(math.sqrt(sum((float(v) - avg) ** 2 for v in numeric_values) / n), 6)
    elif op.startswith("group_"):
        result = []
        for key, grp in groups.items():
            metric = (grp["rows"] if op == "group_count" else
                      (_formatted(grp["numeric_sum"]) if grp["numeric_count"] else None) if op == "group_sum" else
                      (_formatted(grp["numeric_sum"] / grp["numeric_count"]) if grp["numeric_count"] else None))
            result.append({"group": dict(zip(group_by, key)), "value": metric,
                           "rows": grp["rows"], "numeric_rows": grp["numeric_count"] if op != "group_count" else None})
        if order.startswith("key"):
            result.sort(key=lambda x: tuple(str(x["group"][c]) for c in group_by), reverse=order == "key_desc")
        else:
            result.sort(key=lambda x: (x["value"] is None, -Decimal(str(x["value"] or 0)) if order == "desc" else Decimal(str(x["value"] or 0))))
        evidence.update({"result": result[:limit], "group_by": group_by, "field": col,
                         "distinct_groups": len(result), "result_truncated": len(result) > limit,
                         "non_numeric_or_missing_rows": invalid_numeric if op != "group_count" else 0})
    return evidence


def execute_many(dataset, plans):
    if isinstance(plans, dict) and "plans" in plans:
        plans = plans["plans"]
    elif isinstance(plans, dict):
        plans = [plans]
    if not isinstance(plans, list) or not 1 <= len(plans) <= MAX_PLANS:
        raise ValueError("Supply one to three bounded analytical queries.")
    outputs = [execute(dataset, plan) for plan in plans]
    return outputs


def explain(outputs):
    """Deterministic fallback / checked answer from actual calculations."""
    lines = []
    for e in outputs:
        op = e["operation"]
        if op == "schema":
            details = e["result"]
            lines.append(f"I can query all {details['rows']:,} uploaded rows across {len(details['columns'])} columns: "
                         + ", ".join(str(c['name']) for c in details['columns']) + ".")
            continue
        if op == "count_distinct":
            lines.append(f"There are {e['result']:,} distinct non-empty values in '{e['field']}'. "
                         f"Checked {e['matched_rows']:,} matching rows out of {e['total_rows']:,} uploaded records.")
            if e.get("missing_count"):
                lines.append(f"{e['missing_count']:,} matching rows have a blank '{e['field']}' value and are excluded from the distinct count.")
            continue
        if op == "group_count":
            lines.append("Record counts by " + ", ".join(e['group_by']) + ":")
            lines.extend("• " + " / ".join("(missing or invalid)" if v is None else str(v) for v in row['group'].values()) + f": {row['value']:,} rows" for row in e['result'])
            if e.get('result_truncated'):
                lines.append(f"Showing {len(e['result'])} of {e['distinct_groups']} groups.")
            lines.append(f"Checked {e['matched_rows']:,} matching rows out of {e['total_rows']:,} uploaded records.")
            continue
        label = f"{op.replace('_',' ')}" + (f" of '{e['field']}'" if e.get('field') else "")
        lines.append(f"{label.capitalize()}: {e['result']}. Checked {e['matched_rows']:,} matching rows "
                     f"out of {e['total_rows']:,} uploaded records.")
        if e.get("result_truncated"):
            lines.append(f"Only the first {len(e['result'])} of {e['distinct_groups']} groups are shown.")
        if e.get("non_numeric_or_missing_rows"):
            lines.append(f"{e['non_numeric_or_missing_rows']:,} matched values were missing or not numeric.")
    lines.append("These are descriptive calculations on the uploaded file, not verified causal findings or a supplier-change authorization.")
    return "\n".join(lines)[:MAX_RESPONSE_CHARS]


def _field_phrase(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).casefold()).strip()


def _entity_column(dataset, phrase):
    """Resolve explicit whole field names or unambiguous common entity aliases."""
    term = _field_phrase(phrase)
    if not term:
        return None
    forms = {term}
    if term.endswith("ies"):
        forms.add(term[:-3] + "y")
    elif term.endswith("s"):
        forms.add(term[:-1])
    else:
        forms.add(term + "s")
    exact = [c for c in dataset.columns if _field_phrase(c) == term]
    if len(exact) == 1:
        return exact[0]
    matches = [c for c in dataset.columns if _field_phrase(c) in forms]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return None
    aliases = {
        "supplier_id": {"supplier", "suppliers", "vendor", "vendors", "seller", "sellers"},
        "order_id": {"order", "orders"},
        "item_id": {"item", "items", "product", "products"},
        "destination_state": {"destination state", "destination states"},
    }
    for role, words in aliases.items():
        if term in words and dataset.mapping.get(role) in dataset.columns:
            return dataset.mapping[role]
    entity_names = ["supplier", "vendor", "seller", "customer", "order", "item", "product"]
    for entity in entity_names:
        if term in {entity, entity + "s"}:
            names = {entity + " id", entity + " name", entity + " reference", entity + " code"}
            candidates = [c for c in dataset.columns if _field_phrase(c) in names]
            return candidates[0] if len(candidates) == 1 else None
    return None


def _entity_plan(question, dataset, history=None):
    """Handle complete, unfiltered cardinality/list requests; never drop qualifiers."""
    q = _field_phrase(question)
    tail = r"(?: (?:are there|do we have|are in (?:the|this|my|our) (?:data|dataset|file|upload)|in (?:the|this|my|our) (?:uploaded )?(?:data|dataset|file|upload)))?"
    m = re.fullmatch(r"(?:how many (?:distinct|unique) values (?:in|of)|(?:number of )?unique values (?:in|of)) (.+)", q)
    if m:
        col = _entity_column(dataset, m.group(1))
        if col:
            return {"operation": "count_distinct", "column": col}
    m = re.fullmatch(r"(?:how many|(?:what is the |what s the |tell me the )?number of|count) (?:distinct |unique |different )?(.+?)" + tail, q)
    if m:
        term = m.group(1)
        if term in {"rows", "records", "entries", "data rows"}:
            return {"operation": "count"}
        col = _entity_column(dataset, term)
        if col:
            return {"operation": "count_distinct", "column": col}
    # A field-only follow-up or list request gets a checked profile, not a guess.
    m = re.fullmatch(r"(?:list|show(?: me)?|what are) (?:all |the |unique |distinct )?(.+?)" + tail, q)
    term = m.group(1) if m else q
    col = _entity_column(dataset, term)
    if col:
        return {"plans": [
            {"operation": "count_distinct", "column": col},
            {"operation": "group_count", "group_by": [col], "filters": [{"column": col, "op": "present"}], "limit": 20}
        ]}
    # A bare request for names can inherit the specific previous count question.
    if q in {"list them", "show them", "what are their names", "which ones", "name them"} and history:
        prior = _entity_plan(history[-1].get("question", ""), dataset)
        if prior and prior.get("operation") == "count_distinct":
            col = prior["column"]
        elif prior and prior.get("plans") and prior["plans"][0].get("operation") == "count_distinct":
            col = prior["plans"][0]["column"]
        else:
            col = None
        if col:
            return {"operation": "group_count", "group_by": [col], "filters": [{"column": col, "op": "present"}], "limit": 20}
    return None


def basic_plan(question, dataset, history=None):
    """Best-effort offline interpretation. Local Qwen handles complex phrasings."""
    q = str(question or "").lower().strip()
    if not q:
        return None
    entity_plan = _entity_plan(question, dataset, history)
    if entity_plan is not None:
        return entity_plan
    q = _field_phrase(question)
    q = re.sub(r"^(?:(?:please|tell me|show me|what is|what s|give me|calculate|can you tell me) )+", "", q)
    q = re.sub(r"(?: please| in (?:the|this|my|our) (?:uploaded )?(?:dataset|data|file|upload))$", "", q)
    if q in {"show the columns", "list the fields", "what fields", "what columns", "show schema", "columns", "schema"}:
        return {"operation":"schema"}
    if q in {"total rows", "how many records", "how many rows", "number of entries", "count rows", "count records"}:
        return {"operation":"count"}
    m=re.fullmatch(r"(?:the )?(average|mean|total|sum(?: of)?|maximum|highest value(?: of)?|largest value(?: of)?|minimum|lowest value(?: of)?|smallest value(?: of)?|median|standard deviation|std dev) (?:of )?(.+?)(?: by (.+))?",q)
    if m:
        op={"average":"average","mean":"average","total":"sum","sum":"sum","sum of":"sum","maximum":"max","highest value":"max","highest value of":"max","largest value":"max","largest value of":"max","minimum":"min","lowest value":"min","lowest value of":"min","smallest value":"min","smallest value of":"min","median":"median","standard deviation":"stddev","std dev":"stddev"}[m.group(1)]
        col=_entity_column(dataset,m.group(2))
        if col is None: return None
        if m.group(3):
            group=_entity_column(dataset,m.group(3))
            if group and group!=col and op in {"average","sum"}:
                return {"operation":"group_average" if op=="average" else "group_sum","column":col,"group_by":[group],"limit":10}
            return None
        return {"operation":op,"column":col}
    m=re.fullmatch(r"(?:number of (?:records|rows)|count(?: of)?(?: records| rows)?|record counts|breakdown|distribution) by (.+)",q)
    if m:
        col=_entity_column(dataset,m.group(1))
        if col: return {"operation":"group_count","group_by":[col],"limit":10}
    if q in {"show records","show rows","show examples","sample records","records","rows"}:
        return {"operation":"preview","limit":5}
    return None
