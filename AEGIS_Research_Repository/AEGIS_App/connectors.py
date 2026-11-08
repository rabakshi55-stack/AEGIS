"""AEGIS local SQLite connector: metadata and explicitly requested read-only table snapshots.

No automatic database reads, persistence of imported rows, model training, or business actions.
External databases and ERP integrations still require authorization and separate development.
"""

from pathlib import Path
from contextlib import closing
import os
import sqlite3
from datetime import date, datetime
from itertools import chain
import math


# Exact proposed business contracts from the existing AEGIS Step 182 audit.
# Column presence does not prove data semantics, timeliness, or validity.
CONTRACTS = {
    "orders_at_decision": {
        "module": "PREDICTION", "keys": ["order_id"],
        "fields": ["order_id", "purchase_timestamp", "promised_delivery_date",
                   "destination_state", "decision_timestamp", "purchase_known_at",
                   "promise_known_at", "destination_known_at"],
    },
    "demand_lines": {
        "module": "RECOVERY", "keys": ["order_id", "item_id"],
        "fields": ["order_id", "item_id", "required_units", "required_by_date"],
    },
    "supplier_quotes": {
        "module": "RECOVERY", "keys": ["item_id", "supplier_id", "quote_recorded_at"],
        "fields": ["item_id", "supplier_id", "unit_cost", "quoted_lead_days",
                   "minimum_order_qty", "eligible_for_item", "quote_recorded_at",
                   "quote_valid_until"],
    },
    "supplier_capacity": {
        "module": "RECOVERY", "keys": ["item_id", "supplier_id", "capacity_asof"],
        "fields": ["item_id", "supplier_id", "available_units", "capacity_asof",
                   "capacity_valid_until"],
    },
    "baseline_allocations": {
        "module": "RECOVERY", "keys": ["order_id", "item_id", "supplier_id"],
        "fields": ["order_id", "item_id", "supplier_id", "allocated_units",
                   "baseline_total_cost"],
    },
    "realized_outcomes": {
        "module": "VALIDATION", "keys": ["order_id"],
        "fields": ["order_id", "actual_delivery_timestamp", "realized_total_cost",
                   "outcome_recorded_at"],
    },
    "decision_log": {
        "module": "VALIDATION", "keys": ["order_id", "decision_timestamp"],
        "fields": ["order_id", "decision_timestamp", "recommended_action",
                   "human_approved", "action_executed", "execution_timestamp"],
    },
    "comparison_assignment": {
        "module": "VALIDATION", "keys": ["order_id"],
        "fields": ["order_id", "evaluation_group", "assignment_timestamp",
                   "assignment_method"],
    },
}


def _table_contract_rows(available=None):
    available = available or {}
    rows = []
    for name, contract in CONTRACTS.items():
        if name not in available:
            state, missing = "TABLE_MISSING", contract["fields"]
        else:
            existing = set(available[name])
            missing = [column for column in contract["fields"] if column not in existing]
            state = "FIELDS_MISSING" if missing else "COLUMNS_PRESENT_NOT_CERTIFIED"
        rows.append({
            "table": name,
            "module": contract["module"],
            "required_fields": len(contract["fields"]),
            "key_fields": contract["keys"],
            "missing_fields": missing,
            "status": state,
        })
    return rows


def inspect_local_sqlite(database_path=None):
    """Inspect table names and column names only; never select business rows."""
    raw = database_path if database_path is not None else os.environ.get("AEGIS_ENTERPRISE_SQLITE", "")
    base = {
        "adapter": "LOCAL_SQLITE_READ_ONLY",
        "configured": bool(str(raw).strip()),
        "connected": False,
        "database_name": Path(str(raw)).name if str(raw).strip() else None,
        "status": "NOT_CONFIGURED",
        "table_contracts": _table_contract_rows(),
        "columns_present": 0,
        "required_tables": len(CONTRACTS),
        "complete_table_schemas": 0,
        "certified_decision_time_inputs": False,
        "operational_approval": "NOT_GRANTED",
        "permitted_action": "NONE",
        "message": "No approved local SQLite database has been configured.",
    }
    if not base["configured"]:
        return base

    try:
        path = Path(str(raw)).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Configured SQLite source is not a regular file.")
        # SQLite URI mode=ro prevents writing even if file permissions permit it.
        uri = path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=3)) as conn:
            conn.execute("PRAGMA query_only=ON")
            table_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            ).fetchall()
            actual = {}
            required = set(CONTRACTS)
            for (table_name,) in table_rows:
                if table_name not in required:
                    continue
                identifier = '"' + table_name.replace('"', '""') + '"'
                actual[table_name] = [
                    row[1] for row in conn.execute(f"PRAGMA table_info({identifier})")
                ]

        contracts = _table_contract_rows(actual)
        complete = sum(row["status"] == "COLUMNS_PRESENT_NOT_CERTIFIED" for row in contracts)
        base.update({
            "connected": True,
            "status": "SCHEMA_INSPECTION_COMPLETE",
            "table_contracts": contracts,
            "columns_present": sum(
                row["required_fields"] - len(row["missing_fields"]) for row in contracts
            ),
            "complete_table_schemas": complete,
            "message": (
                f"Read-only schema inspection completed. {complete} of {len(CONTRACTS)} "
                "table contracts have all required column names. "
                "Data correctness, decision-time availability and deployment remain unverified."
            ),
        })
    except (OSError, ValueError, sqlite3.Error):
        # Do not return raw errors that could disclose sensitive local paths.
        base["status"] = "CONNECTION_FAILED"
        base["message"] = "Cannot open the configured source read-only. Check the local configuration."
    return base



