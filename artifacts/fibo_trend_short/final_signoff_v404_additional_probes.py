from pathlib import Path
from types import SimpleNamespace as NS
import sys,json,copy,ast
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts/fibo_research')]
sys.stdout.reconfigure(encoding='utf-8')
import verify_red_team_reaudit_v404 as v4
import verify_red_team_reaudit_v402 as v2
import verify_red_team_audit_2026 as eng
import universe_reaudit_v402_worker as uw
from dao_vang.fibo_short.backtest import FiboBacktestTrade
ART=ROOT/'artifacts/fibo_trend_short'
e=json.loads((ART/'FINAL_SIGNOFF_VERIFICATION_v4_0_4_EVIDENCE.json').read_text(encoding='utf-8'))
old=ast.parse((ART/'final_signoff_verify_v403_independent.py').read_text(encoding='utf-8'))
for n in old.body:
    if isinstance(n,ast.FunctionDef) and n.name in ('bar','candidate'):
        exec(compile(ast.Module(body=[n],type_ignores=[]),'<old_fixture>','exec'))
def bench(c):
    sig=NS(id=c['symbol']+c['wave_key'],signal_time=c['decision_time'],h1_confirmation=NS(confirmation_tier='COMBO_1_2',pattern_name='ENGULFING',current_fibo_ratio=.55),wave=NS(impulse_drop_pct=.1,prior_pump_pct=.8))
    return {**c,'sig':sig,'setup':NS(entry_price=100.,stop_loss=150.,tp1=10.,tp2=8.,tp3=5.),'fibo_levels':NS(level_0000=50.,wave_range=60.),'atr_1h':0.}
a=candidate('GAP',0,[100,100]); a['future_slice']=[bar(0,100),bar(9,100)]
a['sim_std']=eng.simulate_trade_v2(a['future_slice'],entry_price=100,stop_loss=150,tp1=10,tp2=8,tp3=5,entry_timestamp_utc=a['decision_ts'])
for k in ('sim_m6','sim_std_0831','sim_m6_0831'):a[k]=a['sim_std']
b=candidate('GAP',5,[100,100]); b['wave_key']='NEW_WAVE'
bc=[bench(c) for c in [a,b]]
bi=eng.execute_configuration(bc,'m1_f1a_pump50')
ui=uw.execute_symbol_candidates_from_raw([a,b])['independent']['m4_f2_elite']
bcpl=v2.run_portfolio_coupled_execution(bc,'m1_f1a_pump50','2025-01-01T00:00:00Z','2025-01-01T12:00:00Z',max_total_notional_frac=1.,max_total_sl_risk_frac=1.)
ucpl=uw.run_universe_portfolio_coupled_execution([a,b],'m4_f2_elite','2025-01-01T00:00:00Z','2025-01-01T12:00:00Z',max_total_notional_frac=1.,max_total_sl_risk_frac=1.)
e['gap_cooldown_real_exit']={'first_entry':a['decision_time'],'first_exit':a['sim_std']['exit_close_time'],'first_hold_hours':a['sim_std']['hold_hours'],'second_entry':b['decision_time'],'same_symbol_tf':True,'expected_accepted_if_cooldown_until_exit':1,'benchmark_independent_accepted':len(bi),'universe_independent_accepted':len(ui),'benchmark_coupled_accepted':bcpl['accepted_trades'],'universe_coupled_accepted':ucpl['accepted_trades']}
# Valid OHLC: TP1 reached; last bar stays strictly below BE stop and time-exits nearby.
bars=[dict(open_time_str='2025-01-01T00:00:00Z',open=99.,high=99.5,low=89.,close=95.),dict(open_time_str='2025-01-01T01:00:00Z',open=95.,high=99.9998,low=94.,close=99.9995)]
sim=eng.simulate_trade_v2(bars,entry_price=100.,stop_loss=110.,tp1=90.,tp2=80.,tp3=70.,entry_timestamp_utc='2025-01-01T00:00:00Z')
t=FiboBacktestTrade(trade_id='NEAR_BE',symbol='TEST',higher_timeframe='4h',confirmation_tier='COMBO_1_2',pattern_name='ENGULFING',entry_time='2025-01-01T00:00:00Z',exit_time=sim['exit_close_time'],entry_price=100.,stop_loss=110.,tp1=90.,tp2=80.,tp3=70.,exit_price=sim['exit_price'],outcome=sim['outcome'],tp1_reached=sim['tp1_hit'],tp2_reached=sim['tp2_hit'],tp3_reached=sim['tp3_hit'],gross_return_pct=sim['gross_pct'],net_return_pct=sim['net_pct'],r_multiple=sim['r_mult'],hold_hours=sim['hold_hours'],fibo_entry_ratio=.5,impulse_drop_pct=.1,terminal_outcome=sim['detailed_outcome'],ratcheted_sl_hit=sim['ratcheted_sl_hit'],time_exit_used=sim['time_exit_used'])
e['terminal_time_exit_near_stop']={'bars':bars,'sim_terminal':sim['detailed_outcome'],'sim_time_exit_used':sim['time_exit_used'],'sim_ratcheted_sl_hit':sim['ratcheted_sl_hit'],'trade_terminal':t.terminal_outcome,'trade_time_exit_used':t.time_exit_used,'trade_ratcheted_sl_hit':t.ratcheted_sl_hit,'exit_price':sim['exit_price']}
d=json.loads((ART/'red_team_reaudit_recalculation_v4_0_4.json').read_text(encoding='utf-8'));u=json.loads((ART/'universe_338_reaudit_v4_0_4_summary.json').read_text(encoding='utf-8'))
bad=copy.deepcopy(d);node=bad['re_audit_1_portfolio_accounting_and_caps']['portfolio_coupled_vs_independent_14_coins']['is_2020_2025']['m6_f4_expanded']['execution_coupled_portfolio']
before=node['executed_trade_ids'][0];node['executed_trade_ids'][0]='CORRUPTED_TRADE_ID'
md=v4.generate_markdown_report_v404(bad)
try:r=v4.verify_markdown_json_consistency_v404(bad,md,u);caught=False
except AssertionError as ex:r=str(ex);caught=True
e['trade_id_mutation_not_detected']={'original_id':before,'replacement':'CORRUPTED_TRADE_ID','caught':caught,'result':r}
unodes=[]
for tier,basket in u['by_universe_tier'].items():
 for key,v in basket.items():
  if key.startswith('portfolio_coupled_execution'):
   for milestone,z in v.items():unodes.append({'path':f'{tier}/{key}/{milestone}','has_accepted_trade_ids':'accepted_trade_ids'in z,'has_executed_trade_ids':'executed_trade_ids'in z,'declares_exact_match':z.get('trade_id_set_exact_match')})
e['universe_exported_id_coverage']={'nodes':len(unodes),'with_both_id_lists':sum(x['has_accepted_trade_ids'] and x['has_executed_trade_ids'] for x in unodes),'details':unodes}
(ART/'FINAL_SIGNOFF_VERIFICATION_v4_0_4_EVIDENCE.json').write_text(json.dumps(e,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({k:e[k] for k in ['gap_cooldown_real_exit','terminal_time_exit_near_stop','trade_id_mutation_not_detected']},ensure_ascii=False,indent=2))
print('universe ID coverage',len(unodes),sum(x['has_accepted_trade_ids'] and x['has_executed_trade_ids'] for x in unodes))
