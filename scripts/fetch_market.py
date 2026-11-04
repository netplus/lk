"""Optional AKShare adapter. Writes local pending snapshots, never verified data.
Requires an authorized data source, network access and separately installed AKShare.
Live retrieval was NOT completed during repository initialization.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from validate import check_ohlc, number

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['日期','开盘','收盘','最高','最低','成交量','成交额','换手率']

def worker(args: argparse.Namespace) -> None:
    import akshare as ak
    df = ak.stock_zh_a_hist(symbol=args.symbol, period='daily',
                           start_date=args.start.replace('-',''),
                           end_date=args.end.replace('-',''), adjust=args.adjust)
    if df.empty or any(c not in df.columns for c in FIELDS):
        raise ValueError('Empty response or upstream schema changed')
    rows = []; seen = set()
    for record in df.to_dict('records'):
        day = str(record['日期'])[:10]
        if day in seen or not args.start <= day <= args.end:
            raise ValueError('Duplicate/out-of-window date')
        seen.add(day)
        if '股票代码' in record and str(record['股票代码']).zfill(6) != args.symbol:
            raise ValueError('Upstream symbol mismatch')
        row = {k:str(record[v]) for k,v in [('open','开盘'),('high','最高'),('low','最低'),('close','收盘')]}
        check_ohlc(row)
        lots = number(str(record['成交量']))
        amount = number(str(record['成交额']))
        turnover = number(str(record['换手率']))
        if lots < 0 or amount < 0 or turnover < 0:
            raise ValueError('Negative trading measure')
        row.update(symbol=args.symbol+'.SZ', date=day,
                   volume_shares=str(lots*100), amount_cny=str(amount),
                   turnover_pct=str(turnover), adjustment=args.adjust or 'none',
                   status='pending_independent_crosscheck')
        rows.append(row)
    rows.sort(key=lambda r:r['date'])
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT/'.cache'/f'{args.symbol}_{args.adjust or "raw"}_{stamp}'
    folder.mkdir(parents=True,exist_ok=False)
    # This is the adapter-returned table, not an HTTP-body archive.
    raw = df.to_csv(index=False).encode('utf-8')
    (folder/'adapter_returned.csv').write_bytes(raw)
    with (folder/'normalized_pending.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        w.writeheader();w.writerows(rows)
    metadata = {'symbol':args.symbol,'requested_start':args.start,'requested_end':args.end,
                'actual_start':rows[0]['date'],'actual_end':rows[-1]['date'],
                'adjustment':args.adjust or 'none','rows':len(rows),'retrieved_utc':stamp,
                'akshare_version':importlib.metadata.version('akshare'),
                'source':'Eastmoney via AKShare stock_zh_a_hist',
                'schema_reference':'https://akshare.akfamily.xyz/data/stock/stock_quote.html',
                'adapter_table_sha256':hashlib.sha256(raw).hexdigest(),
                'coverage_calendar_verified':False,'redistribution_rights_verified':False,
                'status':'pending_independent_crosscheck'}
    (folder/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(folder)

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start',default='2023-11-04');p.add_argument('--end',default='2026-11-03')
    p.add_argument('--symbol',choices=['002466','002460'])
    p.add_argument('--adjust',choices=['all','none','qfq','hfq'],default='all')
    p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--authorized-source',action='store_true',help='Confirm source usage is permitted; does not authorize public redistribution')
    a=p.parse_args()
    start=datetime.strptime(a.start,'%Y-%m-%d').date();end=datetime.strptime(a.end,'%Y-%m-%d').date()
    if start>end or end>=datetime.now(timezone.utc).date():
        p.error('Use an ordered range ending before today; no intraday rows')
    if not a.authorized_source:
        p.error('Source permission must be confirmed with --authorized-source')
    if a.worker:
        if not a.symbol:p.error('Worker requires symbol')
        if a.adjust == 'all':p.error('Worker requires one adjustment mode')
        if a.adjust == 'none':a.adjust = ''
        worker(a);return
    failures=[]
    for symbol in ([a.symbol] if a.symbol else ['002466','002460']):
        for adjust in (['none','qfq','hfq'] if a.adjust == 'all' else [a.adjust]):
            command=[sys.executable,__file__,'--worker','--authorized-source','--symbol',symbol,
                     '--start',a.start,'--end',a.end,'--adjust',adjust]
            try:
                subprocess.run(command,check=True,timeout=90)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
                failures.append(f'{symbol}:{adjust or "none"}:{type(exc).__name__}')
            time.sleep(1)
    if failures:
        print(json.dumps({'status':'INCOMPLETE','failures':failures},indent=2),file=sys.stderr)
        raise SystemExit(1)
    print('Downloaded pending snapshots only; calendar, corporate actions and second-source verification still required.')

if __name__ == '__main__':
    main()
