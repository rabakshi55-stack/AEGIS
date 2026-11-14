import json, unittest
from cloud_engine import CloudWorkspace, SAMPLE
from focused_analysis import focused_analysis
from dataset_overview import asks_for_overview
from hosted_copilot import HostedUnavailable

class Fake:
    def __init__(self,*plans): self.plans=iter(plans);self.calls=[]
    def complete(self,messages): self.calls.append(list(messages));return json.dumps(next(self.plans))

class FocusedTests(unittest.TestCase):
    def setUp(self):
        self.w=CloudWorkspace();self.w.upload('fiction.csv',SAMPLE)
        self.w.map({x['role']:x['column'] for x in self.w.store.dataset.suggested_mappings() if x['status']=='suggested_only'})
    def test_exact_delivery_trend_questions_standard(self):
        for q in ['what does the delivery data trend say ?', 'what is the trend in the delivery date','analyze the trend in the delivery performance','delivery performance by month']:
            with self.subTest(q=q):
                r=self.w.ask(q);s=r['answer'];self.assertEqual(r['routing_mode'],'OFFLINE_RECOMPUTED_FOCUSED_ANALYSIS')
                self.assertIn('2026-01: 2 orders; 1 early, 0 exactly on date, 1 late',s)
                self.assertIn('2026-02: 2 orders; 0 early, 1 exactly on date, 1 late',s)
                self.assertIn('2026-03: 2 orders; 1 early, 0 exactly on date, 0 late; 1 comparable; 1 not comparable',s)
                self.assertIn('not reliable evidence of improved or worsening performance',s)
                self.assertNotIn('Activity over time:',s)
    def test_delivery_column_and_promise_count(self):
        for q in ['what does the delivery column say','tell me how many orders were fulfilled according to the promised delivery date','How many orders were delivered on or before the promised date?']:
            with self.subTest(q=q):
                s=self.w.ask(q)['answer'];self.assertIn('3 of 5 comparable orders (60.0%)',s);self.assertIn('2 early and 1 on the exact',s);self.assertIn('1 missing actual delivery dates',s)
    def test_exact_date_and_late_questions_answer_metric_first(self):
        s=self.w.ask('How many orders were delivered on the promised date?')['answer'];self.assertTrue(s.startswith('1 of 5 comparable orders (20.0%)'))
        s=self.w.ask('How many orders were delivered after the promised date?')['answer'];self.assertTrue(s.startswith('2 of 5 comparable orders (40.0%)'))
    def test_hosted_specific_not_broad(self):
        f=Fake({'kind':'answer','answer':'The late rate improved to zero and this proves reliability.','basis':'evidence'})
        r=self.w.ask('what is the trend in the delivery date',hosted_client=f)
        self.assertEqual(r['routing_mode'],'HOSTED_LLM_CHECKED_FOCUSED_ANALYSIS');self.assertIn('Verified focused analysis',r['answer']);self.assertNotIn('proves reliability',r['answer']);self.assertNotIn('Activity over time:',r['answer'])
        self.assertIn('Checked focused analysis',str(f.calls[0]));self.assertIn('2026-03',str(f.calls[0]))
    def test_hosted_overview_tool_cannot_replace_focus(self):
        f=Fake({'kind':'overview'},{'kind':'answer','answer':'Here are the results.','basis':'evidence'})
        r=self.w.ask('what does the delivery data trend say?',hosted_client=f)
        self.assertIn('Verified focused analysis',r['answer']);self.assertNotIn('Verified descriptive overview',r['answer'])
    def test_provider_down_preserves_focused_evidence(self):
        class Down:
            def complete(self,messages): raise HostedUnavailable('provider unavailable')
        r=self.w.ask('what does the delivery column say',hosted_client=Down())
        self.assertEqual(r['routing_mode'],'HOSTED_LLM_PARTIAL_EVIDENCE');self.assertIn('3 of 5 comparable orders',r['answer']);self.assertIn('hosted explanation unavailable',r['answer'])
    def test_other_fields(self):
        s=self.w.ask('what does the quantity column say')['answer'];self.assertIn('mean 12.17',s)
        s=self.w.ask('what does the supplier column say')['answer'];self.assertIn('3 distinct nonblank',s);self.assertIn('shared by 3',s)
        s=self.w.ask('describe the actual_delivery_date column')['answer'];self.assertIn('2026-01-04 to 2026-03-04',s);self.assertIn('1 blanks',s)
    def test_do_not_swallow_filter_or_chart(self):
        for q in ['delivery trend in West','what is the trend in delivery dates for Beta','compare delivery trends by supplier','create a chart for the delivery trend','delivery performance by month in 2026']:
            with self.subTest(q=q): self.assertIsNone(focused_analysis(self.w.store.dataset,q));self.assertFalse(asks_for_overview(q))
    def test_missing_invalid_duplicate_rows(self):
        self.w.upload('other.csv',b'order_id,order_date,promised_delivery_date,actual_delivery_date\nA,2026-01-01,2026-01-02,2026-01-02\nA,2026-01-01,2026-01-02,2026-01-03\nB,2026-02-01,2026-02-02,bad\nC,2026-02-01,2026-02-02,\n')
        # Explicitly map the field: automatic suggestions correctly decline a
        # column containing malformed dates; a user may still map it for audit.
        self.w.map({'order_id':'order_id','purchase_timestamp':'order_date','promised_delivery_date':'promised_delivery_date','actual_delivery_timestamp':'actual_delivery_date'})
        s=self.w.ask('what is the trend in the delivery date')['answer'];self.assertIn('1 of 2 comparable source rows',s);self.assertIn('1 nonblank but invalid date pairs',s);self.assertIn('Late rate: not available',s);self.assertIn('fewer than two comparable months',s)
    def test_unmapped_requires_mapping(self):
        self.w.map({});s=self.w.ask('what does the delivery column say')['answer'];self.assertIn('map the actual and promised',s)
    def test_broad_overview_remains(self):
        r=self.w.ask('what is happening in the data');self.assertIn('Flat across all displayed periods',r['answer']);self.assertEqual(r['routing_mode'],'OFFLINE_RECOMPUTED_MANAGER_OVERVIEW')

if __name__=='__main__': unittest.main()
