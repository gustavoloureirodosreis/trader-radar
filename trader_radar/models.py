from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Trader:
    venue: str            # "hyperliquid" | "pacifica"
    address: str
    display_name: str | None
    equity: float
    pnl_1d: float
    pnl_7d: float
    pnl_30d: float
    pnl_all_time: float
    roi_30d: float        # fraction, e.g. 0.12 = +12%
    volume_7d: float
    volume_30d: float
    score: float = 0.0
    rank: int = 0
    score_parts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Position:
    venue: str
    address: str
    trader_rank: int
    symbol: str           # normalized (kPEPE -> PEPE etc.)
    raw_symbol: str
    direction: str        # "long" | "short"
    size: float           # base units, absolute
    entry_price: float
    mark_price: float
    notional_usd: float
    unrealized_pnl_usd: float | None
    upnl_pct: float       # price move since entry, signed by direction
    leverage: float | None
    opened_at_ms: int | None  # None = unknown / older than lookback window
    age_days: float | None

    def to_dict(self) -> dict:
        return asdict(self)
