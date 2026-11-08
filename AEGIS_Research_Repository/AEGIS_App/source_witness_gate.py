"""AEGIS source-snapshot cryptographic integrity verifier (NOT a time machine).

Verifies a locally supplied digest manifest and, optionally, Ed25519 signature
against an independently pinned key. A signed manifest does not prove that a
feature existed at historical decision time, nor that a holdout was pristine.
No private keys are stored or created by the app.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re

HEX64=re.compile(r'^[a-f0-9]{64}$')
NAME=re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,150}$')
MAX_FILES=200
MAX_SIZE=200_000_000

def digest(path):
    hashval=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): hashval.update(chunk)
    return hashval.hexdigest()


def canonical_manifest(manifest):
    if not isinstance(manifest,dict) or set(manifest)!={'source_system','snapshot_id','claimed_recorded_at','decision_at','files'}:
        raise ValueError('Manifest contract must contain exactly source_system, snapshot_id, claimed_recorded_at, decision_at, files')
    from asof_validation import _timestamp
    for k in ('source_system','snapshot_id'):
        if not isinstance(manifest[k],str) or not manifest[k].strip() or len(manifest[k])>150:
            raise ValueError('Missing or oversized source identifier')
    claimed=_timestamp(manifest['claimed_recorded_at'])
    decision=_timestamp(manifest['decision_at'])
    if not isinstance(manifest['files'],dict) or not 1<=len(manifest['files'])<=MAX_FILES:
        raise ValueError('Files digest registry is empty or too large')
    for name,hexdigest in manifest['files'].items():
        if not isinstance(name,str) or not NAME.fullmatch(name) or name in ('.','..'):
            raise ValueError('Flat, safe source filenames are required')
        if not isinstance(hexdigest,str) or not HEX64.fullmatch(hexdigest):
            raise ValueError('Expected 64-digit lowercase SHA-256 digest')
    return json.dumps(manifest,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8'),claimed<=decision


def verify_snapshot(source_dir,envelope,trusted_pem=None):
    if not isinstance(envelope,dict) or set(envelope)-{'manifest','signature_base64'}:
        raise ValueError('Unexpected attestation envelope fields')
    raw,clock_claim_valid=canonical_manifest(envelope['manifest'])
    root=Path(source_dir).resolve(strict=True)
    if not root.is_dir():raise ValueError('Source directory must exist')
    files=envelope['manifest']['files']
    issues=[]
    for name,expected in sorted(files.items()):
        target=root/name
        if target.is_symlink() or not target.is_file():issues.append(f'{name}:MISSING_OR_SYMLINK');continue
        if target.stat().st_size>MAX_SIZE:issues.append(f'{name}:TOO_LARGE');continue
        if digest(target)!=expected:issues.append(f'{name}:DIGEST_MISMATCH')
    if not clock_claim_valid:issues.append('CLAIMED_SOURCE_RECORD_AFTER_DECISION')
    signed=False
    if trusted_pem is not None:
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            public=serialization.load_pem_public_key(Path(trusted_pem).read_bytes())
            if not isinstance(public,Ed25519PublicKey):raise ValueError('An Ed25519 public key is required')
            signature=base64.b64decode(envelope['signature_base64'],validate=True)
            public.verify(signature,raw)
            signed=True
        except (KeyError,ValueError,TypeError) as exc:
            issues.append('SIGNATURE_MISSING_OR_INVALID:'+type(exc).__name__)
        except Exception as exc:
            # A signature failure is always fatal to this claim, never a fallback to unsigned.
            issues.append('SIGNATURE_VERIFICATION_FAILED:'+type(exc).__name__)
    elif envelope.get('signature_base64'):
        issues.append('SIGNATURE_PRESENT_BUT_NO_INDEPENDENT_TRUST_KEY')
    return {'product':'AEGIS','study':'SOURCE_SNAPSHOT_INTEGRITY_AND_WITNESS_GATE',
            'status':('BLOCKED_INTEGRITY_FAILURE' if issues else
                      'PINNED_SIGNER_AND_DIGEST_MATCH_SOURCE_TIME_UNATTESTED' if signed else
                      'LOCAL_HASH_MATCH_SOURCE_TIME_UNATTESTED'),
            'file_count':len(files),'file_checks_pass':len(issues)==0,
            'cryptographic_signature_verified_against_pinned_key':signed,
            'claimed_time_before_decision':clock_claim_valid,
            'source_event_time_independently_attested':False,
            'source_system_completeness_independently_attested':False,
            'historical_feature_availability_certified':False,
            'pristine_future_holdout_certified':False,
            'issues':issues,'automatic_business_action':'DISABLED',
            'interpretation':'Local hash/signature validation verifies snapshot bytes and potentially signer ownership. It cannot establish trusted contemporaneous ingestion timestamps, source completeness, uncontaminated future holdouts, or procurement approval.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir',required=True,type=Path)
    p.add_argument('--envelope',required=True,type=Path)
    p.add_argument('--trusted-ed25519-public-key',type=Path)
    p.add_argument('--report',required=True,type=Path)
    args=p.parse_args()
    envelope=json.loads(args.envelope.read_text(encoding='utf-8'))
    report=verify_snapshot(args.source_dir,envelope,args.trusted_ed25519_public_key)
    with args.report.open('x',encoding='utf-8') as file:json.dump(report,file,indent=2)
    print(report['status'])
    return 2 if report['status'].startswith('BLOCKED') else 0
if __name__=='__main__':raise SystemExit(main())
