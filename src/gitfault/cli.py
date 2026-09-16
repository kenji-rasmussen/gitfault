"""gitfault command-line interface."""
from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict

from . import __version__
from . import analysis as A
from . import gitlog
from . import render


_REMOTE_SCHEMES = ("http://", "https://", "git://", "ssh://", "git@", "file://")
_SHORTHAND = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$")


def _is_remote(spec: str) -> bool:
    """True if `spec` should be cloned rather than read as a local path."""
    if spec.startswith(_REMOTE_SCHEMES):
        return True
    if spec.startswith("github.com/") or spec.startswith("gitlab.com/"):
        return True
    # `owner/repo` shorthand — only when it isn't an existing local path
    if _SHORTHAND.match(spec) and not os.path.exists(spec):
        return True
    return False


def _clone_url(spec: str) -> str:
    if spec.startswith(_REMOTE_SCHEMES):
        return spec
    if spec.startswith(("github.com/", "gitlab.com/")):
        return "https://" + spec
    return "https://github.com/" + spec  # owner/repo shorthand


def _resolve_path(spec: str) -> str:
    """Return a local path for `spec`, cloning it first if it's remote."""
    if not _is_remote(spec):
        return spec
    url = _clone_url(spec)
    if shutil.which("git") is None:
        raise gitlog.NotAGitRepo("git is required to clone a remote repository")
    tmp = tempfile.mkdtemp(prefix="gitfault-clone-")
    atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))
    render.err_console.print(f"[dim]cloning {url} …[/dim]")
    try:
        subprocess.run(
            ["git", "clone", "--quiet", url, tmp],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or b"").decode("utf-8", "replace").strip()
        raise gitlog.NotAGitRepo(
            f"could not clone {url}" + (f": {msg}" if msg else "")) from None
    return tmp


def _load(args):
    spec = args.path
    args.path = _resolve_path(spec)
    # for cloned remotes, show the friendly spec instead of the temp dir
    args.display = spec if args.path != spec else None
    root, commits = gitlog.collect_commits(args.path, since=args.since,
                                           until=args.until)
    excludes = list(A.DEFAULT_EXCLUDES)
    if args.exclude:
        excludes += args.exclude
    if args.no_default_excludes:
        excludes = list(args.exclude or [])
    commits = A.filter_commits(commits, excludes, args.include)
    line_counts = gitlog.current_line_counts(args.path, root)
    # only keep live files that passed include/exclude filters
    if args.include or not args.no_default_excludes:
        keep = {f.path for c in commits for f in c.files}
        line_counts = {p: n for p, n in line_counts.items() if p in keep}
    return root, commits, line_counts


def _emit_json(obj) -> None:
    def default(o):
        from datetime import datetime
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)
    json.dump(obj, sys.stdout, default=default, indent=2)
    sys.stdout.write("\n")


def cmd_overview(args):
    root, commits, lc = _load(args)
    o = A.overview(commits, lc)
    hs = A.hotspots(commits, lc)
    k = A.knowledge(commits, lc)
    hlth = A.health(hs, k)
    if args.json:
        _emit_json({"overview": asdict(o),
                    "health": asdict(hlth),
                    "hotspots": [asdict(h) for h in hs[:args.top]]})
        return
    render.console.print(
        f"[bold]gitfault[/bold] [dim]{args.display or root}[/dim]\n")
    render.render_overview(o)
    render.render_health(hlth)
    render.console.print()
    render.render_hotspots(hs, args.top)
    render.console.print("\n[dim]› gitfault coupling · gitfault knowledge · "
                         "--help for more[/dim]")


def cmd_hotspots(args):
    _, commits, lc = _load(args)
    hs = A.hotspots(commits, lc)
    if args.json:
        _emit_json([asdict(h) for h in hs[:args.top]])
    else:
        render.render_hotspots(hs, args.top)


def cmd_coupling(args):
    _, commits, lc = _load(args)
    cp = A.coupling(commits, lc, min_shared=args.min_shared,
                    min_revs=args.min_revs)
    if args.json:
        _emit_json([asdict(c) for c in cp[:args.top]])
    else:
        render.render_coupling(cp, args.top)


def cmd_knowledge(args):
    _, commits, lc = _load(args)
    k = A.knowledge(commits, lc)
    if args.json:
        _emit_json(asdict(k))
    else:
        render.render_knowledge(k, args.top)


def cmd_markdown(args):
    """render the full analysis as GitHub-flavoured Markdown (to stdout)"""
    from . import mdreport
    root, commits, lc = _load(args)
    o = A.overview(commits, lc)
    hs = A.hotspots(commits, lc)
    cp = A.coupling(commits, lc, min_shared=args.min_shared,
                    min_revs=args.min_revs)
    k = A.knowledge(commits, lc)
    md = mdreport.build_markdown(args.display or root, o, hs, cp, k, top=args.top)
    if getattr(args, "output", None):
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(md)
        render.console.print(
            f"[green]✓[/green] wrote Markdown report → [bold]{args.output}[/bold] "
            f"[dim]({len(md):,} bytes)[/dim]")
    else:
        sys.stdout.write(md)


