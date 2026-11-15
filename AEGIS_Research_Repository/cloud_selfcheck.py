"""Owner-run fictional-data checks; never inspect the visitor's active upload."""
from cloud_engine import CloudWorkspace, SAMPLE
from cohort_analysis import checked_cohort
from hosted_copilot import ReadOnlyDataset
from dataset_queries import execute

def run_selfcheck(hosted_client=None):
    results=[]
    w=CloudWorkspace(); w.upload('AEGIS_SELF_CHECK_FICTIONAL.csv',SAMPLE); ds=w.store.dataset
    def check(name,expected,fn):
        try:
            actual=fn(); ok=actual==expected
            results.append({'Check':name,'Expected':str(expected),'Observed':str(actual),'Status':'PASS' if ok else 'FAIL'})
        except Exception as e:
            results.append({'Check':name,'Expected':str(expected),'Observed':type(e).__name__,'Status':'FAIL'})
    check('Distinct suppliers',3,lambda:execute(ds,{'operation':'count_distinct','column':'supplier'})['result'])
    check('Total quantity',73,lambda:execute(ds,{'operation':'sum','column':'quantity'})['result'])
    def cohort():
        g=next(x for x in checked_cohort(ds,'supplier')['groups'] if x['group']=='Gamma')
        return (g['rows'],g['comparable'],g['late'],g['quantity'],g['cost'])
    check('Gamma: rows, valid dates, late, units, value',(2,1,1,'19','473'),cohort)
    def ties():
        db=ReadOnlyDataset(ds)
        try: return sorted(x[0] for x in db.query('SELECT c2 AS supplier, COUNT(*) AS n FROM dataset GROUP BY c2 ORDER BY n DESC LIMIT 1')['rows'])
        finally: db.close()
    check('Tie-aware supplier ranking',['Alpha','Beta','Gamma'],ties)
    check('Separate session does not see upload',True,lambda:CloudWorkspace().store.dataset is None)
    if hosted_client is not None:
        def live():
            r=w.ask('Which supplier appears most frequently? Give all tied suppliers.',hosted_client=hosted_client)
            ev=r.get('analysis_evidence',[])
            names={str(x) for e in ev for row in e['rows'] for x in row}
            return (r.get('routing_mode')=='HOSTED_LLM_TOOL_AGENT' and {'Alpha','Beta','Gamma'}<=names)
        check('Live hosted ranking with evidence (no fallback)',True,live)
    return results
