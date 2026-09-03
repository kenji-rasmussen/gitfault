"""Rich-based terminal rendering."""
from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table
from rich import box

from . import analysis as A

console = Console()
err_console = Console(stderr=True)


def _ago(dt: datetime) -> str:
    days = (datetime.now(timezone.utc) - dt).days
    if days <= 0:
        return "today"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


def _bar(frac: float, width: int = 10) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = round(frac * width)
    color = "red" if frac > 0.66 else "yellow" if frac > 0.33 else "green"
    return f"[{color}]{'█' * filled}{'░' * (width - filled)}[/{color}]"


def render_overview(o: A.Overview) -> None:
    t = Table(box=box.SIMPLE_HEAVY, show_header=False, title="repository")
    t.add_column(style="bold cyan")
    t.add_column()
    span = f"{o.first:%Y-%m-%d} → {o.last:%Y-%m-%d}"
    t.add_row("commits", f"{o.commits:,}")
    t.add_row("authors", f"{o.authors:,}")
    t.add_row("tracked files", f"{o.files_tracked:,}")
    t.add_row("history", span)
    t.add_row("busiest month", f"{o.busiest_month[0]} ({o.busiest_month[1]} commits)")
    console.print(t)


_HEALTH_STYLE = {
    "brightgreen": "bold green", "green": "green", "yellowgreen": "yellow",
    "yellow": "yellow", "orange": "dark_orange", "red": "bold red",
}


def render_health(h: A.Health) -> None:
    style = _HEALTH_STYLE.get(h.color, "white")
    console.print(
        f"health score  [{style}]{h.score}/100  grade {h.grade}[/{style}]"
        f"   [dim](bus factor {h.bus_factor} · "
        f"{h.solo_ratio:.0%} solo-owned lines)[/dim]")


def render_hotspots(rows: list[A.Hotspot], top: int) -> None:
    t = Table(title=f"🔥 hotspots (top {top}) — high change × high complexity",
              box=box.SIMPLE_HEAVY, header_style="bold")
    t.add_column("risk", justify="left")
    t.add_column("file", overflow="fold")
    t.add_column("revs", justify="right")
    t.add_column("lines", justify="right")
    t.add_column("churn", justify="right")
    t.add_column("devs", justify="right")
    t.add_column("last", justify="right")
    top_score = rows[0].score if rows else 1.0
    for h in rows[:top]:
        rel = h.score / top_score if top_score else 0
        t.add_row(_bar(rel), h.path, str(h.revisions), f"{h.lines:,}",
                  f"{h.churn:,}", str(h.authors), _ago(h.last_change))
    console.print(t)
    if not rows:
        console.print("[dim]no hotspots found (empty/filtered history)[/dim]")


def render_coupling(rows: list[A.Coupling], top: int) -> None:
    t = Table(title=f"🔗 change coupling (top {top}) — files that change together",
              box=box.SIMPLE_HEAVY, header_style="bold")
    t.add_column("coupling", justify="left")
    t.add_column("file A", overflow="fold")
    t.add_column("file B", overflow="fold")
    t.add_column("shared", justify="right")
    for c in rows[:top]:
        t.add_row(f"{_bar(c.degree)} {c.degree*100:4.0f}%", c.a, c.b,
                  f"{c.shared}/{min(c.revs_a, c.revs_b)}")
    console.print(t)
    if not rows:
        console.print("[dim]no significant coupling found "
                      "(try lowering --min-shared)[/dim]")


def render_knowledge(k: A.KnowledgeReport, top: int) -> None:
    hdr = Table(box=box.SIMPLE_HEAVY, show_header=False, title="🧠 knowledge risk")
    hdr.add_column(style="bold cyan")
    hdr.add_column()
    solo = (k.solo_owned_lines / k.total_lines * 100) if k.total_lines else 0
    hdr.add_row("bus factor", f"[bold]{k.bus_factor}[/bold] "
                f"(devs holding 50% of the code)")
    hdr.add_row("contributors", str(k.total_authors))
    hdr.add_row("single-author code", f"{solo:.0f}% of lines owned by one dev")
    console.print(hdr)

    t = Table(title=f"top contributors by code owned", box=box.SIMPLE,
              header_style="bold")
    t.add_column("author", overflow="fold")
    t.add_column("lines owned", justify="right")
    t.add_column("share", justify="right")
    total = k.total_lines or 1
    for name, lines in k.top_authors[:min(top, 10)]:
        t.add_row(name, f"{lines:,}", f"{lines/total*100:.0f}%")
    console.print(t)

    risky = [f for f in k.files if f.authors == 1 and f.lines >= 40][:top]
    if risky:
        rt = Table(title="⚠️  key files known to only ONE developer",
                   box=box.SIMPLE, header_style="bold")
        rt.add_column("file", overflow="fold")
        rt.add_column("owner", overflow="fold")
        rt.add_column("lines", justify="right")
        for f in risky:
            rt.add_row(f.path, f.main_author, f"{f.lines:,}")
        console.print(rt)
