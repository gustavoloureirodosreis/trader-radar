from __future__ import annotations

from statistics import median

from .config import Settings
from .models import Position

# Verdicts, in the sense the user cares about:
#   EARLY    - several top traders entered recently and price hasn't run yet.
#   CROWDED  - heavily held and already deep in profit; late to chase.
#   UNDERWATER - top traders are down on it; contrarian/bagholding read.
#   MID      - established position, moderate profit; neither fresh nor late.


def aggregate_assets(positions: list[Position], s: Settings) -> list[dict]:
    by_symbol: dict[str, list[Position]] = {}
    for p in positions:
        by_symbol.setdefault(p.symbol, []).append(p)

    total_traders = len({(p.venue, p.address) for p in positions}) or 1
    assets = []
    for symbol, plist in by_symbol.items():
        longs = [p for p in plist if p.direction == "long"]
        shorts = [p for p in plist if p.direction == "short"]
        notional_long = sum(p.notional_usd for p in longs)
        notional_short = sum(p.notional_usd for p in shorts)
        dominant = longs if notional_long >= notional_short else shorts
        dominant_dir = "long" if notional_long >= notional_short else "short"

        upnls = [p.upnl_pct for p in dominant]
        ages = [p.age_days for p in dominant if p.age_days is not None]
        unknown_age = sum(1 for p in dominant if p.age_days is None)
        recent_entries = [
            p for p in dominant if p.age_days is not None and p.age_days <= s.recent_entry_days
        ]
        med_upnl = median(upnls) if upnls else 0.0
        med_age = median(ages) if ages else None

        assets.append(
            {
                "symbol": symbol,
                "traders": len({(p.venue, p.address) for p in plist}),
                "crowding_pct": round(
                    100 * len({(p.venue, p.address) for p in plist}) / total_traders, 1
                ),
                "longs": len(longs),
                "shorts": len(shorts),
                "notional_long_usd": round(notional_long, 0),
                "notional_short_usd": round(notional_short, 0),
                "net_notional_usd": round(notional_long - notional_short, 0),
                "dominant_direction": dominant_dir,
                "median_upnl_pct": round(med_upnl, 2),
                "median_age_days": round(med_age, 1) if med_age is not None else None,
                "positions_older_than_lookback": unknown_age,
                "recent_entries_7d": len(recent_entries),
                "recent_entry_notional_usd": round(
                    sum(p.notional_usd for p in recent_entries), 0
                ),
                "verdict": _verdict(med_upnl, len(recent_entries), len(dominant), unknown_age, s),
                "venues": sorted({p.venue for p in plist}),
            }
        )

    assets.sort(key=lambda a: a["notional_long_usd"] + a["notional_short_usd"], reverse=True)
    return assets


def _verdict(
    med_upnl: float, n_recent: int, n_dominant: int, n_unknown_age: int, s: Settings
) -> str:
    if med_upnl >= s.late_min_upnl_pct:
        return "CROWDED/LATE"
    if med_upnl <= -10:
        return "UNDERWATER"
    # Mostly-fresh positioning that hasn't moved yet is the early signal.
    if (
        n_recent >= s.early_min_recent_entries
        and n_recent >= 0.5 * max(n_dominant - n_unknown_age, 1)
        and -5 <= med_upnl <= s.early_max_upnl_pct
    ):
        return "EARLY"
    return "MID"


def fresh_conviction(positions: list[Position], s: Settings) -> list[dict]:
    """Positions opened in the last week, grouped by (symbol, direction),
    ranked by how much top-trader money just moved in. The strongest
    'possible early call' feed."""
    recent = [
        p for p in positions if p.age_days is not None and p.age_days <= s.recent_entry_days
    ]
    grouped: dict[tuple[str, str], list[Position]] = {}
    for p in recent:
        grouped.setdefault((p.symbol, p.direction), []).append(p)

    out = []
    for (symbol, direction), plist in grouped.items():
        if len(plist) < 2:  # one trader is noise; two or more is a lean
            continue
        out.append(
            {
                "symbol": symbol,
                "direction": direction,
                "traders": len({(p.venue, p.address) for p in plist}),
                "notional_usd": round(sum(p.notional_usd for p in plist), 0),
                "median_upnl_pct": round(median(p.upnl_pct for p in plist), 2),
                "median_age_days": round(median(p.age_days for p in plist), 1),
                "best_ranked_trader": min(p.trader_rank for p in plist),
                "venues": sorted({p.venue for p in plist}),
            }
        )
    out.sort(key=lambda r: (r["traders"], r["notional_usd"]), reverse=True)
    return out


def elite_divergences(
    positions: list[Position],
    s: Settings,
    main_assets: list[dict],
    elite_rank: int = 25,
) -> list[str]:
    """Where the top-25-per-venue cohort reads differently than the full one.
    Only checks widely-held assets; returns short human-readable notes."""
    elite_positions = [p for p in positions if p.trader_rank <= elite_rank]
    elite = {a["symbol"]: a for a in aggregate_assets(elite_positions, s)}
    notes = []
    for a in main_assets:
        if a["traders"] < 5:
            continue
        e = elite.get(a["symbol"])
        if not e or e["traders"] < 3:
            continue
        if e["dominant_direction"] != a["dominant_direction"]:
            e_long, e_short = e["notional_long_usd"], e["notional_short_usd"]
            big, small = max(e_long, e_short), min(e_long, e_short)
            notes.append(
                f"{a['symbol']}: elite money leans {e['dominant_direction']} by notional "
                f"(${big / 1e6:.1f}M vs ${small / 1e6:.1f}M) while the full cohort "
                f"leans {a['dominant_direction']}"
            )
        elif e["median_upnl_pct"] - a["median_upnl_pct"] >= 15:
            notes.append(
                f"{a['symbol']}: elite entries are much earlier — already "
                f"{e['median_upnl_pct']:+.0f}% vs {a['median_upnl_pct']:+.0f}% for the "
                f"cohort; later entrants are chasing"
            )
        elif a["median_upnl_pct"] - e["median_upnl_pct"] >= 15:
            notes.append(
                f"{a['symbol']}: elite are underwater relative to the cohort "
                f"({e['median_upnl_pct']:+.0f}% vs {a['median_upnl_pct']:+.0f}%) — "
                f"the best accounts entered late or are averaging in"
            )
    return notes


def disagreements(assets: list[dict]) -> list[dict]:
    """Assets where top traders are meaningfully split long vs short."""
    out = []
    for a in assets:
        if a["longs"] >= 3 and a["shorts"] >= 3:
            small = min(a["notional_long_usd"], a["notional_short_usd"])
            big = max(a["notional_long_usd"], a["notional_short_usd"])
            if big > 0 and small / big >= 0.33:
                out.append(a)
    return out
