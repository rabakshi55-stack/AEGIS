import json, os, unittest
from unittest.mock import patch
from cloud_engine import CloudWorkspace, SAMPLE
from hosted_copilot import GroqClient, PlanFormatError, _validate_provider_plan
from test_combined_reliability import plan, response

class PlanRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.w=CloudWorkspace(); self.w.upload('example.csv', SAMPLE)
        self.env=patch.dict(os.environ,{'AEGIS_OFFLINE_TEST_MODE':'0'}); self.env.start(); self.addCleanup(self.env.stop)
        self.quota=patch('hosted_copilot._quota');self.quota.start();self.addCleanup(self.quota.stop)
    def test_query_with_premature_answer(self):
        bad=plan(kind='query',sql='SELECT COUNT(DISTINCT c2) AS suppliers FROM dataset',answer='999 suppliers',basis='evidence')
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[response(bad),response(plan(answer='Three suppliers.',basis='evidence'))]
            r=self.w.ask('How many suppliers are there?',hosted_client=GroqClient('fake'))
            self.assertEqual(r['analysis_evidence'][0]['rows'],[[3]])
            self.assertNotIn('999 suppliers',r['answer'])
            self.assertEqual(opener.return_value.open.call_count,2)
            messages=json.loads(opener.return_value.open.call_args_list[1].args[0].data)['messages']
            self.assertNotIn('999 suppliers',json.dumps(messages))
    def test_overview_and_chart_discard_inactive_text(self):
        for obj in [plan(kind='overview',answer='wrong',basis='general'),plan(kind='chart',options=dict(chart_type='bar',x='supplier',y=None,aggregation='count',date_grain='none',sort='value_desc',limit=20),answer='wrong',basis='general')]:
            checked=json.loads(_validate_provider_plan(json.dumps(obj)))
            self.assertIsNone(checked['answer']);self.assertIsNone(checked['basis'])
    def test_ambiguous_actions_not_normalized(self):
        opts=dict(chart_type='bar',x='supplier',y=None,aggregation='count',date_grain='none',sort='value_desc',limit=20)
        for obj in [plan(kind='query',sql='SELECT COUNT(*) FROM dataset',options=opts),plan(kind='answer',sql='SELECT COUNT(*) FROM dataset',answer='Six',basis='evidence'),plan(kind='overview',sql='SELECT COUNT(*) FROM dataset'),plan(kind='query',sql='  '),plan(kind='answer',answer='missing basis')]:
            with self.subTest(obj=obj),self.assertRaises(PlanFormatError):_validate_provider_plan(json.dumps(obj))
    def test_inconsistent_plan_repair_then_execute(self):
        bad=plan(kind='answer',sql='DELETE FROM dataset',answer='six',basis='evidence')
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[response(bad),response(plan(kind='query',sql='SELECT COUNT(*) AS n FROM dataset')),response(plan(answer='Six records.',basis='evidence'))]
            r=self.w.ask('How many rows?',hosted_client=GroqClient('fake'))
            self.assertEqual(r['analysis_evidence'][0]['rows'],[[6]])
            payload=json.loads(opener.return_value.open.call_args_list[1].args[0].data)
            self.assertIn('inconsistent analytical plan fields',payload['messages'][-1]['content'])
    def test_failed_repair_falls_back_labeled(self):
        bad=plan(kind='answer',sql='DELETE FROM dataset',answer='fake',basis='evidence')
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[response(bad),response(bad)]
            r=self.w.ask('How many suppliers are there?',hosted_client=GroqClient('fake'))
            self.assertEqual(r['routing_mode'],'HOSTED_PLAN_RECOVERY_STANDARD')
            self.assertIn('Standard analytics (not a hosted AI answer)',r['answer'])
            self.assertIn('3',r['answer']);self.assertNotIn('fake',r['answer'])
            self.assertEqual(len(self.w.store.dataset.rows),6);self.assertEqual(len(self.w.history),1)
    def test_no_dataset_fallback_is_honest(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[response(plan()),response(plan())]
            r=CloudWorkspace().ask('Hello',hosted_client=GroqClient('fake'))
            self.assertEqual(r['routing_mode'],'HOSTED_PLAN_RECOVERY_NO_DATA');self.assertIn('No calculation',r['answer'])
    def test_verified_evidence_survives_invalid_final_plan(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[response(plan(kind='query',sql='SELECT COUNT(*) AS n FROM dataset')),response(plan()),response(plan())]
            r=self.w.ask('How many rows?',hosted_client=GroqClient('fake'))
            self.assertEqual(r['routing_mode'],'HOSTED_LLM_PARTIAL_EVIDENCE');self.assertEqual(r['analysis_evidence'][0]['rows'],[[6]])
    def test_recovered_sql_still_rejected_if_write(self):
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[response(plan(kind='query',sql='DELETE FROM dataset',answer='done',basis='evidence')),response(plan(kind='query',sql='SELECT COUNT(*) AS n FROM dataset')),response(plan(answer='Six records.',basis='evidence'))]
            r=self.w.ask('Count the rows',hosted_client=GroqClient('fake'))
            self.assertTrue(r['tool_errors']);self.assertEqual(r['analysis_evidence'][0]['rows'],[[6]])

if __name__=='__main__':unittest.main()
