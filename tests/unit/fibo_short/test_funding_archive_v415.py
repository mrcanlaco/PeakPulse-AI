from pathlib import Path
import io,sys,zipfile
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import recover_funding_marks_v415 as f


def archive(ts,header=False,price=10):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        text=('open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_base,taker_quote,ignore\n' if header else '')
        text+=f'{ts},{price},11,9,10,0,{ts+3599999},0,3600,0,0,0\n'
        z.writestr('TESTUSDT-1h-2021-02.csv',text)
    return out.getvalue()


@pytest.mark.parametrize('header',[False,True])
def test_archive_header_and_headerless_open_only(header):
    t=int(pd.Timestamp('2021-02-01T00:00Z').timestamp()*1000)
    assert f.parse_archive(archive(t,header),'TESTUSDT','2021-02')=={t:10.}


def test_wrong_month_or_hour_rejected():
    t=int(pd.Timestamp('2021-03-01T00:00Z').timestamp()*1000)
    with pytest.raises(AssertionError):f.parse_archive(archive(t),'TESTUSDT','2021-02')
    t=int(pd.Timestamp('2021-02-01T00:00Z').timestamp()*1000)+1
    with pytest.raises(AssertionError):f.parse_archive(archive(t),'TESTUSDT','2021-02')


def test_future_archive_rejected_before_loading():
    with pytest.raises(ValueError,match='Forbidden'):f.parse_archive(b'', 'TESTUSDT','2026-01')


def test_nonpositive_mark_cannot_be_used_as_zero_funding():
    t=int(pd.Timestamp('2021-02-01T00:00Z').timestamp()*1000)
    with pytest.raises(AssertionError):f.parse_archive(archive(t,price=0),'TESTUSDT','2021-02')
