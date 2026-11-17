"""Offline accounting prototype, not a fitted forecast or a trading model.
All quantities within one call require the caller to prove matching boundaries.
Missing values remain missing. Rule dates are supplied, not guessed here.
"""
from dataclasses import dataclass
from datetime import datetime
from math import isfinite, isclose
from typing import Optional, Sequence

Number = Optional[float]


def valid(*values: float) -> None:
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not isfinite(v) for v in values):
        raise ValueError("finite numeric inputs required")


def residual(opening: Number, closing: Number, inflow: Number,
             outflow: Number, adjustment: Number, *, same_boundary: bool) -> Number:
    """Return unexplained stock change, never label it demand."""
    if not same_boundary:
        raise ValueError("boundary/unit/time/sample mismatch")
    values = (opening, closing, inflow, outflow, adjustment)
    if any(v is None for v in values):
        return None
    valid(*values)
    if min(opening, closing, inflow, outflow) < 0:
        raise ValueError("physical stocks and gross flows must be nonnegative")
    return closing - opening - inflow + outflow - adjustment


def transfer(stocks: Sequence[float], origin: int, destination: int,
             amount: float) -> tuple[float, ...]:
    """Internal physical transfer conserves total stock."""
    valid(*stocks, amount)
    if origin == destination or not (0 <= origin < len(stocks)
                                    and 0 <= destination < len(stocks)):
        raise ValueError("two distinct valid nodes required")
    if min(stocks) < 0 or amount < 0 or amount > stocks[origin]:
        raise ValueError("invalid transfer")
    result = list(stocks)
    result[origin] -= amount
    result[destination] += amount
    return tuple(result)


def warrant_change(registrations: Number, cancellations: Number,
                   adjustment: Number) -> Number:
    """Total registrations/cancellations only; no gross flows inferred from net."""
    if any(v is None for v in (registrations, cancellations, adjustment)):
        return None
    valid(registrations, cancellations, adjustment)
    if min(registrations, cancellations) < 0:
        raise ValueError("negative gross warrant flow")
    return registrations - cancellations + adjustment


def contained_lce(wet_tonnes: float, moisture: float,
                  li2o_dry_fraction: float) -> float:
    """Chemical content only, not saleable output; 73.89/29.88 molar ratio."""
    valid(wet_tonnes, moisture, li2o_dry_fraction)
    if wet_tonnes < 0 or not 0 <= moisture < 1 or not 0 <= li2o_dry_fraction <= 1:
        raise ValueError("invalid mass, moisture, or dry grade fraction")
    return wet_tonnes * (1 - moisture) * li2o_dry_fraction * (73.89 / 29.88)


def recoverable_lce(contained: float, recovery: Number) -> Number:
    if recovery is None:
        return None
    valid(contained, recovery)
    if contained < 0 or not 0 <= recovery <= 1:
        raise ValueError("invalid recovery")
    return contained * recovery


def lagged_arrivals(shipments: Sequence[float], kernel: Sequence[float]) -> list[float]:
    """Scenario convolution: include the entire tail to conserve shipped mass.
    Kernel[0] is same-period arrival; do not fit this from interpolated quarters.
    """
    valid(*shipments, *kernel)
    if not shipments or not kernel or min(shipments) < 0 or min(kernel) < 0:
        raise ValueError("nonempty nonnegative sequences required")
    if not isclose(sum(kernel), 1.0, abs_tol=1e-10, rel_tol=0):
        raise ValueError("arrival shares must sum to one including the tail")
    result = [0.0] * (len(shipments) + len(kernel) - 1)
    for t, qty in enumerate(shipments):
        for lag, fraction in enumerate(kernel):
            result[t + lag] += qty * fraction
    return result


@dataclass(frozen=True)
class Vintage:
    value: float
    published_at: datetime
    observed_at: datetime
    status: str  # actual or forecast


def latest_actual_asof(vintages: Sequence[Vintage], cutoff: datetime) -> Number:
    """One metric/period/source series only; caller separates survey samples.
    observed_at preserves operational availability; late downloads are not PIT.
    """
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("timezone-aware cutoff required")
    eligible = []
    for row in vintages:
        valid(row.value)
        if any(d.tzinfo is None or d.utcoffset() is None
               for d in (row.published_at, row.observed_at)):
            raise ValueError("timezone-aware timestamps required")
        if row.observed_at < row.published_at:
            raise ValueError("observation precedes publication")
        if row.status not in ("actual", "forecast"):
            raise ValueError("unknown evidence status")
        if row.status == "actual" and max(row.published_at, row.observed_at) <= cutoff:
            eligible.append(row)
    return max(eligible, key=lambda r: (r.published_at, r.observed_at)).value if eligible else None


def cash_available(ocf_after_tax_interest: Number, maintenance_capex: Number,
                   growth_capex: Number, debt_principal: Number,
                   liquidity_reserve_addition: Number) -> Number:
    """Entity-level distribution-capacity bridge without new debt; negative means funding need.
    Inputs must use one entity/currency/period and avoid interest double counting.
    This is capacity, not declared dividends nor cash received by a listed parent.
    """
    values = (ocf_after_tax_interest, maintenance_capex, growth_capex,
              debt_principal, liquidity_reserve_addition)
    if any(v is None for v in values):
        return None
    valid(*values)
    if min(maintenance_capex, growth_capex, debt_principal) < 0:
        raise ValueError("capex and principal outflows must be nonnegative")
    return ocf_after_tax_interest - maintenance_capex - growth_capex - debt_principal - liquidity_reserve_addition
