"""Behavioural analyses computed from parsed commits."""
from __future__ import annotations

import fnmatch
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations

from .gitlog import Commit

DEFAULT_EXCLUDES = [
    "*.lock", "*-lock.json", "*.min.js", "*.min.css", "*.map",
    "*.svg", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.pdf",
    "*.woff*", "*.ttf", "*.eot", "*.mp4", "*.mp3", "*.zip", "*.gz",
    "vendor/*", "*/vendor/*", "node_modules/*", "*/node_modules/*",
    "dist/*", "*/dist/*", "build/*", "*/build/*", ".git/*",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "composer.lock", "go.sum", "*.snap",
    "*.pb.go", "*_pb2.py", "*.generated.*",
]


def _match_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def filter_commits(commits: list[Commit], excludes: list[str],
                   include: list[str] | None) -> list[Commit]:
    out = []
    for c in commits:
        files = [f for f in c.files
                 if not _match_any(f.path, excludes)
                 and (not include or _match_any(f.path, include))]
        if files:
            nc = Commit(c.sha, c.author, c.email, c.when, c.subject, files)
            out.append(nc)
    return out


# ---------------------------------------------------------------- hotspots ---
@dataclass
class Hotspot:
    path: str
    revisions: int
    churn: int
    lines: int
    authors: int
    last_change: datetime
    score: float  # normalised 0..1


def hotspots(commits: list[Commit], line_counts: dict[str, int]) -> list[Hotspot]:
    revs: Counter[str] = Counter()
    churn: Counter[str] = Counter()
    authors: dict[str, set[str]] = defaultdict(set)
    last: dict[str, datetime] = {}
    for c in commits:
        for f in c.files:
            revs[f.path] += 1
            churn[f.path] += f.added + f.deleted
            authors[f.path].add(c.email)
            if f.path not in last or c.when > last[f.path]:
                last[f.path] = c.when

    rows: list[Hotspot] = []
    max_rev = max(revs.values(), default=1)
    max_loc = max((line_counts.get(p, 0) for p in revs), default=1) or 1
    for path, r in revs.items():
        loc = line_counts.get(path)
        if loc is None:  # not a live text file in HEAD
            continue
        # hotspot = frequency * size, each normalised to 0..1
        score = (r / max_rev) * (loc / max_loc)
        rows.append(Hotspot(path, r, churn[path], loc, len(authors[path]),
                            last[path], score))
    rows.sort(key=lambda h: h.score, reverse=True)
    return rows


# ---------------------------------------------------------------- coupling ---
@dataclass
class Coupling:
    a: str
    b: str
    shared: int
    degree: float  # 0..1, shared / min(revs)
    revs_a: int
    revs_b: int


def coupling(commits: list[Commit], line_counts: dict[str, int],
             min_shared: int = 4, min_revs: int = 5,
             max_files_per_commit: int = 30) -> list[Coupling]:
    revs: Counter[str] = Counter()
    pair: Counter[tuple[str, str]] = Counter()
    for c in commits:
        paths = sorted({f.path for f in c.files if f.path in line_counts})
        for p in paths:
            revs[p] += 1
        if len(paths) > max_files_per_commit:
            continue  # skip mega-commits (mass reformat/import) — noise
        for a, b in combinations(paths, 2):
            pair[(a, b)] += 1

    rows: list[Coupling] = []
    for (a, b), shared in pair.items():
        if shared < min_shared:
            continue
        ra, rb = revs[a], revs[b]
        if min(ra, rb) < min_revs:
            continue
        degree = shared / min(ra, rb)
        rows.append(Coupling(a, b, shared, degree, ra, rb))
    rows.sort(key=lambda c: (c.degree, c.shared), reverse=True)
    return rows


# --------------------------------------------------------------- knowledge ---
@dataclass
class FileOwnership:
    path: str
    main_author: str
    main_share: float  # 0..1 of lines added by main author
    authors: int
    lines: int


@dataclass
class KnowledgeReport:
    files: list[FileOwnership]
    bus_factor: int
    total_authors: int
    top_authors: list[tuple[str, int]]  # (name, lines owned across live files)
    solo_owned_lines: int
    total_lines: int


def _display_name(commits: list[Commit]) -> dict[str, str]:
    name: dict[str, str] = {}
    for c in commits:
        name.setdefault(c.email, c.author)
    return name


