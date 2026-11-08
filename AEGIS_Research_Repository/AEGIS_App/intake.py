"""Local, memory-only inspection of user-supplied CSV/XLSX data.

Research evidence boundaries: importing, profiling and mapping do not validate
operational semantics, fit an AEGIS model or authorize business actions.
Only one dataset is held in process memory; nothing is written to disk.
"""

from collections import Counter
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from threading import Lock
from urllib.parse import unquote
from xml.etree import ElementTree as ET
import csv
import json
import re
import zipfile


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLUMNS = 60
MAX_CELLS = 1_500_000
PREVIEW_ROWS = 10
EXCEL_MAX_UNCOMPRESSED = 65 * 1024 * 1024

ROLES = {
    "order_id": "Order reference",
    "purchase_timestamp": "Purchase / creation timestamp",
    "promised_delivery_date": "Promised delivery date",
    "actual_delivery_timestamp": "Recorded delivery timestamp",
    "supplier_id": "Supplier reference",
    "item_id": "Item reference",
    "destination_state": "Destination / region",
    "required_units": "Requested units",
    "unit_cost": "Unit cost (currency not assumed)",
    "available_units": "Available capacity units",
    "decision_timestamp": "Historical decision timestamp",
    "purchase_known_at": "Purchase information known at",
    "promise_known_at": "Promise information known at",
    "outcome_recorded_at": "Outcome recorded at",
}


