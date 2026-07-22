"""Self-contained interactive HTML report.

Zero runtime dependencies, no CDN, no network: everything (CSS + a squarified
treemap laid out in Python and emitted as inline SVG + a little vanilla JS for
tooltips/filtering) is inlined into one file you can open offline or drop into
a CI artifact / GitHub Pages.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from . import analysis as A

_MAX_TILES = 220  # keep the SVG light and readable


# --------------------------------------------------------------- treemap ---
def _squarify(items, x, y, w, h):
    """Squarified treemap (Bruls, Huizing, van Wijk 2000).

    items: list of (value, payload) sorted desc by value. Returns list of
    (payload, x, y, w, h) rectangles filling the (x,y,w,h) box.
    """
    rects = []
    items = [it for it in items if it[0] > 0]
    total = sum(v for v, _ in items)
    if total <= 0 or w <= 0 or h <= 0:
        return rects
    # scale values to area
    scale = (w * h) / total
    vals = [(v * scale, p) for v, p in items]

    def worst(row, length):
        s = sum(v for v, _ in row)
        mx = max(v for v, _ in row)
        mn = min(v for v, _ in row)
        if s == 0:
            return float("inf")
        return max((length * length * mx) / (s * s),
                   (s * s) / (length * length * mn))

    def layout_row(row, x, y, w, h, horizontal):
        s = sum(v for v, _ in row)
        if horizontal:
            rw = s / h if h else 0
            cy = y
            for v, p in row:
                rh = v / rw if rw else 0
                rects.append((p, x, cy, rw, rh))
                cy += rh
            return x + rw, y, w - rw, h
        else:
            rh = s / w if w else 0
            cx = x
            for v, p in row:
                rw = v / rh if rh else 0
                rects.append((p, cx, y, rw, rh))
                cx += rw
            return x, y + rh, w, h - rh

    row = []
    i = 0
    while i < len(vals):
        horizontal = w >= h
        length = h if horizontal else w
        v = vals[i]
        if not row:
            row = [v]
            i += 1
            continue
        if worst(row, length) >= worst(row + [v], length):
            row.append(v)
            i += 1
        else:
            x, y, w, h = layout_row(row, x, y, w, h, horizontal)
            row = []
    if row:
        horizontal = w >= h
        layout_row(row, x, y, w, h, horizontal)
    return rects


def _heat(frac: float) -> str:
    """green -> yellow -> red for frac in 0..1."""
    frac = max(0.0, min(1.0, frac))
    if frac < 0.5:
        t = frac / 0.5
        r, g, b = int(46 + t * (240 - 46)), int(160 + t * (196 - 160)), int(67 + t * (15 - 67))
    else:
        t = (frac - 0.5) / 0.5
        r, g, b = int(240 + t * (215 - 240)), int(196 + t * (40 - 196)), int(15 + t * (40 - 15))
    return f"rgb({r},{g},{b})"


def _treemap_svg(hotspots, width=1000, height=520):
    rows = hotspots[:_MAX_TILES]
    if not rows:
        return "<p class='empty'>No hotspots to plot.</p>"
    max_rev = max(h.revisions for h in rows) or 1
    items = [(max(h.lines, 1), h) for h in rows]
    rects = _squarify(items, 0, 0, width, height)
    parts = [f'<svg viewBox="0 0 {width} {height}" '
             f'preserveAspectRatio="xMidYMid meet" class="treemap" '
             f'role="img" aria-label="Hotspot treemap">']
    for h, x, y, w, wh in rects:
        if w < 0.6 or wh < 0.6:
            continue
        frac = h.revisions / max_rev
        fill = _heat(frac)
        label = html.escape(h.path.rsplit("/", 1)[-1])
        tip = html.escape(f"{h.path} · {h.revisions} revs · {h.lines:,} lines "
                          f"· {h.authors} devs")
        parts.append(
            f'<g class="tile" data-path="{html.escape(h.path)}">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{wh:.1f}" '
            f'fill="{fill}" stroke="#0d1117" stroke-width="0.7">'
            f'<title>{tip}</title></rect>')
        if w > 46 and wh > 16:
            fs = min(13, max(9, wh / 2.4))
            parts.append(
                f'<text x="{x + 3:.1f}" y="{y + fs:.1f}" '
                f'font-size="{fs:.0f}" fill="#0d1117" '
                f'style="pointer-events:none">{label}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------- template ---
_CSS = """
:root{--bg:#0d1117;--panel:#161b22;--border:#30363d;--fg:#e6edf3;
--muted:#8b949e;--accent:#58a6ff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1060px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 2px}
h1 .fault{color:#f85149}
.sub{color:var(--muted);margin:0 0 26px;font-size:14px}
h2{font-size:16px;margin:38px 0 12px;letter-spacing:.02em}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.card .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.card .v{font-size:22px;font-weight:600;margin-top:4px}
.card .v small{font-size:13px;color:var(--muted);font-weight:400}
.legend{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:12px;margin:6px 0 10px}
.grad{height:10px;width:180px;border-radius:5px;
background:linear-gradient(90deg,rgb(46,160,67),rgb(240,196,15),rgb(215,40,40))}
.treewrap{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:10px}
.treemap{width:100%;height:auto;display:block}
.tile:hover rect{stroke:#fff;stroke-width:1.4}
table{width:100%;border-collapse:collapse;background:var(--panel);
border:1px solid var(--border);border-radius:10px;overflow:hidden;font-size:14px}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--border)}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.path{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.bar{height:8px;border-radius:4px;background:#21262d;overflow:hidden;min-width:60px}
.bar>span{display:block;height:100%}
.pill{display:inline-block;padding:1px 8px;border-radius:20px;font-size:12px;
background:#21262d;color:var(--muted)}
.warn{color:#f0b429}
footer{margin-top:48px;color:var(--muted);font-size:12px;border-top:1px solid var(--border);padding-top:16px}
a{color:var(--accent);text-decoration:none}
.empty{color:var(--muted)}
"""


def _bar(frac, color):
    pct = max(0, min(100, frac * 100))
    return (f'<div class="bar"><span style="width:{pct:.0f}%;'
            f'background:{color}"></span></div>')


def _ago(dt: datetime) -> str:
    days = (datetime.now(timezone.utc) - dt).days
    if days <= 0:
        return "today"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def build_report(root, overview, hotspots, coupling, knowledge,
                 top: int = 30) -> str:
    esc = html.escape
    o = overview
    max_rev = max((h.revisions for h in hotspots), default=1) or 1

    # hotspot rows
    hs_rows = []
    top_score = hotspots[0].score if hotspots else 1.0
    for h in hotspots[:top]:
        rel = (h.score / top_score) if top_score else 0
        hs_rows.append(
            f"<tr><td style='width:90px'>{_bar(rel, _heat(h.revisions/max_rev))}</td>"
            f"<td class='path'>{esc(h.path)}</td>"
            f"<td class='num'>{h.revisions}</td>"
            f"<td class='num'>{h.lines:,}</td>"
            f"<td class='num'>{h.churn:,}</td>"
            f"<td class='num'>{h.authors}</td>"
            f"<td class='num'>{_ago(h.last_change)}</td></tr>")

    # coupling rows
    cp_rows = []
    for c in coupling[:top]:
        cp_rows.append(
            f"<tr><td style='width:110px'>{_bar(c.degree, '#58a6ff')}</td>"
            f"<td class='num'>{c.degree*100:.0f}%</td>"
            f"<td class='path'>{esc(c.a)}</td>"
            f"<td class='path'>{esc(c.b)}</td>"
            f"<td class='num'>{c.shared}/{min(c.revs_a, c.revs_b)}</td></tr>")
    if not cp_rows:
        cp_rows.append("<tr><td colspan='5' class='empty'>No significant "
                       "coupling found (try lowering --min-shared).</td></tr>")

    # knowledge
    k = knowledge
    solo = (k.solo_owned_lines / k.total_lines * 100) if k.total_lines else 0
    total = k.total_lines or 1
    ka_rows = []
    for name, lines in k.top_authors[:12]:
        share = lines / total
        ka_rows.append(
            f"<tr><td>{esc(name)}</td>"
            f"<td class='num'>{lines:,}</td>"
            f"<td style='width:120px'>{_bar(share, '#3fb950')}</td>"
            f"<td class='num'>{share*100:.0f}%</td></tr>")
    risky = [f for f in k.files if f.authors == 1 and f.lines >= 40][:top]
    risk_rows = []
    for f in risky:
        risk_rows.append(
            f"<tr><td class='path'>{esc(f.path)}</td>"
            f"<td>{esc(f.main_author)}</td>"
            f"<td class='num'>{f.lines:,}</td></tr>")
    if not risk_rows:
        risk_rows.append("<tr><td colspan='3' class='empty'>No single-owner "
                         "key files — knowledge is well spread. 🎉</td></tr>")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    span = f"{o.first:%Y-%m-%d} → {o.last:%Y-%m-%d}"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gitfault report — {esc(root.rsplit('/', 1)[-1])}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<h1>git<span class="fault">fault</span> report</h1>
<p class="sub"><span class="path">{esc(root)}</span> · {span} · generated {generated}</p>

<div class="cards">
  <div class="card"><div class="k">commits</div><div class="v">{o.commits:,}</div></div>
  <div class="card"><div class="k">authors</div><div class="v">{o.authors:,}</div></div>
  <div class="card"><div class="k">tracked files</div><div class="v">{o.files_tracked:,}</div></div>
  <div class="card"><div class="k">bus factor</div><div class="v">{k.bus_factor} <small>hold 50%</small></div></div>
  <div class="card"><div class="k">single-author code</div><div class="v">{solo:.0f}%</div></div>
  <div class="card"><div class="k">busiest month</div><div class="v">{esc(o.busiest_month[0])} <small>{o.busiest_month[1]}</small></div></div>
</div>

<h2>🔥 Hotspot map</h2>
<div class="legend"><span>size = lines of code</span><span>·</span>
<span>colour = change frequency</span><div class="grad"></div>
<span>low → high</span></div>
<div class="treewrap">{_treemap_svg(hotspots)}</div>

<h2>🔥 Hotspots — high change × high complexity</h2>
<table><thead><tr><th>risk</th><th>file</th><th class="num">revs</th>
<th class="num">lines</th><th class="num">churn</th><th class="num">devs</th>
<th class="num">last</th></tr></thead><tbody>{''.join(hs_rows)}</tbody></table>

<h2>🔗 Change coupling — files that change together</h2>
<table><thead><tr><th>coupling</th><th class="num">degree</th><th>file A</th>
<th>file B</th><th class="num">shared</th></tr></thead>
<tbody>{''.join(cp_rows)}</tbody></table>

<h2>🧠 Knowledge — who owns what</h2>
<table><thead><tr><th>contributor</th><th class="num">lines owned</th>
<th>share</th><th class="num"></th></tr></thead>
<tbody>{''.join(ka_rows)}</tbody></table>

<h2 class="warn">⚠️ Key files known to only ONE developer</h2>
<table><thead><tr><th>file</th><th>owner</th><th class="num">lines</th></tr></thead>
<tbody>{''.join(risk_rows)}</tbody></table>

<footer>Generated by <a href="https://github.com/kenji-rasmussen/gitfault">gitfault</a>
— behavioural code analysis from your git history. This report is fully
self-contained (no tracking, no network).</footer>
</div></body></html>"""
