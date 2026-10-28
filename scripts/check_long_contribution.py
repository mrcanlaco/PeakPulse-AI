"""Predeclared follow-up: remove Long signals while preserving three Short slots."""
import json
import pandas as pd
from account_side_quota_replay import simulate
from compare_account_risk import ROOT,sha,write,summarize,exchange_rules
from directional_capacity_metrics import side_metrics
from capital_research_metrics import utilization
from frozen_extension_inputs import load
from monthly_account_metrics import monthly_metrics
from prepare_altcoin_search import RULE_PATH
from research_capacity_config import configuration
from research_directional_audit import audit_directional
from search_side_capacity import OUT as PARENT,windows,BOUNDARIES,COSTS
from search_multitimeframe_rolling import grouped_signals

OUT=PARENT/"long_contribution_control"
REFERENCE="pullback_any_hybrid_n25_hold_L2S3"


def main():
    OUT.mkdir(exist_ok=True);(OUT/"runs").mkdir(exist_ok=True)
    parent=json.loads((PARENT/"summary.json").read_text(encoding="utf-8"))
    sp=next(p for p in parent["specs"] if p["id"]==REFERENCE)
    source=json.loads((PARENT/"signals.json").read_text(encoding="utf-8"))[sp["source"]["id"]]
    signals=[s for s in source if s["side"]=="SHORT"]
    protocol=dict(created_at=pd.Timestamp.now(tz="UTC").isoformat(),reference=REFERENCE,
        question="DoesapparentbenefitofL2S3hybridcome fromLongpositionsorjustholdingfewerShorts?",
        trigger="Parent384pathresultsalreadyinspected. Thiscontrolchosenposthocformechanismdiagnosis,notindependentconfirmationorpromotion.",
        intervention="RemoveLongsignalsONLY.KeepfrozenhybridShortidentity,ATR,priority,3Shortslots,twoLongslotsunused,500wallet,x5,25totalnotional,3tranches,trailing,DDpause. PositionsarenotscaledandShort-onlycap5isnotanequivalentcontrol.",
        scope="Same12windowsand2costs=24additionalpaths;compareeverywindow/costwithoutchoosingnewbestallocation. RemovingLongcanalsoreleasecoinlocksandalterwhichShortsfill;reportthatinteraction.",
        policy=sp["policy"],windows=windows(),costs=COSTS,source_signals=len(signals),
        parent_sha256=sha(PARENT/"summary.json"),signals_sha256=sha(PARENT/"signals.json"),
        live_config_sha256=sha(ROOT/"configs/live.yaml"),rules_sha256=sha(RULE_PATH),
        source_sha256={n:sha(ROOT/"scripts"/n) for n in ["check_long_contribution.py","account_side_quota_replay.py","research_directional_audit.py","directional_capacity_metrics.py"]})
    write(OUT/"protocol.json",protocol);write(OUT/"signals.json",signals)
    prices,funding,_=load();rules=exchange_rules(RULE_PATH);results=[];fc=fills=curves=0
    for window,(start,end) in windows().items():
        for cost,fee,slip in COSTS:
            r=simulate(list(range(start,end+1,300000)),grouped_signals(signals,start,end),lambda c:prices.get(c,{}),rules,
                lambda c:funding[c],configuration(5,fee,slip),research_policy=sp["policy"])
            r["liquidation_status"]="verified_5m_marks_but_historical_maintenance_tiers_unknown_proxy1pct"
            curve=pd.DataFrame(r["curve"]);m=side_metrics(r,curve,sp["policy"]["side_caps"])
            assert m["sides"]["LONG"]["entries"]==0 and m["sides"]["SHORT"]["peak_positions"]<=3
            a,b,c=audit_directional(r,curve,prices,funding,fee,slip,5,25);fc+=a;fills+=b;curves+=c
            row=summarize(r,"short_only3","Short only3",sp["policy"],5,cost,window)
            row.update(id=f"{window}_{cost}_short_only3",side_metrics=m,utilization=utilization(curve,r,25),
                monthly=monthly_metrics(r["curve"],boundaries=[t for t in BOUNDARIES if start<=t<=end]))
            row["target_met"]=r["ending_equity"] is not None and row["monthly"]["all_months_50pct"]
            both=next(v for v in parent["results"] if v["strategy_id"]==REFERENCE and v["window"]==window and v["cost"]==cost)
            original=json.loads((PARENT/"runs"/f"{both['id']}.json").read_text(encoding="utf-8"))
            short_ids={j["event_id"] for j in r["journal"] if j["kind"]=="entry"}
            both_short={j["event_id"] for j in original["journal"] if j["kind"]=="entry" and j["side"]=="SHORT"}
            row["comparison"]=dict(hybrid_ending=both["ending_equity"],hybrid_dd=both["max_drawdown"],hybrid_entries=both["side_entries"],
                hybrid_long_contribution=both["side_metrics"]["sides"]["LONG"]["total_contribution"],
                hybrid_minus_control=both["ending_equity"]-r["ending_equity"] if both["ending_equity"] is not None and r["ending_equity"] is not None else None,
                same_short_events=short_ids==both_short,only_hybrid_short_events=sorted(both_short-short_ids),only_control_short_events=sorted(short_ids-both_short))
            write(OUT/"runs"/f"{row['id']}.json",{k:v for k,v in r.items() if k!="curve"})
            curve.to_parquet(OUT/"runs"/f"{row['id']}_equity.parquet",index=False);results.append(row)
        print("CONTROL",window,flush=True)
    assert sha(ROOT/"configs/live.yaml")==protocol["live_config_sha256"]
    write(OUT/"summary.json",dict(protocol=protocol,results=results,target_met_rows=sum(r["target_met"] for r in results),
        verification=dict(journals_audited=len(results),funding_quantities_checked=fc,directional_fills_checked=fills,equity_states_reconstructed=curves,
                          hashes_match=True,live_config_unchanged=True)))
    print("COMPLETE",len(results),flush=True)


if __name__=="__main__":main()
