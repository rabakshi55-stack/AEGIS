"""Manager-defined read-only charts for the current in-memory upload.

Never executes expressions, SQL or Python supplied by users or an LLM. Each
chart is computed from the full accepted dataset; render limits are disclosed.
"""
from collections import defaultdict
from datetime import datetime
from math import floor, isfinite
from statistics import median
import re

CHART_TYPES = ("bar", "horizontal_bar", "line", "area", "pie", "donut", "scatter", "histogram", "table")
AGGREGATIONS = ("count", "sum", "average", "minimum", "maximum", "median", "count_nonblank", "distinct_count")
DATE_GRAINS = ("none", "day", "week", "month", "quarter", "year")
SORTS = ("value_desc", "value_asc", "x_asc", "x_desc")
MAX_CHART_POINTS = 100
MAX_SCATTER_POINTS = 300


def _number(value):
    try:
        text = str(value).strip().replace(",", "")
        if not text or text.startswith(("=", "+=")):
            return None
        result = float(text)
        return result if isfinite(result) and abs(result) <= 1e15 else None
    except (TypeError, ValueError):
        return None


def _date(value):
    text = str(value).strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$", text):
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _period(value, grain):
    if grain == "none":
        return value
    day = _date(value)
    if day is None:
        return None
    if grain == "day":
        return day.strftime("%Y-%m-%d")
    if grain == "week":
        y, w, _ = day.isocalendar()
        return f"{y:04d}-W{w:02d}"
    if grain == "month":
        return day.strftime("%Y-%m")
    if grain == "quarter":
        return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
    if grain == "year":
        return str(day.year)
    raise ValueError("Unsupported date grouping.")


