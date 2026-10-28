"""Batch36: entry carry filters of the two development-selected pullback policies."""
import pandas as pd
from account_capital_trace import simulate
from pullback_carry_gates import observations,filtered,GATES
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

OUT=ROOT/'artifacts/pullback_carry_20260925'
PRIOR=ROOT/'artifacts/pullback_dip_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=PRIOR/'signals.json'


def definitions(previous):
    selected={r['strategy_id'] for r in previous['selected'] if r['strategy_id']}
    assert selected=={'dip_n25_none','dip_n100_counter24'}
    result=[]
    for old in previous['specs']:
        if old['id'] not in selected:continue
        for gate in GATES:
            result.append(dict(old,id=f'carry_n{old["notional"]}_{gate}',reference=old['id'],source_gate=old['gate'],gate=gate,baseline=gate=='none'))
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:288dipentrypaths/66tests/48controls/18causalprefixes. No50%monthlypasses. Deep25SOONshort priceprofit1.19/funding-68.30/net-67.12 after91days identified without excluding it.',
        hypothesis='Funding already known at entry may identify costly holds before opening, improving net monthly outcomes without posthoc coin exclusions.',
        gates='none identicalcontrol;avoid_costly requires signedlastreceipt>=-0.0005 andsignedsum24h>=-0.001;nonnegative requiresboth>=0;atr10/atr25 require7*max(0,-signedsum24h)/(3*frozenoriginATR/originclosedprice)<=0.10/0.25. The7daycost is a screening proxy extrapolating past24h,not futurefunding forecast,guarantee,holdinglimit orstop. ATR14closed4h frozenat source,3ATRpriceactivation unchanged.',
        observations='Useonlysettlement timestamps<=decisiontime-60000. Last24hwindow=(cutoff-24h,cutoff],sumallactualintervals,notassumed3payments. Requireobservedsettlementat/beforeleftboundary,atleastonewithinwindow,nogap>8h5m fromprecedingrecordthroughwindow,latestage<=8h5m,finiteknownrates. Missing/staleexplicitanddisallowsbatchacceptance. Roundreceipt ratesto12decimalplaces;Shortreceivespositivefunding,Longpays. No futurefundingrate/sign/nextinterval used.',
        intervention='Freeze previousdevelopment-selected sources:noneentryfilter25 andcounter24entryfilter100. Fundinggateatfirstoriginalpullbacktrigger;discardifnoteligible,noadditionalwait/rerank/retry. SameeventID/side/ATR/time/priority. Keep3favorableparts,3ATR/1%price trailing,noSL/noageclose. Newfundingdoesnotchangeheldpositions oradds. Larger100notional is offline research.',
        account='500USDT sharedCrossx5,5slots,onecoinoneposition,persistent20%DDentrypause,noautoresume.25/100totalnotional across3parts,5/20plannedmargin. Allactualfees/funding/MTM/pendingcapitalincluded. No livechanges.',
        evaluation='2frozenrefsx5fundinggatesx12windowsx2cost=240paths. Choosegateperreference onSep-May:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling. All10three-monthstartsforeach;overlap/historyreuse notnewOOS.48nonecontrols exactprior. Independentpastwindoworacle andcausalprefixchecks;analyzehistoricalSOONdiagnosticeligibilitywithoutassumingaccountwouldadmitit.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_pullback_carry.py','pullback_carry_gates.py','account_capital_trace.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    source=read(SIGNALS);obs=observations(source['none'],funding);all_signals={};counts={}
    for sp in specs:
        key=sp['source_gate']+'__'+sp['gate']
        all_signals[key],counts[key]=filtered(source[sp['source_gate']],obs,sp['gate'])
    write(OUT/'signals.json',all_signals);write(OUT/'gate_counts.json',counts);write(OUT/'funding_observations.json',obs)
    assert all(o['complete'] for o in obs.values()),'required_past_funding_incomplete'
    print('FUNDING_GATES',counts,flush=True);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            signals=all_signals[sp['source_gate']+'__'+sp['gate']]
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],sp['cap'],cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],timing=sp['timing'],cap=sp['cap'],gate=sp['gate'],source_gate=sp['source_gate'],
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
