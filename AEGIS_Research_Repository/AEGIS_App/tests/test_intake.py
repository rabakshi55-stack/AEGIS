"""All intake tests use tiny fictional in-memory records, never user datasets."""

from io import BytesIO
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import quote
from unittest.mock import patch
from zipfile import ZipFile
import importlib.util
import json
import sys
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import intake

spec = importlib.util.spec_from_file_location("aegis_intake_http", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


CSV = ("order_id,promised_delivery_date,actual_delivery_timestamp,required_units,note\n"
       "A1,2026-03-01,2026-03-02,4,\"red, blue\"\n"
       "A2,2026-03-01,2026-02-28,-2,\n"
       "A2,2026-03-01,not-a-date,1,done\n").encode()


def fake_xlsx():
    source = BytesIO()
    with ZipFile(source, "w") as archive:
        archive.writestr("xl/workbook.xml", """<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Business Inputs" sheetId="1" r:id="rId1" /></sheets></workbook>""")
        archive.writestr("xl/_rels/workbook.xml.rels", """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml" /></Relationships>""")
        archive.writestr("xl/worksheets/sheet1.xml", """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>order_id</t></is></c><c r="B1" t="inlineStr"><is><t>supplier_id</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Fictional-1</t></is></c><c r="B2" t="inlineStr"><is><t>Fake-Supplier</t></is></c></row></sheetData></worksheet>""")
    return source.getvalue()


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.intake = intake.IntakeStore()

    def test_csv_profile_and_complete_mapping(self):
        p = self.intake.upload("fictional.csv", CSV)
        self.assertTrue(p["loaded"])
        self.assertEqual(p["rows"], 3)
        self.assertEqual(p["preview"][0]["note"], "red, blue")
        self.assertEqual(p["column_profiles"][0]["blank_count"], 0)
        p = self.intake.mapping({"order_id": "order_id", "promised_delivery_date": "promised_delivery_date",
                                 "actual_delivery_timestamp": "actual_delivery_timestamp", "required_units": "required_units"})
        self.assertEqual(p["insights"]["duplicate_order_rows"], 1)
        self.assertEqual(p["insights"]["timestamp_pairs"], 2)
        self.assertEqual(p["insights"]["recorded_after_promise"], 1)
        self.assertEqual(p["insights"]["recorded_before_promise"], 1)
        self.assertEqual(p["insights"]["recorded_on_promise_date"], 0)
        self.assertEqual(p["insights"]["unparseable_timestamp_pairs"], 1)
        self.assertEqual(p["insights"]["negative_numeric_values"]["required_units"], 1)
        self.assertFalse(p["model_training"])
        self.assertEqual(p["permitted_action"], "NONE")

    def test_invalid_upload_does_not_replace_previous(self):
        self.intake.upload("good.csv", CSV)
        with self.assertRaisesRegex(ValueError, "unique"):
            self.intake.upload("bad.csv", b"same,SAME\n1,2\n")
        self.assertEqual(self.intake.status()["filename"], "good.csv")
        with self.assertRaisesRegex(ValueError, "more cells"):
            self.intake.upload("bad.csv", b"only\n1,2\n")
        self.assertEqual(self.intake.status()["filename"], "good.csv")

    def test_mapping_rejects_ambiguous_roles(self):
        self.intake.upload("safe.csv", CSV)
        with self.assertRaisesRegex(ValueError, "only one role"):
            self.intake.mapping({"order_id":"order_id", "supplier_id":"order_id"})
        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.intake.mapping({"supplier_id":"wrong"})
        self.assertEqual(self.intake.status()["mapping"], {})

    def test_xlsx_first_sheet_works_with_no_excel_dependency(self):
        result = self.intake.upload("fictional.xlsx", fake_xlsx())
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["preview"][0]["supplier_id"], "Fake-Supplier")
        self.assertIn("Business Inputs", result["warnings"][0])

    def test_styled_excel_serial_date_conversion(self):
        self.assertEqual(intake._formatted_excel_date("46082", False), "2026-03-01")
        self.assertEqual(intake._formatted_excel_date("1", False), "1900-01-01")
        self.assertEqual(intake._formatted_excel_date("60", False), "60")
        self.assertEqual(intake._formatted_excel_date("not a date", False), "not a date")

    def test_rejected_oversize_does_not_change_session(self):
        self.intake.upload("fictional.csv", CSV)
        with self.assertRaisesRegex(ValueError, "smaller than"):
            self.intake.upload("oversize.csv", b"X" * (intake.MAX_UPLOAD_BYTES + 1))
        self.assertEqual(self.intake.status()["filename"], "fictional.csv")

    def test_local_copilot_refuses_procurement_and_ignores_original_models(self):
        self.intake.upload("fictional.csv", CSV)
        answer = self.intake.answer("Should we switch suppliers?")
        self.assertIn("can't infer supplier causality", answer["answer"])
        self.assertEqual(answer["routing_mode"], "CONTEXTUAL_DESCRIPTIVE_RULES_NO_LLM")
        self.assertTrue(answer["safety_gate"])
        self.assertEqual(answer["permitted_action"], "NONE")
        self.assertFalse(self.intake.clear()["loaded"])
        with self.assertRaisesRegex(ValueError, "Upload a dataset"):
            self.intake.answer("How many rows?")

    def test_conversational_followups_check_current_records(self):
        self.intake.upload("fictional.csv", CSV)
        self.intake.mapping({"order_id":"order_id", "promised_delivery_date":"promised_delivery_date",
                             "actual_delivery_timestamp":"actual_delivery_timestamp"})
        factual = self.intake.answer("How many were delivered late?")
        self.assertIn("1 after the mapped promise date", factual["answer"])
        self.assertIn("Missing actual-delivery values: 0", factual["answer"])
        followup = self.intake.answer("are you sure?", history=[{"question":"How many were delivered late?"}])
        self.assertIn("I checked the original uploaded records again", followup["answer"])
        self.assertIn("1 after the mapped promise date", followup["answer"])
        action_followup = self.intake.answer("are you sure?", history=[{"question":"Should we switch suppliers?"}])
        self.assertIn("evidence isn't enough to justify changing suppliers", action_followup["answer"])
        self.assertEqual(action_followup["permitted_action"], "NONE")
        self.assertTrue(action_followup["safety_gate"])
        extra = self.intake.answer("Can you explain that?", history=[{"question":"How many were delivered late?"}])
        self.assertIn("comparison comes directly", extra["answer"])
        explicit_ids = self.intake.answer("Which ones were late?", history=[{"question":"How many were delivered late?"}])
        self.assertTrue(explicit_ids["safety_gate"])
        self.assertIn("A1", explicit_ids["answer"])

    def test_natural_summary_and_greeting_with_no_model(self):
        self.intake.upload("fictional.csv", CSV)
        summary = self.intake.answer("Can you summarize this dataset?")
        self.assertIn("3 rows and 5 columns", summary["answer"])
        size = self.intake.answer("How many rows are there?")
        self.assertIn("3 data rows", size["answer"])
        greeting = self.intake.answer("hello")
        self.assertTrue(greeting["answer"].startswith("Hi!"))
        reaction = self.intake.answer("bruh")
        self.assertIn("more like a compliance report", reaction["answer"])

    def test_safe_model_facts_exclude_individual_rows(self):
        self.intake.upload("fictional.csv", CSV)
        self.intake.mapping({"order_id":"order_id", "promised_delivery_date":"promised_delivery_date",
                             "actual_delivery_timestamp":"actual_delivery_timestamp"})
        facts = self.intake.model_facts()
        self.assertEqual(facts["file_rows"], 3)
        self.assertEqual(facts["dates_recorded_after_promise"], 1)
        self.assertNotIn("A1", json.dumps(facts))
        self.assertNotIn("A2", json.dumps(facts))
        self.assertFalse(facts["semantics_certified"])

    def test_oversized_conversation_history_is_rejected(self):
        self.intake.upload("fictional.csv", CSV)
        with self.assertRaisesRegex(ValueError, "history"):
            self.intake.answer("are you sure?", history=[{"question":"hello"}] * 7)


