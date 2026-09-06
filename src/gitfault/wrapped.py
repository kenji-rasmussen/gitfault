"""gitfault wrapped — a shareable "year in review" for any git repository.

Reads the same in-memory commit model as the rest of gitfault and distils it
into a fun, screenshot-ready recap: commits, active days, the longest streak,
the busiest month, night-owl share, top contributors and the single biggest
commit of the period.  Renders a colourful terminal card *and* can emit a
self-contained SVG image (no third-party deps, no network) that people can
drop straight into a README or share on social.
"""
from __future__ import annotations

import html
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .gitlog import Commit

_MONTHS = ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]
_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday"]


@dataclass
class Contributor:
    name: str
    commits: int
    added: int
    deleted: int


@dataclass
class WrappedStats:
    label: str                      # "2026" or "all time"
    commits: int
    active_days: int
    lines_added: int
    lines_deleted: int
    files_touched: int
    contributors: list[Contributor] = field(default_factory=list)
    total_contributors: int = 0
    busiest_month: tuple[str, int] = ("", 0)
    busiest_weekday: tuple[str, int] = ("", 0)
    peak_hour: tuple[int, int] = (0, 0)          # (hour 0-23, count)
    night_owl_pct: float = 0.0                   # commits between 00:00-04:59
    longest_streak: int = 0                      # consecutive active days
    streak_range: tuple[str, str] = ("", "")
    biggest_commit: tuple[str, str, int] = ("", "", 0)   # (sha7, subject, churn)
    most_changed_file: tuple[str, int] = ("", 0)         # (path, revisions)
    first: datetime | None = None
    last: datetime | None = None


def _years(commits: list[Commit]) -> list[int]:
    return sorted({c.when.year for c in commits})


def _churn(c: Commit) -> int:
    return sum(f.added + f.deleted for f in c.files if not f.binary)


def compute(commits: list[Commit], year: int | None = None,
            top: int = 5) -> WrappedStats:
    """Distil commits (optionally filtered to a single calendar year)."""
    if year is not None:
        commits = [c for c in commits if c.when.year == year]
    label = str(year) if year is not None else "all time"
    st = WrappedStats(label=label, commits=len(commits), active_days=0,
                      lines_added=0, lines_deleted=0, files_touched=0)
    if not commits:
        return st

    commits = sorted(commits, key=lambda c: c.when)
    st.first, st.last = commits[0].when, commits[-1].when

    # display name per author email (most common spelling wins)
    names: dict[str, Counter] = defaultdict(Counter)
    for c in commits:
        names[c.email][c.author] += 1
    display = {e: n.most_common(1)[0][0] for e, n in names.items()}

    per_author: dict[str, Contributor] = {}
    months: Counter = Counter()
    weekdays: Counter = Counter()
    hours: Counter = Counter()
    file_revs: Counter = Counter()
    days: set[date] = set()
    night = 0

    for c in commits:
        d = c.when
        days.add(d.date())
        months[(d.year, d.month)] += 1
        weekdays[d.weekday()] += 1
        hours[d.hour] += 1
        if d.hour < 5:
            night += 1
        name = display.get(c.email, c.author)
        con = per_author.get(c.email)
        if con is None:
            con = per_author[c.email] = Contributor(name, 0, 0, 0)
        con.commits += 1
        touched = set()
        for f in c.files:
            if f.binary:
                continue
            con.added += f.added
            con.deleted += f.deleted
            st.lines_added += f.added
            st.lines_deleted += f.deleted
            if f.path not in touched:
                file_revs[f.path] += 1
                touched.add(f.path)

    st.active_days = len(days)
    st.files_touched = len(file_revs)
    st.total_contributors = len(per_author)
    st.contributors = sorted(per_author.values(),
                             key=lambda c: (-c.commits, c.name))[:top]
    st.night_owl_pct = night / len(commits)

    if months:
        (y, m), n = months.most_common(1)[0]
        st.busiest_month = (f"{_MONTHS[m]} {y}", n)
    if weekdays:
        wd, n = weekdays.most_common(1)[0]
        st.busiest_weekday = (_WEEKDAYS[wd], n)
    if hours:
        st.peak_hour = hours.most_common(1)[0]
    if file_revs:
        st.most_changed_file = file_revs.most_common(1)[0]

    big = max(commits, key=_churn)
    st.biggest_commit = (big.sha[:7], big.subject.strip()[:72], _churn(big))

    # longest streak of consecutive active calendar days
    ordered = sorted(days)
    best = run = 1
    run_start = best_start = best_end = ordered[0]
    for prev, cur in zip(ordered, ordered[1:]):
        if cur - prev == timedelta(days=1):
            run += 1
        else:
            run, run_start = 1, cur
        if run > best:
            best, best_start, best_end = run, run_start, cur
    st.longest_streak = best
    st.streak_range = (best_start.isoformat(), best_end.isoformat())
    return st