def cmd_badge(args):
    """emit a shields.io endpoint JSON for an embeddable code-health badge"""
    _, commits, lc = _load(args)
    hs = A.hotspots(commits, lc)
    k = A.knowledge(commits, lc)
    h = A.health(hs, k)
    label = args.label or "code health"
    message = args.message or f"{h.grade} ({h.score})"
    badge = {
        "schemaVersion": 1,
        "label": label,
        "message": message,
        "color": h.color,
    }
    if getattr(args, "output", None):
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(badge, fh, indent=2)
            fh.write("\n")
        render.err_console.print(
            f"[green]OK[/green] wrote badge endpoint -> [bold]{args.output}[/bold] "
            f"[dim](grade {h.grade}, score {h.score})[/dim]")
    else:
        _emit_json(badge)


def cmd_report(args):
    """generate a self-contained interactive HTML report"""
    from . import htmlreport
    root, commits, lc = _load(args)
    o = A.overview(commits, lc)
    hs = A.hotspots(commits, lc)
    cp = A.coupling(commits, lc, min_shared=args.min_shared,
                    min_revs=args.min_revs)
    k = A.knowledge(commits, lc)
    html_text = htmlreport.build_report(args.display or root, o, hs, cp, k, top=args.top)
    out = args.output
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    render.console.print(
        f"[green]✓[/green] wrote self-contained report → [bold]{out}[/bold] "
        f"[dim]({len(html_text):,} bytes)[/dim]")
    if args.open:
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(out)}")


def cmd_wrapped(args):
    """a shareable 'year in review' recap of a repo's git history"""
    from . import wrapped
    root, commits, lc = _load(args)
    repo = args.display or os.path.basename(os.path.abspath(root)) or root
    year = args.year
    if year is None and not args.all_time:
        years = wrapped._years(commits)
        if years:
            year = years[-1]  # most recent year with activity
    st = wrapped.compute(commits, year=year, top=max(5, args.top))
    if args.json:
        _emit_json(asdict(st))
        return
    if getattr(args, "svg", None):
        svg = wrapped.build_svg(st, repo)
        with open(args.svg, "w", encoding="utf-8") as fh:
            fh.write(svg)
        render.console.print(
            f"[green]\u2713[/green] wrote recap card \u2192 [bold]{args.svg}[/bold] "
            f"[dim]({len(svg):,} bytes)[/dim]")
        return
    wrapped.render_terminal(render.console, st, repo)


