"""Resolve conservative lifecycle screening without removing any candidate."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import gzip
import pickle
import pandas as pd
import evaluate_universe_v415 as base

v=base.v;r=base.r;ART=base.ART
_fingerprint=base.fingerprint


def register():
    base.verify_sources()
    if (ART/'BOUNDARY_RESOLUTION_PROTOCOL.json').exists():raise FileExistsError('Already registered')
    r.save(ART/'BOUNDARY_RESOLUTION_PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':r.sha(__file__),
        'economic_protocol_sha256':r.sha(ART/'ECONOMIC_PROTOCOL.json'),
        'rule':'The24h pre-boundary window is a screening buffer. Resolve only when the candidate exits strictly before an explicitly known official settlement, its entry is allowed by known close-only rules, and its path has no execution issue. Keep the candidate and every price unchanged. Unknown matches remain blocked.',
        'reason':'Five TLM holding paths enter the conservative pre-settlement buffer but exit hours before the official09:00 settlement. A buffer is not an exchange halt time.',
        'no_candidates_removed':True,'no_economic_outcomes_seen':not (ART/'RESULTS.json').exists()})


def resolve():
    base.verify_sources();p=r.read(ART/'BOUNDARY_RESOLUTION_PROTOCOL.json');assert p['source_sha256']==r.sha(__file__)
    audit=r.read(ART/'CANDIDATE_AUDIT.json');events=r.read(ART/'EVENTS.json')['events'];resolved=[];unknown=[]
    for a in audit['observed_lifecycle_boundary_overlaps']:
        entry=pd.Timestamp(a['entry']);exit=pd.Timestamp(a['exit']);matches=[]
        for ev in events:
            if ev['symbol']!=a['symbol']:continue
            settle=pd.Timestamp(ev['settlement_at']);known=pd.Timestamp(ev['known_from_utc'])
            if known<=entry<exit<settle and (settle-exit)<=pd.Timedelta(days=1) and v.allowed_entry({'symbol':a['symbol'],'entry_ts':int(entry.timestamp())},[ev]):matches.append(ev)
        if len(matches)==1:resolved.append({**a,'official_settlement_at':matches[0]['settlement_at'],'source_url':matches[0]['source_url'],'resolution':'closed_before_official_settlement_candidate_retained'})
        else:unknown.append(a)
    r.save(ART/'BOUNDARY_RESOLUTION.json',{'resolved':resolved,'unknown':unknown,'all_screened_records_resolved':not unknown,
        'primary_records_resolved':sum(a['primary'] for a in resolved),'audit_sha256':r.sha(ART/'CANDIDATE_AUDIT.json'),
        'protocol_sha256':r.sha(ART/'BOUNDARY_RESOLUTION_PROTOCOL.json'),'candidates_removed':0})
    print({'resolved':len(resolved),'unknown':len(unknown)},flush=True)


def verify_sources():
    base.verify_sources();p=r.read(ART/'BOUNDARY_RESOLUTION_PROTOCOL.json');assert p['source_sha256']==r.sha(__file__)
    assert p['economic_protocol_sha256']==r.sha(ART/'ECONOMIC_PROTOCOL.json')
    a=r.read(ART/'BOUNDARY_RESOLUTION.json');assert a['protocol_sha256']==r.sha(ART/'BOUNDARY_RESOLUTION_PROTOCOL.json') and a['audit_sha256']==r.sha(ART/'CANDIDATE_AUDIT.json')
    assert a['all_screened_records_resolved'] and not a['unknown'] and a['candidates_removed']==0


def load_candidates():
    verify_sources();audit=r.read(ART/'CANDIDATE_AUDIT.json');resolution=r.read(ART/'BOUNDARY_RESOLUTION.json')
    assert audit['candidate_manifest_sha256']==r.sha(ART/'CANDIDATE_MANIFEST.json')
    assert not audit['primary_execution_issues']
    assert resolution['primary_records_resolved']==audit['primary_boundary_overlaps']
    assert not r.read(ART/'MEMBERSHIP_CORRECTION.json')['remaining_stale_member_months']
    with gzip.open(ART/'PRIMARY_CANDIDATES.pkl.gz','rb') as fh:rows=pickle.load(fh)
    assert len(rows)==audit['primary_candidates'];return rows


def fingerprint():
    return {**_fingerprint(),'boundary_resolution_sha256':r.sha(ART/'BOUNDARY_RESOLUTION.json'),'boundary_protocol_sha256':r.sha(ART/'BOUNDARY_RESOLUTION_PROTOCOL.json')}


def evaluate():
    verify_sources();base.load_candidates=load_candidates;base.fingerprint=fingerprint;base.evaluate()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','resolve','evaluate']);a=p.parse_args()
    {'register':register,'resolve':resolve,'evaluate':evaluate}[a.action]()
