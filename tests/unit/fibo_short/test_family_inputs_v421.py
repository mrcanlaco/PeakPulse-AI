from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/fibo_research'))
import research_family_v421 as v


def frame(times, marks=None):
    return pd.DataFrame({'funding_ts_ms': times, 'funding_rate': [.001] * len(times),
        'mark_price': marks or [100.] * len(times), 'price_source': ['funding_api_settlement_mark'] * len(times),
        'mark_reference_ts_ms': times})


def test_identical_overlap_deduplicates_and_conflict_rejects():
    t = v.f.START_MS
    merged = v.merge_funding([frame([t, t + 3600000]), frame([t + 3600000, t + 7200000])])
    assert len(merged['events']) == 3
    with pytest.raises(ValueError):
        v.merge_funding([frame([t]), frame([t], [99.])])


def test_inactive_gap_is_allowed_only_outside_held_intervals():
    t = v.f.START_MS
    h = 3600000
    pack = v.merge_funding([frame([t, t + 8*h, t + 24*30*h, t + (24*30 + 8)*h])])
    v.coverage(pack, t + h, t + 7*h)
    v.coverage(pack, t + (24*30 + 1)*h, t + (24*30 + 7)*h)
    with pytest.raises(AssertionError):
        v.coverage(pack, t + 7*h, t + (24*30 + 1)*h)


def test_post2025_funding_rejected():
    with pytest.raises(AssertionError):
        v.merge_funding([frame([v.f.LIMIT_MS])])


def test_candidate_requires_unique_contract_phase():
    c = {'entry_ts': int(v.r.utc('2022-01-01').timestamp())}
    old = {'phase': 'old', 'first_open': '2021-01-01', 'last_open': '2022-02-01'}
    new = {'phase': 'new', 'first_open': '2022-03-01', 'last_open': '2025-12-31'}
    assert v.phase_for(c, [old, new])['phase'] == 'old'
    with pytest.raises(ValueError):
        v.phase_for(c, [old, dict(old)])


def test_zero_volume_forced_exit_is_flagged_without_changing_candidate():
    start = int(v.r.utc('2022-01-01').timestamp())
    prices = pd.DataFrame({'open': [100.,100.], 'high': [101.,101.], 'low': [99.,99.],
                           'close': [100.,100.], 'volume': [1.,0.]},
                          index=pd.to_datetime([start,start+300],unit='s',utc=True))
    path = v.r.simulate_path([(start,100.,101.,99.,100.),(start+300,100.,101.,99.,100.)],100.,110.,[90.,80.,70.])
    c = {'symbol': 'TEST', 'entry_ts': start, 'entry': 100., 'paths': {'ladder': path}}
    q = v.audit_path(c,path,prices,[],1/6)
    assert q['zero_volume_exit_groups'] == [start+600] and v.issues(q)
    assert c['paths']['ladder'] is path and path['exit_ts'] == start+600
