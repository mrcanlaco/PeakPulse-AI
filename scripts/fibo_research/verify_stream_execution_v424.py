"""Replay all six frozen policies via sequential observations through2025.

Uses the archived candidate decision feed; this does not claim end-to-end
online signal/PIT integration. Each code revision gets a separate attempt
directory, preserving failed receipts rather than rewriting earlier evidence.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import pickle
import shutil
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import evaluate_family_v421 as baseline
import stream_execution_v424 as stream

v = baseline.v
r = v.r
ROOT = v.ROOT
BASE = v.ART
PRIOR = BASE.parent / 'research_v4_0_23'
ART = BASE.parent / 'research_v4_0_24'
SCENARIOS = v.SCENARIOS
FAMILY = v.FAMILY
DAY_MS = 86400000
TOL = 1e-7


def preserve():
    for directory in (BASE,PRIOR):
        p = r.read(directory / 'CHECKPOINT.json')
        for name,digest in p['files'].items():
            assert r.sha(directory/name) == digest, name
        for name,digest in p['additional_sources'].items():
            assert r.sha(ROOT/name) == digest, name


def prepare():
    preserve()
    p = ART/'INPUTS.json'
    if p.exists():
        verify_inputs()
        return
    manifest = r.read(BASE/'PATH_MANIFEST.json')
    metadata = []
    for spec in manifest['symbols'].values():
        path = BASE/spec['paths']
        assert r.sha(path) == spec['paths_sha256']
        with gzip.open(path,'rb') as f:
            pack = pickle.load(f)
        for c in pack['full']:
            if not v.previous.annual_eligible(c):
                continue
            metadata.append({k:c[k] for k in ('id','symbol','tf','wave_key','decision_ts','entry_ts',
                                                'entry','stop','targets','score','milestones')})
    metadata.sort(key=lambda c:(c['entry_ts'],-c['score'],c['symbol'],c['tf']))
    assert len(metadata) == 17686 and len({c['id'] for c in metadata}) == len(metadata)
    r.save(ART/'ENTRY_METADATA.json',metadata)
    r.save(p,{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'candidates':len(metadata),'entry_metadata_sha256':r.sha(ART/'ENTRY_METADATA.json'),
        'path_manifest_sha256':r.sha(BASE/'PATH_MANIFEST.json'),
        'views_sha256':r.sha(BASE/'OBSERVED_VIEWS.json'),
        'funding_manifest_sha256':r.sha(BASE/'funding/MANIFEST.json'),
        'baseline_results_sha256':r.sha(BASE/'RESULTS.json'),
        'prior_checkpoint_sha256':r.sha(PRIOR/'CHECKPOINT.json'),
        'data_window':['2020-01-01','2026-01-01 exclusive'],
        'scope':'Archived candidate feed. Sequential execution consumes only entry open, then closed OHLCV and realized funding events; no path, known exit or future outcome.',
        'limitations':['Not yet an integrated live signal/PIT/lifecycle/quote service.',
            'Funding completeness is supplied by the previously verified historical feed.',
            'Funding settlement mark proxies remain explicit.',
            'OHLC stop-first conventions are retained, not exchange fill or latency proof.'],
        'fresh_oos':False,'prospective_started':False,'goal_complete':False})
    print({'prepared_candidates':len(metadata)},flush=True)


def verify_inputs():
    p = r.read(ART/'INPUTS.json')
    assert p['entry_metadata_sha256'] == r.sha(ART/'ENTRY_METADATA.json')
    assert p['path_manifest_sha256'] == r.sha(BASE/'PATH_MANIFEST.json')
    assert p['views_sha256'] == r.sha(BASE/'OBSERVED_VIEWS.json')
    assert p['funding_manifest_sha256'] == r.sha(BASE/'funding/MANIFEST.json')
    assert p['baseline_results_sha256'] == r.sha(BASE/'RESULTS.json')
    assert p['prior_checkpoint_sha256'] == r.sha(PRIOR/'CHECKPOINT.json')
    return p


def tests():
    suites = list(ET.parse(ART/'TESTS.xml').getroot().iter('testsuite'))
    count = {k:sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')}
    assert count['tests'] >= 18 and count['errors'] == count['failures'] == count['skipped'] == 0
    return count


def attempt():
    verify_inputs(); tests()
    paths = [Path(__file__),Path(stream.__file__),ROOT/'tests/unit/fibo_short/test_stream_execution_v424.py']
    sources = {str(p.relative_to(ROOT)):r.sha(p) for p in paths}
    identity = {'sources':sources,'inputs_sha256':r.sha(ART/'INPUTS.json'),'tests_sha256':r.sha(ART/'TESTS.xml')}
    digest = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out = ART/'attempts'/digest[:16]
    if not (out/'PROTOCOL.json').exists():
        out.mkdir(parents=True,exist_ok=True)
        r.save(out/'PROTOCOL.json',{**identity,'registered_at_utc':datetime.now(timezone.utc).isoformat(),
            'scenarios':SCENARIOS,'family':FAMILY,'comparison_tolerance_absolute':TOL,
            'same_timestamp_order':'funding, then closed bars by admission order, then entries ranked score/symbol/timeframe',
            'restart_semantics':'State after a complete batch; repeated/nonmonotonic batch is rejected.',
            'new_signal_parameters':0,'fresh_oos':False,'goal_complete':False})
        for p in paths:
            dest = out/'sources'/p.relative_to(ROOT)
            dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,dest)
    saved = r.read(out/'PROTOCOL.json')
    assert all(saved[k] == val for k,val in identity.items())
    r.save(ART/'CURRENT_ATTEMPT.json',{'path':str(out),'protocol_sha256':r.sha(out/'PROTOCOL.json')})
    return out


def compare(a,b,where=''):
    if isinstance(a,dict):
        assert isinstance(b,dict) and set(a)==set(b),(where,'keys',set(a)^set(b))
        for key in a: compare(a[key],b[key],where+'/'+str(key))
    elif isinstance(a,(list,tuple)):
        assert isinstance(b,(list,tuple)) and len(a)==len(b),(where,'length',len(a),len(b))
        for i,(x,y) in enumerate(zip(a,b)):compare(x,y,where+'/'+str(i))
    elif isinstance(a,(int,float)) and not isinstance(a,bool):
        assert isinstance(b,(int,float)) and np.isfinite(a) and np.isfinite(b) and abs(a-b)<=TOL,(where,a,b)
    else:
        assert a==b,(where,a,b)


def load_quotes(symbols,year,views):
    lo,hi = r.utc(f'{year}-01-01'),r.utc(f'{year+1}-01-01')
    quotes = {}
    for symbol in sorted(symbols):
        frames = []
        for a in views[symbol]:
            if r.utc(a['last_open']) < lo or r.utc(a['first_open']) >= hi:
                continue
            assert r.sha(a['path']) == a['sha256']
            frame = pd.read_parquet(a['path'],filters=[('open_time','>=',lo),('open_time','<',hi)])
            if len(frame):frames.append(frame)
        f = pd.concat(frames).sort_index()
        assert f.index.is_unique and f.index.min() >= lo and f.index.max() < hi <= r.utc('2026-01-01')
        quotes[symbol] = (r.epoch_seconds(f.index)*1000,f[['open','high','low','close','volume']].to_numpy())
    return quotes


def quote_at(quotes,symbol,opened):
    index,values = quotes[symbol]
    i = np.searchsorted(index,opened)
    if i >= len(index) or index[i] != opened:
        raise ValueError(f'Missing actual quote {symbol} {opened}')
    return values[i]


def year_replay(year,metadata,views,funding,out):
    receipt = out/f'YEAR_{year}.json'
    if receipt.exists():
        saved = r.read(receipt)
        assert saved['protocol_sha256'] == r.sha(out/'PROTOCOL.json')
        for name,digest in saved['node_files'].items():assert r.sha(out/name)==digest
        return saved
    lo,hi = [int(r.utc(f'{y}-01-01').timestamp()*1000) for y in (year,year+1)]
    source = [c for c in metadata if lo <= c['entry_ts']*1000 < hi-5*DAY_MS]
    symbols = {c['symbol'] for c in source}
    quotes = load_quotes(symbols,year,views)
    proposed = defaultdict(list)
    for c in source:
        stamp = c['entry_ts']*1000
        observed_open = float(quote_at(quotes,c['symbol'],stamp)[0])
        assert abs(observed_open-c['entry']) <= 1e-12*max(1.,c['entry'])
        proposed[stamp].append({k:c[k] for k in ('id','symbol','tf','wave_key','stop','targets','score','milestones')} |
            {'entry_ts_ms':stamp,'decision_ts_ms':c['decision_ts']*1000,'entry':observed_open})
    settlements = defaultdict(list)
    for symbol in sorted(symbols):
        pack=funding[symbol]
        a,b=np.searchsorted(pack['times'],[lo,hi],side='left')
        for event in pack['events'][a:b]:settlements[event['funding_ts_ms']].append((symbol,event))
    times = sorted(set(range(lo+stream.BAR_MS,hi+1,stream.BAR_MS)) | set(settlements) | set(proposed))
    engines = {(p['id'],cost):stream.SequentialPortfolio(lo,hi,p,scenario)
               for p in FAMILY for cost,scenario in SCENARIOS.items()}
    calls=0
    for stamp in times:
        entries = proposed.get(stamp,())
        events = settlements.get(stamp,())
        needed = {p['symbol'] for e in engines.values() for p in e.positions.values()
                  if e.internal[p['id']]['next_close_ms'] == stamp}
        bars = {}
        for symbol in needed:
            values = quote_at(quotes,symbol,stamp-stream.BAR_MS)
            bars[symbol] = dict(zip(('open','high','low','close','volume'),map(float,values))) | {'open_time_ms':stamp-stream.BAR_MS}
        for engine in engines.values():
            if engine.positions or entries or stamp == hi:
                engine.process(int(stamp),entries=entries,bars=bars,funding=events,funding_complete_through_ms=int(stamp))
                calls+=1
    metrics={}; node_files={}; counts=Counter(); max_curve_error=0.
    expected = r.read(BASE/'RESULTS.json')['annual'][str(year)]
    for (pid,cost),engine in engines.items():
        value=engine.finish()
        reference=baseline.ledger(year,pid,cost)
        compare(value['ledger'],reference['ledger'],f'{year}/{pid}/{cost}/ledger')
        compare(value['curve'],reference['curve'],f'{year}/{pid}/{cost}/curve')
        for k,n in value['metric'].items(): compare(n,expected[pid][cost][k],f'{year}/{pid}/{cost}/{k}')
        assert not value['execution_issues'],value['execution_issues']
        for position in value['ledger']:
            cash=sum((1 if f['side']=='SELL' else -1)*f['notional']-f['fee'] for f in position['fills'])+sum(f['cashflow'] for f in position['funding_events'])
            assert abs(cash-position['pnl'])<=TOL
        path=out/'nodes'/f'{year}_{pid}_{cost}.json.gz';path.parent.mkdir(exist_ok=True)
        with gzip.open(path,'wt',encoding='utf8') as f:json.dump(value,f,separators=(',',':'),allow_nan=False)
        node_files[str(path.relative_to(out))]=r.sha(path)
        metrics.setdefault(pid,{})[cost]=value['metric']
        counts['nodes']+=1;counts['scenario_trades']+=len(value['ledger'])
        counts['fills']+=sum(len(p['fills']) for p in value['ledger'])
        counts['funding_payments']+=sum(len(p['funding_events']) for p in value['ledger'])
        max_curve_error=max(max_curve_error,float(np.max(np.abs(np.asarray(value['curve'])[:,1]-np.asarray(reference['curve'])[:,1]))))
    saved={'year':year,'all_passed':True,'protocol_sha256':r.sha(out/'PROTOCOL.json'),
        'metadata_proposals':len(source),'symbols':len(symbols),'clock_instants':len(times),'engine_batches':calls,
        'counts':dict(counts),'max_curve_abs_error':max_curve_error,'metrics':metrics,'node_files':node_files}
    r.save(receipt,saved)
    print({'year':year,**dict(counts),'max_curve_error':max_curve_error},flush=True)
    return saved


def run():
    out=attempt(); preserve()
    metadata=r.read(ART/'ENTRY_METADATA.json'); views=r.read(BASE/'OBSERVED_VIEWS.json'); funding=v.load_funding()
    completed=[]
    try:
        for year in range(2020,2026):
            completed.append(year_replay(year,metadata,views,funding,out))
            r.save(out/'PROGRESS.json',{'completed_years':[x['year'] for x in completed],'goal_complete':False})
    except Exception as error:
        r.save(out/'FAILURE.json',{'error_type':type(error).__name__,'message':str(error),
            'completed_years':[x['year'] for x in completed],'source_snapshot_retained':True})
        raise
    total=Counter()
    for item in completed:total.update(item['counts'])
    assert total['nodes']==72 and total['scenario_trades']==12873
    result={'all_passed':True,**dict(total),'tests':tests(),
        'max_curve_abs_error':max(x['max_curve_abs_error'] for x in completed),
        'attempt_path':str(out),'attempt_protocol_sha256':r.sha(out/'PROTOCOL.json'),
        'inputs_sha256':r.sha(ART/'INPUTS.json'),
        'years':{str(x['year']):{'path':str(out/f'YEAR_{x["year"]}.json'),'sha256':r.sha(out/f'YEAR_{x["year"]}.json')} for x in completed},
        'all_accepted_execution_issues':0,'post2025_observations':0,'new_strategy_variants':0,
        'fresh_oos':False,'prospective_started':False,'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'VERIFICATION.json',result);print(result,flush=True)


def render(d):
    z=d['verification']
    return f'''# Kiểm chứng thực thi tuần tự — v4.0.24

**Đã đối chiếu thực thi trên dữ liệu lịch sử; chưa xác nhận OOS mới hoặc duyệt giao dịch thật.**

Luồng mới chỉ nhận giá mở cửa khi đến thời điểm vào lệnh, nến vừa đóng và sự kiện funding vừa xảy ra. Không nhận đường giá thoát, thời gian thoát hay lợi nhuận tương lai của lệnh. Hạn mức và khối lượng được tính khi nhận lệnh; trạng thái bận/cooldown được cập nhật khi lệnh thực sự đóng. Funding được xử lý trước lệnh thoát cùng timestamp, sau đó mới nhận lệnh mới.

## Kết quả đối chiếu

- {z['nodes']} tổ hợp: sáu cấu hình × sáu năm 2020–2025 × hai kịch bản chi phí.
- {z['scenario_trades']:,} bản ghi giao dịch, {z['fills']:,} nhóm khớp và {z['funding_payments']:,} khoản funding khớp sổ v4.0.21.
- Danh sách lệnh, lý do thoát, từ chối do hạn mức/cooldown, chi phí và mọi điểm đường vốn khớp trong dung sai tuyệt đối 1e-7; sai lệch NAV lớn nhất {z['max_curve_abs_error']:.3g} trên vốn gốc 100.
- {z['tests']['tests']} kiểm thử đạt, gồm khối lượng cố định, thoát từng phần, stop/ratchet, thứ tự funding, hạn mức cùng timestamp, lưu/khôi phục trạng thái và chặn tính trùng.
- Không có lệnh được nhận dính lỗi khớp trên nến không giao dịch trong bộ đối chiếu này. Thiếu nến hoặc thiếu xác nhận độ đầy đủ của luồng funding sẽ chặn việc tiến thời gian, không tự điền số 0.

Phí mỗi lần khớp giữ nguyên: VIP6 2,5 bps + trượt giá 10 bps; Regular 5 bps + trượt giá 50 bps. Funding dùng tỷ lệ thực, giá mark thay thế lịch sử vẫn được gắn nhãn trong sổ. Các nhóm khớp trong một nến là nhóm hạch toán theo giá bình quân khối lượng, không được coi là dữ liệu khớp thật của sàn.

## Phạm vi và bước tiếp theo

Đầu vào quyết định vẫn là danh sách ứng viên lịch sử đã khóa. Vòng này xác nhận bộ máy thực thi, chưa chứng minh một dịch vụ hoàn chỉnh tự phát hiện tín hiệu, chọn coin, xử lý vòng đời hợp đồng và nhận báo giá trực tuyến. Mô hình khớp theo OHLC cũng chưa xác nhận độ trễ, sổ lệnh hoặc thanh khoản thực tế.

Kết quả kinh tế v4.0.21 giữ nguyên; không có lợi nhuận mới hay alpha mới. Nhật ký bảo toàn {d['registry_entries']} mục. Dữ liệu 2020–2025 đã được sử dụng nghiên cứu, vì vậy phép đối chiếu này không tạo holdout mới. Chưa thu thập dữ liệu sau 2025 và chưa khởi chạy paper trading; phạm vi xác nhận OOS mới vẫn chờ lựa chọn của người dùng.
'''


def publish():
    preserve();verify_inputs()
    z=r.read(ART/'VERIFICATION.json');out=Path(z['attempt_path'])
    assert z['all_passed'] and z['attempt_protocol_sha256']==r.sha(out/'PROTOCOL.json')
    protocol=r.read(out/'PROTOCOL.json')
    for name,digest in protocol['sources'].items():assert r.sha(ROOT/name)==digest
    for item in z['years'].values():
        assert r.sha(item['path'])==item['sha256']
        for name,digest in r.read(item['path'])['node_files'].items():assert r.sha(out/name)==digest
    registry=r.read(PRIOR/'MINI_ALPHA_REGISTRY.json')
    registry['sequential_execution_v424']={'path':str(ART/'VERIFICATION.json'),'sha256':r.sha(ART/'VERIFICATION.json'),
        'new_alpha_entries':0,'fresh_oos':False,'scope':'Archived candidate-feed execution parity'}
    r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    assert registry['entries']==r.read(PRIOR/'MINI_ALPHA_REGISTRY.json')['entries']
    d={'verification':z,'registry_entries':len(registry['entries'])}
    r.save(ART/'REPORT_DATA.json',d);(ART/'REPORT.md').write_text(render(d),encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'REPORT_DATA.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'report_sha256':r.sha(ART/'REPORT.md'),
        'data_sha256':r.sha(ART/'REPORT_DATA.json'),'verification_sha256':r.sha(ART/'VERIFICATION.json')})
    r.save(ART/'PROGRESS.json',{'stage':'sequential_execution_reconciled_on_archived_candidate_feed',
        'next_action':'Verify bounded end-to-end decision/PIT/lifecycle/current-entry-quote integration before prospective activation. Do not label reused history fresh OOS.',
        'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    sources=dict(r.read(PRIOR/'CHECKPOINT.json')['additional_sources']);sources.update(protocol['sources'])
    files=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json')
    r.save(ART/'CHECKPOINT.json',{'files':{str(p.relative_to(ART)):r.sha(p) for p in files},
        'additional_sources':sources,'previous_files_preserved':len(r.read(PRIOR/'CHECKPOINT.json')['files']),
        'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    print({'protected_files':len(files),'registry_entries':len(registry['entries'])},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','run','publish'))
    globals()[p.parse_args().command]()