def _validated(dataset, options):
    if not isinstance(options, dict) or len(options) > 18:
        raise ValueError("Chart configuration must be a small object.")
    permitted = {"chart_type", "x", "y", "aggregation", "date_grain", "sort", "limit"}
    if set(options) - permitted:
        raise ValueError("Unknown chart configuration. Only approved chart controls are accepted.")
    typ = options.get("chart_type", "bar")
    agg = options.get("aggregation", "count")
    grain = options.get("date_grain", "none")
    order = options.get("sort", "value_desc")
    x = options.get("x")
    y = options.get("y") or None
    if typ not in CHART_TYPES or agg not in AGGREGATIONS or grain not in DATE_GRAINS or order not in SORTS:
        raise ValueError("Choose one of the supported chart, calculation, date grouping or sort options.")
    if not isinstance(x, str) or x not in dataset.col_indexes:
        raise ValueError("Choose an existing source column for the X-axis.")
    if y is not None and (not isinstance(y, str) or y not in dataset.col_indexes):
        raise ValueError("The selected Y-axis column does not exist in the uploaded dataset.")
    if grain != "none" and typ in {"scatter", "histogram"}:
        raise ValueError("Date grouping is available for grouped charts, not scatter or histograms.")
    if typ == "scatter":
        if not y or y == x:
            raise ValueError("Scatter charts need two distinct numeric X and Y fields.")
    elif typ == "histogram":
        if y:
            raise ValueError("A histogram displays the distribution of one numeric field. Clear Y or choose a grouped chart.")
    elif agg not in ("count",) and not y:
        raise ValueError("This calculation requires a Y-axis field. For record counts, choose Count rows.")
    elif agg == "count" and y:
        raise ValueError("Count rows does not use a Y field. Clear Y or choose Count nonblank Y / another calculation.")
    if typ not in {"scatter", "histogram"} and agg != "count" and y == x and grain == "none":
        raise ValueError("To aggregate the same field as X and Y, use a grouped date period or choose different fields.")
    limit = options.get("limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 2 <= limit <= MAX_CHART_POINTS:
        raise ValueError(f"Show between 2 and {MAX_CHART_POINTS} groups or bins.")
    if typ in {"scatter", "histogram"} and agg != "count":
        # Scatter uses direct coordinates; histograms use frequencies.
        agg = "count"
    return {"chart_type": typ, "x": x, "y": y, "aggregation": agg,
            "date_grain": grain, "sort": order, "limit": limit}


def build_chart(dataset, options):
    """Compute one chart; returns no original row values except bounded scatter coordinates."""
    conf = _validated(dataset, options)
    typ, x, y, agg = (conf[k] for k in ("chart_type", "x", "y", "aggregation"))
    xi = dataset.col_indexes[x]
    yi = dataset.col_indexes[y] if y else None
    n = len(dataset.rows)
    excluded_x = 0
    invalid_y = 0
    source = {"source": "CURRENT_LOCAL_UPLOADED_DATASET", "dataset": dataset.filename,
              "source_columns": [x] + ([y] if y else []), "source_rows": n,
              "business_definition_certified": False, "permitted_action": "NONE",
              "caution": "Descriptive source values only; definitions, units, currency, causality and decisions are not independently certified."}

    if typ == "scatter":
        points = []
        valid = 0
        for row in dataset.rows:
            xv = _number(row[xi]); yv = _number(row[yi])
            if xv is None:
                excluded_x += 1
            elif yv is None:
                invalid_y += 1
            else:
                valid += 1
                if len(points) < MAX_SCATTER_POINTS:
                    points.append({"x": xv, "y": yv})
        if not valid:
            raise ValueError("Scatter requires numeric values in both fields; no valid pairs were found.")
        return {**source, **conf, "points": points, "plotted_points": len(points),
                "valid_rows": valid, "excluded_x_rows": excluded_x, "excluded_y_rows": invalid_y,
                "truncated": valid > len(points), "note": (
                    f"Showing the first {len(points):,} of {valid:,} valid numeric pairs in source order; "
                    "the full dataset was checked. This is not a random sample." if valid > len(points) else
                    f"Showing all {valid:,} valid numeric pairs.")}

    if typ == "histogram":
        values = []
        for row in dataset.rows:
            value = _number(row[xi])
            if value is None:
                excluded_x += 1
            else:
                values.append(value)
        if not values:
            raise ValueError("Histogram requires a numeric X field with valid values.")
        low, high = min(values), max(values)
        buckets = min(conf["limit"], max(2, floor(len(values) ** 0.5)))
        if high == low:
            counts = [len(values)]
            output = [{"label": f"{low:g}", "value": len(values)}]
        else:
            counts = [0] * buckets
            for v in values:
                ix = min(buckets - 1, int((v - low) / (high - low) * buckets))
                counts[ix] += 1
            output = [{"label": f"{low + i*(high-low)/buckets:.5g} – {low + (i+1)*(high-low)/buckets:.5g}",
                       "value": c} for i, c in enumerate(counts)]
        return {**source, **conf, "values": output, "total_groups": len(output),
                "valid_rows": len(values), "excluded_x_rows": excluded_x,
                "excluded_y_rows": 0, "truncated": False,
                "note": f"All {len(values):,} valid numeric values grouped into {len(output)} bins."}

    grouped = defaultdict(list)
    raw_counts = defaultdict(int)
    for row in dataset.rows:
        v = row[xi]
        if not v:
            excluded_x += 1
            continue
        key = _period(v, conf["date_grain"])
        if key is None:
            excluded_x += 1
            continue
        if agg == "count":
            raw_counts[key] += 1
        elif agg == "count_nonblank":
            if not row[yi]:
                invalid_y += 1
            else:
                raw_counts[key] += 1
        elif agg == "distinct_count":
            value = row[yi]
            if not value:
                invalid_y += 1
            else:
                grouped[key].append(value)
        else:
            value = _number(row[yi])
            if value is None:
                invalid_y += 1
            else:
                grouped[key].append(value)
    if agg in ("count", "count_nonblank"):
        values = {key: count for key, count in raw_counts.items()}
    elif agg == "distinct_count":
        values = {key: len(set(group)) for key, group in grouped.items()}
    elif agg == "sum":
        values = {key: sum(group) for key, group in grouped.items()}
    elif agg == "average":
        values = {key: sum(group) / len(group) for key, group in grouped.items()}
    elif agg == "minimum":
        values = {key: min(group) for key, group in grouped.items()}
    elif agg == "maximum":
        values = {key: max(group) for key, group in grouped.items()}
    else:
        values = {key: median(group) for key, group in grouped.items()}
    if not values:
        raise ValueError("No usable rows for this combination. Check missing values, data types or the selected calculation.")
    if typ in {"donut", "pie"} and (min(len(values), conf["limit"]) > 30 or any(value < 0 for value in values.values()) or
                                    sum(values.values()) <= 0):
        raise ValueError("Pie and donut charts require 1–30 groups with nonnegative values and a positive total. Use a bar or table instead.")
    if conf["sort"] == "value_desc":
        ordered = sorted(values.items(), key=lambda p: (-p[1], p[0]))
    elif conf["sort"] == "value_asc":
        ordered = sorted(values.items(), key=lambda p: (p[1], p[0]))
    else:
        ordered = sorted(values.items(), key=lambda p: p[0], reverse=conf["sort"] == "x_desc")
    truncated = len(ordered) > conf["limit"]
    view = ordered[:conf["limit"]]
    valid_rows = n - excluded_x - invalid_y
    return {**source, **conf, "values": [{"label": key, "value": round(v, 8)} for key,v in view],
            "total_groups": len(values), "valid_rows": valid_rows,
            "excluded_x_rows": excluded_x, "excluded_y_rows": invalid_y,
            "truncated": truncated,
            "note": (f"Calculated from all {n:,} source rows; {valid_rows:,} rows contributed. "
                     f"Showing {len(view):,} of {len(values):,} groups; {excluded_x:,} missing/invalid X and "
                     f"{invalid_y:,} missing/invalid Y rows excluded. "
                     + ("Sort by X ascending to see a chronological trend. " if typ in {"line", "area"} and
                        conf["sort"] not in {"x_asc", "x_desc"} else "")
                     + ("Pie/donut percentages use only the visible groups. " if truncated and typ in {"pie", "donut"} else ""))}
