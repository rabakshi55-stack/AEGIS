import unittest, io, zipfile
from cloud_engine import CloudWorkspace,SAMPLE
from cloud_selfcheck import run_selfcheck
from hosted_copilot import HostedUnavailable
Q='Suggest a scatter plot of supplier expenditure versus delivery performance'
class FinalCloud(unittest.TestCase):
 def setUp(self):self.w=CloudWorkspace();self.w.upload('example.csv',SAMPLE)
 def test_derived_chart_catalog_and_context(self):
  r=self.w.ask(Q);self.w.use_suggestion(r['chart_suggestion']);self.assertTrue(any(c['key']=='d:0' for c in self.w.catalog()));a=self.w.ask('Explain this chart',focus='d:0');self.assertIn('Gamma',a['answer']);self.assertIn('late=1/1',a['answer'])
 def test_derived_chart_hosted_context(self):
  r=self.w.ask(Q);self.w.use_suggestion(r['chart_suggestion']);
  class Fake:
   def complete(self,messages):
    assert any('Gamma' in m['content'] and 'late=1/1' in m['content'] for m in messages)
    return '{"kind":"answer","answer":"The group-level evidence is descriptive.","basis":"evidence"}'
  a=self.w.ask('Explain this chart',focus='d:0',hosted_client=Fake());self.assertIn('Checked chart evidence',a['answer'])
 def test_oversized_workbook_keeps_previous_data(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('huge.xml',b'x'*(21*1024*1024))
  with self.assertRaisesRegex(ValueError,'inspection limit'):self.w.upload('large.xlsx',b.getvalue())
  self.assertEqual(self.w.store.dataset.filename,'example.csv')
 def test_invalid_workbook_keeps_previous_data(self):
  with self.assertRaisesRegex(ValueError,'Invalid Excel'):self.w.upload('bad.xlsx',b'bad')
  self.assertEqual(self.w.store.dataset.filename,'example.csv')
 def test_selfcheck_includes_derived(self):
  checks=run_selfcheck();self.assertTrue(all(x['Status']=='PASS' for x in checks));self.assertTrue(any('Derived chart' in x['Check'] for x in checks))
if __name__=='__main__':unittest.main()
