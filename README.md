# trader-radar

Daily snapshot of the top 100 traders on **Hyperliquid** and **Pacifica**, plus an
analysis of what they hold, in which direction, and whether the trade is early or late.

## Run it

```bash
cd trader-radar
python3 -m trader_radar              # full run, both venues (~6-8 min)
python3 -m trader_radar --fast       # skip HL fill history (~2 min, no HL position ages)
python3 -m trader_radar --venues pacifica --top 50
```

Output goes to `snapshots/YYYY-MM-DD/`:

- `report.html` — standalone styled daily brief (open in any browser). Kept
  deliberately tight: fresh calls, assets held by ≥5 traders (max 15), an
  "elite-25 watch" (where the top 25/venue disagree with the full cohort),
  long/short splits, day-over-day changes, top 10 traders. Everything else
  lives in the JSONs.
- `traders.json` — the scored top-100 cohort per venue
- `positions.json` — every open position, normalized across venues
- `assets.json` — per-asset rollup (used for day-over-day diffs)

`snapshots/latest` always points at the newest day. From the second run onward the
report includes a **Changes vs previous snapshot** section (verdict flips, new
assets on the radar).

## Keys

Copy `.env.example` to `.env`. Everything this tool reads is **public** on both
venues — the only useful key is an optional Pacifica `PACIFICA_API_KEY`
(PF-API-KEY) that raises rate limits and speeds up the Pacifica pass. Hyperliquid
needs no key at all. **Never** put wallet/agent private keys in this project;
nothing here signs or trades.

## Who counts as a "top trader" (selection criteria)

From each venue's full leaderboard (~40k accounts on HL, ~7k on Pacifica):

**Eligibility filters**
1. *Skin in the game*: equity ≥ $50k (HL) / ≥ $10k (Pacifica).
2. *Recency*: traded within the last 7 days (7d volume > 0).
3. *Profitable now and over lifetime*: 30d PnL > 0 **and** all-time PnL > 0
   (kills one-lucky-window accounts).
4. *Not a market maker*: excluded if 30d volume > 300× equity while |30d ROI| < 2%
   — that profile is flow capture, not directional alpha worth copying.

**Composite score** (each metric as percentile rank within the eligible pool):

| Weight | Metric | Why |
|---|---|---|
| 0.30 | 30d PnL | the anchor: recent but not one lucky trade |
| 0.20 | 30d ROI | levels the field so skilled mid-size accounts rank near whales |
| 0.15 | 7d PnL | in form *right now* |
| 0.15 | All-time PnL | lifetime edge |
| 0.10 | Equity | skin in the game |
| 0.10 | Consistency | positive PnL across 1d/7d/30d/all-time windows |

Top 100 per venue by score make the cohort.

## Early vs late (per-asset verdicts)

For each asset, positions of the cohort are aggregated in the dominant direction:

- **EARLY** — ≥3 cohort traders entered within 7 days, fresh entries are the
  majority of the book, and median move since entry is between −5% and +15%
  (conviction is new and the price hasn't paid them yet).
- **CROWDED/LATE** — median move since entry ≥ +50%: the trade already worked;
  you'd be exit liquidity.
- **UNDERWATER** — median move since entry ≤ −10%: smart money is down; either a
  contrarian signal or bagholding.
- **MID** — everything in between.

There's also a **fresh conviction** feed: any (asset, direction) that ≥2 cohort
traders opened in the last 7 days, ranked by trader count and notional — the
rawest "possible early call" list.

**Position age sources**: Pacifica reports `created_at` per position directly.
Hyperliquid doesn't, so age is reconstructed from the last 45 days of fills
(each fill reports the pre-fill position size, so the open point is the last
flat/flip). HL positions older than 45d show as `>45d`.

## Data sources (all public)

| Data | Endpoint |
|---|---|
| HL leaderboard (PnL/ROI/volume per window, equity) | `GET stats-data.hyperliquid.xyz/Mainnet/leaderboard` |
| HL open positions | `POST api.hyperliquid.xyz/info` `{"type":"clearinghouseState"}` |
| HL fills (for position age) | `POST api.hyperliquid.xyz/info` `{"type":"userFillsByTime"}` |
| Pacifica leaderboard | `GET api.pacifica.fi/api/v1/leaderboard` |
| Pacifica positions (incl. `created_at`) | `GET api.pacifica.fi/api/v1/positions?account=` |
| Pacifica mark prices | `GET api.pacifica.fi/api/v1/info/prices` |

Rate limiting is built in: HL fill requests are paced at ~55/min (weight-20 calls
against a 1200/min budget); Pacifica calls are paced to its credit window and
back off on 429s.

## Scheduling

Installed as a launchd LaunchAgent (better than cron on macOS: a run missed
while the Mac was *asleep* fires on wake; cron just skips it). Runs daily at
9:00 local time, logs to `snapshots/run.log`:

```
~/Library/LaunchAgents/com.gustavo.trader-radar.plist
```

Manage it with:

```bash
launchctl list | grep trader-radar                     # is it loaded?
launchctl kickstart gui/$(id -u)/com.gustavo.trader-radar   # run now
launchctl bootout gui/$(id -u)/com.gustavo.trader-radar     # disable
```

If the Mac is fully powered off at 9am, that day is skipped (no local
scheduler survives power-off). For guaranteed daily runs, host it on an
always-on box or a cloud scheduled agent.

## Caveats

- Leaderboards are venue snapshots and can lag live account state slightly.
- Pacifica 30d ROI is approximated as `pnl_30d / current equity` (the venue
  doesn't expose historical equity).
- HL "k"-prefixed symbols (kPEPE etc.) are normalized to the base name.
- Vault/HLP-style accounts that pass the MM filter may still appear; raise
  `HL_MIN_EQUITY_USD` or tighten `mm_max_turnover` if you see them.
