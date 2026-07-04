from __future__ import annotations

from .config import Settings
from .models import Trader

# Composite score weights. Rationale:
# - 30d PnL is the anchor: recent, but long enough to not be one lucky trade.
# - 30d ROI levels the field so skilled mid-size accounts rank near whales.
# - 7d PnL rewards being in form *now*; all-time PnL filters window-wonders.
# - Equity is the "skin in the game" term.
# - Consistency (positive across 1d/7d/30d/all-time) rewards steadiness.
WEIGHTS = {
    "pnl_30d": 0.30,
    "roi_30d": 0.20,
    "pnl_7d": 0.15,
    "pnl_all_time": 0.15,
    "equity": 0.10,
    "consistency": 0.10,
}


def eligible(t: Trader, s: Settings) -> bool:
    min_equity = s.hl_min_equity_usd if t.venue == "hyperliquid" else s.pcf_min_equity_usd
    if t.equity < min_equity:
        return False  # not enough skin in the game
    if t.volume_7d <= 0:
        return False  # hasn't traded this week -> stale read on their book
    if t.pnl_30d <= 0 or t.pnl_all_time <= 0:
        return False  # must be making money recently AND over their lifetime
    turnover = t.volume_30d / t.equity if t.equity else 0
    if turnover > s.mm_max_turnover and abs(t.roi_30d) < s.mm_max_abs_roi:
        return False  # market-maker profile: huge churn, ~zero directional return
    return True


def rank_traders(traders: list[Trader], s: Settings) -> list[Trader]:
    """Filter to eligible traders, score them, return the archive-depth top of
    the venue (report cohort = ranks 1..top_n; the rest is stored for
    retroactive rule changes)."""
    pool = [t for t in traders if eligible(t, s)]
    if not pool:
        return []

    metric_pctl = {
        m: _percentiles([getattr(t, m) for t in pool])
        for m in ("pnl_30d", "roi_30d", "pnl_7d", "pnl_all_time", "equity")
    }
    for i, t in enumerate(pool):
        parts = {m: metric_pctl[m][i] for m in metric_pctl}
        windows = (t.pnl_1d, t.pnl_7d, t.pnl_30d, t.pnl_all_time)
        parts["consistency"] = sum(1 for w in windows if w > 0) / len(windows)
        t.score_parts = {k: round(v, 4) for k, v in parts.items()}
        t.score = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)

    pool.sort(key=lambda t: t.score, reverse=True)
    top = pool[: s.archive_top_n]
    for i, t in enumerate(top, start=1):
        t.rank = i
    return top


def _percentiles(values: list[float]) -> list[float]:
    """Percentile rank (0..1) of each value within its list."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    n = max(len(values) - 1, 1)
    ranks = [0.0] * len(values)
    for rank, idx in enumerate(order):
        ranks[idx] = rank / n
    return ranks
