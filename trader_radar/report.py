from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Position, Trader

# Display cuts. The full data always lands in the JSON files; the report only
# shows what's worth reading.
MAX_HELD_ROWS = 15
MIN_HOLDERS_SHOWN = 5      # an asset needs >=5 cohort traders to make the table
MAX_FRESH_ROWS = 10
FRESH_MIN_TRADERS = 3      # ... or 2 traders with real size (below)
FRESH_MIN_NOTIONAL = 500_000
MAX_SPLITS = 5
MAX_NEW_BETS = 8
MAX_CHANGES = 8


def write_snapshot(
    out_dir: Path,
    traders: list[Trader],
    positions: list[Position],
    assets: list[dict],
    fresh: list[dict],
    splits: list[dict],
    elite_notes: list[str],
) -> Path:
    day_dir = out_dir / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    (day_dir / "traders.json").write_text(
        json.dumps([t.to_dict() for t in traders], indent=1)
    )
    (day_dir / "positions.json").write_text(
        json.dumps([p.to_dict() for p in positions], indent=1)
    )
    (day_dir / "assets.json").write_text(json.dumps(assets, indent=1))

    changes = _diff_vs_previous(out_dir, day_dir, assets)
    (day_dir / "report.html").write_text(
        _render_html(traders, positions, assets, fresh, splits, elite_notes, changes)
    )

    latest = out_dir / "latest"
    latest.unlink(missing_ok=True)
    latest.symlink_to(day_dir.name)
    return day_dir


def _diff_vs_previous(out_dir: Path, today_dir: Path, assets: list[dict]) -> dict:
    prior_days = sorted(
        d for d in out_dir.iterdir()
        if d.is_dir() and not d.is_symlink() and d.name < today_dir.name
    )
    if not prior_days:
        return {}
    prev = prior_days[-1] / "assets.json"
    if not prev.exists():
        return {}
    old = {a["symbol"]: a for a in json.loads(prev.read_text())}
    new = {a["symbol"]: a for a in assets}
    watched = {a["symbol"] for a in assets if a["traders"] >= MIN_HOLDERS_SHOWN}
    return {
        "previous_date": prior_days[-1].name,
        "verdict_changes": [
            f"{sym}: {old[sym]['verdict']} → {new[sym]['verdict']}"
            for sym in sorted(watched & set(old))
            if old[sym]["verdict"] != new[sym]["verdict"]
        ],
        "new_assets": sorted(
            sym for sym in watched - set(old) if new[sym]["traders"] >= MIN_HOLDERS_SHOWN
        ),
    }


def _fmt_usd(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.2f}B"
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    if a >= 1e3:
        return f"${v / 1e3:.0f}k"
    return f"${v:.0f}"


def _esc(v) -> str:
    return html.escape(str(v))


def _badge(verdict: str) -> str:
    cls = {
        "EARLY": "early",
        "CROWDED/LATE": "late",
        "UNDERWATER": "under",
        "MID": "mid",
    }.get(verdict, "mid")
    return f'<span class="badge {cls}">{_esc(verdict)}</span>'


def _dir(direction: str) -> str:
    cls = "long" if direction == "long" else "short"
    return f'<span class="{cls}">{direction.upper()}</span>'


def _pnl(pct: float) -> str:
    cls = "pos" if pct >= 0 else "neg"
    return f'<span class="{cls}">{pct:+.1f}%</span>'


