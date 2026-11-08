"""Audited, session-only attachment of the ORIGINAL Olist order outcome table.

This independent source is never merged into frozen predictions or synthetic
scenarios. Comparison means observed delivery calendar date vs Olist's recorded
*estimated* delivery calendar date, not contractual on-time performance.
"""

from collections import Counter
from io import StringIO
from threading import Lock
import csv

from intake import _date, _safe_name


MAX_OUTCOME_UPLOAD_BYTES = 30 * 1024 * 1024
REQUIRED_COLUMNS = {
    "order_id", "order_status", "order_purchase_timestamp", "order_estimated_delivery_date",
    "order_delivered_customer_date",
}


class HistoricalOutcomes:
    def __init__(self, filename, raw, expected_ids):
        self.filename = _safe_name(filename)
        if not self.filename.lower().endswith(".csv"):
            raise ValueError("Choose the original Olist orders CSV file (not a predictions export).")
        if not raw or len(raw) > MAX_OUTCOME_UPLOAD_BYTES:
            raise ValueError("Original Olist CSV must be non-empty and no larger than 30 MB.")
        source_ids = set(expected_ids)
        if not source_ids or len(source_ids) != len(expected_ids):
            raise ValueError("The research order registry is unavailable or invalid.")
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("Olist CSV must use UTF-8 encoding.") from error
        reader = csv.DictReader(StringIO(decoded, newline=""), strict=True)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not REQUIRED_COLUMNS.issubset(header):
            raise ValueError(
                "This is not the original Olist order table. Expected order_id, "
                "order_status, order_purchase_timestamp, order_estimated_delivery_date and "
                "order_delivered_customer_date columns."
            )
        if len(header) > 30:
            raise ValueError("This file has too many columns for the original order table.")
        self.by_id = {}
        tally = Counter()
        try:
            for record in reader:
                order_id = str(record.get("order_id") or "").strip()
                if not order_id or order_id not in source_ids or order_id in self.by_id:
                    raise ValueError("The imported order IDs do not match the original Olist registry exactly.")
                if None in record:
                    raise ValueError("One or more source rows have too many columns.")
                estimate = str(record.get("order_estimated_delivery_date") or "").strip()
                actual = str(record.get("order_delivered_customer_date") or "").strip()
                purchase = str(record.get("order_purchase_timestamp") or "").strip()
                status = str(record.get("order_status") or "").strip().lower()
                if not status:
                    relation = "UNKNOWN_ORDER_STATUS"
                elif status != "delivered":
                    # A timestamp on a canceled or undelivered order is not a
                    # certified customer-delivery outcome. Preserve conflicts.
                    relation = "NONDELIVERED_WITH_DELIVERY_TIMESTAMP" if actual else "NOT_RECORDED_AS_DELIVERED"
                elif not estimate:
                    relation = "MISSING_ESTIMATE"
                elif not actual:
                    relation = "MISSING_RECORDED_DELIVERY"
                else:
                    estimate_date, actual_date, purchase_date = (
                        _date(estimate), _date(actual), _date(purchase)
                    )
                    if estimate_date is None or actual_date is None:
                        relation = "UNPARSEABLE_DATE"
                    elif purchase_date is None:
                        relation = "MISSING_OR_INVALID_PURCHASE_TIMESTAMP"
                    elif (estimate_date.utcoffset() is None) != (actual_date.utcoffset() is None):
                        relation = "INCOMPARABLE_TIMEZONE_BASIS"
                    elif (estimate_date.utcoffset() is not None
                          and estimate_date.utcoffset() != actual_date.utcoffset()):
                        relation = "INCOMPARABLE_TIMEZONE_BASIS"
                    elif (purchase_date.utcoffset() is None) != (actual_date.utcoffset() is None):
                        relation = "INCOMPARABLE_TIMEZONE_BASIS"
                    elif (purchase_date.utcoffset() is not None
                          and purchase_date.utcoffset() != actual_date.utcoffset()):
                        relation = "INCOMPARABLE_TIMEZONE_BASIS"
                    elif actual_date.date() < purchase_date.date():
                        relation = "DELIVERY_BEFORE_PURCHASE"
                    elif actual_date.date() < estimate_date.date():
                        relation = "BEFORE_ESTIMATE"
                    elif actual_date.date() > estimate_date.date():
                        relation = "AFTER_ESTIMATE"
                    else:
                        relation = "ON_ESTIMATE_DATE"
                tally[relation] += 1
                self.by_id[order_id] = {
                    "estimate": estimate, "actual": actual, "status": status,
                    "relation": relation,
                }
                if len(self.by_id) > len(source_ids):
                    raise ValueError("This source contains more orders than the original registry.")
        except (csv.Error, UnicodeError) as error:
            raise ValueError("Original Olist CSV is malformed or cannot be decoded.") from error
        if len(self.by_id) != len(source_ids):
            raise ValueError(
                f"Source registry mismatch: found {len(self.by_id):,} unique order IDs, "
                f"but the frozen research registry contains {len(source_ids):,}. "
                "No partial import was accepted."
            )
        self.summary = {
            "source_orders": len(self.by_id),
            "comparable": tally["BEFORE_ESTIMATE"] + tally["ON_ESTIMATE_DATE"] + tally["AFTER_ESTIMATE"],
            "before": tally["BEFORE_ESTIMATE"],
            "on": tally["ON_ESTIMATE_DATE"],
            "after": tally["AFTER_ESTIMATE"],
            "missing_estimate": tally["MISSING_ESTIMATE"],
            "missing_actual": tally["MISSING_RECORDED_DELIVERY"],
            "unparseable": tally["UNPARSEABLE_DATE"],
            "not_recorded_as_delivered": tally["NOT_RECORDED_AS_DELIVERED"],
            "contradictory_status_delivery": tally["NONDELIVERED_WITH_DELIVERY_TIMESTAMP"],
            "unknown_status": tally["UNKNOWN_ORDER_STATUS"],
            "incomparable_timezone": tally["INCOMPARABLE_TIMEZONE_BASIS"],
            "delivery_before_purchase": tally["DELIVERY_BEFORE_PURCHASE"],
            "invalid_purchase_timestamp": tally["MISSING_OR_INVALID_PURCHASE_TIMESTAMP"],
            "all_records_reconciled": sum(tally.values()) == len(self.by_id),
            "definition": "Calendar day of recorded delivery vs Olist estimated delivery date",
            "business_kpi_certified": False,
        }

    def status(self):
        return {"loaded": True, "filename": self.filename, "summary": self.summary,
                "evidence_source": "REAL_OLIST_ORIGINAL_OUTCOMES_SEPARATE",
                "storage": "SESSION_MEMORY_ONLY", "predictions_modified": False,
                "note": "Olist estimated date is not an independently certified customer promise."}

    def explain(self, question, order_id=None, history=None):
        text = str(question).lower()
        previous = str((history or [{}])[-1].get("question", "")).lower()
        total = self.summary["source_orders"]
        comparable = self.summary["comparable"]
        base = (f"I compared recorded delivery calendar dates with the Olist estimated dates "
                f"for the original {total:,} orders. {comparable:,} have comparable dates; "
                f"{self.summary['before']:,} were recorded before the estimate, "
                f"{self.summary['on']:,} on its calendar date, and "
                f"{self.summary['after']:,} after it. "
                f"{self.summary['missing_actual']:,} lack a recorded delivery timestamp, "
                f"{self.summary['missing_estimate']:,} lack an estimate, and "
                f"{self.summary['unparseable']:,} have date values I couldn't compare, "
                f"{self.summary['not_recorded_as_delivered']:,} are not marked delivered, "
                f"and {self.summary['contradictory_status_delivery']:,} have contradictory "
                f"status and delivery fields. ")
        caveat = ("These are historical source-record comparisons, not model predictions or "
                  "an independently certified contractual late-delivery rate.")
        asks_count = any(token in text for token in (
            "how many", "count", "number", "total", "percentage", "percent", "rate", "how much"
        )) or ("and " in text and any(token in previous for token in ("how many", "count")))
        asks_before = any(token in text for token in ("before", "early", "earlier"))
        asks_after = any(token in text for token in ("after", "late", "delay"))
        asks_on = any(token in text for token in ("on time", "on the date", "exact date", "same day"))
        is_confirmation = any(token in text for token in ("are you sure", "really?", "check again", "double check", "confirm that"))
        if is_confirmation and any(token in previous for token in ("after", "before", "late", "early", "delivered")):
            return "Yes, the day-level counts are recomputed from the attached source: " + base + caveat
        if asks_count:
            if asks_before and not asks_after:
                start = f"{self.summary['before']:,} of {comparable:,} comparable Olist orders have a recorded delivery date before their estimated date. "
            elif asks_after and not asks_before:
                start = f"{self.summary['after']:,} of {comparable:,} comparable Olist orders have a recorded delivery date after their estimated date. "
            elif "on time" in text:
                early_or_on = self.summary["before"] + self.summary["on"]
                start = (f"{early_or_on:,} of {comparable:,} comparable Olist orders were recorded "
                         "on or before their estimated delivery calendar date. ")
            elif asks_on:
                start = f"{self.summary['on']:,} of {comparable:,} comparable Olist orders were recorded on their estimated calendar date. "
            else:
                start = base
            return start + caveat
        if order_id and order_id in self.by_id:
            row = self.by_id[order_id]
            relation = row["relation"]
            if relation == "BEFORE_ESTIMATE":
                conclusion = "The recorded delivery date is before the estimated delivery date."
            elif relation == "AFTER_ESTIMATE":
                conclusion = "The recorded delivery date is after the estimated delivery date."
            elif relation == "ON_ESTIMATE_DATE":
                conclusion = "The recorded delivery date is on the same calendar day as the estimated date."
            else:
                conclusion = "The recorded dates are missing or not comparable, so I can't determine its timing."
            return (f"For this historical source order, recorded delivery was "
                    f"{row['actual'] or 'missing'} and Olist's estimated date was "
                    f"{row['estimate'] or 'missing'}. {conclusion} {caveat}")
        return base + caveat


class HistoricalOutcomeStore:
    def __init__(self):
        self._lock = Lock()
        self._source = None

    def status(self):
        with self._lock:
            return self._source.status() if self._source else {
                "loaded": False, "max_upload_bytes": MAX_OUTCOME_UPLOAD_BYTES,
                "note": "Attach the original Olist orders CSV to answer recorded delivery-timing questions.",
                "predictions_modified": False,
            }

    def attach(self, filename, raw, source_ids):
        candidate = HistoricalOutcomes(filename, raw, source_ids)
        with self._lock:
            self._source = candidate
        return self.status()

    def explain(self, question, order_id=None, history=None):
        with self._lock:
            return self._source.explain(question, order_id, history) if self._source else None

    def facts(self):
        with self._lock:
            return dict(self._source.summary) if self._source else None

    def clear(self):
        with self._lock:
            self._source = None
        return self.status()


OUTCOMES = HistoricalOutcomeStore()
