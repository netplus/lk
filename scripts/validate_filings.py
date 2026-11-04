"""Validate selected annual tables and generated MD caches, not investment readiness."""
from __future__ import annotations
import json
from decimal import Decimal
from pathlib import Path
try:
    from .build_filing_md import ROOT, CORE, rows, dec, build_outputs
except ImportError:
    from build_filing_md import ROOT, CORE, rows, dec, build_outputs


def validate(root: Path = ROOT) -> dict:
    sources={r['source_id']:r for r in rows(root,'data/sources.csv')}
    annual=rows(root,'data/financials/annual_reported.csv')
    quarters=rows(root,'data/financials/quarterly.csv')
    segments=rows(root,'data/financials/annual_segments.csv')
    volumes=rows(root,'data/operations/annual_volumes.csv')
    keys=set()
    for r in annual:
        sid=r['source_id'];key=(r['symbol'],r['period_end'])
        if key in keys:raise ValueError('Duplicate annual')
        keys.add(key)
        if sources[sid]['symbol']!=r['symbol'] or sources[sid]['period_end']!=r['period_end']:
            raise ValueError('Annual source identity mismatch')
        if r['scope']!='PRC_GAAP_consolidated':raise ValueError('Wrong accounting scope')
        qs=[q for q in quarters if q['symbol']==r['symbol'] and q['period_end'][:4]==r['period_end'][:4]]
        if len(qs)!=4:raise ValueError('Incomplete annual quarters')
        for k in CORE:
            if sum((dec(q[k]) for q in qs),Decimal(0))!=dec(r[k]):raise ValueError('Annual/quarter mismatch')
        cash_delta=sum((dec(r[k]) for k in ['ocf_cny','investing_cf_cny','financing_cf_cny','fx_cash_effect_cny']),Decimal(0))
        if cash_delta!=dec(r['cash_equivalents_end_cny'])-dec(r['cash_equivalents_begin_cny']):
            raise ValueError('Consolidated cash reconciliation failed: '+sid)
        ss=[s for s in segments if s['source_id']==sid]
        if sum((dec(s['revenue_cny']) for s in ss),Decimal(0))!=dec(r['revenue_cny']):
            raise ValueError('Segment revenue reconciliation failed')
        if not r['minority_dividends_cash_cny'] and r['minority_dividends_status']!='source_line_blank_not_imputed':
            raise ValueError('Blank minority dividend must remain explicit')
    unique=set()
    for r in segments:
        key=(r['source_id'],r['product_code'])
        if key in unique:raise ValueError('Duplicate segment')
        unique.add(key)
        if sources[r['source_id']]['symbol']!=r['symbol']:raise ValueError('Segment identity mismatch')
        if r['cost_cny']:
            margin=(dec(r['revenue_cny'])-dec(r['cost_cny']))/dec(r['revenue_cny'])*100
            if abs(margin-dec(r['gross_margin_reported_pct']))>Decimal('.0051'):
                raise ValueError('Reported gross margin mismatch: '+r['source_id']+'/'+r['product_code'])
        elif r['cost_status']!='not_extracted' or r['gross_margin_reported_pct']:
            raise ValueError('Missing cost must not become zero')
    unique=set()
    for r in volumes:
        key=(r['source_id'],r['product_code'])
        if key in unique:raise ValueError('Duplicate volume')
        unique.add(key)
        if sources[r['source_id']]['symbol']!=r['symbol']:raise ValueError('Volume identity mismatch')
        expected='tonne_as_reported' if r['symbol']=='002466.SZ' else 'tonne_LCE'
        if r['unit']!=expected:raise ValueError('Unverified volume normalization')
        if any(dec(r[k])<0 for k in ['production','sales','inventory_end']):raise ValueError('Negative volume')
    expected=build_outputs(root)
    for path,text in expected.items():
        p=root/path
        if not p.exists() or p.read_bytes()!=text.encode():raise ValueError('Stale generated cache: '+path)
    manifest=json.loads((root/'data/filing_cache_manifest.json').read_text())
    if len(manifest['reports'])!=12 or manifest['full_reports_converted']:
        raise ValueError('Wrong cache coverage claim')
    coverage=json.loads((root/'data/coverage.json').read_text())
    if coverage['backtest_gate']!='BLOCKED' or coverage['valuation_gate']!='BLOCKED':
        raise ValueError('Selective filing cache cannot unlock valuation/backtesting')
    return dict(integrity='PASS',annual_rows=len(annual),segment_rows=len(segments),volume_rows=len(volumes),
                filing_md_count=len(manifest['reports']),backtest_gate='BLOCKED',valuation_gate='BLOCKED')

if __name__=='__main__':print(json.dumps(validate(),ensure_ascii=False,indent=2))