def knowledge(commits: list[Commit], line_counts: dict[str, int]
              ) -> KnowledgeReport:
    # lines added per (path, author)
    contrib: dict[str, Counter] = defaultdict(Counter)
    names = _display_name(commits)
    for c in commits:
        for f in c.files:
            if f.path in line_counts and f.added:
                contrib[f.path][c.email] += f.added

    files: list[FileOwnership] = []
    owner_lines: Counter[str] = Counter()  # current lines attributed to owner
    solo_lines = 0
    total_lines = 0
    for path, loc in line_counts.items():
        cc = contrib.get(path)
        total_lines += loc
        if not cc:
            continue
        top_email, top_add = cc.most_common(1)[0]
        share = top_add / sum(cc.values())
        files.append(FileOwnership(path, names.get(top_email, top_email),
                                   share, len(cc), loc))
        owner_lines[names.get(top_email, top_email)] += loc
        if len(cc) == 1:
            solo_lines += loc

    files.sort(key=lambda f: (f.main_share, f.lines), reverse=True)

    top = owner_lines.most_common()
    covered = sum(l for _, l in top)
    bus, acc = 0, 0
    for _, l in top:
        acc += l
        bus += 1
        if covered and acc >= covered / 2:
            break
    return KnowledgeReport(files, bus, len(owner_lines), top[:15],
                           solo_lines, total_lines)


# ---------------------------------------------------------------- overview ---
@dataclass
class Overview:
    commits: int
    authors: int
    files_tracked: int
    first: datetime
    last: datetime
    busiest_month: tuple[str, int]


# ------------------------------------------------------------------ health ---
@dataclass
class Health:
    score: int                 # 0..100, higher = healthier
    grade: str                 # A..F
    color: str                 # shields.io colour name
    solo_ratio: float          # fraction of live lines only one author has touched
    top10_churn_share: float   # fraction of all churn in the 10 biggest hotspots
    bus_factor: int


def _grade_and_color(score: int) -> tuple[str, str]:
    for cutoff, grade, color in (
        (85, "A", "brightgreen"),
        (70, "B", "green"),
        (55, "C", "yellowgreen"),
        (40, "D", "yellow"),
        (25, "E", "orange"),
    ):
        if score >= cutoff:
            return grade, color
    return "F", "red"


def health(hotspots_: list[Hotspot], knowledge_: KnowledgeReport) -> Health:
    """A single 0..100 code-health score from behavioural risk signals.

    Lower is riskier. The score starts at 100 and subtracts penalties for
    interpretable, git-derived signals.

    Change-concentration is structural and always applies:

      * top10_churn_share - share of all churn concentrated in the 10
                            biggest hotspots (change concentration).  up to -30

    Knowledge-silo signals are only a *meaningful, actionable* risk once more
    than one person contributes: a solo project is solo by definition, so
    penalising it for a bus factor of 1 or 100% single-author ownership tells
    you nothing you can act on and just brands healthy small codebases with a
    scary grade.  These therefore apply only when ``total_authors >= 2``:

      * solo_ratio        - share of live lines only ONE author has ever
                            touched (knowledge silo).                 up to -45
      * bus_factor        - people holding 50% of the code.  <=1: -25, ==2: -10
    """
    total_lines = knowledge_.total_lines or 1
    solo_ratio = knowledge_.solo_owned_lines / total_lines

    total_churn = sum(h.churn for h in hotspots_) or 1
    top10_churn = sum(h.churn for h in hotspots_[:10])
    top10_churn_share = top10_churn / total_churn

    score = 100.0
    score -= 30.0 * top10_churn_share

    # Knowledge-silo risk is only meaningful with a team to spread knowledge
    # across; a single-author project can't do anything about "bus factor 1".
    if knowledge_.total_authors >= 2:
        score -= 45.0 * solo_ratio
        if knowledge_.bus_factor <= 1:
            score -= 25.0
        elif knowledge_.bus_factor == 2:
            score -= 10.0

    score_i = max(0, min(100, round(score)))
    grade, color = _grade_and_color(score_i)
    return Health(score_i, grade, color, solo_ratio, top10_churn_share,
                  knowledge_.bus_factor)


def overview(commits: list[Commit], line_counts: dict[str, int]) -> Overview:
    authors = {c.email for c in commits}
    months: Counter[str] = Counter()
    for c in commits:
        months[c.when.strftime("%Y-%m")] += 1
    times = [c.when for c in commits] or [datetime.now(timezone.utc)]
    busiest = months.most_common(1)[0] if months else ("-", 0)
    return Overview(len(commits), len(authors), len(line_counts),
                    min(times), max(times), busiest)
