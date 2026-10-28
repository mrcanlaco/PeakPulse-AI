"""Batch34: coin-local closed-data confirmations of the first pullback entry."""
import pandas as pd
from account_capital_trace import simulate
from pullback_trend_gates import states,filtered,GATES
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

OUT=ROOT/'artifacts/pullback_trend_20260925'
PRIOR=ROOT/'artifacts/pullback_capacity_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=PRIOR/'signals.json'


def definitions(previous):
    assert previous['selected']==[dict(reference='frozen_pull05',strategy_id='pull05_cap5_n25')]
    old=next(sp for sp in previous['specs'] if sp['id']=='pull05_cap5_n25');result=[]
    for notional in [25,100]:
        for gate in GATES:
            result.append(dict(old,id=f'trend_n{notional}_{gate}',reference=f'n{notional}',cap=5,notional=notional,
                gate=gate,policy=dict(old['policy'],position_notional=notional),baseline=gate=='none'))
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:240ATRsizingpaths,50tests,96controls;zero50%monthlypasses;6proxyhaltpathsallatonehistoricaltime.',
        hypothesis='A favorable pullback may already invalidate the coin trend; checking closed local trend at the firsttrigger may improve monthly expectancy without simply raising leverage.',
        gates='none identicalcontrol;ret24/ret72 require signedlogreturn over24/72consecutiveclosedhours>0;ema_trend requires signed(currentclosedhourprice-lastclosed4hEMA20)>0 andsigned(EMA20-EMA60)>0,72complete4hbarsready;trend_ret24 requiresboth; persistence5 requiresatleast5oflast7nonoverlapping24hreturnsstrictlyintrade direction,all169hourlyclosescomplete. EMAadjustFalse,minperiod20/60,latestcompleted4h only;tiesreject. Bothdirectionsmirror.',
        intervention='Onlyatfirstpullbacktrigger hour,usingthen-closeddata:retainorpermanentlydiscardcandidate;noadditionalwaiting/reranking/retry. FrozenoriginATR/eventID/priority/side/time preserved. Keep3favorableparts,3ATR/1%price trailing,noSL/noageclose;filterdoesnotcloseheldpositions or cancelpendingadds.',
        account='500USDT sharedCrossx5,5slots,onecoinoneposition,persistent20%DDentrypause,noautoresume. Fixed25notional(default5plannedmargin) and100notional(research20margin) controls. Allfees/funding/MTM/pendingcapitalincluded. No livechanges.',
        evaluation='6gatesx2sizesx12windowsx2cost=288paths. Choosegate separatelypersize onSep-May:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling. All10three-monthstartsforallgates;overlap/historyreuse notnewOOS.48nonecontrols exactprior. Independentgateoracle andpartial4hcausalprefixes;missingrequiredgate data explicitlycounted and disallowsbatchacceptance.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),previous_evidence_sha256=sha(ROOT/'artifacts/volatility_size_20260925/verification.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_pullback_trend.py','pullback_trend_gates.py','account_capital_trace.py','short_multitimeframe_signals.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    source=read(SIGNALS);state=states(frames);all_signals={};counts={};decisions={}
    for gate in GATES:
        all_signals[gate],counts[gate],decisions[gate]=filtered(source,state,gate)
    write(OUT/'signals.json',all_signals);write(OUT/'gate_counts.json',counts);write(OUT/'gate_decisions.json',decisions)
    assert all(c.get('missing_state',0)==0 for c in counts.values()),'required_gate_data_missing'
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
