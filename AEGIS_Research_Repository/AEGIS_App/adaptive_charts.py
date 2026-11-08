"""Bounded, transparent chart selection for a single uploaded tabular dataset.

The recommender infers *display candidates*, never certified business semantics.
All plotted values are aggregated across accepted rows; no row identifiers or
unaggregated sensitive values are returned. No predictions or supplier actions.
"""
from collections import Counter, defaultdict
from datetime import datetime
from math import isfinite
import re

CHART_LIMIT = 5
POINT_LIMIT = 10


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def _num(value):
    try:
        number = float(str(value).replace(",", "").strip())
        return number if isfinite(number) and abs(number) <= 1e15 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _date(value):
    text = str(value or "").strip()
    if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) or
            re.match(r"^\d{4}-\d{2}-\d{2}[T ]", text)):
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (ValueError, OverflowError):
        return None


def _source(columns, mapping, role, aliases, *, forbid=()):
    if mapping.get(role) in columns:
        return mapping[role], "manager-mapped"
    matches = []
    for col in columns:
        norm = _norm(col)
        if any(bit in norm for bit in forbid):
            continue
        if norm in aliases:
            matches.append((aliases.index(norm), col))
    if matches:
        return min(matches)[1], "header-inferred"
    return None, None


def _top_counts(rows, ix, limit=7):
    tally = Counter(r[ix].strip() for r in rows if r[ix].strip())
    items = sorted(tally.items(), key=lambda v: (-v[1], v[0]))
    main = [{"label": str(key)[:50], "count": count} for key, count in items[:limit]]
    other = sum(count for _, count in items[limit:])
    if other:
        main.append({"label": "Other categories", "count": other})
    return main, len(tally), sum(tally.values())


def _result(identifier, priority, kind, title, reason, source_columns, data, *, caution,
            provenance, value_label="Records"):
    return {"id": identifier, "rank": priority, "type": kind, "title": title,
            "reason": reason, "source_columns": source_columns, "values": data,
            "caution": caution, "selection_basis": provenance, "value_label": value_label,
            "certified": False, "source": "CURRENT_UPLOADED_DATASET", "prediction": False}


