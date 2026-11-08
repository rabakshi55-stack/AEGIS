"""Only ephemeral, fictional SQLite schemas are used in these tests."""

from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors import CONTRACTS, inspect_local_sqlite, enterprise_connections_status


class ConnectionContractTests(unittest.TestCase):
    def test_no_company_access_is_reported_honestly(self):
        with patch.dict(os.environ, {"AEGIS_ENTERPRISE_SQLITE": ""}):
            result = inspect_local_sqlite()
            self.assertFalse(result["connected"])
            self.assertEqual(result["status"], "NOT_CONFIGURED")
            self.assertEqual(result["permitted_action"], "NONE")
            self.assertEqual(result["complete_table_schemas"], 0)
            self.assertEqual(len(result["table_contracts"]), 8)
            self.assertFalse(enterprise_connections_status()["real_enterprise_connection_established"])

    def test_read_only_schema_inspection_never_certifies_business_data(self):
        with tempfile.TemporaryDirectory(prefix="aegis_local_connector_test_") as root:
            db_path = Path(root) / "test_contract_only.sqlite3"
            # sqlite3.Connection.__exit__ commits/rolls back but does NOT
            # close the handle. Windows will refuse to remove an open DB.
            with closing(sqlite3.connect(db_path)) as conn:
                for table, spec in CONTRACTS.items():
                    columns = ", ".join(f'"{name}" TEXT' for name in spec["fields"])
                    conn.execute(f'CREATE TABLE "{table}" ({columns})')
                conn.execute('CREATE TABLE "private_extraneous_table" ("secret_field" TEXT)')
                conn.commit()

            with patch.dict(os.environ, {"AEGIS_ENTERPRISE_SQLITE": str(db_path)}):
                result = inspect_local_sqlite()
                self.assertTrue(result["connected"])
                self.assertEqual(result["complete_table_schemas"], 8)
                self.assertFalse(result["certified_decision_time_inputs"])
                self.assertEqual(result["operational_approval"], "NOT_GRANTED")
                self.assertEqual(result["permitted_action"], "NONE")
                self.assertNotIn("private_extraneous_table", str(result))
                self.assertTrue(all(
                    item["status"] == "COLUMNS_PRESENT_NOT_CERTIFIED"
                    for item in result["table_contracts"]
                ))

            # The adapter's URI configuration is read-only in the real call.
            with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as conn:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute('INSERT INTO "orders_at_decision" ("order_id") VALUES ("demo")')


if __name__ == "__main__":
    unittest.main()
