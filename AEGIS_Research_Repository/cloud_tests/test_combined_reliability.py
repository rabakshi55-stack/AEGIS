import io, json, os, unittest, urllib.error
from unittest.mock import patch
from cloud_engine import CloudWorkspace, SAMPLE
from dataset_overview import build_overview
from intake import LocalDataset
from hosted_copilot import GroqClient, HostedUnavailable, PlanFormatError, ask_hosted


def plan(**fields):
    return dict({'kind':'answer','sql':None,'options':None,'answer':None,'basis':None}, **fields)

class Response(io.BytesIO):
    pass

def response(obj):
    return Response(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(obj)}}]}).encode())

def error(status, code):
    return urllib.error.HTTPError('https://api.groq.com/openai/v1/chat/completions',status,'error',{},io.BytesIO(json.dumps({'error':{'code':code}}).encode()))

class CombinedTests(unittest.TestCase):
    def setUp(self): self.ds=LocalDataset('FICTIONAL_example.csv',SAMPLE)
    def test_exact_screenshot_trend(self):
        r=build_overview(self.ds)['answer']
        self.assertIn('2026-01: 2; 2026-02: 2; 2026-03: 2',r)
        self.assertIn('Flat across all displayed periods',r)
        self.assertIn('3 displayed periods tie for the highest value (2)',r)
        self.assertIn('2 of 5 comparable rows (40%)',r)
        self.assertNotIn('highest displayed period is 2026-01',r)
    def test_fluctuating_equal_endpoints(self):
        d=LocalDataset('x.csv',b'order_date,quantity\n2026-01-01,1\n2026-02-01,1\n2026-02-02,1\n2026-03-01,1\n')
        r=build_overview(d)['answer'];self.assertIn('Fluctuates; the last displayed value is equal to the first',r)
    def test_no_missing_period_zero(self):
        d=LocalDataset('x.csv',b'order_date,quantity\n2026-01-01,1\n2026-01-02,1\n2026-03-01,1\n2026-03-02,1\n')
        r=build_overview(d)['answer'];self.assertIn('Periods without usable records are not inferred to be zero',r);self.assertNotIn('2026-02:',r)
    def test_recover_http_400_with_actual_request_payload(self):
        w=CloudWorkspace();w.upload('example.csv',SAMPLE)
        with patch.dict(os.environ,{'AEGIS_OFFLINE_TEST_MODE':'0'}), patch('hosted_copilot._quota'), patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[error(400,'json_validate_failed'),response(plan(answer='Activity is flat across the displayed months.',basis='evidence'))]
            r=w.ask('can u analyze the trend happening in the dataset ?',hosted_client=GroqClient('test-only'))
            self.assertIn('Flat across all displayed periods',r['answer']);self.assertEqual(r['routing_mode'],'HOSTED_LLM_TOOL_AGENT')
            calls=opener.return_value.open.call_args_list
            self.assertEqual(len(calls),2)
            payloads=[json.loads(c.args[0].data) for c in calls]
            self.assertTrue(payloads[0]['response_format']['json_schema']['strict']);self.assertEqual(payloads[1]['response_format'],{'type':'json_object'})
    def test_bad_fallback_rejected(self):
        with patch.dict(os.environ,{'AEGIS_OFFLINE_TEST_MODE':'0'}),patch('hosted_copilot._quota'),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[error(400,'json_validate_failed'),response({'kind':'query','sql':'DELETE FROM dataset'})]
            with self.assertRaises(PlanFormatError): GroqClient('fake').complete([])
            self.assertEqual(opener.return_value.open.call_count,2)
    def test_no_retry_on_auth(self):
        with patch.dict(os.environ,{'AEGIS_OFFLINE_TEST_MODE':'0'}),patch('hosted_copilot._quota'),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=error(401,'invalid_api_key')
            with self.assertRaisesRegex(HostedUnavailable,'401'):GroqClient('fake').complete([])
            self.assertEqual(opener.return_value.open.call_count,1)
    def test_both_formats_fail_checked_overview(self):
        with patch.dict(os.environ,{'AEGIS_OFFLINE_TEST_MODE':'0'}),patch('hosted_copilot._quota'),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[error(400,'json_validate_failed'),error(400,'json_validate_failed')]
            r=ask_hosted(self.ds,'Can you analyze the trend happening in the dataset?',[],1,GroqClient('fake'))
            self.assertEqual(r['routing_mode'],'HOSTED_LLM_PARTIAL_EVIDENCE');self.assertIn('Flat across all displayed periods',r['answer']);self.assertIn('hosted explanation unavailable',r['answer'])
    def test_retry_plan_still_read_only(self):
        with patch.dict(os.environ,{'AEGIS_OFFLINE_TEST_MODE':'0'}),patch('hosted_copilot._quota'),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=[error(400,'json_validate_failed'),response(plan(kind='query',sql='DELETE FROM dataset')),response(plan(kind='query',sql='SELECT COUNT(*) AS n FROM dataset')),response(plan(answer='Six records.',basis='evidence'))]
            r=ask_hosted(self.ds,'How many rows?',[],1,GroqClient('fake'))
            self.assertEqual(r['analysis_evidence'][0]['rows'],[[6]]);self.assertTrue(r['tool_errors'])
if __name__=='__main__':unittest.main()
