from pathlib import Path
import sys, json, hashlib, copy
from types import SimpleNamespace
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts/fibo_research')]
import verify_red_team_reaudit_v402 as report
import verify_red_team_audit_2026 as engine
from dao_vang.fibo_short.detector import compute_orthogonal_conviction_score
ART=ROOT/'artifacts/fibo_trend_short'
payload=json.loads((ART/'red_team_reaudit_recalculation_v4_0_2.json').read_text(encoding='utf-8'))
manifest=json.loads((ART/'VERSION_MANIFEST_v4_0_2.json').read_text(encoding='utf-8'))
md=(ART/'RED_TEAM_REAUDIT_RESPONSE_v4_0_2_2026-10-16.md').read_text(encoding='utf-8')
evidence={'scope':'Independent verification; original source/artifacts unchanged; no full 338-symbol rerun claimed.'}
evidence['manifest']=[{'path':p,'matches':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha} for p,sha in manifest['sha256_checksums'].items()]
evidence['markdown_regenerated_exact_match']=report.generate_markdown_report_v402(payload)==md
evidence['universe_embedded_equals_separate']=payload['re_audit_3_universe_338_and_rolling_pit']==json.loads((ART/'universe_338_reaudit_v4_0_2_summary.json').read_text(encoding='utf-8'))
evidence['original_consistency_check']=report.verify_markdown_json_consistency(payload,md)
corrupt=md.replace('+37.08%', '+999.99%').replace('10.41%', '99.99%')
evidence['corrupted_rolling_nav_check']={'modified':corrupt!=md,'all_passed':report.verify_markdown_json_consistency(payload,corrupt)['all_passed'],'mutation':'Rolling OOS NAV +37.08 -> +999.99; DD10.41 ->99.99'}
evidence['provided_counterexamples']=report.reproduce_rt2_counterexamples()
def item(symbol,entry,bars,mult=1.,sl=150.):
    t=SimpleNamespace(symbol=symbol,entry_time=entry,entry_price=100.,stop_loss=sl,tp1=10.,tp2=8.,tp3=5.,hold_hours=len(bars))
    return {'trade':t,'future_slice':bars,'pos_mult':mult}
def bar(open_hour,close=100.):
    return {'open_time_str':f'2025-01-01T{open_hour:02d}:00:00+00:00','open':100.,'high':max(101.,close),'low':min(99.,close),'close':close}
def nav(items,end='2025-01-01T12:00:00+00:00',**kw):
    return engine.compute_portfolio_nav_and_concurrency(items,'2025-01-01T00:00:00+00:00',end,round_trip_fee_bps=0.,**kw)
# No settlement at 01:00-03:00 but synthetic stress is charged anyway.
a=item('A','2025-01-01T01:00:00+00:00',[bar(1),bar(2)])
evidence['funding_no_settlement']=nav([a],funding_bps_per_8h=1.)
# Cap uses number of bars instead of actual trace times: a gap must not free an open slot.
a=item('A','2025-01-01T00:00:00+00:00',[bar(0),bar(3)])
b=item('B','2025-01-01T02:00:00+00:00',[bar(2)])
evidence['gap_releases_slot_early']=nav([a,b],max_concurrent_cap=1)
# Dynamic NAV falls to84 before fifth position; static fractions still permit1.0x.
four=[item(str(i),'2025-01-01T00:00:00+00:00',[bar(0,120),bar(1,120)]) for i in range(4)]
fifth=item('E','2025-01-01T01:00:00+00:00',[bar(1)])
evidence['notional_cap_current_equity']={'result':nav(four+[fifth],max_total_notional_frac=1.,max_concurrent_cap=5),'equity_at_fifth_entry':84.,'existing_entry_notional_plus_new_over_equity':(80+16.8)/84,'current_mark_notional_plus_new_over_equity':(96+16.8)/84}
canonical=compute_orthogonal_conviction_score(prior_pump_pct=80.,impulse_drop_pct=7.,fibo_retrace_ratio=.55,wave_ker=.5,impulse_ker=.6,peak_ewmac_16_64=-1.,cur_accel_4_16=-1.2,confirmation_tier='COMBO_1_2',pullback_vol_ratio=1.,h1_body_ratio=.5)
evidence['score_counterexample']={'canonical':canonical,'research_score':11+14+10+20+5+5+12+8,'research_multiplier':1.5,'assumptions':'BTC ewmac<=.5; idiosyncratic spread>=60; pump80; waveKER.5; impulseKER.6/drop7; fibo.55; peakEWMAC-1; accel-1.2; combo; pullbackVolume1; body.5'}
# Funding loader with a real temporary valid parquet: broad except currently hides an API error.
tmp=ART/'_final_signoff_funding_fixture'
tmp.mkdir(exist_ok=True)
fp=tmp/'SYNTHUSDT_funding.parquet'
pd.DataFrame({'funding_time':pd.to_datetime(['2025-01-01T08:00:00Z']),'funding_rate':[.0001]}).to_parquet(fp)
old_shared,old_lake=report.SHARED_FUNDING_DIR,report.DATA_LAKE_FUNDING_DIR
report.SHARED_FUNDING_DIR=tmp; report.DATA_LAKE_FUNDING_DIR=tmp
lookup,coverage=report.load_historical_funding_lookup(['SYNTHUSDT'])
evidence['valid_funding_parquet_load']={'rows_written':1,'lookup':lookup,'coverage':coverage}
report.SHARED_FUNDING_DIR=old_shared;report.DATA_LAKE_FUNDING_DIR=old_lake
fp.unlink();tmp.rmdir()
out=ART/'FINAL_SIGNOFF_VERIFICATION_v4_0_2_EVIDENCE.json'
out.write_text(json.dumps(evidence,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
print(json.dumps(evidence,indent=2,ensure_ascii=False,default=str))
