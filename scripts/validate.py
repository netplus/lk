"""Offline integrity checks. Passing these checks is NOT a backtest permission."""
from __future__ import annotations
import argparse
import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
METRICS = ('revenue_cny', 'net_income_parent_cny',
           'net_income_parent_excl_nonrec_cny', 'ocf_cny')

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

def number(value: str) -> Decimal:
    d = Decimal(value)
    if not d.is_finite():
        raise ValueError('Non-finite numeric value')
    return d

def check_ohlc(row: dict[str, str]) -> None:
    o, h, l, c = (number(row[k]) for k in ('open', 'high', 'low', 'close'))
    if not (Decimal(0) < l <= min(o, c) <= max(o, c) <= h):
        raise ValueError(f'Invalid OHLC: {row}')

def quarter_difference(current: str, previous: str) -> Decimal:
    return number(current) - number(previous)

def next_session(publication_date: str, sessions: list[str]) -> str:
    """Conservative date-only rule; caller must supply an official calendar."""
    p = date.fromisoformat(publication_date)
    for day in sorted(set(sessions)):
        if date.fromisoformat(day) > p:
            return day
    raise ValueError('Calendar does not cover next session')

def available_asof(source_date: str, decision_date: str) -> bool:
    # Date-only release: never make it available on the release date itself.
    return date.fromisoformat(source_date) < date.fromisoformat(decision_date)

def relative_volume(previous: list[float], current: float, window: int = 20) -> float:
    if window < 1 or len(previous) < window or current < 0:
        raise ValueError('Insufficient or invalid volume history')
    values = previous[-window:]
    if any(x < 0 for x in values) or median(values) <= 0:
        raise ValueError('Invalid volume denominator')
    return current / median(values)

def pe_or_none(market_cap: str, net_income: str) -> Decimal | None:
    m, n = number(market_cap), number(net_income)
    if m < 0:
        raise ValueError('Negative market capitalization')
    return m / n if n > 0 else None

def validate(root: Path = ROOT) -> dict:
    sources = {r['source_id']: r for r in read_csv(root/'data/sources.csv')}
    quarters = read_csv(root/'data/financials/quarterly.csv')
    cumul = read_csv(root/'data/financials/cumulative_2026.csv')
    annuals = read_csv(root/'data/financials/annual_derived.csv')
    balances = read_csv(root/'data/financials/balance_2026.csv')
    market = read_csv(root/'data/market/staging_display.csv')
    coverage = json.loads((root/'data/coverage.json').read_text())
    keys = set()
    for row in quarters:
        key = row['symbol'], row['period_end']
        if key in keys:
            raise ValueError(f'Duplicate quarter: {key}')
        keys.add(key)
        ids = row['source_ids'].split(' | ')
        for sid in ids:
            if sid not in sources or sources[sid]['symbol'] != row['symbol']:
                raise ValueError(f'Source identity mismatch: {sid}')
        if row['source_published_date'] != max(sources[x]['source_published_date'] for x in ids):
            raise ValueError('Derived value must use latest input availability')
        if row['period_end'] >= row['source_published_date']:
            raise ValueError('Period/publication dates invalid')
        for metric in METRICS:
            number(row[metric])
    for row in annuals + cumul:
        subset = [q for q in quarters if q['symbol'] == row['symbol']
                  and q['period_end'][:4] == row['period_end'][:4]
                  and q['period_end'] <= row['period_end']]
        for metric in METRICS:
            actual = sum((number(q[metric]) for q in subset), Decimal(0))
            if actual != number(row[metric]):
                raise ValueError(f'Quarter reconciliation failed: {row["symbol"]} {row["period_end"]} {metric}')
    for row in balances:
        if not (number(row['total_assets_cny']) > number(row['equity_parent_cny']) > 0):
            raise ValueError('Asset/equity order invalid')
    market_keys = set()
    for row in market:
        check_ohlc(row)
        key = row['symbol'], row['date']
        if key in market_keys or row['date'] > coverage['market_target_end']:
            raise ValueError('Duplicate or out-of-cutoff market observation')
        market_keys.add(key)
        if row['status'] != 'staging_not_for_returns_or_backtest':
            raise ValueError('Unverified web samples must remain staged')
    if len(quarters) != coverage['financial_quarter_rows'] or len(market) != coverage['market_staging_rows']:
        raise ValueError('Coverage manifest mismatch')
    if coverage['backtest_gate'] != 'BLOCKED':
        raise ValueError('Bootstrap data cannot enable backtesting')
    return {'integrity': 'PASS', 'financial_rows': len(quarters),
            'financial_metric_values': len(quarters)*len(METRICS),
            'source_reports': len(sources), 'market_staging_rows': len(market),
            'backtest_gate': 'BLOCKED', 'valuation_gate': coverage['valuation_gate']}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-backtest-ready', action='store_true')
    args = parser.parse_args()
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_backtest_ready and result['backtest_gate'] != 'READY':
        raise SystemExit(2)
