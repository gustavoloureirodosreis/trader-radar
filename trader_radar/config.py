from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader; real environment variables win over file values."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Settings:
    top_n: int = 100
    # Eligibility floors ("skin in the game"). Pacifica is a smaller venue,
    # so the floor is lower there.
    hl_min_equity_usd: float = 50_000.0
    pcf_min_equity_usd: float = 10_000.0
    # Market-maker filter: huge churn with near-zero return is flow, not alpha.
    mm_max_turnover: float = 300.0  # 30d volume / equity above this ...
    mm_max_abs_roi: float = 0.02    # ... combined with |30d ROI| below this -> exclude
    # Early/late thresholds (see scoring.py / analysis.py docstrings).
    early_max_upnl_pct: float = 15.0
    early_min_recent_entries: int = 3
    late_min_upnl_pct: float = 50.0
    recent_entry_days: float = 7.0
    # Pacifica API config key (PF-API-KEY header). Optional: only raises the
    # rate-limit quota from 125 to 300+ credits per rolling 60s.
    pacifica_api_key: str = ""
    # Hyperliquid needs no credentials for any read used here.
    snapshots_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "snapshots")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        s = cls()
        s.top_n = int(os.environ.get("TOP_N", s.top_n))
        s.hl_min_equity_usd = float(os.environ.get("HL_MIN_EQUITY_USD", s.hl_min_equity_usd))
        s.pcf_min_equity_usd = float(os.environ.get("PCF_MIN_EQUITY_USD", s.pcf_min_equity_usd))
        s.pacifica_api_key = os.environ.get("PACIFICA_API_KEY", "")
        out = os.environ.get("SNAPSHOTS_DIR")
        if out:
            s.snapshots_dir = Path(out).expanduser()
        return s
