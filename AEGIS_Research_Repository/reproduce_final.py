"""Fit/reproduce V3, V4 and frozen JD evaluation; optional full historical benchmark."""
import argparse,hashlib,json,os,platform,subprocess,sys,importlib.metadata as md
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(script,*args):
    subprocess.run([sys.executable,'-B',str(ROOT/script),*map(str,args)],cwd=ROOT,check=True,env={**os.environ,'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'2','MKL_NUM_THREADS':'2'})
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--jd-archive',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--historical',action='store_true',help='Also refit all historical benchmark scripts; may be slow');a=ap.parse_args()
    out=a.output.resolve();jd=a.jd_archive.resolve();olist=ROOT/'Research/Public_Data/Olist_Raw/archive';v4=ROOT/'Review_V4'
    if not jd.is_file():raise SystemExit('Obtain authorized JD CSVs; provide ZIP via --jd-archive.')
    if platform.python_version()!='3.13.5':raise SystemExit('Python 3.13.5 required')
    if a.historical:
        from packaging.requirements import Requirement
        for line in (v4/'requirements-historical.lock.txt').read_text().splitlines():
            req=Requirement(line)
            if (req.marker is None or req.marker.evaluate()) and not req.specifier.contains(md.version(req.name)):raise SystemExit('Historical lock mismatch: '+line)
    checks=json.loads((ROOT/'review-input-hashes.json').read_text());bad=[n for n,h in checks.items() if not (ROOT/n).is_file() or digest(ROOT/n)!=h]
    if bad:raise SystemExit('Missing/mismatched research inputs; see V4_FINAL_REVIEW.md: '+', '.join(bad[:10]))
    out.mkdir(parents=True,exist_ok=False)
    run(Path('reproduce_review.py'),'--output',out/'v3');run(Path('Review_V4/challenger.py'),'--out',out/'challenger.json');run(Path('Review_V4/JD/evaluate_jd.py'),jd,'--out',out/'jd.json')
    comparison={n:{'reproduced_sha256':digest(out/n),'reference_sha256':digest(v4/ref),'exact_match':digest(out/n)==digest(v4/ref)} for n,ref in [('challenger.json','evidence/challenger.json'),('jd.json','JD/result.json')]}
    if a.historical:
        hist=out/'historical';hist.mkdir();old=ROOT/'Research/Validation_Archive/Current_Validation_2026_11_07'
        for script,new,ref,rows,apkey,auckey in [('benchmark_candidates.py','broad.json','BROAD_ALGORITHM_BENCHMARK.json','selection_results','january_ap','january_roc_auc'),('benchmark_extended.py','expanded.json','EXPANDED_BENCHMARK_REPORT.json','results','selection_ap','selection_auc'),('champion_diagnostics.py','champion.json','CHAMPION_TEMPORAL_DIAGNOSTICS.json',None,None,None)]:
            run(Path('AEGIS_App')/script,'--olist-dir',olist,'--output',hist/new)
            fresh=json.loads((hist/new).read_text());archive=json.loads((old/ref).read_text());
            if rows:
                f={v['algorithm']:v for v in fresh[rows]};r={v['algorithm']:v for v in archive[rows]}; comparison[new]={'configurations':len(f),'same_configurations':set(f)==set(r),'matching_ap_auc_1e-6':sum(k in f and f[k].get('status')==r[k].get('status')=='OK' and abs(f[k][apkey]-r[k][apkey])<=1e-6 and abs(f[k][auckey]-r[k][auckey])<=1e-6 for k in r),'reference_count':len(r),'note':'Timings deliberately excluded; version changes may alter metrics.'}
            else:comparison[new]={'report_generated':True,'exact_bytes':digest(hist/new)==digest(old/ref)}
    (out/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n');print(json.dumps(comparison,indent=2));
    if not all(comparison[n]['exact_match'] for n in ('challenger.json','jd.json')):raise SystemExit('Evidence differs: inspect comparison.json; do not claim exact reproduction.')
if __name__=='__main__':main()