class IntakeHttpTests(unittest.TestCase):
    def setUp(self):
        self.original = app.INTAKE
        app.INTAKE = intake.IntakeStore()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.AegisHandler)
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        app.INTAKE = self.original

    def request_json(self, path, data=None, headers=None):
        hdr = headers or {}
        req = urllib.request.Request(self.base + path, data=data, headers=hdr,
                                     method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    def test_http_upload_map_copilot_clear(self):
        self.assertFalse(self.request_json("/api/intake")["loaded"])
        imported = self.request_json("/api/intake/upload?name=" + quote("fictional.csv"), CSV,
                                     {"Content-Type":"application/octet-stream", "X-AEGIS-Upload":"1"})
        self.assertEqual(imported["rows"], 3)
        mapped = self.request_json("/api/intake/mapping", json.dumps({"mapping":{"order_id":"order_id"}}).encode(),
                                   {"Content-Type":"application/json"})
        self.assertEqual(mapped["insights"]["duplicate_order_rows"], 1)
        answer = self.request_json("/api/copilot", json.dumps({"context":"local_dataset","question":"How many duplicate order IDs?"}).encode(),
                                   {"Content-Type":"application/json"})
        self.assertEqual(answer["evidence_source"], "LOCAL_USER_UPLOAD_UNVERIFIED")
        self.assertFalse(self.request_json("/api/intake/clear", b"{}", {"Content-Type":"application/json"})["loaded"])

    def test_local_model_uses_derived_facts_only_and_falls_back_safely(self):
        app.INTAKE.upload("fake.csv", CSV)
        app.INTAKE.mapping({"order_id":"order_id"})
        body = {"context":"local_dataset", "question":"Please explain this dataset",
                "use_local_llm": True, "history":[{"question":"Hello"}]}
        headers={"Content-Type":"application/json"}
        with patch.object(app, "natural_answer", return_value="I can see 3 rows and 5 columns.") as mock_generate:
            result=self.request_json("/api/copilot",json.dumps(body).encode(),headers)
        self.assertEqual(result["routing_mode"], "LOCAL_QWEN_GROUNDED_CONVERSATION")
        facts=mock_generate.call_args.args[2]
        self.assertNotIn("A1",json.dumps(facts))
        self.assertFalse(facts["model_fitted_on_upload"])
        with patch.object(app,"natural_answer",side_effect=app.LocalModelUnavailable("offline")):
            fallback=self.request_json("/api/copilot",json.dumps(body).encode(),headers)
        self.assertEqual(fallback["routing_mode"],"CONTEXTUAL_RULES_MODEL_UNAVAILABLE")
        self.assertEqual(fallback["permitted_action"],"NONE")
        body["question"]="Switch suppliers now"
        with patch.object(app,"natural_answer") as mock_generate:
            blocked=self.request_json("/api/copilot",json.dumps(body).encode(),headers)
        mock_generate.assert_not_called()
        self.assertEqual(blocked["permitted_action"],"NONE")

    def test_cross_origin_and_missing_upload_header_blocked(self):
        for headers in (
            {"Content-Type":"application/octet-stream"},
            {"Content-Type":"application/octet-stream", "X-AEGIS-Upload":"1", "Origin":"https://unknown.example"},
        ):
            req = urllib.request.Request(self.base + "/api/intake/upload?name=example.csv", data=CSV,
                                         headers=headers, method="POST")
            with self.assertRaises(HTTPError) as err:
                urllib.request.urlopen(req, timeout=3)
            err.exception.close()
            self.assertEqual(err.exception.code, 403)
        self.assertFalse(self.request_json("/api/intake")["loaded"])

    def test_cross_site_get_and_rebinding_host_are_blocked(self):
        for headers in ({"Origin":"https://unknown.example"}, {"Host":"unknown.example"}):
            req = urllib.request.Request(self.base + "/api/intake", headers=headers)
            with self.assertRaises(HTTPError) as err:
                urllib.request.urlopen(req, timeout=3)
            err.exception.close()
            self.assertEqual(err.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
