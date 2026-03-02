"""Parse `git log` into an in-memory model. No third-party deps."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone

REC = "\x1e"  # record separator, unlikely to appear in commit metadata
FIELD = "\x1f"  # unit separator


@dataclass
class FileChange:
    path: str
    added: int
    deleted: int
    binary: bool = False


@dataclass
class Commit:
    sha: str
    author: str
    email: str
    when: datetime
    subject: str
    files: list[FileChange] = field(default_factory=list)


def _parse_when(ts: str):
    """Parse a git ``%aI`` author date, preserving the commit's own timezone.

    Returns a timezone-aware ``datetime`` whose wall-clock fields (``.hour``,
    ``.date()``, ``.month`` ...) reflect the author's *local* time when the
    commit was made — not UTC. Falls back to treating a bare integer as an
    epoch (older callers) and to UTC if the offset is somehow absent.
    """
    ts = ts.strip()
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        # Fallback: maybe an epoch integer (legacy) — treat as UTC.
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class NotAGitRepo(RuntimeError):
    pass


def _run(args: list[str], cwd: str) -> str:
    # Force literal UTF-8 paths (disable octal-escaping/quoting of non-ASCII
    # filenames) so numstat + ls-files agree and on-disk lookups succeed.
    if args and args[0] == "git":
        args = [args[0], "-c", "core.quotepath=false", *args[1:]]
    try:
        out = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as e:  # git not installed
        raise NotAGitRepo("`git` executable not found on PATH") from e
    except subprocess.CalledProcessError as e:
        raise NotAGitRepo(e.stderr.strip() or "git command failed") from e
    return out.stdout


def repo_root(cwd: str) -> str:
    root = _run(["git", "rev-parse", "--show-toplevel"], cwd).strip()
    if not root:
        raise NotAGitRepo("not inside a git repository")
    return root


def _rename_target(path: str) -> str:
    """Normalise a numstat rename path to the *new* filename.

    git renders renames as either ``old => new`` or ``dir/{old => new}/file``.
    """
    if "=>" not in path:
        return path
    if "{" in path and "}" in path:
        pre, rest = path.split("{", 1)
        mid, post = rest.split("}", 1)
        new = mid.split("=>", 1)[1].strip()
        return (pre + new + post).replace("//", "/")
    # simple "old => new"
    return path.split("=>", 1)[1].strip()


def collect_commits(cwd: str, since: str | None = None,
                    until: str | None = None) -> tuple[str, list[Commit]]:
    """Return (repo_root, commits newest-first)."""
    root = repo_root(cwd)
    # A freshly-initialised repo has no commits yet; `git log` would error.
    # `rev-list --all -n1` exits 0 with empty output on such repos.
    if not _run(["git", "rev-list", "--all", "-n", "1"], root).strip():
        return root, []
    # %aI = author date, strict ISO-8601 *with the commit's own timezone
    # offset* (e.g. 2026-09-07T21:34:12-07:00). We keep that offset so that
    # wall-clock stats (hour-of-day / "night owl", per-day streaks, busiest
    # month) reflect the time the author actually saw on their clock, rather
    # than everything collapsed to UTC. See gitlog._parse_when.
    fmt = f"{REC}%H{FIELD}%an{FIELD}%ae{FIELD}%aI{FIELD}%s"
    args = ["git", "log", "--no-merges", "--numstat", "-M",
            f"--pretty=format:{fmt}"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    raw = _run(args, root)

    commits: list[Commit] = []
    for block in raw.split(REC):
        block = block.strip("\n")
        if not block:
            continue
        head, _, body = block.partition("\n")
        parts = head.split(FIELD)
        if len(parts) < 5:
            continue
        sha, author, email, ts, subject = parts[:5]
        when = _parse_when(ts)
        if when is None:
            continue
        c = Commit(sha=sha, author=author, email=email.lower(),
                   when=when, subject=subject)
        for line in body.splitlines():
            if not line.strip():
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            a, d, path = cols
            binary = a == "-" or d == "-"
            added = 0 if binary else int(a)
            deleted = 0 if binary else int(d)
            c.files.append(FileChange(_rename_target(path.strip()),
                                      added, deleted, binary))
        commits.append(c)
    return root, commits


def current_line_counts(cwd: str, root: str) -> dict[str, int]:
    """Line counts for files currently tracked in HEAD (text files only)."""
    files = _run(["git", "ls-files"], root).splitlines()
    counts: dict[str, int] = {}
    # Batch: use `git grep -c ''`? Simpler & robust: read via cat-file is heavy.
    # Use wc through git on the working tree paths that exist.
    import os
    for f in files:
        p = os.path.join(root, f)
        try:
            with open(p, "rb") as fh:
                chunk = fh.read()
            if b"\x00" in chunk[:8000]:  # binary
                continue
            counts[f] = chunk.count(b"\n") + (0 if chunk.endswith(b"\n") or not chunk else 1)
        except OSError:
            continue
    return counts
