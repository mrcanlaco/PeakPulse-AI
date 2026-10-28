from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import funding_sensitivity_v415 as f


def test_adverse_short_funding_mark_changes_have_correct_sign():
    event={'mark_price':100.,'funding_rate':.001,'price_source':'official_mark_archive_open_proxy'}
    assert f.stressed_event(event,.05)['mark_price']==95.
    event['funding_rate']=-.001;assert f.stressed_event(event,.05)['mark_price']==105.
    assert event['mark_price']==100.


def test_exact_settlement_marks_and_zero_rates_remain_unchanged():
    event={'mark_price':100.,'funding_rate':-.001,'price_source':'funding_api_settlement_mark'}
    assert f.stressed_event(event,.05)==event
    event.update(price_source='official_mark_candle_open_proxy',funding_rate=0.)
    assert f.stressed_event(event,.05)==event
