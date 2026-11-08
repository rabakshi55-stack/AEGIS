import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intake import LocalDataset, INTAKE
from dataset_queries import execute, execute_many, schema, basic_plan
from conversation import plan_dataset_with_local_qwen, LocalModelUnavailable

CSV = ("Supplier,Item,Amount,Units,Purchased,Status\n"
       "S1,Cable,100.00,2,2026-09-01,Delivered\n"
       "S1,Connector,50,1,2026-09-12,Delayed\n"
       "S2,Cable,200,4,2026-10-01,Delayed\n"
       "S2,Connector,,5,2026-10-08,Delivered\n"
       "S3,Cable,-10,1,2026-10-15,Delivered\n")

class FakeResponse:
    def __init__(self, value):
        self.value = value
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, size): return json.dumps(self.value).encode('utf-8')


class DatasetQueryTests(unittest.TestCase):
    def setUp(self):
        self.ds = LocalDataset('fictional.csv', CSV.encode('utf-8'))

    def test_all_rows_queried_not_just_preview(self):
        r = execute(self.ds, {'operation': 'count'})
        self.assertEqual(r['result'], 5)
        self.assertTrue(r['all_rows_considered'])

    def test_sum_and_non_numeric_count(self):
        r = execute(self.ds, {'operation': 'sum', 'column': 'Amount'})
        self.assertEqual(r['result'], 340)
        self.assertEqual(r['non_numeric_or_missing_rows'], 1)
        self.assertEqual(r['valid_numeric_rows'], 4)

    def test_group_mean_ignores_missing_denominator(self):
        r = execute(self.ds, {'operation': 'group_average', 'group_by': ['Supplier'], 'column': 'Amount'})
        groups = {x['group']['Supplier']: x for x in r['result']}
        self.assertEqual(groups['S1']['value'], 75)
        self.assertEqual(groups['S2']['value'], 200)
        self.assertEqual(groups['S2']['numeric_rows'], 1)

    def test_filter_synonyms_case_and_date(self):
        p = {'operation': 'count', 'filters': [{'column':'supplier','op':'eq','value':'s2'}]}
        self.assertEqual(execute(self.ds, p)['result'], 2)
        p = {'operation': 'count', 'filters': [{'column':'Purchased','op':'date_between',
                                              'value':'2026-10-01','value2':'2026-10-31'}]}
        self.assertEqual(execute(self.ds, p)['result'], 3)

    def test_monthly_trend(self):
        p = {'operation':'group_sum','column':'Amount','group_by':['Purchased'],
             'date_grain':'month','order':'key_asc'}
        result = execute(self.ds, p)['result']
        self.assertEqual([x['group']['Purchased'] for x in result], ['2026-09', '2026-10'])
        self.assertEqual([x['value'] for x in result], [150, 190])

    def test_preview_bounded_and_untrusted_value_never_executed(self):
        r = execute(self.ds, {'operation':'preview','columns':['Supplier','Status'],'limit':2})
        self.assertEqual(len(r['result']), 2)
        self.assertEqual(r['matched_rows'], 5)
        self.assertTrue(r['limited_preview'])
        with self.assertRaises(ValueError):
            execute(self.ds, {'operation':'delete','column':'Supplier'})
        with self.assertRaises(ValueError):
            execute(self.ds, {'operation':'preview','limit':99})
        with self.assertRaises(ValueError):
            execute(self.ds, {'operation':'count','unknown':'DROP TABLE'})
        with self.assertRaises(ValueError):
            execute(self.ds, {'operation':'sum','column':'__class__'})

    def test_multiple_plans_limited(self):
        self.assertEqual(len(execute_many(self.ds, {'plans':[{'operation':'count'},
                                {'operation':'count_distinct','column':'Supplier'}]})), 2)
        with self.assertRaises(ValueError):
            execute_many(self.ds, [{'operation':'count'}]*4)

    def test_offline_natural_variants(self):
        p = basic_plan('Tell me the average Amount by Supplier, please', self.ds)
        self.assertEqual(p['operation'], 'group_average')
        p = basic_plan('How many rows are there?', self.ds)
        self.assertEqual(p['operation'], 'count')

    def test_local_planner_gets_metadata_not_raw_rows(self):
        captured = []
        def opener(req, timeout):
            captured.append(json.loads(req.data))
            return FakeResponse({'message':{'content':json.dumps({'plans':[
                {'operation':'group_sum','group_by':['Supplier'],'column':'Amount'}]})}})
        plan = plan_dataset_with_local_qwen('What is spend per supplier?', schema(self.ds), [], opener)
        self.assertEqual(execute_many(self.ds, plan)[0]['result'][0]['value'], 200)
        self.assertNotIn('Connector,50,1', json.dumps(captured))
        self.assertEqual(captured[0]['model'], 'qwen3.5:4b')

    def test_local_planner_syntax_and_injection_rejected(self):
        def opener(req, timeout):
            return FakeResponse({'message':{'content':'{"plans":[{"operation":"execute","code":"os.system()"}]}'}})
        plan = plan_dataset_with_local_qwen('Hack', schema(self.ds), [], opener)
        with self.assertRaises(ValueError):
            execute_many(self.ds, plan)

    def test_store_query_plan_no_qwen(self):
        previous = INTAKE.dataset
        try:
            INTAKE.dataset = self.ds
            result = INTAKE.query_analysis('What is average Amount by Supplier?')
            self.assertEqual(result[0]['analysis'][0]['operation'], 'group_average')
            self.assertIn('75', result[0]['answer'])
        finally:
            INTAKE.dataset = previous

    def test_store_qwen_integration_uses_all_rows_and_guard(self):
        previous = INTAKE.dataset
        try:
            INTAKE.dataset = self.ds
            with patch('conversation.plan_dataset_with_local_qwen', return_value={'plans':[
                     {'operation':'count','filters':[{'column':'Status','op':'eq','value':'Delayed'}]}]}):
                result = INTAKE.query_analysis('How many delayed?', use_local_llm=True)
            self.assertEqual(result[0]['analysis'][0]['result'], 2)
            self.assertEqual(result[0]['evidence_source'], 'ACTUAL_LOCAL_UPLOADED_DATA_READ_ONLY_QUERY')
        finally:
            INTAKE.dataset = previous

