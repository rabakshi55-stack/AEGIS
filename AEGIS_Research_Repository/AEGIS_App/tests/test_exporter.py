"""Full-count fictional export fixture in a temporary directory only.

This verifies the transfer contract, not performance or source-data validity.
"""

import importlib.util
import tempfile
from pathlib import Path
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExportContractTest(unittest.TestCase):
    def test_full_snapshot_export_import_roundtrip(self):
        exporter = load_module("aegis_export_contract_test", ROOT / "export_from_notebook.py")
        app = load_module("aegis_app_contract_test", ROOT / "app.py")
        original_ids = [f"{i:08x}" + "0" * 24 for i in range(99441)]
        catalog = pd.DataFrame({
            "order_id": original_ids[:58911],
            "Phase": ["TRAIN"] * 26127 + ["VALIDATION"] * 20615 + ["TEST"] * 12169,
            "Purchase_Time": ["2018-07-20 11:00:00"] * 58911,
            "Destination_State": ["RJ"] * 58911,
            "Promise_Days": [24] * 58911,
            "Promise_Band": ["19-29d"] * 58911,
            "Research_Score_Uncalibrated": [.0241] * 58911,
        })
        scenarios = pd.DataFrame({
            "Scenario": list(range(1, 11)), "Rank": list(range(1, 11)),
            "Actual_Reserve_Pct": [5.0] * 10,
            "Minimum_Allowance_Pct": [5.0] * 10,
            "Landed_Cost": [1500.0] * 10,
            "Supplier_HHI": [.45] * 10,
            "Balanced_Score": [0.5] * 10,
        })
        namespace = {
            "olist_tables_163": {"orders": pd.DataFrame({"order_id": original_ids})},
            "aegis_research_catalog_187": catalog,
            "headroom_reference_189": scenarios,
            "policy_evidence_129": [{"Policy": str(i)} for i in range(6)],
            "aegis_olist_readiness_182": pd.DataFrame({
                "Table": ["supplier_quotes"], "Module": ["PRODUCTION"],
                "Status": ["MISSING_TABLE"],
            }),
        }
        with tempfile.TemporaryDirectory(prefix="aegis_contract_test_") as temporary:
            exporter.__file__ = str(Path(temporary) / "export_from_notebook.py")
            path = exporter.export_aegis_research_bundle(namespace)
            store = app.ResearchStore(path)
            self.assertTrue(store.ready, store.error)
            self.assertEqual(store.summary["scored_orders"], 58911)
            self.assertEqual(store.summary["source_orders"], 99441)
            self.assertEqual(store.resolve("00000000"), original_ids[0])
            self.assertEqual(store.by_raw[original_ids[0]]["Research_Score_Uncalibrated"], .0241)
            self.assertEqual(len(store.scenarios), 10)


if __name__ == "__main__":
    unittest.main()
