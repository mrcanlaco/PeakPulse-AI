from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import paper_data_v1 as d


def test_public_adapter_rejects_order_and_account_routes():
    for endpoint in ('order', 'account', 'listenKey', '../v1/order'):
        with pytest.raises(ValueError, match='public market-data'):
            d.request(endpoint)


def test_future_incomplete_and_duplicate_klines_are_rejected():
    row = [0, '100', '101', '99', '100', '2', d.HOUR-1, '200']
    assert len(d.klines_frame([row], d.HOUR, 0, d.HOUR)) == 1
    with pytest.raises(ValueError, match='unclosed'):
        d.klines_frame([row], d.HOUR, 0, d.HOUR-1)
    with pytest.raises(ValueError, match='duplicate'):
        d.klines_frame([row, row], d.HOUR, 0, d.HOUR)


def test_native_ranking_matches_original_closed_hour_ranking():
    cutoff = pd.Timestamp('2025-04-01T00:00:00Z')
    idx = pd.date_range(cutoff-pd.Timedelta(days=63), cutoff-pd.Timedelta(hours=1), freq='h')
    h = pd.DataFrame({'open':100., 'high':101., 'low':99., 'close':100., 'volume':1., 'quote_volume':100.}, index=idx)
    daily = h.resample('1D').agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum', 'quote_volume':'sum'})
    four = d.history.resample_1h_to_htf(h, '4h')
    actual = d.rank_row('TESTUSDT', daily, four, int(cutoff.timestamp()*1000))
    expected = d.history.monthly_rows('TESTUSDT', h, [cutoff])['2025-04']
    assert actual == expected
    future = pd.concat([daily, daily.tail(1).set_axis([cutoff])])
    with pytest.raises(ValueError, match='Future daily'):
        d.rank_row('TESTUSDT', future, four, int(cutoff.timestamp()*1000))


def test_contract_filter_blocks_inactive_noncoin_and_known_settlement():
    good = {'symbol':'TESTUSDT','status':'TRADING','contractType':'PERPETUAL','quoteAsset':'USDT',
            'marginAsset':'USDT','underlyingType':'COIN','onboardDate':0,'deliveryDate':10000}
    rows = [good, {**good,'symbol':'OFFUSDT','status':'SETTLING'},
            {**good,'symbol':'STOCKUSDT','underlyingType':'EQUITY'},
            {**good,'symbol':'NEWUSDT','onboardDate':6000},
            {**good,'symbol':'DUEUSDT','deliveryDate':4000}]
    assert set(d.eligible_contracts({'symbols':rows},5000)) == {'TESTUSDT'}