if __name__ == '__main__':
    unittest.main()

class DatasetHTTPAnalyticsTests(unittest.TestCase):
    """Check the real local HTTP route with mocked Ollama planning + naturalization."""
    def setUp(self):
        from http.server import ThreadingHTTPServer
        from threading import Thread
        import importlib.util
        import urllib.request
        self.previous = INTAKE.dataset
        INTAKE.dataset = LocalDataset('fictional.csv', CSV.encode())
        spec = importlib.util.spec_from_file_location('nl_query_http_app', ROOT / 'app.py')
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.app.AegisHandler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True, kwargs={'poll_interval':0.01})
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}/api/copilot'

    def tearDown(self):
        INTAKE.dataset = self.previous
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, payload):
        import urllib.request
        req = urllib.request.Request(self.url, method='POST',
            headers={'Content-Type':'application/json'}, data=json.dumps(payload).encode())
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.load(resp)

    def test_local_qwen_can_plan_data_query_without_exact_phrase(self):
        with patch('conversation.plan_dataset_with_local_qwen', return_value={'plans':[{
                'operation':'group_sum','column':'Amount','group_by':['Supplier'],'limit':10}]}), \
             patch.object(self.app, 'natural_answer', side_effect=lambda q, checked, f, h: checked):
            result = self.request({'context':'local_dataset','use_local_llm':True,
                                   'question':'Whose share of the booked amount is biggest?'})
        self.assertEqual(result['context'], 'local_dataset')
        self.assertEqual(result['routing_mode'], 'LOCAL_QWEN_PLANNED_AND_GROUNDED_ANALYSIS')
        self.assertEqual(result['analysis'][0]['result'][0]['value'], 200)
        self.assertEqual(result['permitted_action'], 'NONE')

    def test_general_context_routed_by_model_when_reference_is_implicit(self):
        with patch.object(self.app, 'is_dataset_question_with_local_qwen', return_value=True), \
             patch('conversation.plan_dataset_with_local_qwen', return_value={'plans':[{'operation':'count'}]}), \
             patch.object(self.app, 'natural_answer', side_effect=lambda q, checked, f, h: checked):
            result = self.request({'context':'general','use_local_llm':True,
                                   'question':'How much do we have here?'})
        self.assertEqual(result['context'], 'local_dataset')
        self.assertEqual(result['analysis'][0]['matched_rows'], 5)

    def test_rejected_action_never_reaches_planner(self):
        with patch('conversation.plan_dataset_with_local_qwen', side_effect=AssertionError('No model planner for actions')):
            response = self.request({'context':'local_dataset','use_local_llm':True,
                                    'question':'Execute procurement now.'})
        self.assertEqual(response['permitted_action'], 'NONE')
        self.assertTrue(response['safety_gate'])
