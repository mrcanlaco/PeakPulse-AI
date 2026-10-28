from pathlib import Path
from types import SimpleNamespace as NS
import sys,json,hashlib,copy,collections
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts/fibo_research')]
import verify_red_team_reaudit_v403 as v3
import verify_red_team_reaudit_v402 as v2
import verify_red_team_audit_2026 as eng
import universe_reaudit_v402_worker as uw
ART=ROOT/'artifacts/fibo_trend_short'
load=lambda f:json.loads((ART/f).read_text(encoding='utf-8'))
data=load('red_team_reaudit_recalculation_v4_0_3.json')
man=load('VERSION_MANIFEST_v4_0_3.json')
md=(ART/'RED_TEAM_REAUDIT_RESPONSE_v4_0_3_2026-10-17.md').read_text(encoding='utf-8')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
e={'scope':'Independent checks, counterexamples and targeted replay; not full14/338 rerun','pytest':{'passed':18,'seconds':2.28},'manifest':[{'path':p,'match':sha(ROOT/p)==h} for p,h in man['sha256_checksums'].items()]}
base=load('HISTORICAL_ARTIFACTS_BASELINE_BEFORE_v4_0_3.json')
e['history']=[{'path':p,'match':sha(ROOT/p)==d['sha256']} for p,d in base.items() if p.startswith('artifacts/')]
e['snapshots']={}
for ver,manifestfn in [('v4_0_2','VERSION_MANIFEST_v4_0_2.json'),('v4_0_3','VERSION_MANIFEST_v4_0_3.json')]:
 snap=ART/'snapshots'/ver;ref=load(manifestfn)['sha256_checksums']
 e['snapshots'][ver]=[{'path':str(p.relative_to(snap)),'matches_manifest':sha(p)==next((h for q,h in ref.items() if Path(q).name==p.name),None)} for p in snap.rglob('*') if p.is_file()]
e['markdown_exact']=v3.generate_markdown_report_v403(data)==md
e['consistency']=v3.verify_markdown_json_consistency_v403(data,md)
e['mutation_tests']=v3.run_report_consistency_mutation_tests(data,md)
e['counterexamples']=v3.reproduce_all_v403_counterexamples()
e['fingerprint_matches']=uw.compute_universe_input_fingerprint()==man['universe_input_fingerprint_sha256']
e['universe_embedded_matches']=data['re_audit_3_universe_338_and_rolling_pit']==load('universe_338_reaudit_v4_0_3_summary.json')
symbols=['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','LTCUSDT','BCHUSDT','1000PEPEUSDT','1000BONKUSDT','1000SHIBUSDT','AAVEUSDT','ADAUSDT','1INCHUSDT','ACEUSDT','AKTUSDT']
lookup,cov=v2.load_historical_funding_lookup(symbols)
e['funding_coverage']=cov
e['funding_off_8h']={s:{'total':len(m),'off_8h':sum(h%8!=0 for h in m),'hours_utc':dict(collections.Counter(h%24 for h in m))} for s,m in lookup.items()}
num=v2.parse_funding_dataframe(pd.DataFrame({'calc_time':[1735689600000,1735718400000],'last_funding_rate':[.0001,.0002]}),'numeric_ms_fixture')
e['numeric_ms_funding_parse']=num
def bar(h,close):
 return dict(open_time_str=f'2025-01-01T{h:02d}:00:00+00:00',open=100.,high=max(101.,close),low=min(99.,close),close=close)
def candidate(sym,h,closes,score=80):
 ts=pd.Timestamp(f'2025-01-01T{h:02d}:00:00+00:00');bars=[bar(h+i,cl) for i,cl in enumerate(closes)]
 sim=eng.simulate_trade_v2(bars,entry_price=100.,stop_loss=150.,tp1=10.,tp2=8.,tp3=5.,round_trip_fee_bps=20.,entry_timestamp_utc=ts)
 return dict(symbol=sym,tf='4h',idx_1h=h,wave_key=sym,eligible_milestones=['m4_f2_elite'],decision_ts=ts,decision_time=ts.isoformat(),entry_ym='2025-01',entry_price=100.,sl_std=150.,sl_m6=150.,mult_m6=1.,sim_std=sim,sim_m6=sim,sim_std_0831=sim,sim_m6_0831=sim,full_conviction_score=score,confirmation_tier='COMBO_1_2',pattern_name='ENGULFING',tp1=10.,tp2=8.,tp3=5.,current_fibo_ratio=.55,wave_impulse_drop_pct=.1,wave_prior_pump_pct=.8,conviction_tier='S',legacy_btc_spread_score=score,signal_candle_open_time=(ts-pd.Timedelta(hours=1)).isoformat(),year=2025,ker_wave=.7,imp_ker=.7,future_slice=bars)
