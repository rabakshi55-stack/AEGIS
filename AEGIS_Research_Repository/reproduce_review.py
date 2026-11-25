"""Reproduce the V3 research review in a NEW output folder, without changing app data."""
import argparse, json, os, subprocess, sys, hashlib, platform, importlib.metadata as md
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'AEGIS_App'))
from review_v3.research import run as predictive_run
from review_v3.allocation import run as allocation_run
from paired_stress import run_experiment, export_experiment

def write(path,value):
    with path.open('x',encoding='utf-8') as f: json.dump(value,f,indent=2,allow_nan=False); f.write('\n')

def check_inputs():
    expected=dict(line.strip().split('==') for line in (ROOT/'requirements-review.lock.txt').read_text().splitlines() if line.strip())
    actual={k:md.version(k) for k in expected}
    if platform.python_version()!='3.13.5' or actual!=expected: raise SystemExit(f'Expected Python 3.13.5 and exact research lock; found {platform.python_version()}, {actual}')
    checks=json.loads((ROOT/'review-input-hashes.json').read_text())
    bad=[name for name,h in checks.items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    if bad: raise SystemExit('Missing or mismatched protected inputs: '+', '.join(bad[:20]))
    return actual

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',required=True,type=Path); a=p.parse_args(); out=a.output.resolve(); actual=check_inputs(); out.mkdir(parents=True,exist_ok=False)
    if (ROOT/'VERIFY_PACKAGE.py').exists(): subprocess.run([sys.executable,'-B',str(ROOT/'VERIFY_PACKAGE.py')],check=True)
    source=ROOT/'Research'/'Integrated_v02'; olist=ROOT/'Research'/'Public_Data'/'Olist_Raw'/'archive'
    write(out/'predictive_review.json',predictive_run(olist))
    write(out/'allocation_review.json',allocation_run(source,ROOT/'AEGIS_App'/'tests'/'fixtures'))
    result=run_experiment(source,scenarios=500,seed=191); stress_dir=out/'paired_stress'; export_experiment(result,stress_dir)
    subprocess.run([sys.executable,'-B',str(ROOT/'Review_V3/reproduce.py'),'--output',str(out/'sensitivity')],check=True)
    write(out/'review_run_manifest.json',{'python':platform.python_version(),'packages':actual,'holdout_certified':False,'operational_approval':False,'outputs':{str(f.relative_to(out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.rglob('*')) if f.is_file()}})
    print('V3 diagnostics reproduced; no untouched holdout or causal validation claimed.')
if __name__=='__main__': main()
