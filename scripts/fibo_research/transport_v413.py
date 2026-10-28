"""Versioned transport-only amendment: reuse one HTTP session per download thread."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import threading
from urllib.parse import urlparse
import requests
import universe_audit_v413 as v
import sample_archives_v413 as samples
import recover_universe_gaps_v413 as recovery

r=v.r;ART=v.ART


def freeze():
    v.verify_sources();recovery.verify_sources()
    p=ART/'TRANSPORT_AMENDMENT.json'
    if p.exists():raise FileExistsError('Transport amendment already registered')
    paths=[f for base in (ART/'official_samples',ART/'recovery/raw') for f in base.rglob('*') if f.is_file()]
    r.save(p,{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'reason':'Read-only probe measured first fresh connection30.44s versus subsequent request0.16s on the same requests.Session. Per-request new connections slow the acquisition without adding data assurance.',
        'change':'Use a distinct persistent requests.Session per worker thread, with the same URLs, time bounds, timeouts, retries, four workers per process, checksums, parsing, selection and source hashes.',
        'preservation':'Resume verified cached downloads. Stop only the two identified acquisition processes to apply this transport change. Do not restart the completed dataset preparation or independent data verifier.',
        'self_sha256':r.sha(__file__),'main_source_manifest_sha256':r.sha(ART/'SOURCE_MANIFEST.json'),
        'recovery_source_manifest_sha256':r.sha(ART/'recovery/SOURCE_MANIFEST.json'),
        'cached_files':{str(f.relative_to(ART)):r.sha(f) for f in paths},
        'data_selection_changed':False,'strategy_rules_changed':False,'fresh_oos':False})
    print('Transport-only amendment registered; cached files protected:',len(paths),flush=True)


def run(target):
    amendment=r.read(ART/'TRANSPORT_AMENDMENT.json')
    assert amendment['self_sha256']==r.sha(__file__)
    assert amendment['main_source_manifest_sha256']==r.sha(ART/'SOURCE_MANIFEST.json')
    assert amendment['recovery_source_manifest_sha256']==r.sha(ART/'recovery/SOURCE_MANIFEST.json')
    for p,h in amendment['cached_files'].items():assert r.sha(ART/p)==h,p
    thread=threading.local()
    def persistent_get(url,**kwargs):
        parsed=urlparse(url)
        assert parsed.scheme=='https' and parsed.netloc=='data.binance.vision' and parsed.path.startswith('/data/futures/um/')
        if not hasattr(thread,'session'):thread.session=requests.Session()
        return thread.session.get(url,**kwargs)
    requests.get=persistent_get
    samples.main() if target=='samples' else recovery.run()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','samples','recovery']);args=parser.parse_args()
    freeze() if args.action=='freeze' else run(args.action)
