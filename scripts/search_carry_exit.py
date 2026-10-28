"""Batch37: lagged realized funding loss budgets, including loss-making market exits."""
import pandas as pd
from account_carry_exit_replay import simulate
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

OUT=ROOT/'artifacts/carry_exit_20260925'
PRIOR=ROOT/'artifacts/pullback_carry_20260925'
DIAG=ROOT/'artifacts/pullback_dip_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=PRIOR/'signals.json'


def definitions(previous,diagnostic):
    chosen={x['strategy_id'] for x in previous['selected'] if x['strategy_id']}
    assert chosen=={'carry_n25_none','carry_n100_avoid_costly'}
    refs=[(next(sp for sp in previous['specs'] if sp['id']=='carry_n25_none'),'normal25','carry','none__none'),
          (next(sp for sp in previous['specs'] if sp['id']=='carry_n100_avoid_costly'),'counter100','carry','counter24__avoid_costly'),
          (next(sp for sp in diagnostic['specs'] if sp['id']=='dip_n25_dip24_deep'),'deep25','dip','dip24_deep')]
    result=[]
    for old,tag,kind,key in refs:
        for mode,fraction in [('hold',None),('f005',.005),('f010',.01),('f020',.02)]:
            policy=dict(old['policy'])
            if fraction is not None:policy['carry_exit_fraction']=fraction
            result.append(dict(old,id=f'fexit_{tag}_{mode}',parent_id=old['id'],reference=tag,source_kind=kind,source_key=key,carry_rule=mode,carry_fraction=fraction,policy=policy,baseline=mode=='hold'))
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous,read(DIAG/'summary.json'));spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),previous_turn_classification='progress:240entrycarrypaths/53tests/48controls/30causalprefixes. Zero50%monthlypasses;8proxyhaltpaths. AllentryfundinggatesaccepteddiagnosedSOONtradebecauseknowncarrywaspositive.',
        hypothesis='Limiting accrued funding outflow during a hold, rather than only screening entry carry, may improve net expectancy and release capital before costs accumulate.',
        intervention='Offlinealternative that CAN close losing positions,not originalno-loss-close configuration. Same3favorableparts,price3ATR/1%trailing. holdcontrol or closewhen cumulative NET settled funding known at least60seconds ago <= -(0.5%,1%,2%)*PLANNED totalpositionnotional. Fixedcashlimit for entireposition,not rescaled byfilledparts/equity/newATR. Priorfundingcredits offsetpayments;notgrosssumnegativepayments. Always useactualheldqtyandsettlementMark in cash. Thresholdnot maximumtotalPnLloss andpaymentscanovershootit.',
        execution='Ledgerbooksallactualsettlements asusual. Separatecausalqueue releasesonlysettlements<=step-60s toexitdecision. Checkevery5m;carryexitprioritybeforetrailing/nextadds,exit atnexttradeopenwithadverseslip. Same-stepreentryblocked. StillcheckCrossmaintenancebeforeexits andkeeppersistent20%entrypause. Carryexitsremainactiveafterpause;noautoresume. TerminalmissingnextopenmeanspendingexitandMTM,nofictitiousfill.',
        references='Freeze previousdev-selected normal25 andcounter24+avoid_costly100. Also registered diagnosticdeep25source frombatch35 to test mechanism of itsSOONcarryloss;explicitdiagnosticnotpreviousselectedstrategy. No coinexclusions/manualrescue assumptions.',
        evaluation='3refsx4exitmodesx12windowsx2cost=288paths. Chooseexitperreference onSep-May:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling. All10three-monthstartsforeach;overlap/historyreuse notnewOOS.72holdcontrols exactprior. Independentfirstfundingtrigger versusprice trailing audit.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),diagnostic_sha256=sha(DIAG/'summary.json'),signals_sha256=sha(SIGNALS),diagnostic_signals_sha256=sha(DIAG/'signals.json'),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_carry_exit.py','account_carry_exit_replay.py','account_capital_trace.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    all_signals={sp['reference']:read((PRIOR if sp['source_kind']=='carry' else DIAG)/'signals.json')[sp['source_key']] for sp in specs};write(OUT/'signals.json',all_signals);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            signals=all_signals[sp['reference']]
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],sp['cap'],cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['source'],holding=sp['holding'],timing=sp['timing'],cap=sp['cap'],carry_rule=sp['carry_rule'],carry_fraction=sp['carry_fraction'],
                    utilization=utilization(r['curve'],r,sp['notional'],sp['cap']),exit_diagnostics=exit_diagnostics(r),side_metrics=sides,
                    side_entries={side:rs['entries'] for side,rs in sides['sides'].items()},monthly=monthly_metrics(r['curve'],boundaries=[t for t in BOUNDARIES if start<=t<=end]),
                    margin_rejections=r['rejections'].get('insufficient_margin',0)+r['rejections'].get('add_insufficient_margin',0),candidates=sum(start<=e.get('source_at',e['at']) and e['at']<end for e in signals))
                exits=[j for j in r['journal'] if j['kind']=='carry_exit']
                row['carry_diagnostics']=dict(count=len(exits),negative=sum(j['net']<0 for j in exits),total_net=sum(j['net'] for j in exits),worst_net=min((j['net'] for j in exits),default=None),limit=sp['notional']*sp['carry_fraction'] if sp['carry_fraction'] is not None else None,max_observed_cost_ratio=max((-j['known_funding']/j['funding_limit'] for j in exits),default=None))
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
