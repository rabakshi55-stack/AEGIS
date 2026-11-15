"""Independent regression checks for issues found in the final review."""
import unittest, io, zipfile, sys, json, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from intake import LocalDataset, IntakeStore, _xml
from cohort_analysis import checked_cohort, cohort_relationship, build_cohort_scatter, requested_cohort
from chart_copilot import answer_for_charts
from chart_recommendations import recommend_for_question
import hosted_copilot as hc
SAMPLE=b'order_id,supplier,quantity,unit_cost,promised_delivery_date,actual_delivery_date\nA1,Alpha,12,25,2026-01-05,2026-01-04\nA2,Beta,20,21,2026-01-06,2026-01-08\nA3,Alpha,8,24,2026-02-05,2026-02-05\nA4,Gamma,10,23,2026-02-08,2026-02-09\nA5,Beta,14,22,2026-03-05,2026-03-04\nA6,Gamma,9,27,2026-03-09,\n'
QUESTION='Suggest a scatter plot of supplier expenditure versus delivery performance'
class FinalReliability(unittest.TestCase):
 def setUp(self): self.ds=LocalDataset('fiction.csv',SAMPLE)
 def test_delay_denominators(self):
  c=checked_cohort(self.ds,'supplier');g={x['group']:x for x in c['groups']};self.assertEqual((g['Gamma']['signed_delay_days'],g['Gamma']['late_delay_days'],g['Gamma']['comparable'],g['Gamma']['cost']),(1,1,1,'473'));self.assertEqual(g['Alpha']['signed_delay_days'],-1);self.assertEqual(g['Beta']['signed_delay_days'],1);self.assertEqual(g['Beta']['late_delay_days'],2)
  self.assertIn('Mean signed delay',c['answer']);self.assertIn('Late-only mean',c['answer'])
 def test_avg_delay_request(self):
  self.assertEqual(requested_cohort(self.ds,'Compare each supplier by average delay and purchase cost'),('supplier','comparison'))
 def test_compound_delivery_eligibility_clarification(self):
  q='Compare all suppliers by total orders, ordered quantity, purchase value, average delivery delay and late-delivery rate. Include orders with missing delivery dates in the financial analysis but exclude them from delivery-rate calculations.'
  self.assertEqual(requested_cohort(self.ds,q),('supplier','comparison'))
 def test_dont_substitute_delivery_measure(self):
  for metric in ('on time rate','average delay','lead time'):
   r,_=recommend_for_question(self.ds,'Create a scatter chart of supplier expenditure versus '+metric+' delivery performance',revision=1)
   self.assertNotIn('chart_suggestion',r);self.assertIn('No alternative measure',r['answer'])
 def test_derived_chart_recommendation_and_create(self):
  r,_=recommend_for_question(self.ds,QUESTION,revision=9);s=r['chart_suggestion'];self.assertEqual(s['kind'],'cohort_scatter');self.assertEqual(s['dataset_revision'],9)
  store=IntakeStore();store.upload('fiction.csv',SAMPLE);c=store.chart({'kind':s['kind'],'options':s['options'],'dataset_revision':store.revision});self.assertEqual({p['label']:(p['x'],p['y']) for p in c['points']},{'Alpha':(492,0),'Beta':(728,50),'Gamma':(473,100)})
  with self.assertRaises(ValueError):store.chart({'kind':s['kind'],'options':s['options'],'dataset_revision':-1})
 def test_derived_chart_context(self):
  cat=[{'key':'derived:0','kind':'cohort_scatter','options':{'dimension':'supplier','measure':'cost'}}];r,f=answer_for_charts(self.ds,'Explain this chart',cat,'derived:0',dataset_revision=1,current_revision=1);self.assertIn('Gamma',r['answer']);self.assertIn('late=1/1',r['answer']);self.assertIn('group, not a source row',r['answer'])
 def test_tied_chart_overview(self):
  cat=[{'key':'c:0','kind':'custom','options':{'chart_type':'bar','x':'supplier','y':None,'aggregation':'count','date_grain':'none','sort':'x_asc','limit':20}}];r,_=answer_for_charts(self.ds,'Explain this chart',cat,'c:0',dataset_revision=1,current_revision=1);self.assertIn('Alpha, Beta, Gamma',r['answer'])
 def test_no_share_of_averages(self):
  cat=[{'key':'c:0','kind':'custom','options':{'chart_type':'bar','x':'supplier','y':'quantity','aggregation':'average','date_grain':'none','sort':'x_asc','limit':20}}];r,_=answer_for_charts(self.ds,'What percentage share is shown by this chart?',cat,'c:0',dataset_revision=1,current_revision=1);self.assertNotIn('accounts for',r['answer'])
 def test_threshold_scope_rejected(self):
  self.assertIsInstance(cohort_relationship(self.ds,QUESTION+' where quantity above 10',online_chart=True),str)
  r,_=recommend_for_question(self.ds,'Create a bar chart of quantity by supplier where quantity above 10',revision=1);self.assertNotIn('chart_suggestion',r)
 def test_no_mismatched_derived_values(self):
  with self.assertRaises(ValueError):build_cohort_scatter(self.ds,{'dimension':'supplier','measure':'cost','points':[1]})
 def test_utf16_dtd_blocked(self):
  raw=io.BytesIO();
  with zipfile.ZipFile(raw,'w') as z:z.writestr('x.xml','<!DOCTYPE root [<!ENTITY bad "x">]><root>&bad;</root>'.encode('utf-16'))
  with zipfile.ZipFile(raw) as z:
   with self.assertRaisesRegex(ValueError,'Unsafe XML'):_xml(z,'x.xml')
 def test_rate_limit_cooldown(self):
  with patch.object(hc,'_retry_until',0.0),patch.object(hc,'_calls',hc.deque()),patch.object(hc.time,'monotonic',return_value=100):
   hc._provider_cooldown(12);self.assertEqual(hc._retry_until,112)
   with self.assertRaisesRegex(hc.HostedUnavailable,'cooldown'):hc._quota()
   with patch.object(hc.time,'monotonic',return_value=113):hc._quota();self.assertEqual(len(hc._calls),1)
 def test_unique_and_tied_rank_results(self):
  db=hc.ReadOnlyDataset(self.ds)
  try:
   self.assertEqual(len(db.query('SELECT c2 AS supplier, COUNT(*) AS n FROM dataset GROUP BY c2 ORDER BY n DESC LIMIT 1')['rows']),3)
  finally:db.close()
if __name__=='__main__':unittest.main()
