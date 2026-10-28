"""Resolve monthly-sample extra rows against declared official daily repairs."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import requests
import universe_audit_v413 as v
import complete_universe_v413 as independent

r=v.r;ART=v.ART;OUT=ART/'daily_sample_reconciliation'


def register():
    v.verify_sources()
    if (OUT/'PROTOCOL.json').exists():raise FileExistsError('Daily sample reconciliation registered')
    source=r.read(ART/'OFFICIAL_SAMPLE_RESULTS.json');items=[x for x in source['results'] if x['local_extra_rows']]
    r.save(OUT/'PROTOCOL.json',{'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'purpose':'Verify every extra local row not present in the independently checked monthly archive against its declared official daily repair archive.',
        'selection':'All extra rows from the fixed385-symbol sample; no strategy results or performance selection.',
        'items':items,'source_result_sha256':r.sha(ART/'OFFICIAL_SAMPLE_RESULTS.json'),'self_sha256':r.sha(__file__),
        'independent_parser_sha256':r.sha(independent.__file__),'fresh_oos':False,'post_2025_rows_permitted':False})
    target=OUT/'source_snapshot'/Path(__file__).name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(__file__,target)


def run():
    protocol=r.read(OUT/'PROTOCOL.json');assert protocol['self_sha256']==r.sha(__file__) and protocol['independent_parser_sha256']==r.sha(independent.__file__)
    assert protocol['source_result_sha256']==r.sha(ART/'OFFICIAL_SAMPLE_RESULTS.json')
    results=[]
    with requests.Session() as session:
        for item in protocol['items']:
            symbol=item['symbol'];month=item['month'];start=r.utc(month+'-01');end=start+pd.offsets.MonthBegin()
            local=v.bounded_read(item['local_path'],start,end,with_identity=True).set_index('open_time').sort_index()
            monthly=independent.archive_frame(ART/'official_samples'/f'{symbol}-{month}.zip');extra=local.loc[local.index.difference(monthly.index)]
            assert len(extra)==item['local_extra_rows']
            catalog=[a for a in r.read(ART/'SOURCE_CATALOG.json')['files'] if a['path']==item['local_path']];assert len(catalog)==1
            assert r.sha(item['local_path'])==catalog[0]['expected_sha256']
            repaired=set(catalog[0]['gap_repairs']['repaired_dates'])
            for day in item['local_extra_dates']:
                assert day in repaired and '2020-01-01'<=day<='2025-12-31'
                url=f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/5m/{symbol}-5m-{day}.zip'
                path=OUT/f'{symbol}-{day}.zip';checksum=path.with_suffix('.zip.CHECKSUM')
                for destination,source in [(path,url),(checksum,url+'.CHECKSUM')]:
                    if not destination.exists():
                        response=session.get(source,timeout=45);response.raise_for_status();destination.write_bytes(response.content)
                assert r.sha(path)==checksum.read_text(encoding='utf8').split()[0]
                daily=independent.archive_frame(path);assert (daily.index.strftime('%Y-%m-%d')==day).all()
                subset=extra.loc[extra.index.strftime('%Y-%m-%d')==day]
                assert not len(subset.index.difference(daily.index)) and np.allclose(subset.to_numpy(),daily.loc[subset.index].to_numpy(),rtol=1e-12,atol=0)
                results.append({'symbol':symbol,'day':day,'rows_verified':len(subset),'source_url':url,'archive_sha256':r.sha(path),'checksum_file_sha256':r.sha(checksum)})
    assert sum(x['rows_verified'] for x in results)==sum(x['local_extra_rows'] for x in protocol['items'])
    r.save(OUT/'VERIFICATION.json',{'all_passed':True,'extra_rows_verified':sum(x['rows_verified'] for x in results),'daily_archives':len(results),
        'records':results,'protocol_sha256':r.sha(OUT/'PROTOCOL.json'),'source_results_sha256':r.sha(ART/'OFFICIAL_SAMPLE_RESULTS.json'),'post_2025_observations_loaded':0})
    print('All extra sample rows independently matched official daily archives:',sum(x['rows_verified'] for x in results),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['register','run']);args=parser.parse_args()
    register() if args.action=='register' else run()
