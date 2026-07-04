from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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
    parser.add_argument(
        "--rerender",
        metavar="DATE|all",
        help="no fetching: recompute analysis and report.html for stored "
        "snapshot(s) using the current rules (YYYY-MM-DD or 'all')",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.top:
        settings.top_n = args.top
        settings.archive_top_n = max(settings.archive_top_n, settings.top_n)

    if args.rerender:
        return rerender(settings, args.rerender)

    traders: list[Trader] = []
    positions: list[Position] = []
    raw: dict[str, object] = {}

    if args.venues in ("both", "hyperliquid"):
        traders_hl, positions_hl, raw_hl = run_hyperliquid(settings, with_ages=not args.fast)
        traders += traders_hl
        positions += positions_hl
        raw["hl_leaderboard"] = raw_hl

    if args.venues in ("both", "pacifica"):
        traders_pcf, positions_pcf, raw_pcf = run_pacifica(settings)
        traders += traders_pcf
        positions += positions_pcf
        raw["pcf_leaderboard"] = raw_pcf

    print("analyzing...")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_dir = report.write_snapshot(
        settings.snapshots_dir, day, settings, traders, positions,
        *compute(settings, positions),
    )
    archive_raw(day_dir, raw, settings)
    print(f"snapshot written to {day_dir}")
    print(f"  traders: {len(traders)} archived  positions: {len(positions)}")
    return 0


def compute(
    settings: Settings, positions: list[Position]
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """Everything derived from positions, computed on the report cohort only."""
    report_positions = [p for p in positions if p.trader_rank <= settings.top_n]
    assets = analysis.aggregate_assets(report_positions, settings)
    fresh = analysis.fresh_conviction(report_positions, settings)
    splits = analysis.disagreements(assets)
    elite_notes = analysis.elite_divergences(report_positions, settings, assets)
    return assets, fresh, splits, elite_notes


def rerender(settings: Settings, which: str) -> int:
    days = sorted(
        d.name for d in settings.snapshots_dir.iterdir()
        if d.is_dir() and not d.is_symlink() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)
    )
    if which != "all":
        if which not in days:
            print(f"no snapshot for {which}", file=sys.stderr)
            return 1
        days = [which]
    # Ascending order matters: each day's "changes vs previous" section reads
    # the previous day's (freshly rewritten) assets.json.
    for day in days:
        day_dir = settings.snapshots_dir / day
        traders = [Trader(**t) for t in json.loads((day_dir / "traders.json").read_text())]
        positions = [
            Position(**p) for p in json.loads((day_dir / "positions.json").read_text())
        ]
        report.write_snapshot(
            settings.snapshots_dir, day, settings, traders, positions,
            *compute(settings, positions), write_data=False,
        )
        print(f"rerendered {day}")
    return 0


def archive_raw(day_dir: Path, raw: dict, settings: Settings) -> None:
    """Store the raw leaderboards (compressed, dust accounts dropped) so future
    selection-rule changes can be replayed against the full field, not just the
    cohort that today's rules picked."""
    raw_dir = day_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    if "hl_leaderboard" in raw:
        rows = [
            r for r in raw["hl_leaderboard"]["leaderboardRows"]
            if float(r["accountValue"]) >= settings.raw_min_equity_usd
        ]
        _write_gz(raw_dir / "hl_leaderboard.json.gz", {"leaderboardRows": rows})
    if "pcf_leaderboard" in raw:
        rows = [
            r for r in raw["pcf_leaderboard"]
            if float(r.get("equity_current") or 0) >= settings.raw_min_equity_usd
        ]
        _write_gz(raw_dir / "pcf_leaderboard.json.gz", rows)


def _write_gz(path: Path, data) -> None:
    path.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode()))


def run_hyperliquid(
    settings: Settings, with_ages: bool
) -> tuple[list[Trader], list[Position], dict]:
    print("hyperliquid: downloading leaderboard (~35MB)...")
    raw = hyperliquid.fetch_leaderboard_raw()
    all_traders = hyperliquid.parse_leaderboard(raw)
    top = scoring.rank_traders(all_traders, settings)
    print(f"hyperliquid: {len(all_traders)} accounts -> {len(top)} archived "
          f"(report shows top {settings.top_n})")

    positions: list[Position] = []
    started = time.time()
    for i, trader in enumerate(top, 1):
        pos = hyperliquid.fetch_positions(trader)
        if with_ages and pos:
            hyperliquid.annotate_position_ages(trader, pos)
        positions += pos
        if i % 25 == 0:
            print(f"hyperliquid: {i}/{len(top)} traders ({time.time() - started:.0f}s)")
    return top, positions, raw


def run_pacifica(settings: Settings) -> tuple[list[Trader], list[Position], list]:
    source = pacifica.PacificaSource(settings.pacifica_api_key)
    print("pacifica: downloading leaderboard...")
    raw = source.fetch_leaderboard_raw()
    all_traders = source.parse_leaderboard(raw)
    top = scoring.rank_traders(all_traders, settings)
    print(f"pacifica: {len(all_traders)} accounts -> {len(top)} archived")

    marks = source.fetch_mark_prices()
    positions: list[Position] = []
    started = time.time()
    for i, trader in enumerate(top, 1):
        positions += source.fetch_positions(trader, marks)
        if i % 25 == 0:
            print(f"pacifica: {i}/{len(top)} traders ({time.time() - started:.0f}s)")
    return top, positions, raw


if __name__ == "__main__":
    sys.exit(main())
