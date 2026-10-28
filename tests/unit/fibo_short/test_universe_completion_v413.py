import sys
from pathlib import Path
import zipfile
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import complete_universe_v413 as c


def write(path,stamp,close_delta=299999):
    ms=int(pd.Timestamp(stamp).timestamp()*1000)
    with zipfile.ZipFile(path,'w') as z:z.writestr('TEST.csv',f'{ms},100,101,99,100,1,{ms+close_delta},100,1,0,0,0\n')


def test_independent_parser_canonicalizes_ms_to_utc_ns(tmp_path):
    p=tmp_path/'TEST.zip';write(p,'2025-01-01T00:00Z')
    frame=c.archive_frame(p)
    assert frame.index.dtype.unit=='ns' and str(frame.index.tz)=='UTC' and frame.index[0]==pd.Timestamp('2025-01-01T00:00Z')
    assert frame.iloc[0].to_dict()=={'open':100.,'high':101.,'low':99.,'close':100.,'volume':1.,'quote_volume':100.}


def test_independent_parser_rejects_2026_and_wrong_close_time(tmp_path):
    p=tmp_path/'TEST.zip';write(p,'2026-01-01T00:00Z')
    with pytest.raises(AssertionError):c.archive_frame(p)
    write(p,'2025-01-01T00:00Z',close_delta=300000)
    with pytest.raises(AssertionError):c.archive_frame(p)
