"""Export the existing AEGIS historical benchmark feature frame, not a new training run.
Usage: python export_historical_features.py --app-dir PATH --olist-dir PATH --output-dir PATH
Source: Brazilian E-Commerce Public Dataset by Olist, CC BY-NC-SA 4.0.
"""
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

a=argparse.ArgumentParser();a.add_argument('--app-dir',type=Path,required=True);a.add_argument('--olist-dir',type=Path,required=True);a.add_argument('--output-dir',type=Path,required=True);args=a.parse_args()
sys.path.insert(0,str(args.app_dir.resolve()))
from historical_challenger import load_rows,feature_frame,SPLITS

df, hashes=load_rows(args.olist_dir)
features=feature_frame(df,'extended_checkout_unattested').astype(np.float32)
parts=[]; counts={}
for name,(start,end) in SPLITS.items():
    mask=(df.order_purchase_timestamp>=start)&(df.order_purchase_timestamp<end)&df.label_mature
    part=features.loc[mask].copy();part.insert(0,'label_late',df.loc[mask,'label_late'].to_numpy(dtype=np.int8));part.insert(0,'partition',name)
    counts[name]={'rows':len(part),'late_count':int(part.label_late.sum())};parts.append(part)
clean=pd.concat(parts,ignore_index=True);args.output_dir.mkdir(parents=True,exist_ok=True)
output=args.output_dir/'AEGIS_Olist_Historical_Features.csv.gz';clean.to_csv(output,index=False,compression={'method':'gzip','mtime':0})
manifest={'source':'Brazilian E-Commerce Public Dataset by Olist','license':'CC BY-NC-SA 4.0','dataset_url':'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce','source_sha256':hashes,'feature_names':list(features.columns),'partitions':counts,'total_rows':len(clean),'columns':len(clean.columns),'export_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'python':sys.version.split()[0],'numpy':np.__version__,'pandas':pd.__version__,'status':'historical benchmark feature export, no new fitting; feature availability unattested; no pristine holdout or deployment approval'}
(args.output_dir/'FEATURE_EXPORT_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
