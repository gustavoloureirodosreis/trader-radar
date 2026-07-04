"""Build the static Pages site from snapshots/: one page per day plus a
dates.json manifest that powers the prev/next arrow navigation."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOTS = ROOT / "snapshots"
SITE = ROOT / "site"


def main() -> None:
    shutil.rmtree(SITE, ignore_errors=True)
    SITE.mkdir(parents=True)

    dates = []
    for day_dir in sorted(SNAPSHOTS.iterdir()):
        if not day_dir.is_dir() or day_dir.is_symlink():
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_dir.name):
            continue
        report = day_dir / "report.html"
        if not report.exists():
            continue
        shutil.copy(report, SITE / f"{day_dir.name}.html")
        dates.append(day_dir.name)

    if not dates:
        raise SystemExit("no snapshots to publish")

    (SITE / "dates.json").write_text(json.dumps(dates))
    latest = dates[-1]
    (SITE / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'>"
        f"<meta http-equiv='refresh' content='0; url={latest}.html'>"
        f"<title>Trader Radar</title><a href='{latest}.html'>latest report</a>"
    )
    print(f"site built: {len(dates)} day(s), latest {latest}")


if __name__ == "__main__":
    main()