def _safe_name(value):
    name = re.split(r"[/\\]", str(value or ""))[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    if not name or len(name) > 120:
        raise ValueError("Use a filename up to 120 characters.")
    return name


def _clean_rows(iterator):
    try:
        header = next(iterator)
    except StopIteration as error:
        raise ValueError("This file has no header row.") from error
    header = [str(value or "").strip() for value in header]
    if not header or len(header) > MAX_COLUMNS:
        raise ValueError(f"Use a dataset with 1–{MAX_COLUMNS} columns.")
    if any(len(name) > 200 or any(ord(char) < 32 for char in name) for name in header):
        raise ValueError("Column headers must be no longer than 200 characters and contain no control characters.")
    if any(not col for col in header) or len({col.casefold() for col in header}) != len(header):
        raise ValueError("Every column header must be non-empty and unique (ignoring case).")
    rows = []
    for index, raw in enumerate(iterator, start=2):
        if not raw or all(str(value or "").strip() == "" for value in raw):
            continue
        if len(raw) > len(header):
            raise ValueError(f"Row {index} has more cells than the header; please fix the source file.")
        if len(rows) >= MAX_ROWS or (len(rows) + 1) * len(header) > MAX_CELLS:
            raise ValueError(
                f"Dataset exceeds the current safe limit: {MAX_ROWS:,} rows / "
                f"{MAX_CELLS:,} cells. Split or reduce it before import; no sampling was performed."
            )
        values = [str(v if v is not None else "").strip() for v in raw]
        if any(len(value) > 8192 for value in values):
            raise ValueError(f"Row {index} contains a cell longer than 8,192 characters.")
        rows.append(values + [""] * (len(header) - len(values)))
    if not rows:
        raise ValueError("No non-empty data rows were found.")
    return header, rows


def _read_csv(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        decoded = raw.decode("utf-16")
    else:
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("CSV must be UTF-8 or UTF-16 encoded. Re-export the file as UTF-8 CSV.") from error
    try:
        dialect = csv.Sniffer().sniff(decoded[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    try:
        return _clean_rows(csv.reader(StringIO(decoded, newline=""), dialect=dialect, strict=True))
    except (csv.Error, UnicodeError) as error:
        raise ValueError("CSV syntax is invalid; check delimiters and quoted cells.") from error


def _xml(root, member):
    data = root.read(member)
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Unsafe XML declaration in spreadsheet.")
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError("Excel worksheet XML is invalid.") from error


def _excel_date_styles(archive, namespace):
    if "xl/styles.xml" not in archive.namelist():
        return set()
    styles = _xml(archive, "xl/styles.xml")
    custom = {}
    num_formats = styles.find(f"{namespace}numFmts")
    if num_formats is not None:
        custom = {int(row.get("numFmtId", "0")): row.get("formatCode", "")
                  for row in num_formats.findall(f"{namespace}numFmt")}
    xfs = styles.find(f"{namespace}cellXfs")
    if xfs is None:
        return set()
    built_in_dates = {14, 15, 16, 17, 18, 19, 20, 21, 22, 27, 30, 36,
                      45, 46, 47, 50, 57, 58}
    indices = set()
    for index, xf in enumerate(xfs.findall(f"{namespace}xf")):
        num_id = int(xf.get("numFmtId", "0"))
        pattern = custom.get(num_id, "")
        # Strip literals, colors and escaped characters before checking date tokens.
        pattern = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", pattern).lower()
        if num_id in built_in_dates or re.search(r"y{2,}|d{1,2}|m{3,}|h{1,2}|s{1,2}", pattern):
            indices.add(index)
    return indices


def _formatted_excel_date(value, use_1904):
    try:
        serial = float(value)
        if not 0 <= serial <= 2_958_465:
            return value
        if not use_1904 and serial == 60:
            return value  # Excel's fictitious 1900-02-29 cannot be represented.
        origin = datetime(1904, 1, 1) if use_1904 else datetime(1899, 12, 30)
        adjusted = serial + 1 if not use_1904 and 0 < serial < 60 else serial
        stamp = origin + timedelta(days=adjusted)
        return stamp.strftime("%Y-%m-%dT%H:%M:%S") if serial % 1 else stamp.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return value


def _xlsx_cells(raw):
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    relation_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    package_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        members = archive.infolist()
        if any(info.file_size > EXCEL_MAX_UNCOMPRESSED or info.flag_bits & 1 for info in members):
            raise ValueError("Spreadsheet contains oversized or encrypted content.")
        if sum(info.file_size for info in members) > EXCEL_MAX_UNCOMPRESSED:
            raise ValueError("Spreadsheet expands beyond the safe inspection limit.")
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
            raise ValueError("This is not a supported .xlsx workbook.")
        workbook = _xml(archive, "xl/workbook.xml")
        workbook_properties = workbook.find(f"{namespace}workbookPr")
        use_1904 = workbook_properties is not None and workbook_properties.get("date1904") in ("1", "true")
        date_styles = _excel_date_styles(archive, namespace)
        sheets = workbook.find(f"{namespace}sheets")
        if sheets is None:
            raise ValueError("Workbook has no sheets.")
        visible = [s for s in sheets if s.get("state", "visible") == "visible"]
        if not visible:
            raise ValueError("Workbook has no visible worksheet.")
        first = visible[0]
        relation_id = first.get(f"{relation_ns}id")
        relations = _xml(archive, "xl/_rels/workbook.xml.rels")
        target = next((r.get("Target", "") for r in relations
                       if r.get("Id") == relation_id and r.get("Type", "").endswith("/worksheet")), None)
        if not target or ".." in PurePosixPath(target).parts:
            raise ValueError("Workbook worksheet reference is missing or unsafe.")
        member = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if not member.startswith("xl/worksheets/") or member not in names:
            raise ValueError("Workbook worksheet reference is unsupported.")
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared_xml = _xml(archive, "xl/sharedStrings.xml")
            shared = ["".join(n.text or "" for n in si.iter(f"{namespace}t"))
                      for si in shared_xml.iter(f"{namespace}si")]
        worksheet = _xml(archive, member)
        sheet_data = worksheet.find(f"{namespace}sheetData")
        if sheet_data is None:
            raise ValueError("The selected worksheet contains no table.")
        rows = []
        formula_without_cache = 0
        for record in sheet_data.findall(f"{namespace}row"):
            cells = {}
            position = 0
            for cell in record.findall(f"{namespace}c"):
                ref = cell.get("r", "")
                match = re.match(r"([A-Z]+)", ref)
                if match:
                    position = 0
                    for char in match.group(1):
                        position = position * 26 + ord(char) - 64
                    position -= 1
                if position >= MAX_COLUMNS:
                    raise ValueError(f"The worksheet exceeds the {MAX_COLUMNS}-column safety limit.")
                v = cell.find(f"{namespace}v")
                kind = cell.get("t", "")
                if kind == "inlineStr":
                    inline = cell.find(f"{namespace}is")
                    value = "" if inline is None else "".join(n.text or "" for n in inline.iter(f"{namespace}t"))
                elif v is None:
                    value = ""
                    if cell.find(f"{namespace}f") is not None:
                        formula_without_cache += 1
                elif kind == "s":
                    try:
                        value = shared[int(v.text or "-1")]
                    except (ValueError, IndexError) as error:
                        raise ValueError("Worksheet contains an invalid shared-string index.") from error
                elif kind == "b":
                    value = "TRUE" if v.text == "1" else "FALSE"
                elif kind == "e":
                    value = ""
                else:
                    value = v.text or ""
                    try:
                        style = int(cell.get("s", "0"))
                    except ValueError:
                        style = -1
                    if kind not in ("s", "str", "e", "b") and style in date_styles:
                        value = _formatted_excel_date(value, use_1904)
                cells[position] = value
                position += 1
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(i, "") for i in range(width)])
            if len(rows) > MAX_ROWS + 1:
                raise ValueError(f"Worksheet exceeds {MAX_ROWS:,} data rows.")
        headers, data_rows = _clean_rows(iter(rows))
        warnings = [f"Imported first visible worksheet: {first.get('name', 'Sheet 1')}."]
        if len(visible) > 1:
            warnings.append("Other worksheets were not imported; upload them separately if needed.")
        if formula_without_cache:
            warnings.append(f"{formula_without_cache:,} formula cells had no cached value and were treated as blank. Excel formulas were not executed.")
        warnings.append("Styled Excel dates are converted to ISO display values; unstyled numbers stay unchanged. Date semantics are not certified.")
        return headers, data_rows, warnings


def _read_xlsx(raw):
    try:
        return _xlsx_cells(raw)
    except (zipfile.BadZipFile, KeyError, RuntimeError) as error:
        raise ValueError("Could not inspect this .xlsx file. Check that it is a valid, unencrypted workbook.") from error


def _date(text):
    text = str(text or "").strip()
    if not text:
        return None
    try:
        # No ambiguous day/month format or Excel serial assumptions.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.fromisoformat(text)
        if re.match(r"^\d{4}-\d{2}-\d{2}[T ]", text):
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return None


# Header suggestions are never written as confirmed mappings.  They are based on
# exact, unambiguous aliases rather than an LLM guessing from individual rows.
ROLE_ALIASES = {
    "order_id": ("order_id", "order_reference", "order_number", "po_number", "purchase_order_id", "purchase_order_number"),
    "purchase_timestamp": ("purchase_timestamp", "purchase_date", "order_purchase_timestamp", "order_date", "date_ordered"),
    "promised_delivery_date": ("promised_delivery_date", "estimated_delivery_date", "expected_delivery_date", "delivery_due_date", "order_estimated_delivery_date"),
    "actual_delivery_timestamp": ("actual_delivery_timestamp", "actual_delivery_date", "delivered_at", "date_delivered", "order_delivered_customer_date"),
    "supplier_id": ("supplier_id", "vendor_id", "supplier_name", "vendor_name", "supplier_reference", "vendor_reference"),
    "item_id": ("item_id", "item_code", "sku", "product_id", "material_code", "part_number"),
    "destination_state": ("destination_state", "shipping_state", "customer_state", "delivery_region", "shipping_region"),
    "required_units": ("required_units", "ordered_quantity", "quantity_ordered", "order_qty", "ordered_qty", "quantity", "qty"),
    "unit_cost": ("unit_cost", "purchase_unit_cost", "unit_purchase_cost", "cost_per_unit"),
    "available_units": ("available_units", "available_capacity_units", "capacity_available_units"),
    "decision_timestamp": ("decision_timestamp", "decision_at"),
    "purchase_known_at": ("purchase_known_at",),
    "promise_known_at": ("promise_known_at",),
    "outcome_recorded_at": ("outcome_recorded_at",),
}
DATE_ROLES = {"purchase_timestamp", "promised_delivery_date", "actual_delivery_timestamp",
              "decision_timestamp", "purchase_known_at", "promise_known_at", "outcome_recorded_at"}
NUMBER_ROLES = {"required_units", "unit_cost", "available_units"}


def _normalized_header(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def refers_to_uploaded_data(question, dataset=None):
    """Conservative source routing: a general question stays general.

    The local dataset must exist; the question must explicitly concern its
    columns/records or clearly ask to analyze business data. This does not
    give Qwen direct access to files or allow the LLM to choose its own source.
    """
    if dataset is None:
        return False
    from dataset_overview import asks_for_overview
    if asks_for_overview(question):
        return True
    q = re.sub(r"\s+", " ", str(question or "").lower()).strip()
    explicit = ("upload", "uploaded", "uploads", "dataset", "my data", "our data", "this data", "the data",
                "my file", "this file", "the file", "source file", "file i", "file we",
                "field mapping", "map fields", "map the", "which field maps", "mapping", "column", "columns", "schema",
                "data quality", "these records", "my records", "our records",
                "my orders", "our orders", "our suppliers", "my suppliers",
                "my dashboard", "the dashboard", "the charts", "my chart")
    def mentions(phrase):
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", q) is not None
    if any(mentions(phrase) for phrase in explicit):
        return True
    question_patterns = ("which supplier", "which vendor", "switch supplier", "switch suppliers", "change supplier",
                         "recommend supplier", "which orders", "how many orders",
                         "how many rows", "how many records", "missing values",
                         "delivery performance", "recorded after", "late deliveries",
                         "where are the delays", "what needs attention", "what should we prioritize",
                         "what should we check first", "summarize the sales",
                         "summarize the inventory", "stock by warehouse")
    if any(mentions(phrase) for phrase in question_patterns):
        return True
    # A specific header can name the evidence without saying "uploaded".
    return any(len(name) >= 6 and re.search(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)", q)
               for name in dataset.columns if len(name) <= 100)


class LocalDataset:
    def __init__(self, filename, raw):
        self.filename = _safe_name(unquote(filename))
        if not raw or len(raw) > MAX_UPLOAD_BYTES:
            raise ValueError(f"Select a non-empty file smaller than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        self.size_bytes = len(raw)
        if self.filename.lower().endswith(".csv"):
            self.columns, self.rows = _read_csv(raw)
            self.warnings = []
            self.format = "CSV"
        elif self.filename.lower().endswith(".xlsx"):
            self.columns, self.rows, self.warnings = _read_xlsx(raw)
            self.format = "XLSX"
        else:
            raise ValueError("Supported formats: .csv and .xlsx. Legacy .xls is not supported.")
        self.mapping = {}
        self.col_indexes = {name: i for i, name in enumerate(self.columns)}
        self.blank_counts = [sum(not row[i] for row in self.rows) for i in range(len(self.columns))]

    @classmethod
    def from_sqlite_snapshot(cls, filename, columns, rows, warning):
        dataset = cls.__new__(cls)
        dataset.filename = _safe_name(filename)
        dataset.format = "SQLITE_READ_ONLY_SNAPSHOT"
        dataset.columns, dataset.rows = _clean_rows(iter([columns] + rows))
        dataset.size_bytes = sum(len(value.encode("utf-8")) for record in dataset.rows for value in record)
        dataset.warnings = [warning, "Snapshot is a local descriptive copy, not a certified real-time system feed."]
        dataset.mapping = {}
        dataset.col_indexes = {name:i for i,name in enumerate(dataset.columns)}
        dataset.blank_counts = [sum(not row[i] for row in dataset.rows) for i in range(len(dataset.columns))]
        return dataset

    def profile(self):
        total = len(self.rows)
        return {
            "loaded": True,
            "filename": self.filename,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "rows": total,
            "columns": self.columns,
            "column_profiles": [
                {"name": name, "blank_count": self.blank_counts[i],
                 "blank_pct": round(self.blank_counts[i] / total * 100, 2)}
                for i, name in enumerate(self.columns)
            ],
            "preview": [dict(zip(self.columns, row)) for row in self.rows[:PREVIEW_ROWS]],
            "mapping": dict(self.mapping),
            "roles": ROLES,
            "insights": self.insights(),
            "visualizations": self.visualizations(),
            "adaptive_dashboard": __import__("adaptive_charts").recommend(self),
            "review_priorities": self.review_priorities(),
            "warnings": list(self.warnings),
            "storage": "MEMORY_ONLY_UNTIL_APP_EXIT_OR_REMOVE",
            "original_research_bundle_changed": False,
            "model_training": False,
            "operational_approval": "NOT_GRANTED",
            "permitted_action": "NONE",
        }


    def suggested_mappings(self):
        """Only candidate field mappings; no edits and no semantic certification."""
        result = []
        normalized = {}
        for column in self.columns:
            normalized.setdefault(_normalized_header(column), []).append(column)
        for role, aliases in ROLE_ALIASES.items():
            if role in self.mapping:
                result.append({"role": role, "column": self.mapping[role],
                               "status": "user_mapped", "reason": "Selected by the manager; not certified."})
                continue
            matches = [(index, col) for index, alias in enumerate(aliases)
                       for col in normalized.get(alias, [])]
            if not matches:
                continue
            best_rank = min(index for index, _ in matches)
            candidates = sorted({col for index, col in matches if index == best_rank})
            if len(candidates) != 1 or candidates[0] in self.mapping.values():
                continue
            column = candidates[0]
            ix = self.col_indexes[column]
            samples = [row[ix] for row in self.rows if row[ix]][:100]
            if role in DATE_ROLES and samples and sum(_date(value) is not None for value in samples) < 0.8 * len(samples):
                continue
            if role in NUMBER_ROLES and samples:
                def numeric(value):
                    try:
                        value = float(value.replace(",", ""))
                        return value == value and abs(value) < 1e15
                    except (ValueError, OverflowError):
                        return False
                if sum(numeric(value) for value in samples) < 0.8 * len(samples):
                    continue
            result.append({"role": role, "column": column, "status": "suggested_only",
                           "reason": "Header alias and compatible observed format; confirm meaning and units."})
        return result


    def map(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Column mapping must be an object.")
        if any(role not in ROLES for role in payload):
            raise ValueError("Unknown column role in mapping.")
        mapping = {role: str(value) for role, value in payload.items() if value not in (None, "")}
        if any(value not in self.col_indexes for value in mapping.values()):
            raise ValueError("A mapped column does not exist in this upload.")
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("Each field can have only one role; revise duplicate selections.")
        self.mapping = mapping
        return self.profile()

    def insights(self):
        result = {
            "mapped_roles": len(self.mapping),
            "warnings": [],
            "duplicate_order_rows": None,
            "order_values_present": None,
            "timestamp_pairs": None,
            "recorded_after_promise": None,
            "recorded_before_promise": None,
            "recorded_on_promise_date": None,
            "unparseable_timestamp_pairs": None,
            "missing_actual_delivery": None,
            "missing_promise_date": None,
            "recorded_after_examples": [],
            "negative_numeric_values": {},
        }
        if not self.mapping:
            result["warnings"].append("Map columns to unlock descriptive checks. A mapping is not semantic certification.")
            return result
        if "order_id" in self.mapping:
            i = self.col_indexes[self.mapping["order_id"]]
            ids = [row[i] for row in self.rows if row[i]]
            result["order_values_present"] = len(ids)
            result["duplicate_order_rows"] = len(ids) - len(set(ids))
            if result["duplicate_order_rows"]:
                result["warnings"].append("Repeated order IDs were found. Repetition may be valid in order-line data; no rows were deleted.")
        if "promised_delivery_date" in self.mapping and "actual_delivery_timestamp" in self.mapping:
            promised = self.col_indexes[self.mapping["promised_delivery_date"]]
            actual = self.col_indexes[self.mapping["actual_delivery_timestamp"]]
            order_index = self.col_indexes.get(self.mapping.get("order_id"))
            pairs, after, before, on_date, invalid = 0, 0, 0, 0, 0
            result["missing_actual_delivery"] = sum(not row[actual] for row in self.rows)
            result["missing_promise_date"] = sum(not row[promised] for row in self.rows)
            for index, row in enumerate(self.rows, start=1):
                if not row[promised] or not row[actual]:
                    continue
                date_a, date_b = _date(row[promised]), _date(row[actual])
                if date_a is None or date_b is None:
                    invalid += 1
                    continue
                try:
                    # The mapped promise may be a date without a time. A
                    # delivery on that same calendar date is NOT marked late.
                    if date_b.date() > date_a.date():
                        after += 1
                        if len(result["recorded_after_examples"]) < 4:
                            result["recorded_after_examples"].append(
                                row[order_index] if order_index is not None and row[order_index]
                                else f"source row {index}"
                            )
                    elif date_b.date() < date_a.date():
                        before += 1
                    else:
                        on_date += 1
                    pairs += 1
                except TypeError:
                    invalid += 1  # mixed timezone aware / naive
            result.update(timestamp_pairs=pairs, recorded_after_promise=after,
                          recorded_before_promise=before, recorded_on_promise_date=on_date,
                          unparseable_timestamp_pairs=invalid)
            result["warnings"].append(
                "Delivery comparisons use ISO-style calendar dates, not time-of-day; mapped meanings, timezones and contractual promise status still require source-owner review."
            )
        for role in ("required_units", "unit_cost", "available_units"):
            if role in self.mapping:
                index = self.col_indexes[self.mapping[role]]
                negatives = 0
                for row in self.rows:
                    try:
                        negatives += bool(row[index]) and float(row[index]) < 0
                    except ValueError:
                        pass
                result["negative_numeric_values"][role] = negatives
        if "decision_timestamp" not in self.mapping:
            result["warnings"].append("Decision-time availability is not established. No operational prediction is authorized.")
        else:
            result["warnings"].append("A decision timestamp column is mapped, but source-system provenance is not independently certified.")
        return result

    def visualizations(self):
        """Transparent, aggregate-only visuals computed on all accepted source rows.

        Labels are observed source values; no business semantics or predictive
        capability are inferred from their presence.
        """
        total = len(self.rows)
        overall = sum(self.blank_counts)
        capacity = total * len(self.columns)
        completeness = round(100 * (capacity - overall) / capacity, 1)
        completeness_by_field = [
            {"label": name, "count": total - self.blank_counts[i], "total": total}
            for i, name in enumerate(self.columns)
        ]
        group_col = None
        for role in ("destination_state", "supplier_id", "item_id"):
            if role in self.mapping:
                group_col = self.mapping[role]
                break
        if group_col is None:
            for i, name in enumerate(self.columns):
                samples = [row[i] for row in self.rows[:500] if row[i]]
                unique = len(set(samples))
                if samples and 2 <= unique <= 20 and unique / len(samples) <= 0.7:
                    group_col = name
                    break
        categories = []
        if group_col is not None:
            i = self.col_indexes[group_col]
            counts = Counter(row[i] for row in self.rows if row[i])
            categories = [{"label": k, "count": v} for k, v in sorted(
                counts.items(), key=lambda item: (-item[1], item[0]))[:7]]
            other_count = sum(counts.values()) - sum(i["count"] for i in categories)
            if other_count:
                categories.append({"label": "Other values", "count": other_count})
        timeline = []
        if "purchase_timestamp" in self.mapping:
            i = self.col_indexes[self.mapping["purchase_timestamp"]]
            months = Counter()
            for row in self.rows:
                stamp = _date(row[i]) if row[i] else None
                if stamp is not None:
                    months[stamp.strftime("%Y-%m")] += 1
            # Showing last twelve periods, not silently presenting them as all periods.
            timeline = [{"label": month, "count": months[month]} for month in sorted(months)[-12:]]
        checks = self.insights()
        outcomes = []
        if checks["timestamp_pairs"] is not None:
            outcomes = [
                {"label": "Before mapped date", "count": checks["recorded_before_promise"]},
                {"label": "On mapped date", "count": checks["recorded_on_promise_date"]},
                {"label": "After mapped date", "count": checks["recorded_after_promise"]},
            ]
        return {
            "row_count": total,
            "column_count": len(self.columns),
            "completeness_pct": completeness,
            "filled_cells": capacity - overall,
            "total_cells": capacity,
            "categories_source_column": group_col,
            "categories": categories,
            "completeness_by_field": completeness_by_field,
            "monthly_source_column": self.mapping.get("purchase_timestamp"),
            "timeline_last_12_periods": timeline,
            "delivery_date_comparison": outcomes,
            "delivery_comparable_rows": checks["timestamp_pairs"],
            "certified_business_metrics": False,
            "prediction_model_applied": False,
        }

    def review_priorities(self):
        """Only descriptive verification next-steps, never execution advice."""
        checks = self.insights()
        total = len(self.rows)
        priorities = []
        if not self.mapping:
            priorities.append({"title": "Confirm what the fields mean",
                "evidence": "No business columns have been mapped yet.",
                "next_step": "Review column names with the data owner and map the relevant fields."})
        if any(self.blank_counts):
            i = max(range(len(self.blank_counts)), key=lambda j: self.blank_counts[j])
            priorities.append({"title": "Review missing source values",
                "evidence": f"{self.blank_counts[i]:,} of {total:,} rows are blank in '{self.columns[i]}'.",
                "next_step": "Check whether these blanks are expected before relying on this field."})
        if checks["recorded_after_promise"]:
            priorities.append({"title": "Investigate date exceptions",
                "evidence": (f"{checks['recorded_after_promise']:,} of "
                    f"{checks['timestamp_pairs']:,} comparable rows have a recorded delivery date after the mapped promise date."),
                "next_step": "Verify date definitions and trace these orders with the source owner; do not infer supplier fault."})
        if checks["duplicate_order_rows"]:
            priorities.append({"title": "Check repeated order references",
                "evidence": f"{checks['duplicate_order_rows']:,} repeated non-empty references were counted.",
                "next_step": "Confirm whether these are valid order lines or data-quality exceptions."})
        for role, count in checks["negative_numeric_values"].items():
            if count:
                priorities.append({"title": "Validate negative numbers",
                    "evidence": f"{count:,} negative values are present in the mapped {role.replace('_', ' ')} field.",
                    "next_step": "Confirm whether they represent adjustments, returns, or incorrect entries."})
        if not priorities:
            priorities.append({"title": "Validate the dataset before decisions",
                "evidence": f"{total:,} uploaded rows have been inspected descriptively.",
                "next_step": "Confirm field meanings, source timestamps, and a measurable business decision with the data owner."})
        return priorities[:4]

    def model_facts(self):
        """Small derived-only packet: never include source records or individual IDs."""
        checks = self.insights()
        return {
            "file_rows": len(self.rows),
            "file_columns": len(self.columns),
            "mapped_roles": dict(self.mapping),
            "source_columns_only_not_rows": [column[:100] for column in self.columns],
            "candidate_mapping_not_certified": self.suggested_mappings(),
            "blank_cells_by_column": {
                self.columns[i]: count for i, count in enumerate(self.blank_counts) if count
            },
            "repeated_order_rows": checks["duplicate_order_rows"],
            "comparable_delivery_date_pairs": checks["timestamp_pairs"],
            "dates_recorded_after_promise": checks["recorded_after_promise"],
            "dates_recorded_before_promise": checks["recorded_before_promise"],
            "dates_recorded_on_promise": checks["recorded_on_promise_date"],
            "missing_delivery_values": checks["missing_actual_delivery"],
            "invalid_date_pairs": checks["unparseable_timestamp_pairs"],
            "negative_numeric_values": checks["negative_numeric_values"],
            "semantics_certified": False,
            "decision_time_provenance_certified": False,
            "model_fitted_on_upload": False,
            "permitted_business_action": "NONE",
        }

    def answer(self, question, history=None):
        """Answer with verified, recomputed facts and narrow conversational context.

        Browser history is used only to identify what a follow-up refers to. No
        claims or figures from the browser history are trusted as evidence.
        """
        text = str(question or "").strip()
        if not text or len(text) > 1500:
            raise ValueError("Enter a question of 1–1,500 characters.")
        if history is None:
            history = []
        if not isinstance(history, list) or len(history) > 6 or any(
            not isinstance(item, dict) or not isinstance(item.get("question"), str)
            or len(item["question"]) > 1500 for item in history
        ):
            raise ValueError("Conversation history is invalid or too long.")
        previous = history[-1]["question"].lower() if history else ""
        words = text.lower()
        insights = self.insights()
        total = len(self.rows)
        count = insights["timestamp_pairs"]
        after = insights["recorded_after_promise"]
        missing = insights["missing_actual_delivery"]

        def delivery_summary():
            if count is None:
                return "I need both the promised-delivery and actual-delivery fields mapped before I can compare those dates."
            detail = (f"I checked {total:,} rows: {count:,} have comparable recorded promise and delivery dates, "
                      f"{insights['recorded_before_promise']:,} were before the mapped promise date, "
                      f"{insights['recorded_on_promise_date']:,} on the same calendar date, "
                      f"and {after:,} after the mapped promise date. "
                      f"Missing actual-delivery values: {missing:,}")
            if insights["missing_promise_date"]:
                detail += f", and {insights['missing_promise_date']:,} have no promise date"
            detail += ". "
            if insights["unparseable_timestamp_pairs"]:
                detail += (f"Another {insights['unparseable_timestamp_pairs']:,} non-empty date pairs "
                           "couldn't be parsed. ")
            return detail + "This is a recorded-date comparison, not yet a verified business late-delivery KPI."

        def supplier_boundary(confirmation=False):
            lead = ("Yes—I'm sure the evidence isn't enough to justify changing suppliers. " if confirmation else
                    "Not on this evidence. I wouldn't recommend switching suppliers yet. ")
            evidence = (delivery_summary() + " " if count is not None else "")
            return (lead + evidence + "I can't infer supplier causality from delivery dates alone. "
                    "We would need supplier dispatch records, carrier milestones, verified alternatives, "
                    "capacity, costs and a fair baseline comparison before evaluating a switch. "
                    "No supplier change or purchase is authorized here.")

        is_action = any(term in words for term in (
            "switch", "reallocat", "procure", "execute", "recommend supplier", "change suppliers",
            "should we buy", "place an order", "place purchase", "issue purchase order", "buy from",
            "automatically purchase", "make the purchase", "approve a", "approve the",
            "move orders", "change the supplier", "reroute", "allocate orders",
        ))
        prior_action = any(term in previous for term in (
            "switch", "reallocat", "procure", "execute", "recommend supplier", "change suppliers",
            "purchase", "approve", "reroute", "allocate orders",
        ))
        prior_delivery = any(term in previous for term in ("late", "delay", "promise", "delivered", "delivery"))
        prior_mapping = any(term in previous for term in ("mapping", "map fields", "columns", "schema", "field names"))
        is_confirmation = any(term in words for term in (
            "are you sure", "you sure", "is that correct", "is that right", "really?",
            "can you confirm", "check again", "double check", "double-check", "verify that",
        ))
        asks_for_elaboration = any(term in words for term in (
            "explain more", "tell me more", "what do you mean", "can you elaborate",
            "explain that", "how do you know", "where did that come from",
        ))

        if is_confirmation:
            if prior_action:
                answer = supplier_boundary(confirmation=True)
            elif prior_delivery:
                answer = "I checked the original uploaded records again. " + delivery_summary()
            elif history:
                answer = (f"I can verify the source file has {total:,} rows and {len(self.columns)} columns. "
                          "Which part of my previous answer would you like me to double-check? "
                          "I won't treat an unverified upload as proof of supplier causes or business outcomes.")
            else:
                answer = "I can double-check a specific finding. Which number or conclusion are you referring to?"
        elif is_action:
            answer = supplier_boundary()
        elif asks_for_elaboration and prior_action:
            answer = supplier_boundary()
        elif prior_mapping and (asks_for_elaboration or re.fullmatch(r"(?:why|how|why that|why these|explain)[?.! ]*", words)):
            proposed = [x for x in self.suggested_mappings() if x["status"] == "suggested_only"]
            examples = "; ".join(f"{ROLES[x['role']]} matched '{x['column']}'" for x in proposed[:4])
            answer = ("Those were suggestions based on recognizable column headers and compatible sample formats, "
                      "not confirmed meanings. " + (examples + ". " if examples else "") +
                      "For example, Unit Price may be a selling price rather than the purchasing cost. "
                      "Please confirm field meanings, units and dates with whoever owns the data before saving the mapping.")
        elif asks_for_elaboration and prior_delivery:
            answer = ("The comparison comes directly from the two fields you mapped: "
                      f"'{self.mapping.get('promised_delivery_date', 'promised delivery')}' and "
                      f"'{self.mapping.get('actual_delivery_timestamp', 'actual delivery')}'. "
                      + delivery_summary() +
                      " It does not explain who caused a delay, whether timestamps use comparable timezones, "
                      "or whether the business uses this definition of lateness.")
        elif any(term in words for term in ("why late", "why delayed", "why did", "who caused", "responsible", "whose fault", "supplier cause")):
            answer = ("We can't tell who caused a delivery delay from this file alone. " +
                      delivery_summary() + " To investigate causes, we'd need timestamps for picking, "
                      "dispatch, carrier handoffs and delivery exceptions—not just supplier IDs.")
        elif any(term in words for term in ("which ones", "which orders", "show me the orders")) and prior_delivery:
            if count is None:
                answer = delivery_summary()
            elif after:
                sample = ", ".join(insights["recorded_after_examples"])
                answer = (f"The recorded-after-promise examples are {sample}. "
                          f"There are {after:,} such rows in the uploaded file. "
                          "These are source references, not verified supplier-fault findings.")
            else:
                answer = "I found no parseable pairs with a delivery date after the mapped promise date."
        elif any(term in words for term in ("missing delivery", "missing outcome", "missing ones", "unknown outcome")):
            answer = (f"{missing:,} of the {total:,} rows have no actual-delivery value. "
                      "I can't classify those orders as on time or late from the current file.") if missing is not None else delivery_summary()
        elif any(term in words for term in ("column", "field", "mapping", "schema", "which headers")):
            proposals = self.suggested_mappings()
            existing = [x for x in proposals if x["status"] == "user_mapped"]
            suggested = [x for x in proposals if x["status"] == "suggested_only"]
            names = ", ".join(repr(name[:75]) for name in self.columns[:32])
            if len(self.columns) > 32:
                names += f", and {len(self.columns) - 32} more columns"
            answer = (f"I can read the structure of your currently uploaded file: {total:,} rows, "
                      f"{len(self.columns)} columns. Available column names: {names}.\n")
            if existing:
                answer += "\nAlready mapped by you: " + "; ".join(
                    f"{x['role']} → {x['column']}" for x in existing) + "."
            if suggested:
                answer += "\nSuggested mappings to review (NOT automatically applied):\n" + "\n".join(
                    f"• {ROLES[x['role']]} → {x['column']}" for x in suggested)
            else:
                answer += "\nNo unambiguous additional mappings can be proposed from the headers and sample formats."
            if "unit_cost" not in {x["role"] for x in proposals} and any(
                    _normalized_header(col) in {"unit_price", "price"} for col in self.columns):
                answer += ("\nI see a price field, but price is not necessarily procurement unit cost; "
                           "confirm its meaning before assigning the cost role.")
            answer += ("\nReview and save these in Data → Field Mapping. Confirm the business definitions, "
                       "date timezones, and units with the data owner; these are suggestions, not certified facts.")
        elif any(term in words for term in ("late", "delay", "promise", "delivered", "delivery date")):
            answer = delivery_summary()
        elif any(term in words for term in ("missing", "blank", "quality", "complete")):
            ranked = sorted(zip(self.columns, self.blank_counts), key=lambda x: x[1], reverse=True)
            top = ", ".join(f"{name}: {count:,} blank" for name, count in ranked[:5])
            answer = (f"I checked all {total:,} rows. The columns with the most empty cells are {top}. "
                      "I haven't assumed that values like 'N/A' or 'unknown' mean missing; those need source-specific rules.")
        elif any(term in words for term in ("duplicate", "unique", "order id")):
            duplicates = insights["duplicate_order_rows"]
            answer = ("Please map the order-reference column first."
                      if duplicates is None else
                      f"I found {duplicates:,} repeated non-empty order references beyond their first occurrence. "
                      "That can be normal if a dataset contains multiple line items per order.")
        elif __import__("dataset_overview").asks_for_overview(words):
            answer = __import__("dataset_overview").build_overview(self)["answer"]
        elif any(term in words for term in ("how many rows", "number of rows", "how many records", "how big is", "file size", "how many entries")):
            answer = (f"I inspected {total:,} data rows across {len(self.columns):,} columns "
                      f"in the uploaded file. {len(self.mapping)} business field roles are mapped so far. "
                      "This is a file count, not a count of independently verified business orders.")
        elif any(term in words for term in ("what can you do", "how can you help", "what can i ask", "help me analyze")):
            answer = ("We can examine the file structure, missing values, repeated order references, "
                      "your column mappings and recorded promise-versus-delivery timestamps. "
                      "You can follow up naturally—for example, ask whether a count is correct or why the "
                      "file is insufficient for a supplier decision. I can't verify business causes or execute changes.")
        elif re.fullmatch(r"(bruh+|bro+|huh+|lol+|wtf|what\??|nah+|okay+|ok+)[!?. ]*", words):
            answer = ("Fair reaction 😅 — that sounded more like a compliance report than a conversation. "
                      "What did you want me to explain? We can take it one question at a time. "
                      "I'll check the file when you ask about a specific finding.")
        elif re.fullmatch(r"(hi|hello|hey|thanks|thank you)[!. ]*", words):
            lead = "You're welcome!" if words.startswith(("thanks", "thank you")) else "Hi!"
            answer = f"{lead} Ask me anything about the uploaded dataset, and we'll work through the evidence together."
        elif any(term in words for term in (
            "recommendation", "recommendations", "prioritize", "priority", "priorities",
            "suggest", "what should we check", "what should i check", "what should we focus",
            "what decision", "what can we improve", "where to start", "what next",
            "next step", "what should i do",
        )):
            items = self.review_priorities()[:3]
            answer = ("Based on the uploaded records, these are the checks I'd prioritize for review:\n"
                + "\n".join(f"{i+1}. {p['title']}: {p['evidence']} {p['next_step']}"
                           for i, p in enumerate(items))
                + "\nThese are data-review suggestions, not verified supplier decisions. "
                  "A manager must validate the source and approve any real-world action.")
        else:
            answer = (f"I don't have enough evidence or a verified method to answer that specific question from "
                      f"this {total:,}-row upload yet. Tell me which measure or outcome you'd like to examine; "
                      "I can check the source columns, missing values and mapped delivery dates without guessing.")
        includes_individual_references = any(
            term in words for term in ("which ones", "which orders", "show me the orders")
        ) and prior_delivery
        safety_gate = is_action or includes_individual_references or (is_confirmation and prior_action) or any(
            term in words for term in ("column", "field", "mapping", "schema", "which headers")
        ) or any(
            token in words for token in ("why did", "who caused", "responsible", "whose fault", "supplier cause")
        )
        return {"answer": answer, "context": "local_dataset", "evidence_source": "LOCAL_USER_UPLOAD_UNVERIFIED",
                "routing_mode": "CONTEXTUAL_DESCRIPTIVE_RULES_NO_LLM", "operational_approval": "NOT_GRANTED",
                "permitted_action": "NONE", "human_review": "REQUIRED", "safety_gate": safety_gate}


class IntakeStore:
    def __init__(self):
        self.lock = Lock()
        self.dataset = None
        self.revision = 0

    def status(self):
        with self.lock:
            return {**self.dataset.profile(), "dataset_revision": self.revision} if self.dataset else {
                "dataset_revision": self.revision,
                "loaded": False, "max_upload_bytes": MAX_UPLOAD_BYTES, "max_rows": MAX_ROWS,
                "max_columns": MAX_COLUMNS, "max_cells": MAX_CELLS,
                "roles": ROLES, "storage": "MEMORY_ONLY_UNTIL_APP_EXIT_OR_REMOVE",
                "permitted_action": "NONE",
            }

    def upload(self, filename, raw):
        dataset = LocalDataset(filename, raw)
        with self.lock:
            self.dataset = dataset  # Successful import replaces only the previous transient upload.
            self.revision += 1
        return self.status()

    def sqlite_snapshot(self, table):
        # Import is invoked by an explicit button from the trusted local UI.
        from connectors import read_sqlite_table_snapshot
        columns, rows, warning, filename = read_sqlite_table_snapshot(table)
        dataset = LocalDataset.from_sqlite_snapshot(filename + "_" + table + ".sqlite", columns, rows, warning)
        with self.lock:
            self.dataset = dataset
            self.revision += 1
        return self.status()

    def mapping(self, fields):
        with self.lock:
            if self.dataset is None:
                raise ValueError("Upload a dataset first.")
            self.dataset.map(fields)
        return self.status()

    def question_is_about_upload(self, question):
        with self.lock:
            return refers_to_uploaded_data(question, self.dataset)

    def answer(self, question, history=None):
        return self.explain(question, history)[0]

    def explain(self, question, history=None):
        with self.lock:
            if self.dataset is None:
                raise ValueError("Upload a dataset before asking about it.")
            return (self.dataset.answer(question, history=history), self.dataset.model_facts())

    def model_facts(self):
        with self.lock:
            if self.dataset is None:
                raise ValueError("Upload a dataset before asking about it.")
            return self.dataset.model_facts()

    def query_analysis(self, question, history=None, use_local_llm=False):
        """Give both AEGIS modes complete read-only analytical access.

        Only the authenticated local upload currently in memory is queried;
        no filesystem access or SQL statement from the model is accepted.
        """
        from dataset_queries import schema, basic_plan, execute_many, explain
        from dataset_overview import asks_for_overview, build_overview
        with self.lock:
            dataset = self.dataset
        if dataset is None:
            raise ValueError("Upload a dataset first.")
        # A broad question needs a data-backed managerial reading, not an LLM
        # plan for an arbitrary metric. Both modes use the identical evidence.
        if asks_for_overview(question):
            with self.lock:
                if self.dataset is not dataset:
                    raise ValueError("The active dataset changed; please ask again.")
                overview = build_overview(dataset)
            result = {"answer": overview["answer"], "context": "local_dataset",
                      "evidence_source": "CURRENT_UPLOADED_DATASET_VERIFIED_OVERVIEW",
                      "routing_mode": "OFFLINE_RECOMPUTED_MANAGER_OVERVIEW",
                      "operational_approval": "NOT_GRANTED", "permitted_action": "NONE",
                      "human_review": "REQUIRED", "safety_gate": False,
                      "overview": {"rows": overview["rows"],
                                   "columns": overview["columns"],
                                   "patterns": overview["patterns"]}}
            facts = {**dataset.model_facts(),
                     "checked_dataset_overview": overview["answer"],
                     "overview_calculations": overview["patterns"],
                     "business_semantics_certified": False,
                     "no_procurement_actions": True}
            return result, facts
        plan = None
        planner_used = False
        if use_local_llm:
            try:
                from conversation import plan_dataset_with_local_qwen, LocalModelUnavailable
                plan = plan_dataset_with_local_qwen(question, schema(dataset), history)
                planner_used = True
            except LocalModelUnavailable:
                pass
        if plan is None:
            plan = basic_plan(question, dataset, history)
        if plan is None:
            return None
        with self.lock:
            if self.dataset is not dataset:
                raise ValueError("Dataset was replaced during this analysis. Please ask again.")
            try:
                outputs = execute_many(dataset, plan)
            except ValueError:
                if planner_used:
                    fallback_plan = basic_plan(question, dataset, history)
                    if fallback_plan is None:
                        return None
                    outputs = execute_many(dataset, fallback_plan)
                    planner_used = False
                else:
                    return None
        checked = explain(outputs)
        model_facts = {"file_rows": len(dataset.rows), "file_columns": len(dataset.columns),
                       "read_only_query_outputs": outputs, "no_procurement_actions": True,
                       "business_semantics_certified": False,
                       "local_qwen_saw_selected_rows_only_if_preview_was_requested": True}
        result = {"answer": checked, "context": "local_dataset",
                  "evidence_source": "ACTUAL_LOCAL_UPLOADED_DATA_READ_ONLY_QUERY",
                  "routing_mode": ("LOCAL_QWEN_PLANNED_VERIFIED_QUERY" if planner_used else
                                   "OFFLINE_VERIFIED_DATA_QUERY"),
                  "operational_approval": "NOT_GRANTED", "permitted_action": "NONE",
                  "human_review": "REQUIRED", "safety_gate": False,
                  "analysis": outputs}
        return result, model_facts

    def chart(self, options):
        """Generate a validated read-only visualization from the active upload."""
        from custom_charts import build_chart
        with self.lock:
            if self.dataset is None:
                raise ValueError("Upload a dataset before building custom charts.")
            return {**build_chart(self.dataset, options), "dataset_revision": self.revision}

    def clear(self):
        with self.lock:
            self.dataset = None
            self.revision += 1
        return self.status()


INTAKE = IntakeStore()
