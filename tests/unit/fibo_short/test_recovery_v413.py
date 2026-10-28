import io
from pathlib import Path
import sys
import zipfile
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import recover_universe_gaps_v413 as recover
import sample_archives_v413 as sample


def test_missing_dates_crosses_midnight_without_inventing_rows():
    times=pd.to_datetime(['2025-01-01T23:50Z','2025-01-02T00:10Z'])
    df=pd.DataFrame(index=times)
    assert recover.missing_dates(df)==['2025-01-01','2025-01-02']
    assert len(df)==2


def zipped(rows):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as z:z.writestr('TEST-5m-2025-01.csv',rows)
    return data.getvalue()


def test_official_csv_parsing_header_and_time_bounds():
    ts=int(pd.Timestamp('2025-01-01T00:00Z').timestamp()*1000)
    row=f'{ts},100,101,99,100,1,{ts+299999},100,1,0,0,0\n'
    frame=sample.parse(zipped(','.join(sample.CSV_COLS)+'\n'+row),'2025-01')
    assert len(frame)==1 and frame.close.iloc[0]==100
    with pytest.raises(ValueError,match='date breach'):sample.parse(zipped(row),'2024-12')


def test_post2025_archive_is_rejected():
    ts=int(pd.Timestamp('2026-01-01T00:00Z').timestamp()*1000)
    row=f'{ts},100,101,99,100,1,{ts+299999},100,1,0,0,0\n'
    with pytest.raises(ValueError,match='date breach'):sample.parse(zipped(row),'2026-01')
