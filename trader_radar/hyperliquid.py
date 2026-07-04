from __future__ import annotations

import time

from .http import request_json
from .models import Position, Trader

LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
INFO_URL = "https://api.hyperliquid.xyz/info"

# userFills-style requests carry API weight 20 against a 1200/min IP budget,
# so pace them; clearinghouseState is weight 2 and needs only a light touch.
FILLS_SLEEP_S = 1.1
STATE_SLEEP_S = 0.15


def fetch_leaderboard() -> list[Trader]:
    data = request_json("GET", LEADERBOARD_URL, timeout=120)
    traders = []
    for row in data["leaderboardRows"]:
        windows = {name: vals for name, vals in row["windowPerformances"]}
        month = windows.get("month", {})
        traders.append(
            Trader(
                venue="hyperliquid",
                address=row["ethAddress"],
                display_name=row.get("displayName"),
                equity=float(row["accountValue"]),
                pnl_1d=float(windows.get("day", {}).get("pnl", 0)),
                pnl_7d=float(windows.get("week", {}).get("pnl", 0)),
                pnl_30d=float(month.get("pnl", 0)),
                pnl_all_time=float(windows.get("allTime", {}).get("pnl", 0)),
                roi_30d=float(month.get("roi", 0)),
                volume_7d=float(windows.get("week", {}).get("vlm", 0)),
                volume_30d=float(month.get("vlm", 0)),
            )
        )
    return traders


def fetch_positions(trader: Trader) -> list[Position]:
    state = request_json(
        "POST", INFO_URL, json_body={"type": "clearinghouseState", "user": trader.address}
    )
    time.sleep(STATE_SLEEP_S)
    positions = []
    for item in state.get("assetPositions", []):
        pos = item["position"]
        szi = float(pos["szi"])
        if szi == 0:
            continue
        size = abs(szi)
        entry = float(pos["entryPx"])
        notional = float(pos["positionValue"])
        mark = notional / size if size else entry
        direction = "long" if szi > 0 else "short"
        sign = 1 if szi > 0 else -1
        upnl_pct = (mark - entry) / entry * 100 * sign if entry else 0.0
        positions.append(
            Position(
                venue="hyperliquid",
                address=trader.address,
                trader_rank=trader.rank,
                symbol=normalize_symbol(pos["coin"]),
                raw_symbol=pos["coin"],
                direction=direction,
                size=size,
                entry_price=entry,
                mark_price=mark,
                notional_usd=notional,
                unrealized_pnl_usd=float(pos["unrealizedPnl"]),
                upnl_pct=upnl_pct,
                leverage=float(pos.get("leverage", {}).get("value") or 0) or None,
                opened_at_ms=None,
                age_days=None,
            )
        )
    return positions


def annotate_position_ages(
    trader: Trader, positions: list[Position], lookback_days: float = 45.0
) -> None:
    """Estimate when each open position was established from recent fills.

    Each fill reports `startPosition` (signed size before the fill), so the
    open time of the current position is the last fill where the position was
    flat or on the opposite side. Positions older than the lookback window
    keep opened_at_ms=None, which downstream reads as "old".
    """
    if not positions:
        return
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - int(lookback_days * 86_400_000)
    fills = request_json(
        "POST",
        INFO_URL,
        json_body={"type": "userFillsByTime", "user": trader.address, "startTime": start_ms},
    )
    time.sleep(FILLS_SLEEP_S)
    by_coin: dict[str, list[dict]] = {}
    for f in fills:
        by_coin.setdefault(f["coin"], []).append(f)

    for position in positions:
        coin_fills = sorted(by_coin.get(position.raw_symbol, []), key=lambda f: f["time"])
        sign = 1 if position.direction == "long" else -1
        opened = None
        for f in coin_fills:
            start_pos = float(f.get("startPosition", 0))
            if start_pos == 0 or (start_pos > 0) != (sign > 0):
                opened = int(f["time"])  # keep latest flat/flip point
        if opened is not None:
            position.opened_at_ms = opened
            position.age_days = (now_ms - opened) / 86_400_000


def normalize_symbol(coin: str) -> str:
    # Hyperliquid lists 1000x-denominated memecoins with a "k" prefix.
    if len(coin) > 1 and coin.startswith("k") and coin[1:].isupper():
        return coin[1:]
    return coin
