"""gitfault command-line interface."""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from . import __version__
from . import analysis as A
from . import gitlog
from . import render


def _load(args):
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
    if args.json:
        _emit_json({"overview": asdict(o),
                    "hotspots": [asdict(h) for h in hs[:args.top]]})
        return
    render.console.print(f"[bold]gitfault[/bold] [dim]{root}[/dim]\n")
    render.render_overview(o)
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


def cmd_report(args):
    """generate a self-contained interactive HTML report"""
    from . import htmlreport
    root, commits, lc = _load(args)
    o = A.overview(commits, lc)
    hs = A.hotspots(commits, lc)
    cp = A.coupling(commits, lc, min_shared=args.min_shared,
                    min_revs=args.min_revs)
    k = A.knowledge(commits, lc)
    html_text = htmlreport.build_report(root, o, hs, cp, k, top=args.top)
    out = args.output
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    render.console.print(
        f"[green]✓[/green] wrote self-contained report → [bold]{out}[/bold] "
        f"[dim]({len(html_text):,} bytes)[/dim]")
    if args.open:
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(out)}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gitfault",
        description="Find the fault lines in any codebase — hotspots, "
                    "change-coupling and knowledge risk from git history.")
    p.add_argument("--version", action="version",
                   version=f"gitfault {__version__}")

    def common(sp):
        sp.add_argument("-C", "--path", default=".",
                        help="path inside the git repo (default: .)")
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
        ("report", cmd_report, "report"),
    ]:
        sp = sub.add_parser(name, help=fn.__doc__)
        common(sp)
        if extra in ("coupling", "report"):
            sp.add_argument("--min-shared", type=int, default=4,
                            help="min shared commits for a pair (default: 4)")
            sp.add_argument("--min-revs", type=int, default=5,
                            help="min revisions per file (default: 5)")
        if extra == "report":
            sp.add_argument("-o", "--output", default="gitfault-report.html",
                            help="output HTML path (default: gitfault-report.html)")
            sp.add_argument("--open", action="store_true",
                            help="open the report in your browser when done")
        sp.set_defaults(func=fn)
    p.set_defaults(func=cmd_overview, cmd="overview")
    return p


def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    # defaults for overview when invoked bare
    for attr, val in [("min_shared", 4), ("min_revs", 5)]:
        if not hasattr(args, attr):
            setattr(args, attr, val)
    try:
        args.func(args)
    except gitlog.NotAGitRepo as e:
        render.console.print(f"[red]error:[/red] {e}")
        return 2
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
