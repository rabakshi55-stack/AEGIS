import json, unittest
from cloud_engine import CloudWorkspace,SAMPLE
from hosted_copilot import HostedUnavailable

class Fake:
    def __init__(self,*answers): self.answers=iter(answers);self.calls=[]
    def complete(self,messages): self.calls.append(list(messages));return json.dumps(next(self.answers))
class HostedWorkspace(unittest.TestCase):
    def setUp(self): self.w=CloudWorkspace();self.w.upload('fiction.csv',SAMPLE)
    def test_real_agent_path(self):
        f=Fake({'kind':'query','sql':'SELECT COUNT(DISTINCT c2) AS suppliers FROM dataset'},{'kind':'answer','answer':'Three suppliers.','basis':'evidence'})
        r=self.w.ask('How many suppliers are there?',hosted_client=f)
        self.assertEqual(r['analysis_evidence'][0]['rows'],[[3]])
        self.assertEqual(self.w.history[-1]['routing_mode'],'HOSTED_LLM_TOOL_AGENT')
    def test_model_can_converse_without_upload(self):
        f=Fake({'kind':'answer','answer':'Hi, I am AEGIS.','basis':'general'})
        self.assertIn('Hi',CloudWorkspace().ask('Hello',hosted_client=f)['answer'])
    def test_session_isolated(self):
        a=CloudWorkspace();a.upload('new.csv',b'supplier\nAnother\n')
        f=Fake({'kind':'query','sql':'SELECT c1 FROM dataset'},{'kind':'answer','answer':'One supplier.','basis':'evidence'})
        self.assertEqual(a.ask('List vendors',hosted_client=f)['analysis_evidence'][0]['rows'],[['Another']]);self.assertEqual(self.w.history,[])
    def test_actions_blocked_before_provider(self):
        f=Fake();r=self.w.ask('execute procurement',hosted_client=f)
        self.assertEqual(r['permitted_action'],'NONE');self.assertEqual(f.calls,[])
    def test_provider_error_not_hidden(self):
        class Down:
            def complete(self,messages): raise HostedUnavailable('quota')
        with self.assertRaisesRegex(ValueError,'quota'):self.w.ask('How many suppliers?',hosted_client=Down())
        self.assertEqual(self.w.history,[])
    def test_chart_context(self):
        self.w.add_chart(dict(chart_type='bar',x='supplier',y='quantity',aggregation='sum',date_grain='none',sort='value_desc',limit=20))
        f=Fake({'kind':'answer','answer':'Beta leads.','basis':'evidence'})
        r=self.w.ask('What does this chart show?',focus='c:0',hosted_client=f)
        self.assertIn('Checked chart evidence',r['answer']);self.assertIn('Beta',r['answer'])
