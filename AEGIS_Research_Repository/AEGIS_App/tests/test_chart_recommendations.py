"""Goal-driven chart selection. All data are fictional; no business decisions."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import quote
from unittest.mock import patch
import importlib.util
import json
import sys
import unittest
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from intake import INTAKE,LocalDataset
from chart_recommendations import is_recommendation_question,recommend_for_question,validate_proposal
from conversation import LocalModelUnavailable,plan_chart_with_local_qwen
from custom_charts import build_chart

CSV=("Supplier,Order Date,Order Amount,Warehouse,Stock Qty,Profit\n"
     "A,2026-01-01,100,North,20,10\n"
     "B,2026-02-01,200,South,30,20\n"
     "A,2026-03-01,300,North,40,30\n"
     "B,2026-04-01,500,South,60,40\n").encode('utf-8')

class ChartSelectionTests(unittest.TestCase):
    def setUp(self):self.ds=LocalDataset('fictional.csv',CSV)
    def rec(self,q,**kwargs):return recommend_for_question(self.ds,q,revision=11,**kwargs)[0]
    def test_variable_combinations_varied_language(self):
        for q in ('Please recommend a chart for total order amount by supplier.',
                  'What is the best visualization to compare supplier spending?',
                  'Which graph would show how the order amounts vary between suppliers?',
                  'How could we compare suppliers by order amount?'):
            with self.subTest(q=q):
                self.assertTrue(is_recommendation_question(q))
                r=self.rec(q);config=r['chart_suggestion']['options']
                self.assertEqual(config['x'],'Supplier')
                self.assertEqual(config['y'],'Order Amount')
                self.assertEqual(config['aggregation'],'sum')
                self.assertEqual(r['permitted_action'],'NONE')
    def test_monthly_trend_and_followup(self):
        r=self.rec('Choose a chart to track recorded sales over time by month')
        spec=r['chart_suggestion']['options']
        self.assertEqual((spec['x'],spec['y'],spec['aggregation'],spec['date_grain']),
                         ('Order Date','Order Amount','sum','month'))
        follow=self.rec('Show it by year instead',history=[{'question':'Choose a chart to track recorded sales over time by month'}])
        self.assertEqual(follow['chart_suggestion']['options']['date_grain'],'year')
    def test_quantity_by_warehouse(self):
        config=self.rec('Please suggest the ideal graph for warehouse inventory quantities')['chart_suggestion']['options']
        self.assertEqual((config['x'],config['y'],config['aggregation']),('Warehouse','Stock Qty','sum'))
    def test_numeric_relationship_uses_scatter(self):
        q='What variable combination lets me see the relationship between Stock Qty and Order Amount?'
        self.assertTrue(is_recommendation_question(q))
        conf=self.rec(q)['chart_suggestion']['options']
        self.assertEqual(conf['chart_type'],'scatter')
        self.assertEqual({conf['x'],conf['y']},{'Stock Qty','Order Amount'})
    def test_correctly_refuses_unavailable_profit_or_margin(self):
        r=self.rec('Suggest a chart showing margin by warehouse')
        self.assertNotIn('chart_suggestion',r)
        self.assertIn('no confirmed margin field',r['answer'])
        bare=LocalDataset('source.csv',b'Supplier,Cost\nA,15\nB,20\n')
        r=recommend_for_question(bare,'Suggest a chart for company profit by supplier',revision=1)[0]
        self.assertNotIn('chart_suggestion',r)
    def test_sales_not_substituted_with_cost(self):
        bare=LocalDataset('source.csv',b'Supplier,Cost\nA,15\nB,20\n')
        r=recommend_for_question(bare,'Suggest a chart for sales by supplier',revision=1)[0]
        self.assertNotIn('chart_suggestion',r)
        self.assertIn('revenue',r['answer'])
    def test_missing_delay_evidence_not_fake_reliability(self):
        r=self.rec('Recommend a chart to find the most reliable suppliers')
        self.assertNotIn('chart_suggestion',r)
        self.assertIn('No validated',r['answer'])
    def test_real_derived_delay_percentage_uses_available_auto_chart(self):
        content=['supplier_id,promised_delivery_date,actual_delivery_timestamp']
        for i in range(12):
            content.append(f'A,2026-01-10,{"2026-01-11" if i < 6 else "2026-01-10"}')
            content.append(f'B,2026-01-10,{"2026-01-11" if i < 2 else "2026-01-10"}')
        dataset=LocalDataset('delivery.csv',("\n".join(content)+"\n").encode('utf-8'))
        answer,_=recommend_for_question(dataset,'What chart should compare supplier delay rates?',revision=3)
        self.assertEqual(answer['chart_suggestion']['kind'],'automatic')
        self.assertEqual(answer['chart_suggestion']['chart_id'],'recorded_date_exceptions_by_supplier')
        self.assertIn('not a supplier reliability rating',answer['answer'])
    def test_existing_chart_explanation_not_hijacked(self):
        for q in ('Can you explain this visualization and what the bars stand for?',
                  'What does this chart show?', 'How is this chart calculated?'):
            self.assertFalse(is_recommendation_question(q),q)
    def test_qwen_valid_matching_chart_accepted(self):
        llm={'kind':'custom','options':{'chart_type':'horizontal_bar','x':'Supplier',
                 'y':'Order Amount','aggregation':'sum','date_grain':'none','sort':'value_desc','limit':10}}
        r=self.rec('Suggest a chart for total order amount by Supplier',llm_proposal=llm)
        self.assertEqual(r['chart_suggestion']['options']['chart_type'],'horizontal_bar')
        self.assertEqual(r['routing_mode'],'LOCAL_QWEN_SCHEMA_PLAN_VALIDATED')
    def test_qwen_wrong_metric_falls_back(self):
        bad={'kind':'custom','options':{'chart_type':'bar','x':'Warehouse','y':'Stock Qty',
                'aggregation':'sum','date_grain':'none','sort':'value_desc','limit':20}}
        r=self.rec('Recommend a chart for Order Amount by Supplier',llm_proposal=bad)
        self.assertEqual(r['chart_suggestion']['options']['x'],'Supplier')
        self.assertEqual(r['chart_suggestion']['options']['y'],'Order Amount')
    def test_qwen_disallowed_code_and_unseen_columns(self):
        for proposal in ({'kind':'custom','options':{'chart_type':'exec','x':'Supplier'}},
                         {'kind':'custom','options':{'chart_type':'bar','x':'SECRET','y':None}},
                         {'kind':'custom','options':{'chart_type':'bar','x':'Supplier','y':None,'sql':'DROP TABLE'}}):
            with self.assertRaises(ValueError):validate_proposal(self.ds,proposal)
    def test_proposed_calculation_uses_all_source_rows(self):
        rec=self.rec('Recommend a chart for total Order Amount by Supplier')
        chart=build_chart(self.ds,rec['chart_suggestion']['options'])
        self.assertEqual({v['label']:v['value'] for v in chart['values']},{'B':700,'A':400})
        self.assertEqual(chart['source_rows'],4)
    def test_html_controls_and_create_hook(self):
        page=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        for text in ('id="chart-goal-form"','id="chart-goal-question"'):
            self.assertIn(text,page)
        for text in ('async function applyRecommendedChart','metadata?.chart_suggestion',
                     'suggestion.dataset_revision','/api/intake/chart',
                     'chart-goal-form','Recommend a chart to answer this question: '):
            self.assertIn(text,js)

class ChartRecommendationHttpTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('aegis_chart_recom_app',ROOT/'app.py')
        self.app=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.app)
        INTAKE.clear()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.app.AegisHandler)
        self.thread=Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.02},daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_address[1]}'
        req=urllib.request.Request(self.base+'/api/intake/upload?name='+quote('fake.csv'),data=CSV,
                headers={'X-AEGIS-Upload':'1'},method='POST')
        with urllib.request.urlopen(req,timeout=5) as res:self.data=json.load(res)
    def tearDown(self):
        INTAKE.clear();self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
    def post(self,q,**kwargs):
        request=urllib.request.Request(self.base+'/api/copilot',
                  data=json.dumps({'question':q,'context':'local_dataset',**kwargs}).encode('utf-8'),
                  headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(request,timeout=10) as res:return json.load(res)
    def test_suggestion_from_standard_mode_and_chart_recalc(self):
        r=self.post('Which chart should I use to see total Order Amount by Supplier?')
        self.assertEqual(r['evidence_source'],'VERIFIED_CHART_RECOMMENDATION')
        self.assertEqual(r['chart_suggestion']['dataset_revision'],self.data['dataset_revision'])
        conf=r['chart_suggestion']['options']
        req=urllib.request.Request(self.base+'/api/intake/chart',
                  data=json.dumps(conf).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=5) as res: chart=json.load(res)
        self.assertEqual(chart['source_rows'],4)
        self.assertEqual(chart['values'][0]['value'],700)
    def test_qwen_on_valid_json_proposal(self):
        llm={'kind':'custom','options':{'chart_type':'horizontal_bar','x':'Supplier','y':'Order Amount',
                                     'aggregation':'sum','date_grain':'none','sort':'value_desc','limit':10}}
        with patch.object(self.app,'plan_chart_with_local_qwen',return_value=llm):
            r=self.post('Recommend a chart to compare Order Amount by Supplier',use_local_llm=True)
        self.assertIn('QWEN',r['routing_mode'])
        self.assertEqual(r['chart_suggestion']['options']['chart_type'],'horizontal_bar')
    def test_qwen_unavailable_falls_back_and_does_not_invent(self):
        with patch.object(self.app,'plan_chart_with_local_qwen',side_effect=LocalModelUnavailable('offline')):
            r=self.post('Recommend a bar chart to see the most spending by Supplier',use_local_llm=True)
        self.assertIn('chart_suggestion',r)
        self.assertEqual(r['chart_suggestion']['options']['x'],'Supplier')
    def test_unrelated_general_chat_kept_out_of_dataset(self):
        r=self.post('Hello',context='general')
        self.assertNotIn('chart_suggestion',r)
        self.assertEqual(r['context'],'general')
    def test_dataset_replacement_during_qwen_planning_is_rejected(self):
        def swap(*_args,**_kwargs):
            INTAKE.upload('replacement.csv',b'Warehouse,Stock Qty\nEast,11\nWest,20\n')
            return {'kind':'custom','options':{'chart_type':'bar','x':'Supplier','y':'Order Amount',
                        'aggregation':'sum','date_grain':'none','sort':'value_desc','limit':20}}
        with patch.object(self.app,'plan_chart_with_local_qwen',side_effect=swap):
            data={'question':'Suggest a chart for Order Amount by Supplier',
                  'context':'local_dataset','use_local_llm':True}
            req=urllib.request.Request(self.base+'/api/copilot',data=json.dumps(data).encode(),
                  headers={'Content-Type':'application/json'},method='POST')
            with self.assertRaises(HTTPError) as err:urllib.request.urlopen(req,timeout=10)
            self.assertEqual(err.exception.code,400)
            self.assertIn('dataset changed',err.exception.read().decode('utf-8'))
            err.exception.close()
    def test_cross_origin_blocked(self):
        q={'question':'Suggest a chart for amount by supplier','context':'local_dataset'}
        request=urllib.request.Request(self.base+'/api/copilot',data=json.dumps(q).encode(),
                  headers={'Content-Type':'application/json','Origin':'http://evil.invalid'},method='POST')
        with self.assertRaises(HTTPError) as e:urllib.request.urlopen(request,timeout=5)
        self.assertEqual(e.exception.code,403)
        e.exception.close()

if __name__=='__main__':unittest.main()
