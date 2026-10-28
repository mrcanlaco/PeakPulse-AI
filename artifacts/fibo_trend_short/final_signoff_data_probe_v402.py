from pathlib import Path
import sys,json
import pandas as pd
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts/fibo_research')]
from study_coin_universe_selection_2026 import STABLE_OR_INDEX_EXCLUDE
import verify_red_team_reaudit_v402 as r
ART=ROOT/'artifacts/fibo_trend_short'
out=ART/'FINAL_SIGNOFF_VERIFICATION_v4_0_2_EVIDENCE.json'
e=json.loads(out.read_text(encoding='utf-8'))
symbols=['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','LTCUSDT','BCHUSDT','1000PEPEUSDT','1000BONKUSDT','1000SHIBUSDT','AAVEUSDT','ADAUSDT','1INCHUSDT','ACEUSDT','AKTUSDT']
fund=[]
for sym in symbols:
 for dr in [r.SHARED_FUNDING_DIR,r.DATA_LAKE_FUNDING_DIR]:
  p=dr/f'{sym}_funding.parquet'
  if not p.exists():continue
  d=pd.read_parquet(p)
  if isinstance(d.index,pd.DatetimeIndex): ts=d.index
  else:
   col='funding_time' if 'funding_time' in d else 'calc_time'
   ts=pd.to_datetime(d[col],utc=True,unit='ms') if pd.api.types.is_numeric_dtype(d[col]) else pd.to_datetime(d[col],utc=True)
  fund.append({'symbol':sym,'path':str(p),'rows':len(d),'min_time':str(ts.min()),'max_time':str(ts.max()),'columns':list(d.columns)})
e['actual_funding_files']={'symbols_with_files':len(set(x['symbol'] for x in fund)),'files':fund,'loader_actual_output':r.load_historical_funding_lookup(symbols)[1]}
coverage=[]
for p in sorted(Path('C:/Quant-trading/data_lake/klines/5m').glob('*.parquet')):
 if not p.stem.endswith('USDT') or p.stem in STABLE_OR_INDEX_EXCLUDE: continue
 f=pq.ParquetFile(p);ci=f.schema.names.index('open_time')
 st=[f.metadata.row_group(i).column(ci).statistics for i in range(f.num_row_groups)]
 if all(s and s.has_min_max for s in st):
  lo=min(s.min for s in st); hi=max(s.max for s in st)
 else:
  times=f.read(columns=['open_time']).column(0).to_pandas();lo=times.min();hi=times.max()
 coverage.append({'symbol':p.stem,'rows':f.metadata.num_rows,'min_time':str(lo),'max_time':str(hi)})
e['raw_5m_coverage']={'symbols':len(coverage),'last_open_2026_08_31_count':sum(x['max_time'].startswith('2026-08-31') for x in coverage),'max_time_distribution':dict(pd.Series([x['max_time'] for x in coverage]).value_counts().astype(int).items()),'details':coverage}
out.write_text(json.dumps(e,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'funding_symbols':e['actual_funding_files']['symbols_with_files'],'funding_files':len(fund),'loader':e['actual_funding_files']['loader_actual_output'],'raw_5m_coverage':{k:v for k,v in e['raw_5m_coverage'].items() if k!='details'}},indent=2,default=str))
