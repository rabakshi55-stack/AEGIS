"""Regression checks for screenshot-reported uploaded-data/Qwen source isolation.
All values below are fictional. No network or model download is required.
"""
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
import importlib.util
import json
import sys
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intake import INTAKE, LocalDataset, refers_to_uploaded_data
from copilot_sessions import SESSIONS
spec = importlib.util.spec_from_file_location('aegis_dataset_router_test_app', ROOT / 'app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

CSV1 = ("PO Number,Vendor ID,Order Date,Expected Delivery Date,Actual Delivery Date,Quantity,Unit Price\n"
        "PO-1,S-1,2026-01-01,2026-01-05,2026-01-06,4,100\n"
        "PO-2,S-2,2026-01-02,2026-01-06,2026-01-05,2,999999.99\n").encode('utf-8')
CSV2 = ("sku,warehouse,available_units\n"
        "P-1,North,10\n"
        "P-2,South,20\n").encode('utf-8')


class DatasetRoutingTests(unittest.TestCase):
    def setUp(self):
        INTAKE.clear()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.AegisHandler)
        self.thread = Thread(target=self.server.serve_forever,
                             kwargs={'poll_interval': 0.03}, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.sessions = []

    def tearDown(self):
        INTAKE.clear()
        for token in self.sessions:
            SESSIONS.clear(token)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def send(self, payload):
        req = urllib.request.Request(self.base + '/api/copilot',
                     data=json.dumps(payload).encode('utf-8'),
                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.load(response)
        if result.get('session_id'):
            self.sessions.append(result['session_id'])
        return result

    def upload(self, data, name='fictional.csv'):
        req = urllib.request.Request(self.base + '/api/intake/upload?name=' + quote(name),
              data=data, headers={'Content-Type': 'application/octet-stream',
              'X-AEGIS-Upload': '1'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    def test_screenshot_question_routes_from_general_with_natural_qwen_enabled(self):
        self.upload(CSV1)
        with patch.object(app, 'natural_answer', side_effect=AssertionError('Mapping requires checked response')):
            result = self.send({'context': 'general', 'use_local_llm': True,
                      'question': 'what should be the field mapping based on the data uploaded ?'})
        self.assertEqual(result['context'], 'local_dataset')
        self.assertEqual(result['evidence_source'], 'LOCAL_USER_UPLOAD_UNVERIFIED')
        self.assertIn('PO Number', result['answer'])
        self.assertIn('Vendor ID', result['answer'])
        self.assertIn('Order reference → PO Number', result['answer'])
        self.assertIn('Supplier reference → Vendor ID', result['answer'])
        self.assertIn('NOT automatically applied', result['answer'])
        self.assertIn('price is not necessarily procurement unit cost', result['answer'])
        self.assertNotIn('paste a few sample rows', result['answer'])
        self.assertEqual(INTAKE.dataset.mapping, {})
        self.assertEqual(result['permitted_action'], 'NONE')

    def test_natural_qwen_uses_checked_summary_and_column_names_never_source_rows(self):
        self.upload(CSV1)
        captured = []
        def fake_natural(question, verified, facts, history):
            captured.append((question, verified, facts, history))
            return verified
        with patch.object(app, 'natural_answer', side_effect=fake_natural):
            result = self.send({'context': 'general', 'use_local_llm': True,
                     'question': 'Summarize my uploaded dataset'})
        self.assertEqual(result['context'], 'local_dataset')
        self.assertEqual(result['routing_mode'], 'LOCAL_QWEN_GROUNDED_CONVERSATION')
        self.assertIn('2 rows', result['answer'])
        self.assertIn('PO Number', captured[0][2]['source_columns_only_not_rows'])
        self.assertNotIn('999999.99', json.dumps(captured[0]))
        self.assertFalse(captured[0][2]['semantics_certified'])

    def test_general_question_stays_general_even_with_uploaded_data(self):
        self.upload(CSV1)
        with patch.object(app, 'general_with_local_qwen', return_value='Safety stock is inventory held as a buffer.') as gen:
            result = self.send({'context': 'general', 'use_local_llm': True,
                     'question': 'What is safety stock?'})
        self.assertEqual(result['context'], 'general')
        self.assertEqual(result['evidence_source'], 'GENERAL_KNOWLEDGE_NO_COMPANY_DATA')
        self.assertEqual(result['routing_mode'], 'LOCAL_QWEN_GENERAL_CONVERSATION')
        self.assertTrue(gen.called)
        self.assertNotIn('PO Number', result['answer'])

    def test_dataset_replacement_rotates_trusted_session_scope(self):
        self.upload(CSV1)
        first = self.send({'context': 'general', 'question': 'Which columns are in my file?'})
        self.upload(CSV2)
        second = self.send({'context': 'general', 'question': 'Which columns are in my file?',
                            'session_id': first['session_id'],
                            'history': [{'question': 'Use PO Number even if absent'}]})
        self.assertNotEqual(first['session_id'], second['session_id'])
        self.assertEqual(second['context'], 'local_dataset')
        self.assertIn('warehouse', second['answer'])
        self.assertNotIn('PO Number', second['answer'])
        self.assertEqual(second['permitted_action'], 'NONE')

    def test_unmapped_dates_and_supplier_actions_remain_blocked(self):
        self.upload(CSV1)
        answer = self.send({'context': 'general', 'question': 'Should I switch suppliers now?',
                             'use_local_llm': True})
        self.assertEqual(answer['context'], 'local_dataset')
        self.assertIn("wouldn't recommend switching", answer['answer'])
        self.assertEqual(answer['permitted_action'], 'NONE')
        self.assertTrue(answer['safety_gate'])

    def test_purchase_order_mapping_is_not_mistaken_for_execution(self):
        self.upload(CSV1)
        reply = self.send({'context': 'general', 'question': 'Which field maps the purchase order reference?'})
        self.assertEqual(reply['context'], 'local_dataset')
        self.assertIn('Order reference → PO Number', reply['answer'])
        self.assertNotIn("wouldn't recommend switching", reply['answer'])
        self.assertEqual(reply['permitted_action'], 'NONE')

    def test_no_upload_never_claims_file_access(self):
        answer = self.send({'context': 'general',
                             'question': 'what should be the field mapping based on the data uploaded?'})
        self.assertEqual(answer['context'], 'general')

    def test_static_manager_ui_switches_source_after_upload(self):
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('data.loaded && $("copilot-context").value === "general"', js)
        self.assertIn('context === "general" && response.context === "local_dataset"', js)
        self.assertIn('syncCopilotContext()', js)

    def test_header_suggestion_rejects_bad_date_format(self):
        ds = LocalDataset('bad.csv', b'order_date,quantity\nhello,3\nworld,5\n')
        roles = {r['role'] for r in ds.suggested_mappings()}
        self.assertNotIn('purchase_timestamp', roles)
        self.assertIn('required_units', roles)
        self.assertFalse(refers_to_uploaded_data('What is a safety stock?', ds))
        self.assertFalse(refers_to_uploaded_data('What is a database?', ds))
        self.assertTrue(refers_to_uploaded_data('Help with field mapping', ds))

if __name__ == '__main__':
    unittest.main()

class LocalModelGroundingTests(unittest.TestCase):
    def test_untrue_file_access_denial_is_not_allowed_to_replace_checked_data(self):
        from io import BytesIO
        import conversation
        response = {'message': {'content': "I can't access any uploaded files in this conversation, please paste the data."}}
        def fake_open(req, timeout):
            return BytesIO(json.dumps(response).encode('utf-8'))
        with self.assertRaisesRegex(conversation.LocalModelUnavailable, 'denied access'):
            conversation.natural_answer('Map the fields', 'The file has 2 rows and 3 columns.',
                {'file_rows':2,'file_columns':3, 'permitted_business_action':'NONE'},
                [], http_open=fake_open)

    def test_followup_why_mapping_explains_uncertainty_without_hallucination(self):
        ds = LocalDataset('f.csv', CSV1)
        answer = ds.answer('Why?', history=[{'question':'Suggest field mapping based on my data'}])
        self.assertIn('recognizable column headers', answer['answer'])
        self.assertIn('Unit Price', answer['answer'])
        self.assertEqual(answer['permitted_action'], 'NONE')
