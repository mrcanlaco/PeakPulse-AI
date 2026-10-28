import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from cross_sectional_signals import enrich,rank_state,generate,definitions,LOOKBACKS


def prepared(n=24,equal=False,positive=False):
    idx=pd.date_range('2026-01-01',periods=2,freq='1D',tz='UTC');out={}
    for i in range(n):
        value=1 if equal else (i+1 if positive else i-(n-1)/2)
        f=pd.DataFrame(dict(ready=True,eligible=True,atr=2.),index=idx)
        for h in LOOKBACKS:f[f'raw{h}']=value;f[f'risk_adjusted{h}']=value
        out[f'C{i:02d}']=f
    return out


def test_symmetric_rank_endpoints_and_direction_swap():
    f=prepared();state,ranks=rank_state(f);out=generate(f,state,ranks)
    assert ranks['raw24'].iloc[0].min()==0 and ranks['raw24'].iloc[0].max()==1
    momentum=out['momentum_24h_raw'];reversion=out['reversion_24h_raw']
    assert len(momentum)==len(reversion)==20
    lookup={(e['symbol'],e['at']):e for e in reversion}
    for e in momentum:
        r=lookup[(e['symbol'],e['at'])]
        assert r['side']!=e['side'] and r['probability']==e['probability'] and r['event_id']!=e['event_id']
    assert len({(e['symbol'],e['at']) for e in momentum})==len(momentum)


@pytest.mark.parametrize('n,equal',[(23,False),(24,True)])
def test_insufficient_pool_or_all_ties_do_not_invent_extremes(n,equal):
    f=prepared(n,equal);state,ranks=rank_state(f)
    assert all(not es for es in generate(f,state,ranks).values())


def test_absolute_sign_is_required_and_no_forced_balancing():
    f=prepared(positive=True);state,ranks=rank_state(f);out=generate(f,state,ranks)
    assert {e['side'] for e in out['momentum_24h_raw']}=={'LONG'}
    assert {e['side'] for e in out['reversion_24h_raw']}=={'SHORT'}


def test_missing_coin_is_removed_from_rank_denominator_before_coverage_gate():
    f=prepared();f['C00']['eligible']=False;state,ranks=rank_state(f)
    assert state.coverage.iloc[0]==23 and ranks['raw24']['C00'].isna().all()
    assert all(not es for es in generate(f,state,ranks).values())


def hourly():
    idx=pd.date_range('2025-08-01T01:00Z',periods=1000,freq='1h')
    r=np.random.default_rng(11).normal(.0001,.005,len(idx));close=100*np.exp(np.cumsum(r))
    return pd.DataFrame(dict(open=close*.999,high=close*1.01,low=close*.99,close=close,quote_volume=100000.),index=idx)


def test_features_match_explicit_log_return_and_sample_volatility():
    h=hourly();f=enrich({'X':h})['X'];t=f.index[-2]
    assert f.eligible.loc[t] and (f.index.hour==0).all()
    for n in LOOKBACKS:
        prices=h.close.loc[t-pd.Timedelta(hours=n):t].to_numpy();returns=np.log(prices[1:]/prices[:-1]);raw=np.log(prices[-1]/prices[0])
        assert f.loc[t,f'raw{n}']==pytest.approx(raw)
        assert f.loc[t,f'risk_adjusted{n}']==pytest.approx(raw/(returns.std(ddof=1)*np.sqrt(n)))


def test_future_prices_do_not_change_prior_features_and_missing_hour_blocks_ready():
    h=hourly();t=h.index[719];full=enrich({'X':h})['X'];prefix=enrich({'X':h.loc[:t]})['X']
    pd.testing.assert_frame_equal(prefix.loc[:t],full.loc[:t])
    broken=h.copy();broken.loc[t,'close']=np.nan
    assert not enrich({'X':broken})['X'].loc[t,'eligible']