CSS = """
:root {
  --bg: #0b0e14; --card: #12161f; --border: #222a38; --text: #e7ebf2;
  --muted: #8b94a7; --accent: #6ea8fe; --green: #3fb68b; --red: #e5484d;
  --amber: #f0a53e;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 40px 20px 80px; background: var(--bg); color: var(--text);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.wrap { max-width: 880px; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
header h1 { font-size: 26px; margin: 0 0 4px; letter-spacing: -0.02em; }
header .date { color: var(--muted); font-size: 14px; }
.daynav { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.daynav a {
  display: inline-block; min-width: 34px; text-align: center; padding: 5px 0;
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text); text-decoration: none; font-size: 16px; line-height: 1;
}
.daynav a.off { opacity: 0.25; pointer-events: none; }
.daynav .hint { color: var(--muted); font-size: 11px; }
.chips { display: flex; flex-wrap: wrap; gap: 10px; margin: 22px 0 8px; }
.chip {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 10px 16px; min-width: 120px;
}
.chip .k { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; }
.chip .v { font-size: 19px; font-weight: 600; font-variant-numeric: tabular-nums; }
section { margin-top: 34px; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--accent);
     margin: 0 0 4px; }
.sub { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
        overflow: hidden; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
     color: var(--muted); padding: 10px 14px; border-bottom: 1px solid var(--border);
     font-weight: 600; }
td { padding: 9px 14px; border-bottom: 1px solid var(--border); font-size: 14px; }
tr:last-child td { border-bottom: none; }
td.num, th.num { text-align: right; }
.sym { font-weight: 700; }
.badge { font-size: 10.5px; font-weight: 700; letter-spacing: 0.05em; padding: 3px 8px;
         border-radius: 20px; white-space: nowrap; }
.badge.early { background: rgba(63,182,139,.15); color: var(--green); }
.badge.late  { background: rgba(240,165,62,.15); color: var(--amber); }
.badge.under { background: rgba(229,72,77,.15); color: var(--red); }
.badge.mid   { background: rgba(139,148,167,.15); color: var(--muted); }
.long  { color: var(--green); font-weight: 700; font-size: 12px; }
.short { color: var(--red); font-weight: 700; font-size: 12px; }
.pos { color: var(--green); } .neg { color: var(--red); }
ul.notes { margin: 0; padding: 6px 14px 6px 30px; }
ul.notes li { padding: 5px 0; }
.empty { padding: 16px 14px; color: var(--muted); font-style: italic; }
footer { margin-top: 44px; color: var(--muted); font-size: 12.5px; border-top: 1px solid var(--border);
         padding-top: 16px; }
.muted { color: var(--muted); }
@media (max-width: 640px) { td, th { padding: 8px 8px; font-size: 13px; } }
"""


