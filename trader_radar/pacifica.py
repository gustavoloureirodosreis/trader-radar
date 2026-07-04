from __future__ import annotations

import time

from .http import request_json
from .models import Position, Trader

REST_URL = "https://api.pacifica.fi/api/v1"

# Credit budget per rolling 60s: ~125 unidentified, ~300 with a PF-API-KEY.
SLEEP_ANON_S = 0.55
SLEEP_KEYED_S = 0.22


class PacificaSource:
    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.sleep_s = SLEEP_KEYED_S if api_key else SLEEP_ANON_S

    def _headers(self) -> dict[str, str] | None:
        return {"PF-API-KEY": self.api_key} if self.api_key else None

    def _get(self, path: str, params: dict | None = None) -> dict:
        result = request_json("GET", f"{REST_URL}{path}", params=params, headers=self._headers())
        if not result.get("success", True):
            raise RuntimeError(f"pacifica error on {path}: {result}")
        return result

    def fetch_leaderboard(self) -> list[Trader]:
        rows = self._get("/leaderboard")["data"]
        traders = []
        for row in rows:
            equity = float(row.get("equity_current") or 0)
            pnl_30d = float(row.get("pnl_30d") or 0)
            traders.append(
                Trader(
                    venue="pacifica",
                    address=row["address"],
                    display_name=row.get("username"),
                    equity=equity,
                    pnl_1d=float(row.get("pnl_1d") or 0),
                    pnl_7d=float(row.get("pnl_7d") or 0),
                    pnl_30d=pnl_30d,
                    pnl_all_time=float(row.get("pnl_all_time") or 0),
                    # Pacifica doesn't report ROI; approximate against current
                    # equity (equity 30d ago isn't exposed).
                    roi_30d=pnl_30d / equity if equity > 0 else 0.0,
                    volume_7d=float(row.get("volume_7d") or 0),
                    volume_30d=float(row.get("volume_30d") or 0),
                )
            )
        return traders

    def fetch_mark_prices(self) -> dict[str, float]:
        rows = self._get("/info/prices")["data"]
        return {row["symbol"]: float(row["mark"]) for row in rows}

    def fetch_positions(self, trader: Trader, marks: dict[str, float]) -> list[Position]:
        rows = self._get("/positions", params={"account": trader.address})["data"]
        time.sleep(self.sleep_s)
        now_ms = int(time.time() * 1000)
        positions = []
        for row in rows:
            size = float(row["amount"])
            if size == 0:
                continue
            entry = float(row["entry_price"])
            mark = marks.get(row["symbol"], entry)
            direction = "long" if row["side"] == "bid" else "short"
            sign = 1 if direction == "long" else -1
            opened = int(row["created_at"])
            positions.append(
                Position(
                    venue="pacifica",
                    address=trader.address,
                    trader_rank=trader.rank,
                    symbol=row["symbol"],
                    raw_symbol=row["symbol"],
                    direction=direction,
                    size=size,
                    entry_price=entry,
                    mark_price=mark,
                    notional_usd=size * mark,
                    unrealized_pnl_usd=(mark - entry) * size * sign,
                    upnl_pct=(mark - entry) / entry * 100 * sign if entry else 0.0,
                    leverage=None,
                    opened_at_ms=opened,
                    age_days=(now_ms - opened) / 86_400_000,
                )
            )
        return positions
