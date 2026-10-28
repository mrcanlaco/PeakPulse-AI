from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/fibo_research'))
import verify_lifecycle_fast_v414 as f
import verify_lifecycle_v414 as original


@pytest.mark.parametrize('unit',['ns','us','ms'])
@pytest.mark.parametrize('gap',[False,True])
def test_unit_normalization_preserves_missing_zero_and_event_boundaries(unit,gap):
    start=pd.Timestamp('2025-01-01T00:00Z');minutes=[0,10] if gap else [0,5,10]
    index=pd.DatetimeIndex([start+pd.Timedelta(minutes=t) for t in minutes]).as_unit(unit)
    frame=pd.DataFrame({'open':100.,'high':100.,'low':100.,'close':100.,'volume':[1.]+[0.]*(len(index)-1)},index=index)
    t=int(start.timestamp());trace=[(int(x.timestamp())+300,100.,1.,0. if i==len(index)-1 else 1.,110.,0.,i==len(index)-1) for i,x in enumerate(index)]
    c={'symbol':'TESTUSDT','tf':'4h','entry_ts':t,'paths':{'ladder':{'exit_ts':t+900,'exit_reason':'horizon','trace':trace}}}
    events=[{'symbol':'TESTUSDT','known_from_utc':'2024-12-31T00:00Z','settlement_at':'2025-01-01T00:10Z','entry_close_only_from':'2025-01-01T00:00Z','source_url':'https://www.binance.com/test'}]
    a=f.independent_quality(c,frame,events);b=original.independent_quality(c,frame,events)
    assert a==b and a['missing_bars_through_modelled_exit']==int(gap)
    assert a['zero_volume_exit_groups']==[t+900] and len(a['official_lifecycle_flags'])==2
