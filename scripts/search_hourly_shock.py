"""Batch39: hourly price-volume shock continuation/reversal and finite holding alternatives."""
import pandas as pd
from account_capital_trace import simulate
from hourly_shock_signals import prepare,generate,definitions as signal_definitions
SOURCES=['control']+[s['id'] for s in signal_definitions()]
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

OUT=ROOT/'artifacts/hourly_shock_20260925'
PRIOR=ROOT/'artifacts/pullback_capacity_20260925'
TIMING_PRIOR=ROOT/'artifacts/momentum_timing_20260925'
SIGNALS=PRIOR/'signals.json'


def definitions(previous):
    old=next(sp for sp in previous['specs'] if sp['id']=='pull05_cap5_n25');result=[]
    for notional in [25,100]:
        for source in SOURCES:
            for holding in (['hold'] if source=='control' else ['hold','risk12']):
                policy=dict(old['policy'],position_notional=notional)
                if holding=='risk12':policy.update(stop_atr=2,max_hold_hours=12)
                result.append(dict(old,id=f'hour_n{notional}_{source}_{holding}',reference=f'n{notional}',cap=5,notional=notional,
                    gate=source,source=source,holding=holding,exit=holding,timing='pull05' if source=='control' else 'immediate',
                    policy=policy,baseline=source=='control'))
    assert len(result)==18
    return result


def main():
    OUT.mkdir(exist_ok=True);(OUT/'runs').mkdir(exist_ok=True)
    previous=read(PRIOR/'summary.json');specs=definitions(previous);spans=windows()
    protocol=dict(created_at=pd.Timestamp.now(tz='UTC').isoformat(),
        previous_turn_classification='progress:336residualmomentumpaths,28tests,48controls,zero50%monthlypasses. Newrankingsdidnotbeatraw7daycontrolonmajorityofquarterstarts;12proxyhaltsatoneevent.',
        hypothesis='Hourly large candle bodies accompanied by unusually large quote volume may support continuation or exhaustion reversals with higher turnover than daily ranking; evaluate both signs without hindsight exclusions.',
        signals='Everyclosed1hcandlefor30alts. TrueRange=max(high-low,abs(high-prevclose),abs(low-prevclose)). FreezeATRmeanof14hoursBEFOREshock. Body=(close-open)/priorATR; thresholds1.5/2.5absolute. Currentquotevolume>=2xmeanof24PREVIOUShours. Upwardshockmustcloseintheupper20%ofrange;downwardinlower20%. Require72consecutivevalidpositiveOHLCVhoursandcurrent24hquotevolume>=2m. Followbuysup/sellsdown;fadeopposite. Global6hpercoinpersourcecooldownBEFOREwalletadmission,no retry. Priority=abs(bodyATR)*log1p(volumeratio). Sourceobservationsareclosedhours,next5mopenadverseslip. EventATRneverupdated.',
        intervention='4sourcesx2exitbundles. Hold keeps3ATR/1%price trailing,noSL/noageclose. risk12 adds2ATRweightedentry-versuslastclosedMarkexitand12hmaximumage;bothCANrealizeloss,offlinealternativetodefault. ATRstopbeforeageexitbeforetrailing/adds,actualnextopenNOTtriggerprice. Same3favorableparts0.25ATR/6h. Originalraw7daypull05control48pathsexactprior;hourlyATR scale differs intentionally with source.',
        account='500USDT Crossx5,5sharedslots,onecoinposition,persistent20%DDentrypause,keepfunding/MTM/exits,neverautoresume. Fixedtotalnotional25(default5margin)or100(research20margin),notperpart. Fullpendingcapital/fees/funding/MTM. No livechanges.',
        evaluation='(4sourcesx2exits+1control)x2sizesx12windowsx2cost=432paths. Selectsource+exitpersizeonSep-May:bothcostprofit/DD<20/20closed/complete,maxworstmonthlythenworstending. Lockbeforelater/rolling.10overlappingquarterstarts,reusedhistoryNOTfreshOOS. Independentdirectwindow/cooldownoracle,causalprefixes,fullcapitalandfinancial/stop/trailingaudits. Report all alternatives and failures.',
        target='Atleast50%netMTM EVERYcalendar month;notpositiveyear/window oraverage.',limitations=previous['protocol']['limitations'],
        specs=specs,windows=spans,costs=COSTS,prior_sha256=sha(PRIOR/'summary.json'),previous_evidence_sha256=sha(ROOT/'artifacts/residual_momentum_20260925/verification.json'),signals_sha256=sha(SIGNALS),
        data_sha256=sha(DATA/'reconciled_manifest.json'),rules_sha256=sha(RULE_PATH),live_config_sha256=sha(ROOT/'configs/live.yaml'),
        source_sha256={n:sha(ROOT/'scripts'/n) for n in ['search_hourly_shock.py','hourly_shock_signals.py','account_capital_trace.py','frozen_extension_inputs.py']})
    write(OUT/'protocol.json',protocol)
    prices,funding,frames=load();rules=exchange_rules(RULE_PATH)
    source=read(SIGNALS);enriched=prepare(frames);generated=generate(enriched)
    all_signals={'control':source,**{key:[e for e in es if BOUNDARIES[0]<=e['at']<BOUNDARIES[-1]] for key,es in generated.items()}}
    coverage=[]
    start=pd.Timestamp(BOUNDARIES[0],unit='ms',tz='UTC');end=pd.Timestamp(BOUNDARIES[-1]-1,unit='ms',tz='UTC')
    for coin,h in enriched.items():
        f=h.loc[start:end];cols=['open','high','low','close','quote_volume']
        coverage.append(dict(symbol=coin,hours=len(f),missing_hours=int(f[cols].isna().any(axis=1).sum()),ready_hours=int(f.ready.sum())))
    assert all(r['hours']==8760 and r['missing_hours']==0 for r in coverage),'missing_hourly_data'
    write(OUT/'signals.json',all_signals);write(OUT/'coverage.json',coverage)
    print('SIGNALS',{k:len(es) for k,es in all_signals.items()},flush=True);results=[]
    for window,(start,end) in spans.items():
        for sp in specs:
            signals=all_signals[sp['gate']]
            for cost,fee,slip in COSTS:
                r=simulate(list(range(start,end+1,300000)),grouped_signals([e for e in signals if e.get('source_at',e['at'])>=start],start,end),lambda c:prices.get(c,{}),rules,lambda c:funding[c],configuration(sp['cap'],fee,slip),research_policy=sp['policy'])
                r['liquidation_status']='verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct'
                row=summarize(r,sp['id'],sp['id'],sp['policy'],sp['cap'],cost,window);sides=side_metrics(r,r['curve'])
                row.update(id=f'{window}_{cost}_{sp["id"]}',strategy_id=sp['id'],reference=sp['reference'],exit=sp['exit'],notional=sp['notional'],baseline=sp['baseline'],source=sp['gate'],holding=sp['holding'],timing=sp['timing'],cap=sp['cap'],gate=sp['gate'],
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
