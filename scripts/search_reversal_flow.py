"""Batch16: frozen reversal signals with taker-flow ablations."""
import json
import pandas as pd
from compare_account_risk import ROOT,sha,write,exchange_rules
from frozen_extension_inputs import load
from prepare_altcoin_search import RULE_PATH
from research_account_grid import run_grid,WINDOWS,COSTS
from short_reversal_flow import load_flow,generate,definitions as sources,OLD_FLOW,DATA

OUT=ROOT/"artifacts/reversal_flow_20260925"
PRIOR=ROOT/"artifacts/market_breadth_20260925"


def definitions(previous):
    result=[]
    for src in sources():
        for n in [25,100]:
            base=next(s for s in previous["specs"] if s["id"]==f"benchmark_mask{src['mask']}_n{n}")
            for holding in ["hold","time48"]:
                policy=dict(base["policy"])
                if holding=="time48":policy["max_hold_hours"]=48
                result.append(dict(id=f"{src['id']}_n{n}_{holding}",source=src,notional=n,holding=holding,policy=policy,
                    baseline=src["gate"]=="none",reference_id=base["id"] if src["gate"]=="none" and holding=="hold" else None))
    return result


def select(specs,rows):
    result=[]
    for n in [25,100]:
        for holding in ["hold","time48"]:
            pool=[]
            for s in specs:
                if s["baseline"] or (s["notional"],s["holding"])!=(n,holding):continue
                rs=[r for r in rows if r["strategy_id"]==s["id"] and r["window"]=="development"]
                if len(rs)==2 and all(r["ending_equity"] is not None and r["ending_equity"]>500 and r["monthly"]["complete"] and r["max_drawdown"]<.2 and r["exits"]>=20 for r in rs):
                    pool.append((min(r["monthly"]["min_monthly_return"] for r in rs),min(r["ending_equity"] for r in rs),s["id"]))
            if pool:result.append(max(pool)[2])
    return result


def main():
    OUT.mkdir(exist_ok=True);prior=json.loads((PRIOR/"summary.json").read_text(encoding="utf-8"));specs=definitions(prior)
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),specs=specs,windows=WINDOWS,costs=COSTS,
        previous_turn_classification="progress:204failedrallypaths audited,allfourselected lateraccountslose;66tests.",
        hypothesis="Short post-overextension reversal only when completed taker-buy flow weakens, or buying fails to sustainprice. Ablate against samepriceevents.",
        flow="Use base-asset units; completed4h sumtakerbuy/sumvolume,notmeanratios. Require4validhours,andprevious4hratio finite. Nonegate retainsoriginalevenifflowmissing;othergates rejectmissing explicitly. Inputsoldverifiedhourlyflow andextension90cachedofficialZIPs;everyextensionprice/quotevolbar checkedagainstfrozenprices,volume boundsandchecksumchecked.",
        gates="none; seller current<=.50; drop5 current<=previous-.05; exhaust previous>=.55,current<=.50; absorbed current>=.55 despite redreversalprice. Absorbed iscontrast hypothesis,not sameasweakening. Applytoexactfrozenoverextensioneventlists mask0/ret6mask2. Preserveoriginaleventid,ATR,score,ordering,andcooldown: doNOTre-armadditionalpriceevents afterfiltering. No futurebar use.",
        account="500USDT,Crossx5,cap5,25/100notional total3parts,favorable0.25ATR additions/6hexpiry,trail3ATR/1%,persistent20%DDpause. Holdnostoploss vs48hmarketexitincludinglosses. Larger20margin/timeexit are researchdepartures;no live changes.",
        selection="10sources x2sizes x2holding=40policies x3windows x2cost=240paths. Selectnon-nonegate oneper(size,holding),developmentbothcostcomplete,ending>500,DD<20%,>=20closed;maximizeworstcostminmonth thenequity. Positiveendinggate preregistered here,notposthocrelaxation. Lockbeforelaterinbatch; reusedhistorynotpristineOOS.",
        target="50%netMTMgrowth EVERYcalendar month,notaverage/best/total. Nohistoricalfitguaranteesfutureprofit.",limitations=prior["protocol"]["limitations"],
        live_config_sha256=sha(ROOT/"configs/live.yaml"),prior_sha256=sha(PRIOR/"summary.json"),signals_sha256=sha(PRIOR/"signals.json"),data_sha256=sha(DATA/"reconciled_manifest.json"),old_flow_sha256=sha(OLD_FLOW/"flow_evidence.json"),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["search_reversal_flow.py","short_reversal_flow.py","research_account_grid.py","prepare_flow_research.py","account_scaled_replay.py","frozen_extension_inputs.py","monthly_account_metrics.py","capital_research_metrics.py"]})
    write(OUT/"protocol.json",protocol)
    flow,evidence=load_flow();write(OUT/"flow_evidence.json",evidence)
    signals,counts=generate(json.loads((PRIOR/"signals.json").read_text(encoding="utf-8")),flow);write(OUT/"signals.json",signals);write(OUT/"signal_counts.json",counts)
    prices,funding,_=load();results,selected=run_grid(OUT,specs,signals,prices,funding,exchange_rules(RULE_PATH),select)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,specs=specs,selected=selected,results=results,target_met_rows=sum(r["target_met"] for r in results),incomplete_paths=sum(r["ending_equity"] is None for r in results)))
    pd.DataFrame(results).to_csv(OUT/"comparison.csv",index=False);print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