def recommend(dataset):
    """Return ranked chart specs using actual entire in-memory uploaded records.

    Never infer contractual lateness, realized spend, causal effects or source truth.
    A heuristic header inference is always disclosed. Missing/invalid values do
    not get silently converted to zeros.
    """
    columns, rows, mapping = dataset.columns, dataset.rows, dataset.mapping
    n = len(rows)
    lookup = {name: i for i, name in enumerate(columns)}
    charts = []
    warnings = ["Chart selection is based on uploaded column names and recorded values; inferred meanings require confirmation.",
                "All charts are descriptive, not verified operational predictions or supplier recommendations."]

    supplier, sup_origin = _source(columns, mapping, "supplier_id", [
        "supplier_id", "supplier", "vendor_id", "vendor", "supplier_name", "vendor_name"])
    category, cat_origin = _source(columns, mapping, "destination_state", [
        "category", "product_category", "region", "destination_state", "state", "area", "segment", "department", "warehouse", "product_type", "carrier", "delivery_zone", "warehouse_id", "location"])
    qty, qty_origin = _source(columns, mapping, "required_units", [
        "required_units", "quantity", "qty", "ordered_units", "order_quantity", "units", "units_ordered", "requested_quantity", "stock_quantity", "inventory_qty", "on_hand", "on_hand_units", "stock_on_hand", "stock_level"])
    price, price_origin = _source(columns, mapping, "unit_cost", [
        "unit_cost", "unit_price", "price_per_unit", "cost_per_unit", "price", "cost", "freight_value", "total_cost"])
    purchase, pur_origin = _source(columns, mapping, "purchase_timestamp", [
        "purchase_timestamp", "order_purchase_timestamp", "purchase_date", "order_date", "created_at", "created_date", "transaction_date", "date"])
    promise, prom_origin = _source(columns, mapping, "promised_delivery_date", [
        "promised_delivery_date", "order_estimated_delivery_date", "expected_delivery_date", "promise_date", "delivery_due_date"])
    actual, actual_origin = _source(columns, mapping, "actual_delivery_timestamp", [
        "actual_delivery_timestamp", "order_delivered_customer_date", "actual_delivery_date", "delivered_at", "delivery_date", "received_date"])

    amount, amount_origin = _source(columns, mapping, "__recorded_amount__", [
        "revenue", "sales_amount", "net_sales", "total_sales", "recorded_sales", "order_total", "invoice_amount", "total_amount", "line_total"])
    domain = "Unclassified business dataset"
    if promise and actual:
        domain = "Delivery and logistics records (inferred)"
    elif supplier:
        domain = "Supplier and procurement records (inferred)"
    elif qty and category and any(t in _norm(category) for t in ("warehouse", "location")):
        domain = "Inventory and warehouse records (inferred)"
    elif amount:
        domain = "Sales and financial records (inferred)"

    if promise and actual and promise != actual:
        p, a = lookup[promise], lookup[actual]
        before = same = after = comparable = 0
        missing = 0
        for row in rows:
            if not row[p] or not row[a]:
                missing += 1
                continue
            d1, d2 = _date(row[p]), _date(row[a])
            if d1 is None or d2 is None:
                continue
            comparable += 1
            before += d2 < d1
            same += d2 == d1
            after += d2 > d1
        if comparable >= 3 and comparable / n >= .5:
            if supplier:
                si = lookup[supplier]
                pair_counts = Counter()
                after_counts = Counter()
                for record in rows:
                    group = record[si].strip()
                    if not group or not record[p] or not record[a]:
                        continue
                    pd, ad = _date(record[p]), _date(record[a])
                    if pd is None or ad is None:
                        continue
                    pair_counts[group] += 1
                    if ad > pd:
                        after_counts[group] += 1
                qualified = [(group, pair_counts[group], after_counts[group])
                             for group in pair_counts if pair_counts[group] >= 10]
                if len(qualified) >= 2:
                    qualified.sort(key=lambda x: (-x[2]/x[1], -x[1], x[0]))
                    bar_values = [{"label":str(group)[:50], "count":round(100 * late / total, 2),
                                   "comparable_rows":total, "after_date_rows":late}
                                  for group,total,late in qualified[:8]]
                    charts.append(_result("recorded_date_exceptions_by_supplier", 112, "bar",
                        "Recorded-after-date share by supplier",
                        f"Share of comparable rows delivered after the mapped date; minimum 10 comparable rows per supplier ({len(qualified)} suppliers qualified).",
                        [supplier, promise, actual], bar_values,
                        caution="This is not a supplier reliability rating or causal attribution. Different order mixes, routes, promises and data gaps may explain differences.",
                        provenance="header-inferred", value_label="After mapped date (%)"))
            charts.append(_result("date_comparison", 110, "bar", "Delivery-date comparison",
                f"{comparable:,} of {n:,} rows have comparable recorded dates.",
                [promise, actual], [{"label":"Before mapped date", "count":before},
                {"label":"On mapped date", "count":same}, {"label":"After mapped date", "count":after}],
                caution=f"{missing:,} rows lacked one or both dates. Calendar-day comparison only; not contractual lateness or supplier fault.",
                provenance="manager-mapped" if prom_origin == actual_origin == "manager-mapped" else "header-inferred"))

    if purchase and amount and purchase != amount:
        p, a = lookup[purchase], lookup[amount]
        monthly = defaultdict(float)
        valid = invalid = 0
        for row in rows:
            dt, number = _date(row[p]), _num(row[a])
            if dt and number is not None:
                monthly[dt.strftime("%Y-%m")] += number
                valid += 1
            elif row[p] and row[a]:
                invalid += 1
        if valid >= 4 and len(monthly) >= 2 and valid / max(valid + invalid, 1) >= .9 and min(monthly.values()) >= 0:
            labels = sorted(monthly)[-12:]
            charts.append(_result("recorded_amount_trend", 105, "line", "Recorded amount over time",
                f"Sum of '{amount}' across {valid:,} rows with valid recorded dates; last {len(labels)} months.",
                [purchase, amount], [{"label":label, "count":round(monthly[label], 2)} for label in labels],
                caution="Amounts are recorded as supplied. Currency, returns and net revenue definitions are not certified.",
                provenance="header-inferred", value_label="Recorded amount"))

    if purchase:
        idx = lookup[purchase]
        months = Counter()
        valid = 0
        for row in rows:
            date = _date(row[idx])
            if date:
                valid += 1
                months[date.strftime("%Y-%m")] += 1
        nonblank = n - dataset.blank_counts[idx]
        if valid >= 3 and len(months) >= 2 and valid / max(nonblank, 1) >= .8:
            labels = sorted(months)[-12:]
            charts.append(_result("activity_over_time", 100, "line", "Activity over time",
                f"{valid:,} parseable dates; showing the last {len(labels)} recorded months.",
                [purchase], [{"label": key, "count": months[key]} for key in labels],
                caution=f"{n-valid:,} rows had no usable ISO date. Recorded row counts, not demand forecasts.",
                provenance=pur_origin))

    grouping = supplier or category
    grouping_origin = sup_origin if supplier else cat_origin
    if not grouping:
        # Generic categorical fallback for datasets whose vocabulary differs
        # from the built-in supply/sales/inventory aliases. Exclude likely IDs.
        for i, col in enumerate(columns):
            norm = _norm(col)
            if any(part in norm for part in ("id", "reference", "email", "phone", "name", "code", "timestamp")):
                continue
            values = [row[i] for row in rows if row[i]]
            distinct = len(set(values))
            if len(values) >= 5 and len(values) / n >= .7 and 2 <= distinct <= min(15, len(values) // 2):
                grouping, grouping_origin = col, "value-pattern-inferred"
                break
    if grouping:
        idx = lookup[grouping]
        values, unique, valid = _top_counts(rows, idx)
        # A unique transaction/order ID is not a useful categorical chart.
        if unique >= 2 and valid >= 3 and unique <= max(12, valid // 2):
            charts.append(_result("records_by_group", 88 if supplier else 78,
                "donut" if unique <= 5 else "bar",
                f"Records by {grouping}",
                f"{valid:,} nonblank records grouped into {unique:,} distinct categories.",
                [grouping], values,
                caution="Counts are source rows, not unique business entities or a measure of category performance.",
                provenance=grouping_origin))

    if amount and grouping and amount != grouping:
        i, j = lookup[amount], lookup[grouping]
        amounts = defaultdict(float)
        valid = invalid = 0
        for row in rows:
            if not row[i] or not row[j]:
                continue
            value = _num(row[i])
            if value is not None:
                amounts[row[j]] += value
                valid += 1
            else:
                invalid += 1
        if valid >= 4 and len(amounts) >= 2 and valid / max(valid + invalid, 1) >= .9 and min(amounts.values()) >= 0:
            top = sorted(amounts.items(), key=lambda t:(-t[1], t[0]))
            values = [{"label":str(k)[:50],"count":round(v,2)} for k,v in top[:7]]
            extra = sum(v for _,v in top[7:])
            if extra:
                values.append({"label":"Other categories","count":round(extra,2)})
            charts.append(_result("recorded_amount_by_group", 99, "bar", f"Recorded amount by {grouping}",
                f"Sum of '{amount}' across {valid:,} categorized rows.", [amount, grouping], values,
                caution=f"{invalid:,} nonnumeric populated rows excluded. Currency, transaction definition and business meaning unverified.",
                provenance="header-inferred", value_label="Recorded amount"))

    if qty and grouping and qty != grouping:
        i, j = lookup[qty], lookup[grouping]
        sums = defaultdict(float)
        valid = invalid = 0
        for row in rows:
            if not row[i] or not row[j]:
                continue
            value = _num(row[i])
            if value is not None and value >= 0:
                sums[row[j]] += value
                valid += 1
            else:
                invalid += 1
        if valid >= 3 and len(sums) >= 2 and (invalid == 0 or valid / (valid + invalid) >= .9):
            leaders = sorted(sums.items(), key=lambda item: (-item[1], item[0]))
            output = [{"label": str(k)[:50], "count": round(v, 2)} for k, v in leaders[:7]]
            rest = sum(v for _, v in leaders[7:])
            if rest:
                output.append({"label": "Other categories", "count": round(rest, 2)})
            charts.append(_result("units_by_group", 94, "bar",
                f"Recorded units by {grouping}",
                f"Sum of nonnegative '{qty}' values across {valid:,} grouped rows.",
                [qty, grouping], output,
                caution=f"{invalid:,} nonnumeric or negative quantity values excluded. Check units and whether rows duplicate orders.",
                provenance="manager-mapped" if qty_origin == grouping_origin == "manager-mapped" else "header-inferred",
                value_label="Recorded units"))

    # For unfamiliar domains, choose a genuine numeric measure only when the
    # values are parseable and non-identifier-like. This is never called spend.
    if not price and not amount:
        for i, col in enumerate(columns):
            norm = _norm(col)
            if any(part in norm for part in ("id", "ref", "code", "zip", "postal", "year", "date", "timestamp", "phone")):
                continue
            nonblank = [row[i] for row in rows if row[i]]
            parsed = [x for x in (_num(v) for v in nonblank) if x is not None]
            if (len(parsed) >= 5 and len(parsed) / max(len(nonblank), 1) >= .9
                    and len(set(parsed)) >= 4):
                price, price_origin = col, "numeric-value-inferred"
                break

    if price:
        idx = lookup[price]
        nums = [_num(row[idx]) for row in rows if row[idx]]
        numbers = [v for v in nums if v is not None]
        if len(numbers) >= 5 and len(numbers) / max(len(nums), 1) >= .9:
            mn, mx = min(numbers), max(numbers)
            if mx > mn:
                width = (mx - mn) / 5
                buckets = [0] * 5
                for v in numbers:
                    buckets[min(4, int((v - mn) / width))] += 1
                labels = [f"{mn+width*i:.2f}–{mn+width*(i+1):.2f}" for i in range(5)]
                charts.append(_result("numeric_distribution", 67, "histogram",
                    f"Distribution of {price}",
                    f"{len(numbers):,} parseable numeric values, split into five equal-width ranges.",
                    [price], [{"label": k, "count": v} for k, v in zip(labels, buckets)],
                    caution=f"{len(nums)-len(numbers):,} nonnumeric populated values excluded. The unit and business meaning are unverified; not total spend.",
                    provenance=price_origin))

    missing = [(columns[i], count) for i, count in enumerate(dataset.blank_counts) if count > 0]
    if missing:
        missing.sort(key=lambda t: (-t[1], t[0]))
        charts.append(_result("field_completeness", 75, "bar", "Fields needing data-quality review",
            f"{len(missing)} of {len(columns)} columns contain blank cells.",
            [name for name, _ in missing[:8]],
            [{"label": str(name)[:50], "count": count} for name, count in missing[:8]],
            caution="These are empty cells only; special missing-value codes are not recognized automatically.",
            provenance="observed-values", value_label="Blank cells"))

    if not charts:
        charts.append(_result("records_overview", 10, "bar", "Records and populated values",
            "This file has no sufficiently reliable numerical, categorical or date fields for specialized charts.",
            columns[:8], [{"label":name[:50], "count": n - dataset.blank_counts[i]}
                         for i, name in enumerate(columns[:8])],
            caution="Only nonblank source cell counts are shown. Map fields to unlock additional views.",
            provenance="observed-values", value_label="Populated rows"))

    charts.sort(key=lambda c: (-c["rank"], c["id"]))
    for chart in charts:
        del chart["rank"]
    selected = charts[:CHART_LIMIT]
    return {"status":"DESCRIPTIVE_ONLY", "business_context":domain, "selection":"RECOMPUTED_ON_DATASET_AND_MAPPING_CHANGE",
            "charts":selected, "candidates":len(charts), "warnings":warnings,
            "excluded_count":len(charts)-len(selected), "permitted_action":"NONE"}
