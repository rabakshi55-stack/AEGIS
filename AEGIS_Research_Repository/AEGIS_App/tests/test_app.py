"""Software-only tests: temporary invented fixtures never enter the app data folder."""
from contextlib import closing
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from unittest.mock import patch
import importlib.util
import json
import sys
import unittest
import urllib.request

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
sys.path.insert(0, str(APP_PATH.parent))
spec = importlib.util.spec_from_file_location("aegis_local_test_module", APP_PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def software_fixture():
    store = app.ResearchStore(path=Path(__file__).parent / "does_not_exist.json")
    row = {
        "order_id": "1234567890abcdef1234567890abcdef", "Short_Reference": "12345678",
        "Phase": "TEST", "Purchase_Time": "2018-07-20T19:27:48",
        "Destination_State": "RJ", "Promise_Days": 32, "Promise_Band": "31-45d",
        "Research_Score_Uncalibrated": 0.0241,
    }
    store.ready, store.error = True, None
    store.orders = [row]
    store.by_raw = {row["order_id"]: row}
    store.by_short = {row["Short_Reference"]: row["order_id"]}
    store.short_by_raw = {row["order_id"]: row["Short_Reference"]}
    store.scenarios = [{"Scenario": 1, "Rank": 1, "Actual_Reserve_Pct": 3.2,
                        "Minimum_Allowance_Pct": 5.0, "Landed_Cost": 100.0,
                        "Supplier_HHI": .58, "Balanced_Score": 1.0}]
    store.readiness = [{"Table": "supplier_quotes", "Module": "PRODUCTION", "Status": "MISSING_TABLE"}]
    store.policies = [{"Policy": "TEST ONLY"}]
    store.summary = {"scored_orders": 1, "source_orders": 1, "scenarios": 1,
                     "phase_counts": {"TEST": 1}, "score_histogram": [1] + [0] * 11,
                     "score_min": .0241, "score_max": .0241}
    store.bundle = {"exported_at_utc": "2018-07-20T00:00:00Z"}
    return store


class AegisSafetyTests(unittest.TestCase):
    def setUp(self):
        self.previous = app.STORE
        app.STORE = software_fixture()

    def tearDown(self):
        app.STORE = self.previous

    def test_short_id_and_raw_id_resolve(self):
        self.assertEqual(app.STORE.resolve("Order 12345678"), "1234567890abcdef1234567890abcdef")
        self.assertEqual(app.STORE.resolve("1234567890abcdef1234567890abcdef"), "1234567890abcdef1234567890abcdef")

    def test_score_is_not_presented_as_probability(self):
        result = app.research_answer("What does this score mean?", order_id="12345678")
        self.assertIn("0.0241", result["answer"])
        self.assertIn("not a verified percentage", result["answer"])
        self.assertEqual(result["permitted_action"], "NONE")

    def test_cross_source_request_is_blocked(self):
        result = app.research_answer("Can we switch suppliers to reduce this order's risk?", order_id="12345678")
        self.assertEqual(result["evidence_source"], "CROSS_EVIDENCE_REQUEST_BLOCKED")

    def test_execution_is_blocked(self):
        result = app.research_answer("Place purchase order now", context="headroom")
        self.assertEqual(result["routing_mode"], "SAFETY_GATE")
        self.assertEqual(result["permitted_action"], "NONE")

    def test_delivery_outcome_is_not_inferred(self):
        result = app.research_answer("Was this actually delivered late?", order_id="12345678")
        self.assertIn("doesn't contain actual delivery timestamps", result["answer"])
        self.assertIn("original 'olist_orders_dataset.csv'", result["answer"])

    def test_followup_requires_source_outcomes_not_model_guesses(self):
        result=app.research_answer("and how many were after their estimated date?",
            order_id="12345678", history=[{"question":"How many were before their estimated date?"}])
        self.assertIn("cannot calculate how many", result["answer"])
        with patch.object(app.OUTCOMES,"explain",return_value="Invented test fixture: 1 of 3 were after"):
            result=app.research_answer("how many delivered after?",order_id="12345678")
        self.assertEqual(result["evidence_source"],"REAL_OLIST_ORIGINAL_OUTCOMES_SEPARATE")
        self.assertIn("1 of 3",result["answer"])

    def test_social_message_bypasses_research_templates(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),app.AegisHandler)
        worker=Thread(target=server.serve_forever,kwargs={"poll_interval":.05},daemon=True)
        worker.start()
        try:
            base=f"http://127.0.0.1:{server.server_address[1]}"
            body=json.dumps({"question":"bruh","context":"historical_order"}).encode()
            req=urllib.request.Request(base+"/api/copilot",data=body,
                headers={"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=3) as response:
                answer=json.load(response)
            self.assertIn("way too robotic",answer["answer"])
            self.assertEqual(answer["evidence_source"],"SOCIAL_DIALOGUE_NO_BUSINESS_DATA")
            self.assertEqual(answer["permitted_action"],"NONE")
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)

    def test_evidence_preserves_source_id(self):
        result = app.STORE.public_order(app.STORE.orders[0], full=True)
        self.assertEqual(result["original_order_id"], "1234567890abcdef1234567890abcdef")
        self.assertEqual(result["permitted_action"], "NONE")

    def test_http_is_read_only(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.AegisHandler)
        worker = Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/api/status", timeout=3) as response:
                self.assertEqual(json.load(response)["safety"]["permitted_action"], "NONE")
            with urllib.request.urlopen(base + "/api/orders/12345678", timeout=3) as response:
                self.assertEqual(json.load(response)["original_order_id"], "1234567890abcdef1234567890abcdef")
            with urllib.request.urlopen(base + "/api/connections", timeout=3) as response:
                connector_status = json.load(response)
            self.assertEqual(connector_status["security"]["permitted_action"], "NONE")
            self.assertFalse(connector_status["security"]["business_record_rows_exposed"])
            with urllib.request.urlopen(base + "/favicon.ico", timeout=3) as response:
                self.assertEqual(response.headers.get_content_type(), "image/x-icon")
                self.assertEqual(response.read(), (APP_PATH.parent / "web" / "favicon.ico").read_bytes())
            data = json.dumps({"question": "What does this score mean?", "context": "historical_order", "order_id": "12345678"}).encode()
            req = urllib.request.Request(base + "/api/copilot", data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=3) as response:
                self.assertEqual(json.load(response)["permitted_action"], "NONE")
            bad = urllib.request.Request(base + "/api/procurement", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(HTTPError) as error:
                urllib.request.urlopen(bad, timeout=3)
            with closing(error.exception):
                self.assertEqual(error.exception.code, 405)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_http_attaches_exact_original_outcome_source_separately(self):
        app.STORE.bundle["original_order_ids"]=["1234567890abcdef1234567890abcdef"]
        original=app.OUTCOMES
        from historical_outcomes import HistoricalOutcomeStore
        app.OUTCOMES=HistoricalOutcomeStore()
        server=ThreadingHTTPServer(("127.0.0.1",0),app.AegisHandler)
        worker=Thread(target=server.serve_forever,kwargs={"poll_interval":.05},daemon=True)
        worker.start()
        base=f"http://127.0.0.1:{server.server_address[1]}"
        data=("order_id,order_estimated_delivery_date,order_delivered_customer_date,order_status,order_purchase_timestamp\n"
              "1234567890abcdef1234567890abcdef,2018-07-31,2018-08-01 16:00:00,delivered,2018-07-01\n").encode()
        try:
            req=urllib.request.Request(base+"/api/historical-outcomes/upload?name=olist_orders_dataset.csv",
                data=data,headers={"Content-Type":"application/octet-stream","X-AEGIS-Upload":"1"},method="POST")
            with urllib.request.urlopen(req,timeout=5) as result:
                attached=json.load(result)
            self.assertTrue(attached["loaded"])
            self.assertEqual(attached["summary"]["after"],1)
            self.assertFalse(attached["predictions_modified"])
            chat=json.dumps({"question":"how many delivered after the estimated date?",
                "context":"historical_order","order_id":"12345678"}).encode()
            req=urllib.request.Request(base+"/api/copilot",data=chat,
                headers={"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=5) as result:
                response=json.load(result)
            self.assertIn("1 of 1 comparable",response["answer"])
            self.assertEqual(response["evidence_source"],"REAL_OLIST_ORIGINAL_OUTCOMES_SEPARATE")
            self.assertEqual(response["permitted_action"],"NONE")
            wrong=data.replace(b"1234567890abcdef1234567890abcdef",b"badbadbad")
            req=urllib.request.Request(base+"/api/historical-outcomes/upload?name=olist_orders_dataset.csv",
                data=wrong,headers={"Content-Type":"application/octet-stream","X-AEGIS-Upload":"1"},method="POST")
            with self.assertRaises(HTTPError) as error:
                urllib.request.urlopen(req,timeout=5)
            with closing(error.exception):
                self.assertEqual(error.exception.code,400)
            with urllib.request.urlopen(base+"/api/historical-outcomes",timeout=5) as result:
                self.assertEqual(json.load(result)["summary"]["after"],1)
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)
            app.OUTCOMES=original


if __name__ == "__main__":
    unittest.main()
