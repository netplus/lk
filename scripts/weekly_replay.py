"""Auditable weekly replay primitives. No downloads, real orders or default signals.
Missing data raises an error; it is never interpreted as a 0%-return cash strategy.
The public CLI only audits readiness. Integration with a verified data feed is pending.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median, stdev

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments' / 'weekly_replay_v1'
SYMBOLS = ('002466.SZ', '002460.SZ')

class DataGap(ValueError):
    pass

def aware(value: str) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise DataGap('Timezone-aware timestamps required')
    return stamp

def eligible_evidence(rows: list[dict], cutoff: str) -> list[dict]:
    """Filter by publication availability, NOT accounting period or retrieval date."""
    t = aware(cutoff)
    eligible = []
    for row in rows:
        if row.get('status') != 'verified' or not row.get('source_id'):
            continue
        if aware(row['available_at']) <= t:
            eligible.append(row)
    return eligible

def recommend(packet: dict, evidence: list[dict]) -> dict[str, float]:
    """V1 mapping of audited research states, NOT a trained forecasting model.
    State construction must be audited separately and uses only eligible evidence.
    """
    valid = {r['evidence_id'] for r in eligible_evidence(evidence, packet['cutoff'])}
    def checked(item: dict, allowed: tuple[str, ...]) -> str:
        refs = item.get('evidence_ids', [])
        if item.get('state') not in allowed or not refs or not set(refs) <= valid:
            raise DataGap('Unknown state or missing/as-yet-unpublished evidence')
        return item['state']
    industry = checked(packet['industry'], ('improving', 'stable', 'deteriorating'))
    if set(packet['companies']) != set(SYMBOLS):
        raise DataGap('Both companies must be assessed; missing is not neutral')
    weights = {}
    for symbol in SYMBOLS:
        company = packet['companies'][symbol]
        business = checked(company['business'], ('improving', 'stable', 'impaired'))
        valuation = checked(company['valuation'], ('attractive', 'fair', 'expensive'))
        market = checked(company['price_volume'], ('supportive', 'neutral', 'adverse'))
        if industry == 'deteriorating' or business == 'impaired' or valuation == 'expensive':
            weight = 0.0
        elif industry == 'improving' and business == 'improving' and valuation == 'attractive':
            weight = 0.4
        else:
            weight = 0.2
        if market == 'adverse':
            weight = min(weight, 0.2)
        weights[symbol] = weight
    return weights

def fees(notional: float, side: str, cfg: dict) -> float:
    if notional <= 0:
        return 0.0
    commission = max(cfg['minimum_commission_cny'], notional * cfg['commission_rate'])
    transfer = notional * cfg['transfer_fee_rate']
    stamp = notional * cfg['sell_stamp_rate'] if side == 'sell' else 0.0
    return round(commission + transfer + stamp, 2)

def rebalance(day: str, cash: float, holdings: dict[str, int], weights: dict[str, float],
              bars: dict[str, dict], past_volume: dict[str, list[float]], cfg: dict,
              receivables: float = 0.0) -> tuple[float, dict[str, int], list[dict]]:
    """Execute precommitted weights at next session open, sells before buys.
    Capacity uses PREVIOUS 20-session volume, never the execution day's full volume.
    No borrowed money, shorts, fractional shares or same-day round-trip buying/selling.
    """
    if not weights or any(w < 0 for w in weights.values()) or sum(weights.values()) > 1.0000001:
        raise DataGap('Invalid weights')
    symbols = sorted(set(holdings) | set(weights))
    if set(symbols) - bars.keys():
        raise DataGap('Missing execution bars')
    for s in symbols:
        bar = bars[s]
        if bar['open'] <= 0 or bar['low'] > min(bar['open'], bar['close']) or bar['high'] < max(bar['open'], bar['close']):
            raise DataGap('Invalid unadjusted OHLC')
        if len(past_volume.get(s, [])) < 20:
            raise DataGap('Missing prior liquidity window')
    h = dict(holdings)
    nav = cash + receivables + sum(h.get(s, 0) * bars[s]['open'] for s in symbols)
    lot = cfg['lot_size']
    desired = {s: math.floor(nav * weights.get(s, 0) / bars[s]['open'] / lot) * lot for s in symbols}
    trades = []
    for side in ('sell', 'buy'):
        for s in symbols:
            current = h.get(s, 0)
            delta = desired[s] - current
            if (side == 'buy' and delta <= 0) or (side == 'sell' and delta >= 0):
                continue
            b = bars[s]
            limit_hit = b['open'] >= b['upper_limit'] if side == 'buy' else b['open'] <= b['lower_limit']
            if b['suspended'] or limit_hit:
                trades.append({'date': day, 'symbol': s, 'side': side, 'quantity': 0, 'status': 'blocked_at_open'})
                continue
            cap = math.floor(median(past_volume[s][-20:]) * cfg['participation_limit'] / lot) * lot
            quantity = min(abs(delta), cap)
            # Zero target can close an existing odd lot; partial orders remain board lots.
            if not (side == 'sell' and desired[s] == 0 and quantity == current):
                quantity = quantity // lot * lot
            price = round(b['open'] * (1 + cfg['slippage_rate'] * (1 if side == 'buy' else -1)), 2)
            # Clipping to the day's high/low would use future information; reject instead.
            if price > b['upper_limit'] or price < b['lower_limit']:
                continue
            if side == 'buy':
                while quantity > 0 and quantity * price + fees(quantity * price, side, cfg) > cash + 1e-8:
                    quantity -= lot
            if quantity <= 0:
                continue
            amount = quantity * price
            charge = fees(amount, side, cfg)
            cash = round(cash + (amount - charge if side == 'sell' else -amount - charge), 2)
            h[s] = current + (-quantity if side == 'sell' else quantity)
            trades.append({'date': day, 'symbol': s, 'side': side, 'quantity': quantity,
                           'price': price, 'fees': charge, 'status': 'filled'})
    if cash < -0.001 or any(q < 0 for q in h.values()):
        raise AssertionError('Leverage or short position created')
    return cash, h, trades

def simulate(sessions: list[str], prices: dict[tuple[str, str], dict],
             decisions: dict[str, dict], actions: list[dict], volumes: dict[str, list[float]],
             cfg: dict) -> dict:
    """Replay a COMPLETE approved decision stream. No-decision days are not review days.
    Caller must enforce complete weekly coverage and reference hashes before using this.
    Cash dividends: record-date entitlement, ex-date receivable, pay-date cash.
    Only cash dividends supported. Splits, rights and other actions must block this version.
    """
    if not sessions or sessions != sorted(set(sessions)):
        raise DataGap('Ordered unique sessions required')
    if any(a.get('type') != 'cash_dividend' for a in actions):
        raise DataGap('Unsupported corporate action; cannot silently ignore it')
    for a in actions:
        if not a['record_date'] < a['ex_date'] <= a['pay_date']:
            raise DataGap('Invalid corporate action dates')
    history = {s: list(v) for s, v in volumes.items()}
    cash = float(cfg['initial_cash_cny']); h = {}; entitlement = {}; receivable = {}
    curve = []; ledger = []
    symbols = sorted(history)
    for day in sessions:
        if any((day, s) not in prices for s in symbols):
            raise DataGap('Missing daily valuation bar; do not forward-fill silently')
        bars = {s: prices[(day, s)] for s in symbols}
        for i, a in enumerate(actions):
            if day == a['ex_date']:
                if a['record_date'] >= sessions[0] and i not in entitlement:
                    raise DataGap('Dividend record-date entitlement unavailable')
                receivable[i] = entitlement.get(i, 0) * a['cash_per_share'] * (1 - cfg['dividend_tax_haircut'])
            if day == a['pay_date']:
                cash = round(cash + receivable.pop(i, 0.0), 2)
        if day in decisions:
            d = decisions[day]
            if aware(d['cutoff']) >= aware(day + 'T09:30:00+08:00'):
                raise DataGap('Decision uses execution-time/future information')
            cash, h, fills = rebalance(day, cash, h, d['weights'], bars, history, cfg, sum(receivable.values()))
            ledger.extend(fills)
        stock_value = sum(h.get(s, 0) * bars[s]['close'] for s in symbols)
        nav = cash + stock_value + sum(receivable.values())
        curve.append({'date': day, 'nav': round(nav, 6), 'cash': cash,
                      'receivables': round(sum(receivable.values()), 6),
                      'equity_weight': stock_value / nav, **{s: h.get(s, 0) for s in symbols}})
        for i, a in enumerate(actions):
            if day == a['record_date']:
                entitlement[i] = h.get(a['symbol'], 0)
        for s in symbols:
            history[s].append(bars[s]['volume_shares'])
    return {'curve': curve, 'trades': ledger,
            'metrics': metrics([x['nav'] for x in curve], cfg['initial_cash_cny']),
            'tax_basis': 'gross_dividend_or_explicit_flat_haircut_sensitivity_not_personal_after_tax'}

def metrics(values: list[float], initial: float) -> dict:
    if not values or initial <= 0 or any(not math.isfinite(x) or x <= 0 for x in values):
        raise DataGap('No valid NAV series; do not report 0%')
    returns = []; previous = initial; peak = initial; drawdown = 0.0
    for value in values:
        returns.append(value / previous - 1); previous = value
        peak = max(peak, value); drawdown = min(drawdown, value / peak - 1)
    sd = stdev(returns) if len(returns) > 1 else None
    return {'profit_cny': values[-1] - initial, 'return_pct': (values[-1] / initial - 1) * 100,
            'max_drawdown_pct': drawdown * 100,
            'daily_vol_annualized_pct': sd * math.sqrt(252) * 100 if sd is not None else None,
            'sharpe_rf_zero': (sum(returns) / len(returns)) / sd * math.sqrt(252) if sd else None}

def compare(strategy: list[float], benchmark: list[float], strategy_initial: float,
            benchmark_initial: float, same_return_basis: bool) -> dict:
    if not same_return_basis:
        raise DataGap('Price and total returns cannot be scored as comparable alpha')
    if not strategy or len(strategy) != len(benchmark):
        raise DataGap('Identical valuation timestamps required')
    s = metrics(strategy, strategy_initial); b = metrics(benchmark, benchmark_initial)
    return {'excess_return_pp': s['return_pct'] - b['return_pct'],
            'relative_wealth_pct': ((strategy[-1] / strategy_initial) / (benchmark[-1] / benchmark_initial) - 1) * 100,
            'drawdown_difference_pp': s['max_drawdown_pct'] - b['max_drawdown_pct']}

def audit_readiness(root: Path = ROOT) -> dict:
    coverage = json.loads((root / 'data/coverage.json').read_text())
    gaps = []
    if coverage.get('verified_full_daily_rows', 0) == 0: gaps.append('verified_daily_ohlcv_missing')
    if not coverage.get('point_in_time_complete'): gaps.append('point_in_time_filings_incomplete')
    if not coverage.get('industry_history_complete'): gaps.append('industry_history_incomplete')
    for name in ('market_manifest.json', 'evidence_packets.json', 'actions_manifest.json', 'benchmark_manifest.json'):
        p = root / 'experiments/weekly_replay_v1/inputs' / name
        if not p.exists(): gaps.append(name + '_missing')
        else:
            obj = json.loads(p.read_text())
            if obj.get('status') != 'verified': gaps.append(name + '_not_verified')
    # Even after files arrive, integration, chronology and independent review must pass.
    gaps.append('production_integration_not_yet_validated')
    return {'status': 'BLOCKED', 'missing': gaps, 'performance': None,
            'message': 'No historical performance computed. BLOCKED is not a cash strategy.'}

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit', action='store_true')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = audit_readiness()
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text)
    print(text, end='')
    raise SystemExit(2)

if __name__ == '__main__': main()
