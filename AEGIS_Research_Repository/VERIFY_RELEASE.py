"""Verify unchanged release bytes; no writes, training, or procurement."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))
bad = []
for name, digest in manifest['sha256'].items():
    path = root / name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        bad.append(name)
print(f"AEGIS release integrity: {len(manifest['sha256'])-len(bad)}/{len(manifest['sha256'])} checked files matched")
if bad:
    print('Missing or changed files:', *bad[:30], sep='\n')
sys.exit(bool(bad))
