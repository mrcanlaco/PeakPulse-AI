"""Batch44: choose the direction of a frozen hourly shock from a daily trend."""
import pandas as pd
from account_capital_trace import simulate
from shock_weekly_alignment import states
from shock_weekly_direction import transform,MODES
SOURCES=['weekly_control','follow','fade',*MODES]
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from capital_research_metrics import utilization
from directional_capacity_metrics import side_metrics
from monthly_account_metrics import monthly_metrics
from search_side_capacity import windows,robustness
from search_frozen_exits import BOUNDARIES,COSTS,DATA,exit_diagnostics
from search_multitimeframe_rolling import grouped_signals
from search_net_trailing import read
from search_cross_regime import select

OUT=ROOT/'artifacts/shock_weekly_direction_20260926'
PRIOR=ROOT/'artifacts/hourly_shock_20260925'
PREVIOUS=ROOT/'artifacts/shock_weekly_alignment_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=PRIOR/'signals.json'


def definitions(previous):
    assert previous['selected']==[dict(reference='n100',strategy_id='hour_n100_shock_follow_a15_hold'),dict(reference='n25',strategy_id='hour_n25_control_hold')]
    old=next(sp for sp in previous['specs'] if sp['id']=='hour_n100_shock_follow_a15_hold');result=[]
    for notional in [25,100]:
        for mode in SOURCES:
            policy=dict(old['policy'],position_notional=notional)
            result.append(dict(old,id=f'direction_n{notional}_{mode}',reference=f'n{notional}',cap=5,notional=notional,
                gate=mode,source='control' if mode=='weekly_control' else 'shock_fade_a15' if mode=='fade' else 'shock_follow_a15' if mode=='follow' else 'shock_weekly_direction',
                holding='hold',exit='hold',timing='pull05' if mode=='weekly_control' else 'immediate',
                policy=policy,baseline=mode in ['weekly_control','follow','fade']))
    assert len(result)==14
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),
        previous_turn_classification='progress:batch43 completed288newpaths,6tests,96exactcontrols,zero50percentmonthlypasses. Weeklyalignmentat100notionalwaspickedondevelopmentbutlostmoneyinthelaterJun-Augwindow.',
        hypothesis='When a large hourly shock occurs, the weekly direction may be a better entry side than blindly following or fading the shock. Test signs and cross-sectional extremes, including counter-direction, with same shock times and wallet rules.',
        source='Frozen3704shock_follow_a15andmatching3704fadeeventsfrombatch39,original6hcooldownbeforeanydailyfilter. Preserveat,coin,ATR,priorityandnext5mopenentry. NewdirectionalIDsderivefromorigins. Separateweekly7daypull05reference.',
        gates='weekly_control;follow;fade;weekly_sign;anti_sign;weekly_extreme;anti_extreme. Latestcompleted00UTCsnapshot<=hourlyshockclose. Weekly_signuses7dayrawlogreturnsign;extremeusescommonpool>=24and20percenttop/bottomwithrawsign. Ineligiblecoinsrejectnovelweeklymodes;zero-returnhasnodirection. Anti modesreverseselecteddailyside. No future daily snapshot or reranking.',
        intervention='Onlyentrydirectionandeligibilitychangeatoriginalshock;newIDsavoidsidecollisions. No delay,retry,positionaddagainstprice,orheldpositionexitsfromlaterdailychanges. Threefavorableparts0.25ATR/6h,3ATR/1%price trailing,noSL/noageclose. No exclusionsorretroactivemanualrescue.',
        account='500USDT Crossx5,5slots,onecoinposition,25totalnotional(default5margin)or100(research20margin). Allfees/funding/openMTM/pendingcapital. Persistent20%DDentrypause,neverautoresume;keepholdingsandtrailing. No livechanges.',
        evaluation='7sourcesx2sizesx12windowsx2cost=336paths. SelectsourcepersizeonSep-May:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling.10overlappingquarterstarts,reusedhistoryNOTfreshOOS.144oldcontrols exactbatch39. Independent frozen daily-event membership,pairedfollow/fade shockidentity,directseven-day-returnoracle,causalprefixes,fullfinancial/capital/exitchecks.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),previous_evidence_sha256=sha(PREVIOUS/'verification.json'),signals_sha256=sha(SIGNALS),
        frozen_weekly_signals_sha256=sha(ROOT/'artifacts/cross_sectional_20260925/signals.json'),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_shock_weekly_direction.py','shock_weekly_direction.py','shock_weekly_alignment.py','cross_sectional_signals.py','account_capital_trace.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    source=read(SIGNALS);origin=source['shock_follow_a15'];fade=source['shock_fade_a15'];state=states(frames)
    assert len(origin)==len(fade)==3704
    assert all((a['at'],a['symbol'],a['atr'],a['probability'])==(b['at'],b['symbol'],b['atr'],b['probability'])
               and a['side']!=b['side'] for a,b in zip(origin,fade))
    all_signals={'weekly_control':source['control'],'follow':origin,'fade':fade};counts={};details={}
    for gate in MODES:
        all_signals[gate],counts[gate],details[gate]=transform(origin,state,gate)
        assert not counts[gate].get('missing_state'),counts[gate]
    write(OUT/'signals.json',all_signals);write(OUT/'gate_counts.json',counts);write(OUT/'gate_decisions.json',details)
    print('GATES',counts,flush=True);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            signals=all_signals[sp['gate']]
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],sp['cap'],cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],timing=sp['timing'],cap=sp['cap'],gate=sp['gate'],
                    utilization=utilization(r['curve'],r,sp['notional'],sp['cap']),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    risk_exits=sum(j['kind']=='atr_stop' for j in r['journal']),time_exits=sum(j['kind']=='time_exit' for j in r['journal']),
                    margin_rejections=r['rejections'].get('insufficient_margin',0)+r['rejections'].get('add_insufficient_margin',0),candidates=sum(start<=e.get('source_at',e['at']) and e['at']<end for e in signals))
                row['target_met']=r['ending_equity'] is not None and row['monthly']['all_months_50pct']
                write(OUT/'runs'/f'{row["id"]}.json',{k:v for k,v in r.items() if k!='curve'});pd.DataFrame(r['curve']).to_parquet(OUT/'runs'/f'{row["id"]}_equity.parquet',index=False);results.append(row)
            write(OUT/'progress.json',dict(window=window,runs=len(results)))
        print(window,'COMPLETE',len(results),flush=True)
        if window=='development':
            selected=select(specs,results);write(OUT/'candidate_lock.json',dict(selected=selected,locked_at=pd.Timestamp.now(tz='UTC').isoformat(),later_not_run_in_batch=True,pristine_oos=False));print('LOCKED',selected,flush=True)
    assert sha(ROOT/'configs/live.yaml')==protocol['live_config_sha256']
    write(OUT/'summary.json',dict(protocol=protocol,specs=specs,selected=selected,results=results,robustness=robustness(results),
        target_met_rows=sum(r['target_met'] for r in results),incomplete_paths=sum(r['ending_equity'] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/'comparison.csv',index=False);print('COMPLETE',len(results),flush=True)


if __name__=='__main__':main()