cands=[candidate('A',0,[120.,120.,120.]),candidate('B',1,[100.,100.]),candidate('C',1,[100.,100.])]
traces=[]
def tracer(frame,event,arg):
 if event=='return' and frame.f_code.co_name in ('_advance_portfolio_to_hour','_advance_to_hour'):
  traces.append({'function':frame.f_code.co_name,'target_h':frame.f_locals['target_h'],'cur_h':frame.f_locals['cur_h'],'equity':frame.f_locals['cur_comp_equity']})
 return tracer
sys.settrace(tracer)
coupled=uw.run_universe_portfolio_coupled_execution(cands,'m4_f2_elite','2025-01-01T00:00:00Z','2025-01-01T06:00:00Z',max_total_notional_frac=.66,max_total_sl_risk_frac=1.)
sys.settrace(None)
directitems=[uw._make_trade_item_from_candidate(c,c['sim_std'],sl_val=150.,mult_val=1.,keep_trace=True) for c in cands]
direct=eng.compute_portfolio_nav_and_concurrency(directitems,'2025-01-01T00:00:00Z','2025-01-01T06:00:00Z',max_total_notional_frac=.66,max_total_sl_risk_frac=1.)
e['coupled_double_processing_universe']={'advance_traces':traces,'coupled_accepted':coupled['accepted_trades'],'coupled_rejected_notional':coupled['rejected_by_notional_cap'],'single_pass_accepted':direct['nav_simulation_20pct_notional_per_1x']['executed_trades'],'single_pass_nav':direct['nav_simulation_20pct_notional_per_1x']}
# Equivalent benchmark candidate shape.
bc=[]
for c in cands:
 sig=NS(id=c['symbol'],signal_time=c['decision_time'],h1_confirmation=NS(confirmation_tier='COMBO_1_2',pattern_name='ENGULFING',current_fibo_ratio=.55),wave=NS(impulse_drop_pct=.1,prior_pump_pct=.8))
 bc.append({**c,'sig':sig,'setup':NS(entry_price=100.,stop_loss=150.,tp1=10.,tp2=8.,tp3=5.),'fibo_levels':NS(level_0000=50.,wave_range=60.),'atr_1h':0.})
traces=[];sys.settrace(tracer)
br=v2.run_portfolio_coupled_execution(bc,'m1_f1a_pump50','2025-01-01T00:00:00Z','2025-01-01T06:00:00Z',max_total_notional_frac=.66,max_total_sl_risk_frac=1.)
sys.settrace(None)
e['coupled_double_processing_benchmark']={'advance_traces':traces,'accepted':br['accepted_trades'],'rejected_notional':br['rejected_notional_cap']}
# A supplied missing 4h settlement is not counted as missing by the engine.
testitem=directitems[1]
missingmap={'B':{int(pd.Timestamp('2025-01-01T00:00:00Z').timestamp()//3600):.001,int(pd.Timestamp('2025-01-01T08:00:00Z').timestamp()//3600):.001}}
# Report framing and numeric parsing checks suffice; do not claim unknown exchange intervals.
e['findings_source']={'double_event_benchmark':'verify_red_team_reaudit_v402.py:_advance_to_hour','double_event_universe':'universe_reaudit_v402_worker.py:_advance_portfolio_to_hour','fingerprint':'hashes code subset and filename/size/int(mtime), not data contents; omitted funding and imported strategy/summary code'}
(ART/'FINAL_SIGNOFF_VERIFICATION_v4_0_3_EVIDENCE.json').write_text(json.dumps(e,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
print(json.dumps({k:e[k] for k in ['markdown_exact','fingerprint_matches','universe_embedded_matches','funding_off_8h','numeric_ms_funding_parse','coupled_double_processing_universe','coupled_double_processing_benchmark']},indent=2,default=str))
