import json, unittest
from cloud_engine import CloudWorkspace, SAMPLE
from cohort_analysis import checked_cohort, requested_cohort
from hosted_copilot import HostedUnavailable, _validate_provider_plan
from chat_presentation import renderable_answer

QUESTION='Analyze the delivery performance of each supplier. Compare their late-delivery rates, ordered quantities and total purchase costs. Tell me which supplier management should investigate first and why.'
FOLLOW='what should be avoided from the next transaction ?'
class Fake:
    def __init__(self,*plans): self.plans=iter(plans);self.calls=[]
    def complete(self,messages): self.calls.append(list(messages));return json.dumps(next(self.plans))

def mapped(w):
    w.map({'order_id':'order_id','supplier_id':'supplier','destination_state':'region','required_units':'quantity','unit_cost':'unit_cost','purchase_timestamp':'order_date','promised_delivery_date':'promised_delivery_date','actual_delivery_timestamp':'actual_delivery_date'})

def answer(text): return {'kind':'answer','answer':text,'basis':'evidence'}

class SemanticCohortTests(unittest.TestCase):
    def setUp(self):
        self.w=CloudWorkspace(); self.w.upload('example.csv',SAMPLE);mapped(self.w)
    def test_complete_metrics_independent_of_delivery_filter(self):
        f=Fake(answer('Gamma has one order, 10 units and $230; this proves systematic delays. Pause orders.'))
        r=self.w.ask(QUESTION,hosted_client=f)
        self.assertEqual(r['routing_mode'],'HOSTED_LLM_CHECKED_COHORT')
        g={x['group']:x for x in r['cohort_analysis']['groups']}
        self.assertEqual((g['Gamma']['rows'],g['Gamma']['comparable'],g['Gamma']['late'],g['Gamma']['quantity'],g['Gamma']['cost']),(2,1,1,'19','473'))
        self.assertEqual(g['Beta']['cost'],'728');self.assertEqual(g['Alpha']['cost'],'492')
        s=r['answer'];self.assertIn('19.00 (2)',s);self.assertIn('473.00 (2)',s);self.assertIn('1/1 (100.0%)',s);self.assertIn('not evidence of a systematic',s);self.assertNotIn('$',s);self.assertNotIn('Pause orders',s)
        self.assertIn('Checked cohort evidence',str(f.calls[0]))
        self.assertIn('quantity times unit cost must use all relevant rows',f.calls[0][0]['content'])
    def test_followup_answers_action_not_previous_comparison(self):
        self.w.ask(QUESTION,hosted_client=Fake(answer('Gamma')))
        f=Fake(answer('Repeat the supplier ranking; suspend Gamma.'))
        r=self.w.ask(FOLLOW,hosted_client=f)
        self.assertEqual(r['cohort_analysis']['mode'],'next_action');self.assertTrue(r['answer'].startswith('**Before the next transaction:**'));self.assertIn('Avoid changing allocation',r['answer']);self.assertNotIn('Repeat the supplier ranking',r['answer']);self.assertIn('Current question (answer this, not earlier questions): '+FOLLOW,str(f.calls[0]));self.assertEqual(self.w.history[-1]['cohort_dimension'],'supplier')
    def test_standard_mode_same_authoritative_metrics(self):
        r=self.w.ask(QUESTION);self.assertEqual(r['routing_mode'],'OFFLINE_CHECKED_COHORT');self.assertIn('473.00',r['answer']);self.assertEqual(self.w.ask(FOLLOW)['cohort_analysis']['mode'],'next_action')
    def test_model_can_select_reusable_cohort_tool(self):
        f=Fake({'kind':'supplier_cohort'},answer('Use the computed metrics.'))
        r=self.w.ask('Give me a supplier scorecard',hosted_client=f)
        self.assertEqual(r['routing_mode'],'HOSTED_LLM_CHECKED_COHORT');self.assertIn('473.00',r['answer']);self.assertIn('checked_cohort',str(f.calls[1]))
        obj={'kind':'supplier_cohort','sql':None,'options':None,'answer':None,'basis':None};self.assertEqual(json.loads(_validate_provider_plan(json.dumps(obj)))['kind'],'supplier_cohort')
    def test_provider_failure_does_not_lose_checked_results(self):
        class Down:
            def complete(self,messages): raise HostedUnavailable('unavailable')
        r=self.w.ask(QUESTION,hosted_client=Down());self.assertEqual(r['routing_mode'],'HOSTED_COHORT_FALLBACK');self.assertIn('473.00',r['answer'])
    def test_filtered_requests_not_replaced_with_global_comparison(self):
        for q in ['Compare supplier delivery performance in January','Compare supplier delivery costs for Beta','Compare supplier delivery performance in West','Create a chart of delivery performance by supplier']:
            with self.subTest(q=q):self.assertIsNone(requested_cohort(self.w.store.dataset,q))
        f=Fake({'kind':'supplier_cohort'},{'kind':'query','sql':"SELECT COUNT(*) AS n FROM dataset WHERE c2='Beta'"},answer('Two Beta records.'))
        r=self.w.ask('Compare delivery performance for Beta',hosted_client=f);self.assertIn('not appropriate',str(f.calls[1]));self.assertEqual(r['analysis_evidence'][0]['rows'],[[2]]);self.assertNotIn('cohort_analysis',r)
    def test_other_group_dimension(self):
        r=self.w.ask('Compare delivery performance and purchase costs by region');self.assertEqual(r['cohort_dimension'],'region');self.assertIn('West',r['answer']);self.assertIn('473.00',r['answer'])
    def test_duplicate_orders_missing_dates_and_cost_coverage(self):
        raw=b'order_id,supplier,region,quantity,unit_cost,order_date,promised_delivery_date,actual_delivery_date\nX,A,North,2,5,2026-01-01,2026-01-02,2026-01-04\nX,A,North,3,7,2026-01-01,2026-01-02,bad\nY,B,South,4,,2026-01-01,2026-01-02,\nZ,,South,9,9,2026-01-01,2026-01-02,2026-01-01\n'
        self.w.upload('new.csv',raw);mapped(self.w);r=checked_cohort(self.w.store.dataset,'supplier');g={x['group']:x for x in r['groups']}
        self.assertEqual(r['unit'],'source rows');self.assertEqual(r['excluded_blank_group'],1);self.assertEqual(g['A']['quantity'],'5');self.assertEqual(g['A']['cost'],'31');self.assertEqual(g['A']['invalid_pair'],1);self.assertEqual(g['B']['comparable'],0);self.assertEqual(g['B']['cost_rows'],0);self.assertIn('n/a (no comparable dates)',r['answer']);self.assertNotIn('highest recorded quantity',r['answer']);self.assertIn('not deduplicated',r['answer'])
    def test_tied_rates_and_cost(self):
        raw=b'order_id,supplier,region,quantity,unit_cost,order_date,promised_delivery_date,actual_delivery_date\n1,A,N,2,5,2026-01-01,2026-01-02,2026-01-04\n2,B,S,5,2,2026-01-01,2026-01-02,2026-01-03\n'
        self.w.upload('ties.csv',raw);mapped(self.w);s=checked_cohort(self.w.store.dataset,'supplier')['answer'];self.assertIn('A: 1/1',s);self.assertIn('B: 1/1',s);self.assertIn('A, B share',s)
    def test_dataset_change_clears_followup_context(self):
        self.w.ask(QUESTION);self.w.upload('new.csv',b'supplier\nElse\n');self.assertFalse(self.w.history);self.assertIsNone(requested_cohort(self.w.store.dataset,FOLLOW,self.w.history))
    def test_markdown_and_raw_evidence_separation(self):
        text='**Gamma**\n\n- Recommendation\n![bad](https://example.test/track)\n<script>bad</script>\n\nCalculated evidence (from the active dataset):\nSQL: SELECT 1'
        md,raw=renderable_answer(text);self.assertIn('**Gamma**',md);self.assertNotIn('![',md);self.assertNotIn('<script>',md);self.assertIn('SQL: SELECT 1',raw);self.assertNotIn('SQL:',md)
    def test_unmapped_exact_aliases_are_provisional(self):
        self.w.map({});r=checked_cohort(self.w.store.dataset,'supplier');self.assertIn('provisional',r['answer']);self.assertIn('473.00',r['answer']);self.assertEqual(self.w.store.dataset.mapping,{})
        self.w.upload('ambiguous.csv',b'supplier,vendor,promised_delivery_date,actual_delivery_date\nA,B,2026-01-01,2026-01-02\n');self.assertIsNone(checked_cohort(self.w.store.dataset,'supplier'))
    def test_mixed_currency_not_summed(self):
        self.w.upload('mixed.csv',b'order_id,supplier,quantity,unit_cost,currency,promised_delivery_date,actual_delivery_date\n1,A,2,5,USD,2026-01-01,2026-01-02\n2,A,3,7,EUR,2026-01-01,2026-01-01\n');r=checked_cohort(self.w.store.dataset,'supplier');self.assertFalse(r['cost_comparable']);self.assertIsNone(r['groups'][0]['cost']);self.assertIn('not combined',r['answer']);self.assertNotIn('31.00',r['answer'])
    def test_unverified_currency_or_risk_interpretation_withheld(self):
        for text in ['The total is $1693.','This indicates a systematic problem.','Management should suspend orders.']:
            f=Fake({'kind':'query','sql':'SELECT SUM(c4*c5) AS cost FROM dataset'},answer(text));r=self.w.ask('What is the total purchase cost?',hosted_client=f);self.assertTrue(r['interpretation_withheld']);self.assertNotIn(text,r['answer']);self.assertEqual(r['analysis_evidence'][0]['rows'],[[1693]])
    def test_provider_cannot_use_unrelated_cohort(self):
        f=Fake({'kind':'supplier_cohort'},{'kind':'answer','answer':'Safety stock is buffer inventory.','basis':'general'});r=self.w.ask('Explain safety stock',hosted_client=f);self.assertIn('not appropriate',str(f.calls[1]));self.assertIn('buffer inventory',r['answer']);self.assertNotIn('cohort_analysis',r)
if __name__=='__main__':unittest.main()
