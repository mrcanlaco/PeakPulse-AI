"""Batch40: five-minute entry timing after frozen hourly continuation shocks."""
import pandas as pd
from account_capital_trace import simulate
from shock_five_minute_entry import transform,MODES
SOURCES=['weekly_control',*MODES]
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

OUT=ROOT/'artifacts/shock_five_minute_20260925'
PRIOR=ROOT/'artifacts/hourly_shock_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=PRIOR/'signals.json'


def definitions(previous):
    assert previous['selected']==[dict(reference='n100',strategy_id='hour_n100_shock_follow_a15_hold'),dict(reference='n25',strategy_id='hour_n25_control_hold')]
    old=next(sp for sp in previous['specs'] if sp['id']=='hour_n100_shock_follow_a15_hold');result=[]
    for notional in [25,100]:
        for mode in SOURCES:
            result.append(dict(old,id=f'five_n{notional}_{mode}',reference=f'n{notional}',cap=5,notional=notional,
                gate=mode,source='control' if mode=='weekly_control' else 'shock_follow_a15',holding='hold',exit='hold',timing=mode,
                policy=dict(old['policy'],position_notional=notional),baseline=mode in ['weekly_control','immediate']))
    assert len(result)==12
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),
        previous_turn_classification='progress:432hourlyshockpaths,37tests,48controls,zero50%monthlypasses;selectedhourlyfollow100hadprofitablefreshJunequarterbutonly6/10and7/10profitablequarterstarts.',
        hypothesis='Immediate entry after a large volume shock may pay for temporary price overshoot. Closed5m pullback/retest versus further continuation within the next hour can test entry quality while fixing source,ATR,priority,position sizing and exits.',
        sources='Frozen batch39 hourly shock_follow_a15 (3704events),selectedonSep-Mayat100notional,plusweekly7daypull05referencecontrolselectedat25notional. No new coinexclusions,reranking,changingcooldown orsourceATR. Long/Shortsymmetry.',
        intervention='Immediate samecontrol vs pull25/pull50 firstsignedclosed5mchange<=-0.25/-0.50originATR;retest50 firsttouch<=-0.50ATRthenLATERdistinctbarrebounds>=0.25ATRfromrunningmostfavorableclose,stillatleastasgoodasorigin;break25 firstsignedchange>=+0.25ATR. Originreference=closed5mpriceatT(alsohourclose);observeonlyT+5,10,...55minutes,expirebeforeminute60. No intrabarhigh/loworlimitfill. Actualnext5mopenatdecision+adverseslip,nottriggerprice. SourceATR/side/priority/eventIDunchanged;no retries. Waitingunsubmittedcandidateshavenomarginreservation;admissionchecksattrigger.',
        account='500USDT Crossx5,5slots,onecoinposition,25totalnotional(default5margin)or100(research20margin)across3favorableparts0.25ATR/6hfromactualentry.3ATR/1%price trailing,noSL/noageclose,actualfunding/fees/allopenMTM,persistent20%DDentrypause,neverautoresume. No livechanges.',
        evaluation='6sources/timingsx2sizesx12windowsx2cost=288paths. SelecttimingorweeklycontrolpersizeonSep-May:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling.10overlappingquarterstarts,reusedhistoryNOTfreshOOS.96oldcontrols exactbatch39. Independentvectorfirstpassage,partialhourcausalprefixes,allfinancialandcapitalchecks. Any requiredmissingorrightcensoredtimingdatainfullperioddisallowsacceptance.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),previous_evidence_sha256=sha(PRIOR/'verification.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_shock_five_minute.py','shock_five_minute_entry.py','account_capital_trace.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    source=read(SIGNALS);all_signals={'weekly_control':source['control']};origin=source['shock_follow_a15'];counts={};diagnostics={}
    for mode in MODES:
        all_signals[mode],counts[mode],diagnostics[mode]=transform(origin,prices,mode)
        assert not counts[mode].get('data_error') and not counts[mode].get('right_censored'),counts[mode]
    write(OUT/'signals.json',all_signals);write(OUT/'origin_signals.json',origin);write(OUT/'timing_counts.json',counts);write(OUT/'timing_diagnostics.json',diagnostics)
    print('TIMING',counts,flush=True);results=[]
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
