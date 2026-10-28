import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from residual_momentum_signals import enrich,generate,rank_state
from residual_momentum_oracle import feature_oracle,event_oracle


def fixture(n=2):
    rng=np.random.default_rng(381)
    idx=pd.date_range('2025-08-01T00:00Z',periods=1105,freq='1h')
    br=rng.normal(.0002,.004,len(idx))
    def frame(r):
        close=100*np.exp(np.cumsum(r))
        return pd.DataFrame(dict(open=close*.999,high=close*1.01,low=close*.99,close=close,quote_volume=120000.),index=idx)
    return {'BTCUSDT':frame(br),**{f'C{i:02d}':frame((.4+i*.06)*br+rng.normal((i-n/2)*.00008,.003,len(idx))) for i in range(n)}}


def test_direct_ols_and_fixed_beta_residual_variance():
    frames=fixture();actual=enrich(frames);oracle=feature_oracle(frames)
    for coin,f in actual.items():
        expected=oracle[coin].reindex(f.index)
        assert f.eligible.equals(expected.eligible.rename('eligible'))
        for col in ['beta','atr','raw24','raw72','raw168','risk_adjusted24','risk_adjusted72','risk_adjusted168']:
            np.testing.assert_allclose(f[col],expected[col],atol=1e-10,rtol=1e-9,equal_nan=True)


@pytest.mark.parametrize('coin',['BTCUSDT','C00'])
@pytest.mark.parametrize('damage',['missing','nan','zero'])
def test_incomplete_beta_window_is_never_filled(coin,damage):
    frames=fixture();t=frames[coin].index[-80];end=frames[coin].index[-1]
    if damage=='missing':frames[coin]=frames[coin].drop(t)
    else:frames[coin].loc[t,'close']=np.nan if damage=='nan' else 0
    f=enrich(frames)['C00'];assert not f.loc[end,'eligible']


def test_zero_btc_variance_blocks_signals():
    frames=fixture();frames['BTCUSDT']['close']=100
    assert not enrich(frames)['C00'].eligible.any()


def test_exact_beta_copy_has_no_residual_risk_and_no_signal():
    frames=fixture();frames['C00']=frames['BTCUSDT'].copy()
    f=enrich(frames)['C00'];assert not f.eligible.any()


def test_prefix_and_future_mutation_do_not_change_past():
    frames=fixture();t=frames['BTCUSDT'].index[941];full=enrich(frames)
    prefix=enrich({c:f.loc[:t] for c,f in frames.items()})
    changed={c:f.copy() for c,f in frames.items()}
    for f in changed.values():f.loc[f.index>t,'close']*=1.4
    mutation=enrich(changed)
    for c in full:
        pd.testing.assert_frame_equal(prefix[c].loc[:t],full[c].loc[:t])
        pd.testing.assert_frame_equal(mutation[c].loc[:t],full[c].loc[:t])


def test_rank_and_direction_match_independent_peer_count():
    frames=fixture(26);f=enrich(frames);oracle=feature_oracle(frames)
    actual=generate(f);expected=event_oracle(oracle)
    assert sum(map(len,actual.values()))>0
    for key,events in actual.items():
        assert [dict(e,atr=round(e['atr'],9)) for e in events]==[dict(e,atr=round(e['atr'],9)) for e in expected[key]]
    assert {e['side'] for es in actual.values() for e in es}=={'LONG','SHORT'}


def test_pool_threshold_and_ties():
    t=pd.DatetimeIndex(['2026-01-01T00:00Z'])
    fields=dict(eligible=True,ready=True,atr=1.)
    for h in [24,72,168]:fields[f'raw{h}']=fields[f'risk_adjusted{h}']=1.
    f={f'C{i}':pd.DataFrame(fields,index=t) for i in range(24)}
    assert all(not es for es in generate(f).values())
    for i,frame in enumerate(f.values()):
        for h in [24,72,168]:frame[f'raw{h}']=frame[f'risk_adjusted{h}']=i-12
    assert sum(map(len,generate(f).values()))>0
    f['C0']['eligible']=False
    assert all(not es for es in generate(f).values())
