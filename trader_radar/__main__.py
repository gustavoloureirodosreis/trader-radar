from __future__ import annotations

import argparse
import sys
import time

from . import analysis, hyperliquid, pacifica, report, scoring
from .config import Settings
from .models import Position, Trader


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="trader-radar",
        description="Daily snapshot of top Hyperliquid + Pacifica traders and "
        "what they're positioned in.",
    )
    parser.add_argument("--venues", default="both", choices=["both", "hyperliquid", "pacifica"])
    parser.add_argument("--top", type=int, default=None, help="traders per venue (default 100)")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="skip Hyperliquid fill history (loses position-age data on HL, ~3min faster)",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.top:
        settings.top_n = args.top

    traders: list[Trader] = []
    positions: list[Position] = []

    if args.venues in ("both", "hyperliquid"):
        traders_hl, positions_hl = run_hyperliquid(settings, with_ages=not args.fast)
        traders += traders_hl
        positions += positions_hl

    if args.venues in ("both", "pacifica"):
        traders_pcf, positions_pcf = run_pacifica(settings)
        traders += traders_pcf
        positions += positions_pcf

    print("analyzing...")
    assets = analysis.aggregate_assets(positions, settings)
    fresh = analysis.fresh_conviction(positions, settings)
    splits = analysis.disagreements(assets)
    elite_notes = analysis.elite_divergences(positions, settings, assets)

    day_dir = report.write_snapshot(
        settings.snapshots_dir, traders, positions, assets, fresh, splits, elite_notes
    )
    print(f"snapshot written to {day_dir}")
    print(f"  traders: {len(traders)}  positions: {len(positions)}  assets: {len(assets)}")
    return 0


def run_hyperliquid(settings: Settings, with_ages: bool) -> tuple[list[Trader], list[Position]]:
    print("hyperliquid: downloading leaderboard (~35MB)...")
    all_traders = hyperliquid.fetch_leaderboard()
    top = scoring.rank_traders(all_traders, settings)
    print(f"hyperliquid: {len(all_traders)} accounts -> {len(top)} selected")

    positions: list[Position] = []
    started = time.time()
    for i, trader in enumerate(top, 1):
        pos = hyperliquid.fetch_positions(trader)
        if with_ages and pos:
            hyperliquid.annotate_position_ages(trader, pos)
        positions += pos
        if i % 20 == 0:
            print(f"hyperliquid: {i}/{len(top)} traders ({time.time() - started:.0f}s)")
    return top, positions


def run_pacifica(settings: Settings) -> tuple[list[Trader], list[Position]]:
    source = pacifica.PacificaSource(settings.pacifica_api_key)
    print("pacifica: downloading leaderboard...")
    all_traders = source.fetch_leaderboard()
    top = scoring.rank_traders(all_traders, settings)
    print(f"pacifica: {len(all_traders)} accounts -> {len(top)} selected")

    marks = source.fetch_mark_prices()
    positions: list[Position] = []
    started = time.time()
    for i, trader in enumerate(top, 1):
        positions += source.fetch_positions(trader, marks)
        if i % 20 == 0:
            print(f"pacifica: {i}/{len(top)} traders ({time.time() - started:.0f}s)")
    return top, positions


if __name__ == "__main__":
    sys.exit(main())
