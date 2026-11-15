"""Regression tests from the additional final-release audit (fictional data)."""
import json, unittest
from intake import LocalDataset
from custom_charts import build_chart
from chart_recommendations import recommend_for_question
from adaptive_charts import recommend
from hosted_copilot import ReadOnlyDataset, ask_hosted, HostedUnavailable

class AdditionalIntegrity(unittest.TestCase):
    def setUp(self):
        self.ds=LocalDataset('fiction.csv', b'supplier,quantity,unit_cost,region,order_date,promised_delivery_date,actual_delivery_date\nAlpha,2,10,North,2026-01-01,2026-01-05,2026-01-06\nAlpha,3,12,North,2026-02-01,2026-02-05,2026-02-04\nBeta,4,20,South,2026-03-01,2026-03-05,\n')
    def rec(self,q,**kwargs): return recommend_for_question(self.ds,q,revision=1,**kwargs)[0]
    def test_wrong_derived_metric_never_substituted(self):
        for metric in ('on-time rate','average delivery delay','lead time','total purchase cost'):
            with self.subTest(metric=metric): self.assertNotIn('chart_suggestion',self.rec('Create a chart of '+metric+' by supplier'))
    def test_temporal_filter_not_ignored(self):
        for time in ('in January 2026','last month','since 2026-01-01'):
            self.assertNotIn('chart_suggestion',self.rec('Create a bar chart of quantity by supplier '+time))
        self.assertIn('chart_suggestion',self.rec('Create a chart of quantity by month'))
    def test_zero_count_groups_preserved(self):
        ds=LocalDataset('x.csv',b'group,value\nA,X\nA,X\nB,\n')
        for agg in ('count_nonblank','distinct_count'):
            c=build_chart(ds,dict(chart_type='bar',x='group',y='value',aggregation=agg))
            self.assertEqual({r['label']:r['value'] for r in c['values']},{'A':2 if agg=='count_nonblank' else 1,'B':0})
    def test_nonadditive_pies_rejected(self):
        for agg in ('average','minimum','maximum','median','distinct_count'):
            with self.assertRaisesRegex(ValueError,'not additive'):
                build_chart(self.ds,dict(chart_type='pie',x='supplier',y='quantity',aggregation=agg))
    def test_distinct_text_field_not_row_count(self):
        r=self.rec('Create a chart of unique supplier by region')
        o=r['chart_suggestion']['options'];self.assertEqual((o['x'],o['y'],o['aggregation']),('region','supplier','distinct_count'))
    def test_total_field_not_unit_price(self):
        ds=LocalDataset('totals.csv',b'supplier,unit_cost,total_cost\nA,5,50\nB,7,70\n')
        r,_=recommend_for_question(ds,'Create a chart of total cost by supplier',revision=1)
        self.assertEqual(r['chart_suggestion']['options']['y'],'total_cost')
    def test_qwen_wrong_aggregation_rejected(self):
        wrong={'kind':'custom','options':dict(chart_type='bar',x='supplier',y='quantity',aggregation='sum',date_grain='none',sort='value_desc',limit=20)}
        r=self.rec('Create a chart of average quantity by supplier',llm_proposal=wrong)
        self.assertEqual(r['chart_suggestion']['options']['aggregation'],'average')
    def test_hosted_wrong_aggregation_rejected(self):
        wrong={'kind':'chart','options':dict(chart_type='bar',x='supplier',y='quantity',aggregation='sum',date_grain='none',sort='value_desc',limit=20)}
        class Client:
            def complete(self,messages): return json.dumps(wrong)
        with self.assertRaises(HostedUnavailable): ask_hosted(self.ds,'Create a chart of average quantity by supplier',[],1,Client())
    def test_mixed_currency_not_aggregated(self):
        ds=LocalDataset('mixed.csv',b'supplier,order_date,total_amount,currency\nA,2026-01-01,20,USD\nB,2026-01-02,10,EUR\nA,2026-02-01,30,USD\nB,2026-02-02,40,EUR\n')
        with self.assertRaisesRegex(ValueError,'currency'):
            build_chart(ds,dict(chart_type='bar',x='supplier',y='total_amount',aggregation='sum'))
        self.assertNotIn('recorded_amount_trend',[c['id'] for c in recommend(ds)['charts']])
    def test_quoted_text_numeric_cast_blocked(self):
        db=ReadOnlyDataset(LocalDataset('x.csv',b'amount\n12\ninvalid\n'))
        try:
            for sql in ('SELECT SUM("c1") FROM dataset','SELECT AVG([c1]) FROM dataset','SELECT TOTAL(`c1`) FROM dataset','SELECT CAST("c1" AS REAL) FROM dataset','SELECT SUM(DISTINCT "c1") FROM dataset'):
                with self.subTest(sql=sql),self.assertRaisesRegex(ValueError,'aegis_num'): db.query(sql)
            self.assertEqual(db.query('SELECT SUM(aegis_num(c1)) FROM dataset')['rows'],[[12]])
        finally: db.close()
if __name__=='__main__': unittest.main()