def _norm_path(p: str) -> str:
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def cmd_guard(args):
    """warn when you're touching a repo's fault lines (great as a pre-commit hook)"""
    _, commits, lc = _load(args)
    hs = A.hotspots(commits, lc)
    k = A.knowledge(commits, lc)

    rank = {h.path: i + 1 for i, h in enumerate(hs)}
    hs_by_path = {h.path: h for h in hs}
    own = {f.path: f for f in k.files}
    multi_author = k.total_authors >= 2

    targets = [_norm_path(f) for f in (args.files or [])]
    if not targets:
        try:
            out = subprocess.run(
                ["git", "-C", args.path, "diff", "--name-only", "HEAD~1", "HEAD"],
                capture_output=True, text=True, check=True).stdout
            targets = [_norm_path(x) for x in out.splitlines() if x.strip()]
        except Exception:
            targets = []

    findings = []
    for path in targets:
        h = hs_by_path.get(path)
        o = own.get(path)
        reasons = []
        if h is not None and rank.get(path, 10 ** 9) <= args.top:
            reasons.append({
                "kind": "hotspot", "rank": rank[path],
                "revisions": h.revisions, "churn": h.churn,
                "text": f"hotspot #{rank[path]} ({h.revisions} revs, "
                        f"{h.churn:,} lines churned)",
            })
        if o is not None and multi_author and (
                o.authors == 1 or o.main_share >= args.min_share):
            if o.authors == 1:
                text = f"knowledge silo: only {o.main_author} has ever touched it"
            else:
                text = (f"knowledge silo: {o.main_share*100:.0f}% owned by "
                        f"{o.main_author}")
            reasons.append({
                "kind": "knowledge", "main_author": o.main_author,
                "main_share": round(o.main_share, 3), "authors": o.authors,
                "text": text,
            })
        if reasons:
            findings.append({"path": path, "reasons": reasons})

    if args.json:
        _emit_json({"flagged": findings, "checked": len(targets)})
    elif findings:
        render.err_console.print(
            "[bold yellow]gitfault guard[/bold yellow] flagged "
            f"{len(findings)} file(s) on a fault line:")
        for f in findings:
            render.err_console.print(f"  [bold]{f['path']}[/bold]")
            for r in f["reasons"]:
                render.err_console.print(f"    [yellow]\u2022[/yellow] {r['text']}")
        render.err_console.print(
            "[dim]  \u2192 review carefully; consider pairing / adding a test / "
            "spreading ownership.[/dim]")
    else:
        render.err_console.print(
            f"[green]gitfault guard[/green] OK \u2014 no fault lines in "
            f"{len(targets)} changed file(s).")

    if findings and args.strict:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gitfault",
        description="Find the fault lines in any codebase — hotspots, "
                    "change-coupling and knowledge risk from git history.")
    p.add_argument("--version", action="version",
                   version=f"gitfault {__version__}")

    def common(sp):
        sp.add_argument("-C", "--path", default=".",
                        help="local path, or a remote to clone: a URL or "
                             "'owner/repo' GitHub shorthand (default: .)")
        sp.add_argument("--since", help="only commits after this date "
                        "(e.g. '2023-01-01' or '18 months ago')")
        sp.add_argument("--until", help="only commits before this date")
        sp.add_argument("--top", type=int, default=20,
                        help="rows to show (default: 20)")
        sp.add_argument("--exclude", action="append", metavar="GLOB",
                        help="extra path glob to ignore (repeatable)")
        sp.add_argument("--include", action="append", metavar="GLOB",
                        help="only include paths matching this glob (repeatable)")
        sp.add_argument("--no-default-excludes", action="store_true",
                        help="don't skip lockfiles/vendor/minified/etc.")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    sub = p.add_subparsers(dest="cmd")
    for name, fn, extra in [
        ("overview", cmd_overview, None),
        ("hotspots", cmd_hotspots, None),
        ("coupling", cmd_coupling, "coupling"),
        ("knowledge", cmd_knowledge, None),
        ("markdown", cmd_markdown, "markdown"),
        ("report", cmd_report, "report"),
        ("badge", cmd_badge, "badge"),
        ("wrapped", cmd_wrapped, "wrapped"),
        ("guard", cmd_guard, "guard"),
    ]:
        sp = sub.add_parser(name, help=fn.__doc__)
        common(sp)
        if extra == "badge":
            sp.add_argument("--label", default=None,
                            help="badge left-hand label (default: 'code health')")
            sp.add_argument("--message", default=None,
                            help="override the right-hand text (default: 'A (87)')")
            sp.add_argument("-o", "--output", default=None,
                            help="write endpoint JSON to this file (default: stdout)")
        if extra in ("coupling", "report", "markdown"):
            sp.add_argument("--min-shared", type=int, default=4,
                            help="min shared commits for a pair (default: 4)")
            sp.add_argument("--min-revs", type=int, default=5,
                            help="min revisions per file (default: 5)")
        if extra == "markdown":
            sp.add_argument("-o", "--output", default=None,
                            help="write Markdown to this file (default: stdout)")
        if extra == "report":
            sp.add_argument("-o", "--output", default="gitfault-report.html",
                            help="output HTML path (default: gitfault-report.html)")
            sp.add_argument("--open", action="store_true",
                            help="open the report in your browser when done")
        if extra == "wrapped":
            sp.add_argument("--year", type=int, default=None,
                            help="calendar year to recap (default: latest "
                                 "year with commits)")
            sp.add_argument("--all-time", action="store_true",
                            help="recap the entire history instead of one year")
            sp.add_argument("--svg", metavar="FILE", default=None,
                            help="write a shareable SVG recap card to FILE")
        if extra == "guard":
            sp.add_argument("files", nargs="*",
                            help="files to check (pre-commit passes staged "
                                 "paths; default: files changed in HEAD)")
            sp.add_argument("--strict", action="store_true",
                            help="exit non-zero if any file is on a fault line")
            sp.add_argument("--min-share", type=float, default=0.9,
                            help="flag as a knowledge silo at/above this "
                                 "ownership share (default: 0.9)")
            sp.set_defaults(top=10)
        sp.set_defaults(func=fn)
    p.set_defaults(func=cmd_overview, cmd="overview")
    return p


_SUBCOMMANDS = {"overview", "hotspots", "coupling", "knowledge",
                "markdown", "report", "badge", "wrapped", "guard"}


def main(argv=None) -> int:
    p = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    # Default to `overview` so bare invocations like `gitfault -C owner/repo`
    # work without naming a subcommand.
    if not any(a in _SUBCOMMANDS for a in argv) and \
            not any(a in ("-h", "--help", "--version") for a in argv):
        argv = ["overview"] + argv
    args = p.parse_args(argv)
    # defaults for overview when invoked bare
    for attr, val in [("min_shared", 4), ("min_revs", 5)]:
        if not hasattr(args, attr):
            setattr(args, attr, val)
    try:
        rc = args.func(args)
        if isinstance(rc, int):
            return rc
    except gitlog.NotAGitRepo as e:
        render.console.print(f"[red]error:[/red] {e}")
        return 2
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
