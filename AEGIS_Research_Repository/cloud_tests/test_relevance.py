import unittest
from cloud_engine import CloudWorkspace,SAMPLE
from hosted_copilot import HostedUnavailable
from chart_copilot import is_chart_question

CHART='I want to investigate whether higher purchasing expenditure is associated with worse supplier delivery performance. Select the most appropriate chart, identify the variables and calculations required, and create it if supported.'
CHALLENGE="Since Gamma has a 100% late-delivery rate, doesn't that prove Gamma is an unreliable supplier and should be removed immediately?"
class Down:
    def complete(self,messages): raise HostedUnavailable('rate limit')
class RelevanceTests(unittest.TestCase):
    def setUp(self):
        self.w=CloudWorkspace();self.w.upload('example.csv',SAMPLE)
        self.w.map({'order_id':'order_id','supplier_id':'supplier','destination_state':'region','required_units':'quantity','unit_cost':'unit_cost','purchase_timestamp':'order_date','promised_delivery_date':'promised_delivery_date','actual_delivery_timestamp':'actual_delivery_date'})
    def test_chart_exact_and_outage(self):
        for provider in (None,Down()):
            r=self.w.ask(CHART,hosted_client=provider)
            self.assertEqual(r['routing_mode'],'CHECKED_DERIVED_CHART_GUIDANCE');self.assertEqual(r['chart_suggestion']['kind'],'cohort_scatter')
            for fragment in ('scatter plot','492.00','728.00','473.00','1/1 (100.0%)','Create this chart'):
                self.assertIn(fragment,r['answer'])
    def test_named_challenge_after_chart(self):
        self.w.ask(CHART)
        r=self.w.ask(CHALLENGE)
        self.assertEqual(r['cohort_analysis']['mode'],'decision_challenge');self.assertIn('Gamma has 2 orders; 1 with comparable dates',r['answer']);self.assertIn('1/1 (100.0%)',r['answer']);self.assertIn('does not prove',r['answer']);self.assertNotIn('charts available',r['answer'])
    def test_named_challenge_outage(self):
        self.w.ask(CHART);r=self.w.ask(CHALLENGE,hosted_client=Down());self.assertEqual(r['routing_mode'],'HOSTED_COHORT_FALLBACK');self.assertIn('Gamma has 2 orders',r['answer'])
    def test_no_old_chart_for_unrelated_question(self):
        self.assertFalse(is_chart_question('What is safety stock?',history=[{'question':CHART}]))
        self.assertFalse(is_chart_question(CHALLENGE,history=[{'question':CHART}]))
        self.assertTrue(is_chart_question('Explain this chart',history=[{'question':CHART}]))
    def test_quantity_relationship(self):
        r=self.w.ask('Suggest a scatter plot of supplier quantity versus delivery delays');self.assertIn('total ordered quantity',r['answer']);self.assertIn('19.00',r['answer']);self.assertEqual(r['chart_suggestion']['options']['measure'],'quantity')
    def test_actual_scatter_recomputed_and_saved(self):
        r=self.w.ask(CHART);s=r['chart_suggestion'];c=self.w.use_suggestion(s)
        self.assertEqual({v['label']:(v['x'],v['y'],v['comparable'],v['total']) for v in c['points']},{'Alpha':(492,0,2,2),'Beta':(728,50,2,2),'Gamma':(473,100,1,2)})
        self.assertEqual(len(self.w.derived_charts),1);self.w.use_suggestion(s);self.assertEqual(len(self.w.derived_charts),1)
        self.w.upload('new.csv',SAMPLE);self.assertFalse(self.w.derived_charts)
        with self.assertRaises(ValueError):self.w.use_suggestion(s)
    def test_mixed_currency_no_chart(self):
        self.w.upload('mixed.csv',b'supplier,quantity,unit_cost,currency,promised_delivery_date,actual_delivery_date\nAlpha,2,5,USD,2026-01-01,2026-01-02\nBeta,3,5,EUR,2026-01-01,2026-01-01\n');r=self.w.ask(CHART);self.assertNotIn('chart_suggestion',r)
    def test_missing_cost_or_dates_no_invented_chart(self):
        self.w.upload('bare.csv',b'supplier,quantity\nA,2\nB,3\n');r=self.w.ask(CHART);self.assertIn('not sufficiently established',r['answer']);self.assertNotIn('chart_suggestion',r)
    def test_generic_relationship_missing_axes(self):
        self.w.upload('bare.csv',b'category\nA\nB\n');r=self.w.ask('Recommend a chart to show the relationship between customer satisfaction and profit');self.assertNotIn('chart_suggestion',r)
    def test_group_scope_not_ignored(self):
        r=self.w.ask('Suggest a chart of supplier spending versus delivery performance in 2025');self.assertIn('not sufficiently established',r['answer']);self.assertNotIn('chart_suggestion',r)
if __name__=='__main__':unittest.main()