def _render_html(
    traders: list[Trader],
    positions: list[Position],
    assets: list[dict],
    fresh: list[dict],
    splits: list[dict],
    elite_notes: list[str],
    changes: dict,
) -> str:
    now = datetime.now(timezone.utc)
    n_hl = sum(1 for t in traders if t.venue == "hyperliquid")
    n_pcf = len(traders) - n_hl
    total_notional = sum(p.notional_usd for p in positions)

    held = [a for a in assets if a["traders"] >= MIN_HOLDERS_SHOWN][:MAX_HELD_ROWS]
    fresh_shown = [
        r for r in fresh
        if r["traders"] >= FRESH_MIN_TRADERS
        or (r["traders"] >= 2 and r["notional_usd"] >= FRESH_MIN_NOTIONAL)
    ][:MAX_FRESH_ROWS]

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Trader Radar — {now.strftime('%Y-%m-%d')}</title>",
        f"<style>{CSS}</style></head>",
        f"<body data-date='{now.strftime('%Y-%m-%d')}'><div class='wrap'>",
        "<header><div><h1>Trader Radar</h1>",
        f"<div class='date'>{now.strftime('%A, %B %-d %Y · %H:%M UTC')} · "
        f"{n_hl} Hyperliquid + {n_pcf} Pacifica traders</div></div>",
        "<nav class='daynav' id='daynav' hidden>"
        "<a id='navprev' title='previous day'>&#8249;</a>"
        "<a id='navnext' title='next day'>&#8250;</a>"
        "<span class='hint'>&larr;/&rarr;</span></nav></header>",
        "<div class='chips'>",
        f"<div class='chip'><div class='k'>Positions</div><div class='v'>{len(positions)}</div></div>",
        f"<div class='chip'><div class='k'>Notional</div><div class='v'>{_fmt_usd(total_notional)}</div></div>",
        f"<div class='chip'><div class='k'>Assets held</div><div class='v'>{len(assets)}</div></div>",
        f"<div class='chip'><div class='k'>Fresh calls</div><div class='v'>{len(fresh_shown)}</div></div>",
        "</div>",
    ]

    # --- fresh conviction ---
    parts.append("<section><h2>Possible early calls</h2>")
    parts.append(
        "<p class='sub'>Opened in the last 7 days by multiple top traders, "
        "price barely moved since entry.</p><div class='card'>"
    )
    if fresh_shown:
        parts.append(
            "<table><tr><th>Asset</th><th>Direction</th><th class='num'>Traders</th>"
            "<th class='num'>Fresh notional</th><th class='num'>Move since entry</th>"
            "<th class='num'>Median age</th><th class='num'>Best trader rank</th></tr>"
        )
        for r in fresh_shown:
            parts.append(
                f"<tr><td class='sym'>{_esc(r['symbol'])}</td><td>{_dir(r['direction'])}</td>"
                f"<td class='num'>{r['traders']}</td>"
                f"<td class='num'>{_fmt_usd(r['notional_usd'])}</td>"
                f"<td class='num'>{_pnl(r['median_upnl_pct'])}</td>"
                f"<td class='num'>{r['median_age_days']:.1f}d</td>"
                f"<td class='num'>#{r['best_ranked_trader']}</td></tr>"
            )
        parts.append("</table>")
    else:
        parts.append("<div class='empty'>No qualifying fresh entries today.</div>")
    parts.append("</div></section>")

    # --- most held ---
    parts.append("<section><h2>Most-held assets</h2>")
    parts.append(
        f"<p class='sub'>Assets held by at least {MIN_HOLDERS_SHOWN} of the "
        f"{len(traders)} cohort traders, by gross notional. Full detail in assets.json.</p>"
        "<div class='card'><table>"
        "<tr><th>Asset</th><th>Verdict</th><th class='num'>Held by</th>"
        "<th class='num'>L / S</th><th class='num'>Net notional</th>"
        "<th class='num'>Median uPnL</th><th class='num'>Median age</th>"
        "<th class='num'>New 7d</th></tr>"
    )
    for a in held:
        age = f"{a['median_age_days']:.0f}d" if a["median_age_days"] is not None else "&gt;45d"
        parts.append(
            f"<tr><td class='sym'>{_esc(a['symbol'])}</td><td>{_badge(a['verdict'])}</td>"
            f"<td class='num'>{a['traders']} <span class='muted'>({a['crowding_pct']}%)</span></td>"
            f"<td class='num'><span class='pos'>{a['longs']}</span> / "
            f"<span class='neg'>{a['shorts']}</span></td>"
            f"<td class='num'>{_fmt_usd(a['net_notional_usd'])}</td>"
            f"<td class='num'>{_pnl(a['median_upnl_pct'])}</td>"
            f"<td class='num'>{age}</td><td class='num'>{a['recent_entries_7d']}</td></tr>"
        )
    parts.append("</table></div></section>")

    # --- elite watch ---
    if elite_notes:
        parts.append(
            "<section><h2>Elite-25 watch</h2>"
            "<p class='sub'>Where the top 25 traders per venue read differently "
            "than the full cohort.</p><div class='card'><ul class='notes'>"
        )
        for note in elite_notes[:6]:
            parts.append(f"<li>{_esc(note)}</li>")
        parts.append("</ul></div></section>")

    # --- disagreements ---
    if splits:
        parts.append(
            "<section><h2>Where top traders disagree</h2>"
            "<p class='sub'>Meaningful long/short splits — no consensus here.</p>"
            "<div class='card'><ul class='notes'>"
        )
        for a in splits[:MAX_SPLITS]:
            parts.append(
                f"<li><span class='sym'>{_esc(a['symbol'])}</span>: "
                f"<span class='pos'>{a['longs']} long ({_fmt_usd(a['notional_long_usd'])})</span>"
                f" vs <span class='neg'>{a['shorts']} short "
                f"({_fmt_usd(a['notional_short_usd'])})</span></li>"
            )
        parts.append("</ul></div></section>")

    # --- changes vs previous ---
    if changes:
        items = changes.get("verdict_changes", [])[:MAX_CHANGES]
        new_syms = changes.get("new_assets", [])
        parts.append(
            f"<section><h2>Changes vs {changes['previous_date']}</h2><div class='card'>"
        )
        if items or new_syms:
            parts.append("<ul class='notes'>")
            parts += [f"<li>{_esc(c)}</li>" for c in items]
            if new_syms:
                parts.append(f"<li>New on the radar: {_esc(', '.join(new_syms[:10]))}</li>")
            parts.append("</ul>")
        else:
            parts.append("<div class='empty'>No material changes.</div>")
        parts.append("</div></section>")

    # --- biggest individual new bets ---
    names = {(t.venue, t.address): t.display_name for t in traders}
    new_bets = sorted(
        (p for p in positions if p.age_days is not None and p.age_days <= 7),
        key=lambda p: p.notional_usd,
        reverse=True,
    )[:MAX_NEW_BETS]
    if new_bets:
        parts.append(
            "<section><h2>Biggest new bets</h2>"
            "<p class='sub'>Largest single positions opened in the last 7 days — "
            "solo conviction that aggregate views miss.</p><div class='card'><table>"
            "<tr><th>Trader</th><th>Asset</th><th>Direction</th>"
            "<th class='num'>Size</th><th class='num'>Move since entry</th>"
            "<th class='num'>Age</th></tr>"
        )
        for p in new_bets:
            name = names.get((p.venue, p.address)) or (
                p.address[:6] + "…" + p.address[-4:]
            )
            venue_tag = "HL" if p.venue == "hyperliquid" else "PCF"
            parts.append(
                f"<tr><td>{_esc(name)} <span class='muted'>#{p.trader_rank} "
                f"{venue_tag}</span></td>"
                f"<td class='sym'>{_esc(p.symbol)}</td><td>{_dir(p.direction)}</td>"
                f"<td class='num'>{_fmt_usd(p.notional_usd)}</td>"
                f"<td class='num'>{_pnl(p.upnl_pct)}</td>"
                f"<td class='num'>{p.age_days:.1f}d</td></tr>"
            )
        parts.append("</table></div></section>")

    parts.append(
        "<footer>Verdicts — <b>EARLY</b>: several fresh entries, price hasn't moved yet · "
        "<b>CROWDED/LATE</b>: median move since entry ≥ +50% · <b>UNDERWATER</b>: smart "
        "money down ≥ 10% · <b>MID</b>: in between. Position ages on Hyperliquid are "
        "reconstructed from 45 days of fills; &gt;45d means older than the lookback. "
        "All data from public Hyperliquid and Pacifica endpoints.</footer>"
        "</div>"
        # Day navigation: when hosted next to a dates.json manifest, wire up
        # prev/next links and left/right arrow keys. Standalone (file://) the
        # fetch fails and the nav simply stays hidden.
        "<script>"
        "fetch('dates.json').then(r=>r.json()).then(ds=>{"
        "const cur=document.body.dataset.date,i=ds.indexOf(cur);if(i<0)return;"
        "const prev=i>0?ds[i-1]:null,next=i<ds.length-1?ds[i+1]:null;"
        "const nav=document.getElementById('daynav');nav.hidden=false;"
        "const P=document.getElementById('navprev'),N=document.getElementById('navnext');"
        "if(prev)P.href=prev+'.html';else P.classList.add('off');"
        "if(next)N.href=next+'.html';else N.classList.add('off');"
        "document.addEventListener('keydown',e=>{"
        "if(e.key==='ArrowLeft'&&prev)location.href=prev+'.html';"
        "if(e.key==='ArrowRight'&&next)location.href=next+'.html';});"
        "}).catch(()=>{});"
        "</script></body></html>"
    )
    return "".join(parts)
