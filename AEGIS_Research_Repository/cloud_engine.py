"""Session-specific adapter to the original AEGIS read-only calculations.
No global upload state or local filesystem connectors. Hosted AI is explicit opt-in.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'AEGIS_App'))
from intake import IntakeStore, LocalDataset, ROLES
from adaptive_charts import recommend
from chart_recommendations import recommend_for_question, is_recommendation_question
from chart_copilot import answer_for_charts, is_chart_question, MAX_CHARTS
from app import block_execution, block_cross_source
from hosted_copilot import ask_hosted, HostedUnavailable

MAX_CLOUD_BYTES = 5 * 1024 * 1024
MAX_CLOUD_ROWS = 25000
MAX_CLOUD_CELLS = 500000
SAMPLE = b'order_id,supplier,region,quantity,unit_cost,order_date,promised_delivery_date,actual_delivery_date\nA1,Alpha,North,12,25,2026-01-01,2026-01-05,2026-01-04\nA2,Beta,South,20,21,2026-01-02,2026-01-06,2026-01-08\nA3,Alpha,North,8,24,2026-02-01,2026-02-05,2026-02-05\nA4,Gamma,West,10,23,2026-02-03,2026-02-08,2026-02-09\nA5,Beta,South,14,22,2026-03-01,2026-03-05,2026-03-04\nA6,Gamma,West,9,27,2026-03-04,2026-03-09,\n'

class CloudWorkspace:
    def __init__(self):
        self.store = IntakeStore()
        self.history = []
        self.charts = []

    def upload(self, filename, raw):
        if len(raw) > MAX_CLOUD_BYTES:
            raise ValueError('Public demo uploads are limited to 5 MiB.')
        ds = LocalDataset(filename, raw)
        if len(ds.rows) > MAX_CLOUD_ROWS or len(ds.rows)*len(ds.columns) > MAX_CLOUD_CELLS:
            raise ValueError('Public demo limit: 25,000 rows and 500,000 cells. Use the local edition for larger data.')
        with self.store.lock:
            self.store.dataset = ds
            self.store.revision += 1
        self.history.clear(); self.charts.clear()
        return self.store.status()

    def clear(self):
        self.store.clear(); self.history.clear(); self.charts.clear()

    def map(self, fields):
        result = self.store.mapping(fields)
        self.history.clear(); self.charts.clear()
        return result

    def add_chart(self, options):
        result = self.store.chart(options)
        opts = {k: result[k] for k in ('chart_type','x','y','aggregation','date_grain','sort','limit')}
        if len(self.charts) >= 8: raise ValueError('Maximum eight custom charts per online session. Remove one first.')
        self.charts.append(opts)
        return result

    def catalog(self):
        if self.store.dataset is None: return []
        auto = [{'key': 'a:'+c['id'], 'kind':'automatic','id':c['id']} for c in recommend(self.store.dataset)['charts']]
        custom = [{'key':'c:'+str(i),'kind':'custom','options':o} for i,o in enumerate(self.charts)]
        return (auto+custom)[:16]

    def ask(self, question, focus=None, hosted_client=None):
        q=str(question).strip()
        if not q or len(q)>1500: raise ValueError('Enter a question of 1–1,500 characters.')
        ds=self.store.dataset
        if ds is None and hosted_client is None: raise ValueError('Upload data or load the fictional example first.')
        h=self.history[-6:]
        if hosted_client is not None and not (block_execution(q) or block_cross_source(q)):
            try:
                result=ask_hosted(ds,q,h,self.store.revision,hosted_client,focus,self.catalog())
                self.history.append({'question':q,'answer':result['answer'],'chart_suggestion':result.get('chart_suggestion'),'routing_mode':result['routing_mode']})
                self.history=self.history[-12:]
                return result
            except (HostedUnavailable,ValueError) as exc:
                # Never silently substitute a rules-based response as AI.
                raise ValueError(str(exc)) from None
        if ds is None: raise ValueError('No business actions are available. Load a dataset for analytical research.')
        operational = block_execution(q) or block_cross_source(q) or any(x in q.lower() for x in ('switch supplier','switching suppliers','recommend supplier','reallocate suppliers','who caused','whose fault','responsible for the delay','why did the supplier','field mapping','map the fields','mapping based','which field maps','what should the mapping'))
        if operational:
            result, _ = self.store.explain(q, history=h)
        elif is_recommendation_question(q,h):
            result,_ = recommend_for_question(ds,q,revision=self.store.revision,history=h)
        else:
            catalog=self.catalog()
            # Prioritize selected chart. Existing chart engine imposes a bounded catalog.
            if focus:
                catalog=sorted(catalog,key=lambda c:c['key']!=focus)
            response = answer_for_charts(ds,q,catalog[:MAX_CHARTS],focus, dataset_revision=self.store.revision,current_revision=self.store.revision,history=h) if catalog and is_chart_question(q,focus,h) else None
            if response is None: response=self.store.query_analysis(q,history=h,use_local_llm=False)
            result,_= response if response is not None else self.store.explain(q,history=h)
        self.history.append({'question':q,'answer':result['answer'],'chart_suggestion':result.get('chart_suggestion')})
        self.history=self.history[-12:]
        return result

    def use_suggestion(self, suggestion):
        if suggestion.get('dataset_revision') != self.store.revision: raise ValueError('This recommendation belongs to an older dataset.')
        if suggestion['kind']=='custom': return self.add_chart(suggestion['options'])
        return next(c for c in recommend(self.store.dataset)['charts'] if c['id']==suggestion['chart_id'])
