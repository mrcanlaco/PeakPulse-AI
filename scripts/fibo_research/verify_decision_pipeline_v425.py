"""Rebuild the entire bounded signal feed and replay sequential execution.

The offline signal scan vectorizes strictly trailing features but retains the
per-decision closed-bar slices. PIT membership is an already verified upstream
schedule, not a new online universe-discovery service. No post2025 observations.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import decision_feed_v425 as decision
import signal_snapshot_v423 as signals
import verify_stream_execution_v424 as execution

r=execution.r
ROOT=execution.ROOT
PRIOR=execution.ART
BASE=execution.BASE
ART=BASE.parent/'research_v4_0_25'
LIFECYCLE=BASE.parent/'research_v4_0_15'
START=r.utc('2020-01-01');END=r.utc('2026-01-01')
WORKER_BTC=None
WORKER_MEMBERS=None
WORKER_EVENTS=None


def preserve():
    p=r.read(PRIOR/'CHECKPOINT.json')
    for name,digest in p['files'].items():assert r.sha(PRIOR/name)==digest,name
    for name,digest in p['additional_sources'].items():assert r.sha(ROOT/name)==digest,name
    return p


def dependencies():
    return {str(p):r.sha(p) for p in [PRIOR/'CHECKPOINT.json',PRIOR/'ENTRY_METADATA.json',
        BASE/'OBSERVED_VIEWS.json',BASE/'funding/MANIFEST.json',LIFECYCLE/'MEMBERSHIP.json',LIFECYCLE/'EVENTS.json']}


def prepare():
    preserve()
    if (ART/'INPUTS.json').exists():verify_inputs();return
    members=r.read(LIFECYCLE/'MEMBERSHIP.json');views=r.read(BASE/'OBSERVED_VIEWS.json')
    symbols=sorted({a['symbol'] for rows in members.values() for a in rows})
    jobs=[]
    for symbol in symbols:
        for view in views[symbol]:
            label=symbol+'__'+view['phase']
            assert Path(label).name==label
            jobs.append({'label':label,'symbol':symbol,'view':view})
    assert len(symbols)==244 and len(jobs)==250
    r.save(ART/'INPUTS.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),'dependencies':dependencies(),
        'jobs':jobs,'btc_view':views['BTCUSDT'][0],'symbols':len(symbols),'contract_views':len(jobs),
        'months':len(members),'monthly_slots':sum(map(len,members.values())),
        'scope':'Rebuild decision metadata from raw bounded candle views using v423 signal-only scan, verified monthly PIT membership and known lifecycle events. Then feed observed entry opens and sequential execution.',
        'upstream_pit':'Reuse the independently verified v415 monthly schedule. This run verifies its use, not an independent reranking of all637 symbols.',
        'lifecycle_scope':'15 documented transitions, not an exhaustive exchangeInfo archive.',
        'parameters_changed':0,'data_end_exclusive':END.isoformat(),'fresh_oos':False,'goal_complete':False})
    print({'symbols':len(symbols),'contract_views':len(jobs)},flush=True)


def verify_inputs():
    p=r.read(ART/'INPUTS.json')
    for path,digest in p['dependencies'].items():assert r.sha(path)==digest,path
    return p


def tests():
    suites=list(ET.parse(ART/'TESTS.xml').getroot().iter('testsuite'))
    result={k:sum(int(a.get(k,0)) for a in suites) for k in ('tests','errors','failures','skipped')}
    assert result['tests']>=10 and result['errors']==result['failures']==result['skipped']==0
    return result


def attempt():
    verify_inputs();tests()
    sources=[Path(__file__),Path(decision.__file__),Path(signals.__file__),Path(execution.__file__),
        Path(execution.stream.__file__),ROOT/'tests/unit/fibo_short/test_decision_feed_v425.py']
    identity={'sources':{str(p.relative_to(ROOT)):r.sha(p) for p in sources},
        'inputs_sha256':r.sha(ART/'INPUTS.json'),'tests_sha256':r.sha(ART/'TESTS.xml')}
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    out=ART/'attempts'/digest[:16]
    if not (out/'PROTOCOL.json').exists():
        out.mkdir(parents=True,exist_ok=True)
        r.save(out/'PROTOCOL.json',{**identity,'registered_at_utc':datetime.now(timezone.utc).isoformat(),
            'signal_scan':'v423 formulas, same phase-local past data; no future trade simulation. Compare all reconstructed metadata exactly before economic replay.',
            'entry_sequence':'Signal close, monthly membership and trailing24h continuity, scheduled+5m open-only quote, lifecycle known by entry, ladder validation, portfolio admission.',
            'fresh_oos':False,'goal_complete':False})
        for source in sources:
            target=out/'sources'/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    p=r.read(out/'PROTOCOL.json');assert all(p[k]==value for k,value in identity.items())
    r.save(ART/'CURRENT_ATTEMPT.json',{'path':str(out),'protocol_sha256':r.sha(out/'PROTOCOL.json')})
    return out


def bounded_frame(view):
    assert r.sha(view['path'])==view['sha256']
    f=pd.read_parquet(view['path'],filters=[('open_time','>=',START),('open_time','<',END)])
    assert len(f) and f.index.is_unique and f.index.is_monotonic_increasing
    assert START<=f.index[0]<=f.index[-1]<END
    return f


def initialize_worker(btc_view,members,events):
    global WORKER_BTC,WORKER_MEMBERS,WORKER_EVENTS
    h=r.h1_frame(bounded_frame(btc_view))
    WORKER_BTC={tf:r.calc_htf_features_no_bfill(r.resample_1h_to_htf(h,tf)) for tf in ('4h','1d')}
    WORKER_MEMBERS=members;WORKER_EVENTS=events


def collect_job(job,out_string):
    out=Path(out_string)
    f=bounded_frame(job['view']);h=r.h1_frame(f)
    raw=signals._collect_closed(job['symbol'],h,WORKER_BTC,
        entry_start_ts=START,entry_end_ts=END-pd.Timedelta(days=5,hours=1))
    raw.sort(key=lambda a:(a['decision_time'],a['tf']))
    feed=decision.DecisionFeed(WORKER_MEMBERS,WORKER_EVENTS,START,END)
    hourly=r.epoch_seconds(h.index)
    stamps=r.epoch_seconds(f.index)
    opens=f.open.to_numpy()
    candidates=[]
    for snap in raw:
        t=r.utc(snap['decision_time']);ts=int(t.timestamp())
        left,right=np.searchsorted(hourly,[ts-24*3600,ts],side='left')
        cid=feed.signal(snap,as_of=t,past_hour_opens=h.index[left:right])
        if cid is None:continue
        due=ts+300
        index=np.searchsorted(stamps,due)
        quote=None
        if index<len(stamps) and stamps[index]==due:
            quote={'symbol':job['symbol'],'open_time_ms':due*1000,'open':float(opens[index])}
        item=feed.entry_open(cid,as_of=pd.Timestamp(due,unit='s',tz='UTC'),quote=quote)
        if item is not None:candidates.append(item)
    assert not feed.pending
    file=out/'signals'/f'{job["label"]}.json.gz';file.parent.mkdir(exist_ok=True)
    value={'symbol':job['symbol'],'phase':job['view']['phase'],'view_sha256':job['view']['sha256'],
        'raw_signal_count':len(raw),'counts':dict(feed.counts),'candidates':candidates,'decision_receipts':feed.receipts,
        'hourly_bars':len(h),'source_first_open':f.index[0].isoformat(),'source_last_open':f.index[-1].isoformat()}
    with gzip.open(file,'wt',encoding='utf8') as fh:json.dump(value,fh,separators=(',',':'),allow_nan=False)
    return job['label'],{'path':str(file),'sha256':r.sha(file),'raw_signals':len(raw),'candidates':len(candidates),'counts':dict(feed.counts)}


def collect(workers=3):
    out=attempt();p=verify_inputs();preserve()
    progress_path=out/'COLLECTION_PROGRESS.json'
    progress=r.read(progress_path) if progress_path.exists() else {'protocol_sha256':r.sha(out/'PROTOCOL.json'),'jobs':{}}
    assert progress['protocol_sha256']==r.sha(out/'PROTOCOL.json')
    for item in progress['jobs'].values():assert r.sha(item['path'])==item['sha256']
    pending=[j for j in p['jobs'] if j['label'] not in progress['jobs']]
    members=r.read(LIFECYCLE/'MEMBERSHIP.json');events=r.read(LIFECYCLE/'EVENTS.json')['events']
    with ProcessPoolExecutor(max_workers=workers,initializer=initialize_worker,initargs=(p['btc_view'],members,events)) as pool:
        futures=[pool.submit(collect_job,j,str(out)) for j in pending]
        for future in as_completed(futures):
            label,item=future.result();progress['jobs'][label]=item;r.save(progress_path,progress)
            print(f'Rebuilt signals {len(progress["jobs"])}/{len(p["jobs"])} {label}: {item["candidates"]}',flush=True)
    rebuilt=[];counts=Counter();raw_signals=0
    for label,item in sorted(progress['jobs'].items()):
        assert r.sha(item['path'])==item['sha256']
        with gzip.open(item['path'],'rt',encoding='utf8') as fh:value=json.load(fh)
        rebuilt.extend(value['candidates']);counts.update(value['counts']);raw_signals+=value['raw_signal_count']
    assert len({c['id'] for c in rebuilt})==len(rebuilt),'Duplicate candidate across contract identities'
    rebuilt.sort(key=lambda c:(c['entry_ts'],-c['score'],c['symbol'],c['tf']))
    r.save(out/'ENTRY_METADATA.json',rebuilt)
    previous=r.read(PRIOR/'ENTRY_METADATA.json');old={c['id']:c for c in previous};new={c['id']:c for c in rebuilt}
    missing=sorted(set(old)-set(new));extra=sorted(set(new)-set(old))
    changed=[{'id':cid,'before':old[cid],'after':new[cid]} for cid in sorted(set(old)&set(new)) if old[cid]!=new[cid]]
    comparison={'all_passed':not missing and not extra and not changed,'cases':len(p['jobs']),'symbols':p['symbols'],
        'raw_signals':raw_signals,'reconstructed_candidates':len(rebuilt),'baseline_candidates':len(previous),
        'missing_ids':missing,'extra_ids':extra,'changed':changed,'counts':dict(counts),
        'entry_metadata_sha256':r.sha(out/'ENTRY_METADATA.json'),'baseline_entry_metadata_sha256':r.sha(PRIOR/'ENTRY_METADATA.json'),
        'collection_progress_sha256':r.sha(progress_path),'protocol_sha256':r.sha(out/'PROTOCOL.json'),
        'post2025_observations':0,'fresh_oos':False,'goal_complete':False}
    r.save(out/'METADATA_COMPARISON.json',comparison)
    print({k:v for k,v in comparison.items() if k not in ('missing_ids','extra_ids','changed','counts')},flush=True)
    assert comparison['all_passed'],f'Metadata differences retained: missing={len(missing)}, extra={len(extra)}, changed={len(changed)}'


def replay():
    out=attempt();p=verify_inputs();preserve()
    comparison=r.read(out/'METADATA_COMPARISON.json')
    assert comparison['all_passed'] and comparison['entry_metadata_sha256']==r.sha(out/'ENTRY_METADATA.json')
    assert comparison['collection_progress_sha256']==r.sha(out/'COLLECTION_PROGRESS.json')
    metadata=r.read(out/'ENTRY_METADATA.json');views=r.read(BASE/'OBSERVED_VIEWS.json');funding=execution.v.load_funding()
    folder=out/'execution';folder.mkdir(exist_ok=True)
    protocol={'signal_protocol_sha256':r.sha(out/'PROTOCOL.json'),'comparison_sha256':r.sha(out/'METADATA_COMPARISON.json'),
        'execution_source_sha256':r.sha(execution.stream.__file__),'scenarios':execution.SCENARIOS,
        'family':execution.FAMILY,'fresh_oos':False,'goal_complete':False}
    if (folder/'PROTOCOL.json').exists():assert r.read(folder/'PROTOCOL.json')==protocol
    else:r.save(folder/'PROTOCOL.json',protocol)
    years=[]
    for year in range(2020,2026):years.append(execution.year_replay(year,metadata,views,funding,folder))
    total=Counter()
    for item in years:total.update(item['counts'])
    assert total['nodes']==72 and total['scenario_trades']==12873
    result={'all_passed':True,**dict(total),'signal_jobs':comparison['cases'],'symbols':comparison['symbols'],
        'raw_signals':comparison['raw_signals'],'reconstructed_candidates':len(metadata),'metadata_exact_match':True,
        'max_curve_abs_error':max(a['max_curve_abs_error'] for a in years),'tests':tests(),
        'previous_execution_tests':r.read(PRIOR/'VERIFICATION.json')['tests'],
        'attempt_path':str(out),'attempt_protocol_sha256':r.sha(out/'PROTOCOL.json'),
        'comparison_sha256':r.sha(out/'METADATA_COMPARISON.json'),
        'year_receipts':{str(y['year']):{'path':str(folder/f'YEAR_{y["year"]}.json'),'sha256':r.sha(folder/f'YEAR_{y["year"]}.json')} for y in years},
        'inputs_sha256':r.sha(ART/'INPUTS.json'),'post2025_observations':0,
        'cached_pit_schedule_used':True,'live_service_verified':False,'fresh_oos':False,'prospective_started':False,
        'goal_complete':False,'live_signoff':'NOT_GRANTED'}
    r.save(ART/'VERIFICATION.json',result);print(result,flush=True)


def render(data):
    z=data['verification']
    return f'''# Tái dựng tín hiệu và thực thi lịch sử — v4.0.25

**Luồng lịch sử đã được nối và đối chiếu; chiến lược chưa có OOS mới và chưa được duyệt giao dịch thật.**

Đã quét lại {z['symbols']} mã trong {z['signal_jobs']} giai đoạn hợp đồng từ nến 5 phút giới hạn trong 2020–2025. Bộ phát hiện tín hiệu v4.0.23 chỉ dùng đặc trưng quá khứ và nến đã đóng tại từng quyết định, không mô phỏng trước kết quả lệnh. Phép quét offline tính các đặc trưng theo lô; đây chưa phải chứng nhận dịch vụ dữ liệu trực tuyến hoặc độ trễ vận hành.

## Danh sách quyết định tự tái dựng

Từ {z['raw_signals']:,} tín hiệu thô, áp dụng danh sách coin theo tháng, 24 giờ nến đã đóng, lịch vào lệnh sau 5 phút, thông báo vòng đời hợp đồng đã biết và kiểm tra giá mở cửa. Thu được {z['reconstructed_candidates']:,} ứng viên, khớp chính xác mọi trường với danh sách v4.0.24. Không dùng danh sách cũ để sinh tín hiệu hoặc lựa chọn ứng viên; chỉ đọc nó để so sánh sau khi tái dựng xong. Mọi quyết định loại được lưu theo mã và lý do, không loại theo lợi nhuận tương lai.

Danh sách coin theo tháng là lịch PIT v4.0.15 đã được kiểm chứng độc lập, gồm 72 tháng và 3.181 vị trí thành viên. Vòng này kiểm tra cách sử dụng lịch đó, không tuyên bố đã xây dịch vụ xếp hạng trực tuyến mới. Hồ sơ vòng đời gồm 15 chuyển đổi đã biết, chưa phải danh mục exchangeInfo lịch sử đầy đủ.

## Đối chiếu thực thi

Đã đưa chính danh sách tự tái dựng vào bộ máy tuần tự: {z['nodes']} tổ hợp, {z['scenario_trades']:,} bản ghi giao dịch, {z['fills']:,} nhóm khớp và {z['funding_payments']:,} khoản funding khớp v4.0.21. Sai lệch đường NAV lớn nhất là {z['max_curve_abs_error']:.3g} trên vốn gốc 100.

Có {z['tests']['tests']} kiểm thử mới cho điều phối tín hiệu/giá vào, cùng {z['previous_execution_tests']['tests']} kiểm thử thực thi trước đó được bảo toàn. Giá vào chỉ nhận trường OPEN tại thời điểm khớp dự kiến; dữ liệu OHLC tương lai bị từ chối. Thông báo đóng hợp đồng xuất hiện giữa lúc có tín hiệu và lúc vào lệnh được kiểm tra ở thời điểm vào lệnh.

Hai kịch bản phí từng lần khớp giữ nguyên: VIP6 2,5 bps + trượt giá 10 bps; Regular 5 bps + trượt giá 50 bps. Funding dùng tỷ lệ thực với các mark thay thế cũ được gắn nhãn. Mô hình khớp OHLC chưa chứng minh thanh khoản, sổ lệnh hay độ trễ của giao dịch thật.

## Quyết định hiện tại

Kết quả lợi nhuận không thay đổi và không có alpha mới được ghi nhận. Nhật ký giữ nguyên {data['registry_entries']} mục nghiên cứu. Dữ liệu 2020–2025 đã được xem qua nhiều vòng; kiểm chứng kỹ thuật không biến chúng thành holdout mới. Chưa thu thập dữ liệu sau 2025 hoặc khởi chạy paper trading. Phạm vi xác nhận OOS mới còn chờ lựa chọn của người dùng.
'''


def publish():
    prior=preserve();verify_inputs();z=r.read(ART/'VERIFICATION.json');out=Path(z['attempt_path'])
    assert z['all_passed'] and z['attempt_protocol_sha256']==r.sha(out/'PROTOCOL.json')
    assert z['comparison_sha256']==r.sha(out/'METADATA_COMPARISON.json')
    for name,digest in r.read(out/'PROTOCOL.json')['sources'].items():assert r.sha(ROOT/name)==digest
    for item in r.read(out/'COLLECTION_PROGRESS.json')['jobs'].values():assert r.sha(item['path'])==item['sha256']
    for item in z['year_receipts'].values():
        assert r.sha(item['path'])==item['sha256']
        for name,digest in r.read(item['path'])['node_files'].items():assert r.sha(out/'execution'/name)==digest
    registry=r.read(PRIOR/'MINI_ALPHA_REGISTRY.json')
    registry['decision_pipeline_v425']={'path':str(ART/'VERIFICATION.json'),'sha256':r.sha(ART/'VERIFICATION.json'),
        'new_alpha_entries':0,'fresh_oos':False,'scope':'Reconstructed signal feed with verified cached PIT schedule and sequential historical execution'}
    r.save(ART/'MINI_ALPHA_REGISTRY.json',registry)
    assert registry['entries']==r.read(PRIOR/'MINI_ALPHA_REGISTRY.json')['entries']
    data={'verification':z,'registry_entries':len(registry['entries'])}
    r.save(ART/'REPORT_DATA.json',data);(ART/'REPORT.md').write_text(render(data),encoding='utf8')
    assert (ART/'REPORT.md').read_text(encoding='utf8')==render(r.read(ART/'REPORT_DATA.json'))
    r.save(ART/'REPORT_CONSISTENCY.json',{'all_passed':True,'report_sha256':r.sha(ART/'REPORT.md'),
        'report_data_sha256':r.sha(ART/'REPORT_DATA.json'),'verification_sha256':r.sha(ART/'VERIFICATION.json')})
    r.save(ART/'PROGRESS.json',{'stage':'reconstructed_decision_feed_and_execution_reconciled',
        'next_action':'Review what remains for a locked prospective protocol versus the unresolved OOS scope; do not retune historical thresholds to manufacture a passing result.',
        'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    files=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='CHECKPOINT.json')
    sources=dict(prior['additional_sources']);sources.update(r.read(out/'PROTOCOL.json')['sources'])
    r.save(ART/'CHECKPOINT.json',{'files':{str(p.relative_to(ART)):r.sha(p) for p in files},
        'additional_sources':sources,'previous_files_preserved':len(prior['files']),
        'goal_complete':False,'live_signoff':'NOT_GRANTED'})
    print({'protected_files':len(files),'registry_entries':len(registry['entries'])},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('prepare','collect','replay','publish'))
    parser.add_argument('--workers',type=int,default=3);args=parser.parse_args()
    if args.command=='collect':collect(args.workers)
    else:globals()[args.command]()
