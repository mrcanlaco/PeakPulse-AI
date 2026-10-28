import sys,json,copy,time
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts/fibo_research')]
sys.stdout.reconfigure(encoding='utf-8')
import verify_red_team_reaudit_v404 as v
ART=ROOT/'artifacts/fibo_trend_short'
start=time.time(); raws={};gaps={}
for mode in ['is','oos']:
    frames={}
    for symbol in ['ACEUSDT','BTCUSDT']:
        frames[symbol]=v.load_historical_1h_frame(symbol,start_utc='2020-01-01T00:00:00Z',end_utc='2025-12-31T23:59:59Z',strict_in_sample=True) if mode=='is' else v.load_1h_for_oos(symbol)
        delta=frames[symbol].index.to_series().diff().dt.total_seconds()/3600
        gaps[f'{mode}/{symbol}']={'gap_count_gt_1h':int((delta>1).sum()),'largest_gap_hours':float(delta.max())}
    btc={tf:v.calc_htf_features_no_bfill(v.resample_1h_to_htf(frames['BTCUSDT'],tf)) for tf in ('4h','1d')}
    raws[mode]=v.collect_candidates_and_run_modes({'ACEUSDT':frames['ACEUSDT']},btc,entry_start_ts=pd.Timestamp('2020-01-01T00:00:00Z' if mode=='is' else '2026-01-01T00:00:00Z'),entry_end_ts=pd.Timestamp('2025-12-31T23:59:59Z' if mode=='is' else '2026-12-31T23:59:59Z'),strict_prior_low_before_peak=True,no_bfill=True,swing_right_bars=2,lookback_bars=30)
out={}
for name,raw,reset in [('oos_only',raws['oos'],True),('combined_reset',raws['is']+raws['oos'],True),('combined_continuous',raws['is']+raws['oos'],False),('prefix_outside_cooldown', [x for x in raws['is'] if pd.Timestamp(x['decision_time'])<=pd.Timestamp('2025-12-15T00:00:00Z')]+raws['oos'],False)]:
    items=v.run_standalone_config(raw,'m1_f1a_pump50',reset_at_oos_boundary=reset)
    out[name]=[{'tf':x['trade'].higher_timeframe,'entry':x['trade'].entry_time,'exit':x['trade'].exit_time} for x in items if x['year']==2026]
shift=[{**x,'idx_1h':x['idx_1h']+50000} for x in raws['oos']]
out['index_shift_50000']=[{'tf':x['trade'].higher_timeframe,'entry':x['trade'].entry_time,'exit':x['trade'].exit_time} for x in v.run_standalone_config(shift,'m1_f1a_pump50')]
result={'raw_is':len(raws['is']),'raw_oos':len(raws['oos']),'counts':{k:len(x) for k,x in out.items()},'trades':out,'data_gap_checks':gaps,'elapsed_seconds':round(time.time()-start,2)}
(ART/'final_signoff_v404_ace_replay_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:val for k,val in result.items() if k!='trades'}))
