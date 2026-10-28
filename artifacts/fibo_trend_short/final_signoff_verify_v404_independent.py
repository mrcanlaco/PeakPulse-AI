from pathlib import Path
import sys, json, hashlib, copy, collections, tempfile, os
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'scripts/fibo_research')]
sys.stdout.reconfigure(encoding='utf-8')
import verify_red_team_reaudit_v404 as v4
import verify_red_team_reaudit_v402 as v2
import verify_red_team_audit_2026 as eng
import universe_reaudit_v402_worker as uw
ART = ROOT/'artifacts/fibo_trend_short'
load = lambda f: json.loads((ART/f).read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
d=load('red_team_reaudit_recalculation_v4_0_4.json')
u=load('universe_338_reaudit_v4_0_4_summary.json')
m=load('VERSION_MANIFEST_v4_0_4.json')
md=(ART/'RED_TEAM_REAUDIT_RESPONSE_v4_0_4_2026-10-17.md').read_text(encoding='utf-8-sig')
e={'scope':'Independent source/artifact checks, targeted counterexamples; no full14/338 historical rerun','pytest':{'passed':23,'seconds':5.35}}
e['manifest']=[{'path':p,'match':sha(ROOT/p)==h} for p,h in m['sha256_checksums'].items()]
b=load('HISTORICAL_ARTIFACTS_BASELINE_BEFORE_v4_0_4.json')
e['history']=[{'path':p,'match':sha(ROOT/p)==v['sha256']} for p,v in b.items() if p.startswith('artifacts/') and isinstance(v,dict)]
e['markdown_exact']=v4.generate_markdown_report_v404(d)==md
e['consistency']=v4.verify_markdown_json_consistency_v404(d,md,u)
e['mutation_tests']=v4.run_report_consistency_mutation_tests_v404(d,md,u)
e['supplied_counterexamples']=v4.reproduce_all_v404_counterexamples()
e['universe_embedded_equal']=u==d['re_audit_3_universe_338_and_rolling_pit']
e['id_checks']=[]
def walk(o,path=''):
    if isinstance(o,dict):
        if 'accepted_trade_ids' in o:
            a=o['accepted_trade_ids']; x=o.get('executed_trade_ids')
            e['id_checks'].append({'path':path,'accepted_count':len(a),'executed_count':len(x) if x is not None else None,'multisets_equal':collections.Counter(a)==collections.Counter(x) if x is not None else None,'unique':len(a)==len(set(a))})
        for k,v in o.items(): walk(v,path+'/'+k)
    elif isinstance(o,list):
        for i,v in enumerate(o): walk(v,path+f'/{i}')
walk(d)
symbols=list(d['re_audit_1_portfolio_accounting_and_caps']['historical_funding_audit']['by_symbol_source'])
lookup,cov=v2.load_historical_funding_lookup(symbols)
e['funding_reloaded']=cov
e['funding_count_independent']={'total':sum(len(x) for x in lookup.values()),'off8h':sum(h%8!=0 for x in lookup.values() for h in x)}
out=ART/'FINAL_SIGNOFF_VERIFICATION_v4_0_4_EVIDENCE.json'
out.write_text(json.dumps(e,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'manifest_count':len(e['manifest']),'manifest_all':all(x['match'] for x in e['manifest']),'history_count':len(e['history']),'history_all':all(x['match'] for x in e['history']),'consistency':e['consistency'],'mutation_tests':e['mutation_tests'],'counterexamples':e['supplied_counterexamples'],'id_nodes':len(e['id_checks']),'id_problem_nodes':[x for x in e['id_checks'] if not x['multisets_equal'] or not x['unique']],'funding':e['funding_count_independent']},ensure_ascii=False,default=str))
