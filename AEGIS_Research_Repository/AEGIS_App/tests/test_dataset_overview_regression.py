"""Regression for real reported failure: 2,880-row upload gives empty summary.
Runs without Qwen, network access, training or procurement.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intake import INTAKE, LocalDataset, refers_to_uploaded_data
from dataset_overview import asks_for_overview, build_overview, is_adequate_overview_reply
from conversation import LocalModelUnavailable

SPEC = importlib.util.spec_from_file_location('aegis_overview_integration', ROOT / 'app.py')
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)


def example(n=2880):
    head = 'Supplier,Order Date,Sales Amount,Expected Delivery Date,Actual Delivery Date\n'
    lines = []
    for i in range(n):
        supplier = ('A','B','C')[i % 3]
        month = 1 + (i % 3)
        sales = (100,200,50)[i % 3]
        actual = ('2026-03-02','2026-03-01','')[i % 3]
        lines.append(f'{supplier},2026-{month:02d}-05,{sales},2026-03-01,{actual}')
    return (head+'\n'.join(lines)).encode('utf-8')


class SummaryIntentTests(unittest.TestCase):
    def setUp(self):
        self.dataset = LocalDataset('company.csv', example())

    def test_natural_paraphrases(self):
        for question in (
            'What does the uploaded dataset say?',
            'What is the data telling me?',
            'Can you tell me what is happening in this spreadsheet?',
            'Just give me the big picture.',
            'What do you notice from these figures?',
            'Summarize the upload for management',
            'What is this data showing overall?',
            'Any interesting findings?',
        ):
            with self.subTest(question=question):
                self.assertTrue(asks_for_overview(question))
                self.assertTrue(refers_to_uploaded_data(question, self.dataset))

    def test_directed_and_general_questions_not_overview(self):
        for question in ('What is safety stock?', 'What is logistic regression?',
                         'Which fields should I map?', 'Show sales by month',
                         'How many rows?', 'Recommend a line chart'):
            with self.subTest(question=question):
                self.assertFalse(asks_for_overview(question))

    def test_summary_is_calculated_and_specific_without_mapping(self):
        output = build_overview(self.dataset)
        self.assertEqual(output['rows'], 2880)
        self.assertIn('2,880', output['answer'])
        self.assertIn('Data completeness', output['answer'])
        self.assertIn('Patterns worth examining', output['answer'])
        self.assertIn('Delivery-date comparison', output['answer'])
        self.assertIn('No business meanings', output['answer'])
        self.assertNotIn("I don't have enough evidence", output['answer'])
        self.assertNotIn('Tell me which measure', output['answer'])

    def test_blank_categories_and_no_dates_do_not_mislead(self):
        d = LocalDataset('blank.csv', b'area,ref,value\nNorth,a,\nSouth,b,4\nNorth,c,5\n')
        result = build_overview(d)
        self.assertIn('3 rows and 3 columns', result['answer'])
        self.assertIn('1 blank', result['answer'])
        self.assertIn('not necessarily distinct orders', result['answer'])

    def test_qwen_vague_answer_not_accepted(self):
        report = build_overview(self.dataset)
        self.assertFalse(is_adequate_overview_reply('It looks interesting. Contact the data owner.', report))
        self.assertFalse(is_adequate_overview_reply('There are 2,880 rows. Consult a professional.', report))
        self.assertTrue(is_adequate_overview_reply('The 2,880 rows show a delivery-date comparison worth checking.', report))


class OverviewHTTPTests(unittest.TestCase):
    def setUp(self):
        INTAKE.clear()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), APP.AegisHandler)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval':0.03}, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        req = Request(self.base + '/api/intake/upload?name=company.csv', data=example(),
                      headers={'Content-Type':'application/octet-stream','X-AEGIS-Upload':'1'}, method='POST')
        with urlopen(req,timeout=15) as r:
            self.assertEqual(json.load(r)['rows'], 2880)

    def tearDown(self):
        INTAKE.clear()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def ask(self, question, qwen=False):
        req = Request(self.base+'/api/copilot',data=json.dumps({
            'context':'general','use_local_llm':qwen,'question':question}).encode(),
            headers={'Content-Type':'application/json'}, method='POST')
        with urlopen(req,timeout=15) as r:
            return json.load(r)

    def test_standard_natural_summary_same_verified_data(self):
        with patch.object(APP, 'is_dataset_question_with_local_qwen', side_effect=AssertionError('no model needed')):
            for q in ('What does the uploaded dataset say?', 'What is the data telling me?'):
                answer = self.ask(q)
                self.assertEqual(answer['context'],'local_dataset')
                self.assertIn('2,880',answer['answer'])
                self.assertIn('Patterns worth examining',answer['answer'])
                self.assertIn('Data completeness',answer['answer'])
                self.assertEqual(answer['permitted_action'],'NONE')

    def test_qwen_receives_real_overview_no_planner_for_broad_question(self):
        captured = []
        def pretend_model(question, checked, facts, history):
            captured.append((checked,facts))
            return '2,880 rows show a delivery-date comparison. The data meaning is not certified.'
        with patch.object(APP,'natural_answer',side_effect=pretend_model), \
             patch('conversation.plan_dataset_with_local_qwen',side_effect=AssertionError('do not call planner')):
            answer=self.ask('What does the uploaded dataset say?',qwen=True)
        self.assertEqual(answer['context'],'local_dataset')
        self.assertEqual(answer['routing_mode'],'LOCAL_QWEN_GROUNDED_CONVERSATION')
        self.assertIn('2,880',captured[0][0])
        self.assertIn('Data completeness',captured[0][0])
        self.assertIn('checked_dataset_overview',captured[0][1])
        self.assertEqual(answer['permitted_action'],'NONE')

    def test_vague_qwen_reply_falls_back_to_real_summary(self):
        with patch.object(APP,'natural_answer',return_value='I do not have the specific data; please upload again.'):
            answer=self.ask('What is the dataset telling me?',qwen=True)
        self.assertIn('2,880',answer['answer'])
        self.assertIn('Data completeness',answer['answer'])
        self.assertIn('MODEL_UNAVAILABLE',answer['routing_mode'])
        self.assertEqual(answer['permitted_action'],'NONE')

    def test_general_definition_remains_general(self):
        with patch.object(APP,'general_with_local_qwen',return_value='Safety stock is extra inventory held against uncertainty.'):
            answer=self.ask('What is safety stock?',qwen=True)
        self.assertEqual(answer['context'],'general')
        self.assertNotIn('2,880',answer['answer'])

    def test_dataset_replacement_does_not_repeat_old_summary(self):
        self.ask('What does the data say?')
        smaller=b'warehouse,stock\nA,15\nB,30\n'
        req=Request(self.base+'/api/intake/upload?name=stock.csv',data=smaller,
                    headers={'Content-Type':'application/octet-stream','X-AEGIS-Upload':'1'},method='POST')
        with urlopen(req,timeout=15) as r:
            self.assertEqual(json.load(r)['rows'],2)
        answer=self.ask('What is this dataset saying?')
        self.assertIn('2 rows and 2 columns',answer['answer'])
        self.assertNotIn('2,880',answer['answer'])


if __name__=='__main__':
    unittest.main()
