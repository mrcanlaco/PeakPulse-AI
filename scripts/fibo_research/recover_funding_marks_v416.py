"""Version-local adapter for the previously tested official archive recovery."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import research_v416 as v
import recover_funding_marks_v415 as engine
r=v.r;OUT=v.ART/'funding/archive_recovery'


def context():
    engine.v=SimpleNamespace(verify_sources=v.verify_sources,ROOT=v.ROOT,funding=v.f)
    engine.ART=v.ART;engine.OUT=OUT


def register():
    context();engine.register();p=OUT/'PROTOCOL.json';a=r.read(p)
    a['sources'][str(Path(__file__).relative_to(v.ROOT))]=r.sha(__file__)
    a['observed_missing_source']='CVCUSDT old mark OPEN unavailable from REST; official monthly archive recovery only.'
    r.save(p,a)


def run():
    context();engine.run();p=v.ART/'funding/MANIFEST.json';a=r.read(p)
    a['newly_acquired_symbols']=sum(b['mode']!='reuse_verified' for b in a['symbols'].values())
    a['archive_recovered_symbols']=sum(b['mode']=='official_archive_mark_recovery' for b in a['symbols'].values());r.save(p,a)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','run']);a=p.parse_args();{'register':register,'run':run}[a.action]()