def _sqlite_configured_path():
    raw = os.environ.get("AEGIS_ENTERPRISE_SQLITE", "").strip()
    if not raw:
        raise ValueError("No local SQLite database configured. Set AEGIS_ENTERPRISE_SQLITE before starting.")
    path = Path(raw).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("The configured SQLite source must be a local file.")
    return path


def _sqlite_open_readonly(path):
    # URI path.as_uri() percent-encodes ? and # in local file names.
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    conn.execute("PRAGMA query_only=ON")
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 512 * 1024) # cap any one row/BLOB fetched into memory
    conn.execute("PRAGMA trusted_schema=OFF")
    conn.execute("PRAGMA busy_timeout=2500")
    return conn


def list_sqlite_importable_tables():
    """Only return table metadata, never business rows; source already configured by operator."""
    path = _sqlite_configured_path()
    with closing(_sqlite_open_readonly(path)) as conn:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT 51"
        ).fetchall()]
        if len(names) > 50:
            raise ValueError("This SQLite database has more than 50 tables; export the required table to CSV instead.")
        return [n for n in names if isinstance(n,str) and len(n) <= 120]


def read_sqlite_table_snapshot(table):
    """Import an explicitly selected snapshot only. No caller SQL, updates, or partial sample."""
    from intake import _clean_rows, MAX_ROWS, MAX_COLUMNS, MAX_CELLS
    if not isinstance(table,str) or not table or len(table) > 120:
        raise ValueError("Choose a valid SQLite table name from the connection list.")
    path = _sqlite_configured_path()
    with closing(_sqlite_open_readonly(path)) as conn:
        conn.execute("BEGIN")  # source count and source rows from one read transaction
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
        if table not in names:
            raise ValueError("Only an existing user-selected table can be imported.")
        quoted = '"' + table.replace('"','""') + '"'
        names = [r[1] for r in conn.execute(f"PRAGMA table_info({quoted})")]
        if not 1 <= len(names) <= MAX_COLUMNS:
            raise ValueError(f"Table requires 1–{MAX_COLUMNS} supported fields.")
        if len(set(n.casefold() for n in names)) != len(names):
            raise ValueError("Table contains repeated case-insensitive column names.")
        if any(not n or len(n)>200 or any(ord(char)<32 for char in n) for n in names):
            raise ValueError("Table contains unsupported column names.")
        count = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
        if not 1 <= count <= MAX_ROWS or count * len(names) > MAX_CELLS:
            raise ValueError("The selected table exceeds the row or cell limit. Export a smaller complete cohort instead; no silent sampling.")
        def to_text(value):
            if value is None: return ""
            if isinstance(value,(bytes, bytearray, memoryview)):
                raise ValueError("Binary (BLOB) cells require an explicit sanitized CSV export.")
            if isinstance(value,float) and not math.isfinite(value):
                raise ValueError("Non-finite numeric values require source correction.")
            if isinstance(value,(str,int,float,datetime,date)):
                text = str(value)
                if len(text) > 8192: raise ValueError("A SQLite cell exceeds the 8192-character safety limit.")
                return text
            raise ValueError("Unsupported SQLite cell type.")
        def records():
            for values in conn.execute(f"SELECT * FROM {quoted}"):
                yield [to_text(value) for value in values]
        headers, rows = _clean_rows(chain([names], records()))
        if len(rows) != count:
            raise ValueError("Import row reconciliation failed: blank or inconsistent source rows were found.")
    return headers, rows, f"SQLite table '{table}' from configured local source", path.name

def enterprise_connections_status():
    sqlite = inspect_local_sqlite()
    tables = []
    if sqlite["connected"]:
        try:
            tables = list_sqlite_importable_tables()
        except (OSError, ValueError, sqlite3.Error):
            pass
    return {
        "mode": "ENTERPRISE_CONNECTOR_FOUNDATION",
        "real_enterprise_connection_established": False,
        "available_sqlite_tables": tables,
        "import_requires_explicit_user_click": True,
        "adapters": [
            {"name": "Local SQLite", "kind": "SQLITE", "implementation": "READ_ONLY_METADATA_AND_MANUAL_TABLE_SNAPSHOT", "state": sqlite["status"]},
            {"name": "Enterprise SQL database", "kind": "SQL_SERVER_POSTGRESQL", "implementation": "NOT_BUILT", "state": "SYSTEM_CHOICE_REQUIRED"},
            {"name": "ERP / WMS / TMS API", "kind": "REST_API", "implementation": "NOT_BUILT", "state": "SYSTEM_CHOICE_REQUIRED"},
        ],
        "active_sqlite": sqlite,
        "security": {
            "credentials_stored_in_app": False,
            "web_config_of_file_paths": False,
            "business_record_rows_exposed": False,
            "local_sqlite_import": "EXPLICIT_SELECTED_TABLE_ONLY",
            "permitted_action": "NONE",
            "human_approval": "REQUIRED",
        },
        "next_requirement": "An approved company system, its API/schema specification and authorized read-only access.",
    }
