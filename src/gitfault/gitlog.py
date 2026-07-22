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


class NotAGitRepo(RuntimeError):
    pass


def _run(args: list[str], cwd: str) -> str:
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
    fmt = f"{REC}%H{FIELD}%an{FIELD}%ae{FIELD}%at{FIELD}%s"
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
        try:
            when = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except ValueError:
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
