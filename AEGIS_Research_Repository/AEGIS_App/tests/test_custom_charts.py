"""Read-only manager chart builder tests (all test records fictional)."""
from http.server import ThreadingHTTPServer
from pathlib import Path
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
from intake import LocalDataset, IntakeStore, INTAKE
from custom_charts import build_chart

CSV = ("Month,Supplier,Amount,Units,Promised,Actual,State\n"
       "2026-01-01,A,10,2,2026-01-05,2026-01-06,Delivered\n"
       "2026-01-09,A,20,4,2026-01-14,2026-01-14,Delivered\n"
       "2026-02-08,B,30,6,2026-02-14,2026-02-18,Late\n"
       "2026-02-11,B,-5,8,2026-02-14,2026-02-16,Late\n"
       "2026-03-08,C,,2,2026-03-12,2026-03-13,Late\n").encode('utf-8')


def ch(ds, **options):
    return build_chart(ds, {"chart_type":"bar", "x":"Supplier", "y":"Amount",
                            "aggregation":"sum", "sort":"x_asc", "limit":20,
                            "date_grain":"none", **options})


class CustomChartEngineTests(unittest.TestCase):
    def setUp(self):
        self.ds = LocalDataset('fake_suppliers.csv', CSV)

    def test_sum_by_supplier_uses_every_record_and_negatives(self):
        r = ch(self.ds)
        self.assertEqual([(p['label'],p['value']) for p in r['values']],
                         [('A', 30), ('B', 25)])
        self.assertEqual(r['valid_rows'], 4)
        self.assertEqual(r['excluded_y_rows'], 1)
        self.assertEqual(r['source_rows'], 5)
        self.assertFalse(r['business_definition_certified'])
        self.assertEqual(r['permitted_action'], 'NONE')

    def test_swap_axes_changes_groups_not_data(self):
        r = ch(self.ds, x='State', y='Units', aggregation='average')
        self.assertEqual({p['label']:p['value'] for p in r['values']}['Delivered'], 3)
        self.assertAlmostEqual({p['label']:p['value'] for p in r['values']}['Late'], 16/3)

    def test_group_by_month_week_and_quarter(self):
        for grain, labels in [('month', ['2026-01','2026-02','2026-03']),
                              ('quarter', ['2026-Q1'])]:
            r = ch(self.ds, x='Month', y='Units', aggregation='sum', date_grain=grain)
            self.assertEqual([p['label'] for p in r['values']], labels)
        self.assertEqual([p['value'] for p in ch(self.ds,x='Month',y='Units',aggregation='sum',date_grain='month')['values']], [6,14,2])

    def test_rows_and_distinct_count(self):
        r = ch(self.ds, y=None, aggregation='count')
        self.assertEqual({p['label']: p['value'] for p in r['values']}, {'A':2,'B':2,'C':1})
        r = ch(self.ds, y='State', aggregation='distinct_count')
        self.assertEqual({p['label']: p['value'] for p in r['values']}, {'A':1,'B':1,'C':1})

    def test_count_nonblank_y_and_reject_ignored_y(self):
        r = ch(self.ds,y='Amount',aggregation='count_nonblank')
        self.assertEqual({p['label']:p['value'] for p in r['values']}, {'A':2,'B':2,'C':0})
        self.assertEqual(r['excluded_y_rows'],1)
        with self.assertRaisesRegex(ValueError,'Count rows does not use a Y field'):
            ch(self.ds,y='Amount',aggregation='count')

    def test_median_and_extremes(self):
        self.assertEqual(ch(self.ds,aggregation='median')['values'][0]['value'], 15)
        self.assertEqual(ch(self.ds,aggregation='minimum')['values'][1]['value'], -5)
        self.assertEqual(ch(self.ds,aggregation='maximum')['values'][1]['value'], 30)

    def test_scatter_numeric_pairs_and_bound(self):
        r = ch(self.ds, chart_type='scatter', x='Units', y='Amount')
        self.assertEqual(r['valid_rows'],4)
        self.assertEqual(r['points'][3],{'x':8.0,'y':-5.0})
        self.assertFalse(r['truncated'])
        large = LocalDataset('large.csv', ('X,Y\n' + ''.join(f'{i},{i*2}\n' for i in range(400))).encode('utf-8'))
        r = build_chart(large, {'chart_type':'scatter','x':'X','y':'Y'})
        self.assertEqual(r['valid_rows'],400)
        self.assertEqual(r['plotted_points'],300)
        self.assertTrue(r['truncated'])
        self.assertIn('first 300 of 400',r['note'])

    def test_histogram_all_rows_and_missing(self):
        r = ch(self.ds, chart_type='histogram', x='Units', y=None)
        self.assertEqual(sum(p['value'] for p in r['values']),5)
        self.assertEqual(r['valid_rows'],5)

    def test_pie_rejects_negative_and_too_many_categories(self):
        with self.assertRaisesRegex(ValueError,'Pie and donut'):
            ch(self.ds,chart_type='pie',x='Supplier',y='Amount',aggregation='minimum')
        r = ch(self.ds,chart_type='donut',x='Supplier',y=None,aggregation='count')
        self.assertEqual(sum(p['value'] for p in r['values']),5)

    def test_mixed_invalid_fields_and_code_are_rejected(self):
        for spec in ({'x':'__dict__','chart_type':'bar'},
                     {'x':'Supplier','chart_type':'shell'},
                     {'x':'Supplier','chart_type':'bar','execute':'erase'},
                     {'x':'Supplier','chart_type':'scatter','y':'Supplier'},
                     {'x':'Amount','chart_type':'histogram','y':'Units'},
                     {'x':'Month','chart_type':'area','date_grain':'hour'},
                     {'x':'Supplier','chart_type':'bar','limit':500},
                     {'x':'Supplier','chart_type':'bar','limit':True}):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                build_chart(self.ds,spec)

    def test_render_limit_is_disclosed_but_all_rows_counted(self):
        r = ch(self.ds, y=None, aggregation='count',limit=2,sort='x_asc')
        self.assertTrue(r['truncated'])
        self.assertEqual(len(r['values']),2)
        self.assertEqual(r['source_rows'],5)
        self.assertIn('Showing 2 of 3 groups',r['note'])

    def test_chart_data_not_derived_from_archived_olist(self):
        self.assertEqual(ch(self.ds)['source'],'CURRENT_LOCAL_UPLOADED_DATASET')
        self.assertEqual(ch(self.ds)['dataset'],'fake_suppliers.csv')
        self.assertNotIn('58,911',json.dumps(ch(self.ds)))

    def test_backend_revision_changes_for_replaced_dataset(self):
        store = IntakeStore()
        profile1 = store.upload('original.csv',CSV)
        c1 = store.chart({'x':'Supplier','aggregation':'count','chart_type':'bar'})
        profile2 = store.upload('replacement.csv',b'Foo,Bar\nX,7\nY,2\n')
        self.assertNotEqual(profile1['dataset_revision'],profile2['dataset_revision'])
        self.assertNotEqual(c1['dataset_revision'],profile2['dataset_revision'])
        self.assertEqual(store.chart({'x':'Foo','y':'Bar','aggregation':'sum'})['values'][0]['value'],7)
        with self.assertRaises(ValueError):
            store.chart({'x':'Supplier','aggregation':'count'})
        store.clear()
        with self.assertRaisesRegex(ValueError,'Upload a dataset'):
            store.chart({'x':'Foo'})

    def test_html_and_js_controls_escaped_and_present(self):
        html = (ROOT/'web'/'index.html').read_text(encoding='utf-8')
        js = (ROOT/'web'/'app.js').read_text(encoding='utf-8')
        for token in ('id="custom-chart-x"','id="custom-chart-y"','id="custom-chart-type"',
                      'id="custom-chart-swap"','id="custom-chart-save"','id="custom-chart-cards"'):
            self.assertIn(token,html)
        self.assertIn('setupCustomCharts();',js)
        self.assertIn('Customize a copy',js)
        self.assertIn('const html =',js)
        self.assertIn('answer.dataset_revision !== state.intake.dataset_revision',js)


class CustomChartHttpTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('aegis_custom_charts_app',ROOT/'app.py')
        self.app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.app)
        INTAKE.clear()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.app.AegisHandler)
        self.thread=Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.03},daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_address[1]}'
        req=urllib.request.Request(self.base+'/api/intake/upload?name='+quote('fake_suppliers.csv'),
            data=CSV,headers={'Content-Type':'application/octet-stream','X-AEGIS-Upload':'1'},method='POST')
        with urllib.request.urlopen(req,timeout=5) as res:
            self.upload=json.load(res)

    def tearDown(self):
        INTAKE.clear()
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def post(self,spec,headers=None):
        return urllib.request.Request(self.base+'/api/intake/chart',data=json.dumps(spec).encode('utf-8'),
              headers={'Content-Type':'application/json',**(headers or {})},method='POST')

    def test_uploaded_data_chart_http(self):
        with urllib.request.urlopen(self.post({'x':'Supplier','y':'Amount','aggregation':'sum',
                                               'chart_type':'horizontal_bar'}),timeout=5) as response:
            result=json.load(response)
        self.assertEqual(result['dataset_revision'],self.upload['dataset_revision'])
        self.assertEqual(result['values'][0]['label'],'A')
        self.assertEqual(result['values'][0]['value'],30)
        self.assertEqual(result['permitted_action'],'NONE')

    def test_chart_rejects_foreign_origin_and_arbitrary_code(self):
        with self.assertRaises(HTTPError) as e:
            urllib.request.urlopen(self.post({'x':'Supplier'}, {'Origin':'http://evil.example'}),timeout=5)
        self.assertEqual(e.exception.code,403)
        e.exception.close()
        with self.assertRaises(HTTPError) as e:
            urllib.request.urlopen(self.post({'x':'Supplier','action':'BUY_SUPPLIER'}),timeout=5)
        self.assertEqual(e.exception.code,400)
        e.exception.close()


if __name__=='__main__':
    unittest.main()