# --------------------------------------------------------------- rendering ---

def _fmt(n: int) -> str:
    return f"{n:,}"


def render_terminal(console, st: WrappedStats, repo: str) -> None:
    """Pretty terminal recap using rich."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    if st.commits == 0:
        console.print(Panel(f"No commits found for [bold]{st.label}[/bold].",
                            title="gitfault wrapped", border_style="red"))
        return

    head = Text()
    head.append("  gitfault ", style="bold white")
    head.append("wrapped\n", style="bold magenta")
    head.append(f"  {repo}", style="cyan")
    head.append(f"  ·  {st.label}", style="dim")

    grid = Table.grid(padding=(0, 3))
    grid.add_column(justify="right", style="bold magenta")
    grid.add_column(style="white")
    grid.add_row(_fmt(st.commits), "commits")
    grid.add_row(_fmt(st.active_days), "active days")
    grid.add_row(f"{st.longest_streak}", "day longest streak "
                 f"[dim]({st.streak_range[0]} → {st.streak_range[1]})[/dim]")
    grid.add_row(f"+{_fmt(st.lines_added)} / -{_fmt(st.lines_deleted)}",
                 "lines added / removed")
    grid.add_row(_fmt(st.files_touched), "files touched")
    if st.busiest_month[1]:
        grid.add_row(st.busiest_month[0],
                     f"busiest month [dim]({st.busiest_month[1]} commits)[/dim]")
    if st.busiest_weekday[1]:
        grid.add_row(st.busiest_weekday[0],
                     f"busiest day [dim]({st.busiest_weekday[1]} commits)[/dim]")
    grid.add_row(f"{st.peak_hour[0]:02d}:00", "peak hour")
    grid.add_row(f"{st.night_owl_pct * 100:.0f}%",
                 "committed before 5am [dim](night owl)[/dim]")
    grid.add_row(f"{st.biggest_commit[0]}",
                 f"biggest commit [dim](+/-{_fmt(st.biggest_commit[2])} lines)"
                 f"[/dim] {st.biggest_commit[1]}")

    people = Table.grid(padding=(0, 2))
    people.add_column(justify="right", style="dim")
    people.add_column(style="bold")
    people.add_column(justify="right", style="magenta")
    for i, c in enumerate(st.contributors[:8], 1):
        people.add_row(f"{i}.", c.name, f"{_fmt(c.commits)} commits")

    console.print(Panel(head, border_style="magenta", padding=(1, 2)))
    console.print(grid)
    console.print()
    console.print(Text(f"  Top contributors  "
                       f"({st.total_contributors} total)", style="bold"))
    console.print(people)


# ------------------------------------------------------------------ svg ---

_PALETTE = ["#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#3b82f6"]


def _tile(x: int, y: int, w: int, h: int, value: str, label: str,
          color: str) -> str:
    v = html.escape(value)
    l = html.escape(label)
    fs = 44 if len(v) <= 7 else (34 if len(v) <= 11 else 26)
    return (
        f'<g transform="translate({x},{y})">'
        f'<rect width="{w}" height="{h}" rx="18" fill="#161327" '
        f'stroke="#282444"/>'
        f'<text x="26" y="{h - 34}" font-size="{fs}" font-weight="700" '
        f'fill="{color}" font-family="Menlo,Consolas,monospace">{v}</text>'
        f'<text x="26" y="{h - 12}" font-size="15" fill="#9891b8" '
        f'font-family="-apple-system,Segoe UI,Roboto,sans-serif">{l}</text>'
        f'</g>')


def build_svg(st: WrappedStats, repo: str) -> str:
    """A self-contained 1200x630 SVG recap card (no external assets)."""
    W, H = 1200, 630
    repo_s = html.escape(repo)
    tiles = [
        (_fmt(st.commits), "commits"),
        (_fmt(st.active_days), "active days"),
        (str(st.longest_streak), "day streak"),
        (f"+{_fmt(st.lines_added)}", "lines added"),
        (st.busiest_month[0] or "—", "busiest month"),
        (f"{st.night_owl_pct * 100:.0f}%", "before 5am"),
    ]
    tw, th, gap = 348, 118, 30
    x0, y0 = 60, 210
    body = []
    for i, (val, lab) in enumerate(tiles):
        col, row = i % 3, i // 3
        x = x0 + col * (tw + gap)
        y = y0 + row * (th + gap)
        body.append(_tile(x, y, tw, th, val, lab, _PALETTE[i % len(_PALETTE)]))

    # contributor bar
    cy = 500
    people = []
    total = sum(c.commits for c in st.contributors) or 1
    bx = 60
    bar_w = W - 120
    x = bx
    for i, c in enumerate(st.contributors):
        seg = max(6, int(bar_w * c.commits / total))
        people.append(
            f'<rect x="{x}" y="{cy}" width="{seg - 3}" height="20" rx="6" '
            f'fill="{_PALETTE[i % len(_PALETTE)]}"/>')
        x += seg
    legend = []
    lx = 60
    for i, c in enumerate(st.contributors[:4]):
        nm = html.escape(c.name[:22])
        legend.append(
            f'<circle cx="{lx + 7}" cy="{cy + 52}" r="7" '
            f'fill="{_PALETTE[i % len(_PALETTE)]}"/>'
            f'<text x="{lx + 22}" y="{cy + 58}" font-size="16" fill="#c9c4de" '
            f'font-family="-apple-system,Segoe UI,Roboto,sans-serif">'
            f'{nm} · {c.commits}</text>')
        lx += 60 + len(c.name[:22]) * 10 + 40

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" \
viewBox="0 0 {W} {H}" font-family="-apple-system,Segoe UI,Roboto,sans-serif">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#0d0b1a"/><stop offset="1" stop-color="#1a1330"/>
</linearGradient></defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<rect x="0" y="0" width="{W}" height="8" fill="#8b5cf6"/>
<text x="60" y="88" font-size="30" font-weight="800" fill="#ffffff">gitfault \
<tspan fill="#c4b5fd">wrapped</tspan></text>
<text x="60" y="132" font-size="40" font-weight="800" fill="#ffffff">{repo_s}\
</text>
<text x="60" y="170" font-size="22" fill="#9891b8">{html.escape(st.label)} · \
{st.total_contributors} contributor{"s" if st.total_contributors != 1 else ""} · \
{_fmt(st.files_touched)} files touched</text>
{''.join(body)}
<text x="60" y="{cy - 14}" font-size="16" fill="#9891b8" font-weight="600">\
TOP CONTRIBUTORS</text>
{''.join(people)}
{''.join(legend)}
<text x="{W - 60}" y="{H - 26}" text-anchor="end" font-size="15" \
fill="#6b6488">generated by gitfault · pip install gitfault</text>
</svg>'''
