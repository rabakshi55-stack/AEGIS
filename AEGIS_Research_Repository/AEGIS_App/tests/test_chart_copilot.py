"""Verified chart conversation behavior for automatic & editable user charts.
All data is fictional and no live sourcing actions are authorized.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import quote
import importlib.util
import json
import sys
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from intake import LocalDataset, INTAKE
from chart_copilot import answer_for_charts, is_chart_question
from custom_charts import build_chart
from adaptive_charts import recommend

CSV = ("Month,Supplier,Amount,Units,Promised,Actual,State\n"
       "2026-01-01,A,10,2,2026-01-05,2026-01-06,Delivered\n"
       "2026-01-09,A,20,4,2026-01-14,2026-01-14,Delivered\n"
       "2026-02-08,B,30,6,2026-02-14,2026-02-18,Late\n"
       "2026-02-11,B,-5,8,2026-02-14,2026-02-16,Late\n"
       "2026-03-08,C,,2,2026-03-12,2026-03-13,Late\n").encode('utf-8')
SPEC = {'chart_type':'bar','x':'Supplier','y':'Amount','aggregation':'sum',
        'date_grain':'none','sort':'x_asc','limit':20}

class ChartAnswerTests(unittest.TestCase):
    def setUp(self):
        self.ds=LocalDataset('private_mock.csv',CSV)
        self.defaults=recommend(self.ds)['charts']
        self.catalog=([{'key':'auto:'+c['id'],'kind':'automatic','id':c['id']} for c in self.defaults]
                      +[{'key':'custom:0','kind':'custom','options':SPEC}])
    def answer(self,q,focus='custom:0',catalog=None,revision=9,current=9):
        return answer_for_charts(self.ds,q,self.catalog if catalog is None else catalog,focus,
                                 dataset_revision=revision,current_revision=current)
    def test_custom_chart_gets_actual_aggregations_and_missing_values(self):
        result, facts=self.answer('What does this graph show, which is highest and how did you calculate it?')
        self.assertIn('30',result['answer'])
        self.assertIn('25',result['answer'])
        self.assertIn('4 contributing records',result['answer'])
        self.assertIn('1',result['answer'])
        self.assertEqual(result['evidence_source'],'VERIFIED_CURRENT_DATASET_CHART')
        self.assertEqual(facts['chart_source_facts'][0]['kind'],'custom')
        self.assertEqual(facts['chart_source_facts'][0]['values'][0]['label'],'A')
        self.assertNotIn('Olist historical',result['answer'])
    def test_same_chart_under_varied_phrasings(self):
        for q in ('Explain the figure', 'What is the pattern here?', 'Which is highest?',
                  'Break down that chart', 'Does this visualization tell us anything?',
                  'How is the y-axis calculated?', 'Why did B look smaller?'):
            with self.subTest(question=q):
                answer=self.answer(q)
                self.assertIsNotNone(answer)
                self.assertEqual(answer[0]['context'],'local_dataset')
    def test_nonchart_question_routes_to_the_existing_analysis_engine(self):
        self.assertIsNone(self.answer('How many distinct suppliers are in the dataset?'))
    def test_chart_shows_all_bars_only_on_request(self):
        message=self.answer('List each displayed bar')[0]['answer']
        self.assertIn('A: 30',message)
        self.assertIn('B: 25',message)
    def test_cannot_claim_causal_supplier_performance(self):
        answer=self.answer('Why is A better than B?')[0]['answer']
        self.assertIn('cannot establish its cause',answer)
        self.assertIn('not',answer.lower())
    def test_auto_chart_selectable_and_checked(self):
        self.assertTrue(self.defaults)
        auto_id=self.defaults[0]['id']
        a,_=self.answer('Tell me what the default chart is showing.',focus='auto:'+auto_id)
        self.assertEqual(a['chart_focus'],'auto:'+auto_id)
        self.assertIn(self.defaults[0]['title'],a['answer'])
        self.assertIn('current uploaded dataset',a['answer'])
    def test_charts_overview_includes_both_kinds(self):
        a,_=self.answer('What do these charts visualize?',focus=None)
        self.assertEqual(a['chart_count'],len(self.catalog))
        self.assertIn('automatic',a['answer'])
        self.assertIn('custom',a['answer'])
    def test_selected_chart_comparison_is_cautious(self):
        a,_=self.answer('Compare this chart against the other chart')
        self.assertIn('Second chart',a['answer'])
        self.assertIn('different quantities',a['answer'])
    def test_explicit_question_refers_to_named_chart(self):
        title=self.defaults[0]['title']
        a,_=self.answer('Could you explain the '+title+' chart?',focus=None)
        self.assertIn('**'+title+'**',a['answer'])
    def test_stale_revision_and_invalid_chart_are_hard_errors(self):
        with self.assertRaisesRegex(ValueError,'another dataset'):
            self.answer('Explain this chart',revision=8)
        with self.assertRaisesRegex(ValueError,'not available'):
            self.answer('Explain chart',focus='custom:999')
        with self.assertRaises(ValueError):
            self.answer('Explain this chart',catalog=[{'key':'custom:0','kind':'custom','options':{**SPEC,'shell':'rm'}}])
        with self.assertRaises(ValueError):
            self.answer('Explain chart',catalog=[{'key':'auto:fake','kind':'automatic','id':'not-in-this-data'}],focus='auto:fake')
    def test_ui_exposes_chart_buttons_dropdown_and_trusted_catalog(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        markup=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        self.assertIn('id="copilot-chart-focus"',markup)
        for token in ('Ask AEGIS about this chart','data-custom-ask','currentChartCatalog()',
                      'payload.chart_catalog=currentChartCatalog()','payload.dataset_revision=state.intake.dataset_revision'):
            self.assertIn(token,js)

class ChartAnswerHttpTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('aegis_chart_chat_app',ROOT/'app.py')
        self.app=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        INTAKE.clear()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.app.AegisHandler)
        self.thread=Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.02},daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_address[1]}'
        req=urllib.request.Request(self.base+'/api/intake/upload?name='+quote('private_mock.csv'),data=CSV,
                    headers={'Content-Type':'application/octet-stream','X-AEGIS-Upload':'1'},method='POST')
        with urllib.request.urlopen(req,timeout=5) as res:self.profile=json.load(res)
        self.catalog=[{'key':'custom:0','kind':'custom','options':SPEC}]
    def tearDown(self):
        INTAKE.clear();self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
    def post(self,q,**kwargs):
        body={'question':q,'context':'local_dataset','chart_catalog':self.catalog,
              'chart_focus':'custom:0','dataset_revision':self.profile['dataset_revision'],**kwargs}
        request=urllib.request.Request(self.base+'/api/copilot',data=json.dumps(body).encode('utf-8'),
                                      headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)
    def test_standard_copilot_answers_chart_with_checked_source(self):
        result=self.post('Can you explain this visualization and what the bars stand for?')
        self.assertEqual(result['evidence_source'],'VERIFIED_CURRENT_DATASET_CHART')
        self.assertIn('30',result['answer'])
        self.assertEqual(result['permitted_action'],'NONE')
    def test_qwen_enabled_uses_checked_chart_when_model_unavailable(self):
        # In environments without Ollama, explicit fallback is still checked.
        # Stub a bad local rewrite to make this test deterministic on all machines.
        from unittest.mock import patch
        from conversation import LocalModelUnavailable
        with patch.object(self.app,'natural_answer',side_effect=LocalModelUnavailable('offline')):
            result=self.post('How is this chart calculated?',use_local_llm=True)
        self.assertIn('30',result['answer'])
        self.assertEqual(result['routing_mode'],'CONTEXTUAL_RULES_MODEL_UNAVAILABLE')
    def test_qwen_receives_chart_evidence_in_prompt(self):
        from unittest.mock import patch
        def model_rewrite(question, checked, facts, history):
            self.assertEqual(facts['chart_context'],'SERVER_RECOMPUTED_CURRENT_DATASET')
            self.assertEqual(facts['chart_source_facts'][0]['values'][0]['value'],30)
            return 'From your uploaded chart, A is at 30 and B is at 25; this is descriptive only.'
        with patch.object(self.app,'natural_answer',side_effect=model_rewrite):
            result=self.post('Talk me through this chart in plain language.',use_local_llm=True)
        self.assertEqual(result['routing_mode'],'LOCAL_QWEN_GROUNDED_CONVERSATION')
        self.assertIn('A is at 30',result['answer'])

    def test_rejects_tampered_stale_chart_and_cross_site(self):
        body={'question':'Explain this chart','context':'local_dataset',
              'chart_catalog':self.catalog,'chart_focus':'custom:0',
              'dataset_revision':self.profile['dataset_revision']+1}
        req=urllib.request.Request(self.base+'/api/copilot',data=json.dumps(body).encode('utf-8'),
                    headers={'Content-Type':'application/json'},method='POST')
        with self.assertRaises(HTTPError) as err:urllib.request.urlopen(req,timeout=5)
        self.assertEqual(err.exception.code,400)
        err.exception.close()
        # Use a fresh request (not the request consumed by the previous test).
        # A deliberately rejected POST still has a small body: Windows must
        # receive the 403 instead of a connection reset from unread bytes.
        req = urllib.request.Request(self.base+'/api/copilot',
                    data=json.dumps(body).encode('utf-8'),
                    headers={'Content-Type':'application/json',
                             'Origin':'http://attacker.example'},method='POST')
        with self.assertRaises(HTTPError) as err:urllib.request.urlopen(req,timeout=5)
        self.assertEqual(err.exception.code,403)
        with err.exception as response:
            self.assertIn('Only the local AEGIS interface',response.read().decode('utf-8'))

    def test_rejected_post_replies_reliably_with_a_body(self):
        """Windows must receive 403 for every small cross-origin POST."""
        for extra in ({'Origin':'http://attacker.example'},
                      {'Sec-Fetch-Site':'cross-site'},
                      {'Host':'attacker.example'}):
            with self.subTest(headers=extra):
                headers={'Content-Type':'application/json',**extra}
                req=urllib.request.Request(self.base+'/api/copilot',
                        data=json.dumps({'question':'Explain this chart'}).encode('utf-8'),
                        headers=headers,method='POST')
                with self.assertRaises(HTTPError) as err:
                    urllib.request.urlopen(req,timeout=5)
                self.assertEqual(err.exception.code,403)
                with err.exception as response:
                    self.assertIn(b'Only the local AEGIS interface',response.read())
    def test_no_chart_questions_still_use_data_engine(self):
        result=self.post('How many rows are there in this file?')
        self.assertNotEqual(result['evidence_source'],'VERIFIED_CURRENT_DATASET_CHART')

if __name__=='__main__':unittest.main()
