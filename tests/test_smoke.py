"""End-to-end smoke tests: build a tiny throwaway git repo and analyse it."""
from __future__ import annotations

import subprocess
import textwrap

import pytest

from gitfault import analysis
from gitfault.gitlog import collect_commits, current_line_counts


def _git(repo, *args, env=None):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True, env=env)


@pytest.fixture()
def sample_repo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "a@x.io")
    _git(repo, "config", "user.name", "Alice")

    core = repo / "core.py"
    util = repo / "util.py"
    lonely = repo / "lonely.py"

    # core.py and util.py always change together -> coupling
    for i in range(5):
        core.write_text(f"# core rev {i}\n" + "x = 1\n" * (i + 2))
        util.write_text(f"# util rev {i}\n" + "y = 1\n" * (i + 1))
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", f"change {i}")

    # a second author touches only lonely.py once
    env = {"GIT_AUTHOR_NAME": "Bob", "GIT_AUTHOR_EMAIL": "b@x.io",
           "GIT_COMMITTER_NAME": "Bob", "GIT_COMMITTER_EMAIL": "b@x.io",
           "PATH": __import__("os").environ["PATH"]}
    lonely.write_text("# solely bob\n" + "z = 1\n" * 20)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "bob adds lonely", env=env)
    return str(repo)


def test_collect_and_hotspots(sample_repo):
    root, commits = collect_commits(sample_repo)
    assert len(commits) == 6
    counts = current_line_counts(sample_repo, root)
    hs = analysis.hotspots(analysis.filter_commits(commits, [], None), counts)
    paths = [h.path for h in hs]
    assert "core.py" in paths
    # core.py changed most often and is largest -> top hotspot
    assert hs[0].path == "core.py"
    assert hs[0].revisions == 5


def test_coupling(sample_repo):
    root, commits = collect_commits(sample_repo)
    counts = current_line_counts(sample_repo, root)
    commits = analysis.filter_commits(commits, [], None)
    pairs = analysis.coupling(commits, counts, min_shared=2, min_revs=2)
    pair_names = {frozenset((p.a, p.b)) for p in pairs}
    assert frozenset(("core.py", "util.py")) in pair_names


def test_knowledge(sample_repo):
    root, commits = collect_commits(sample_repo)
    counts = current_line_counts(sample_repo, root)
    commits = analysis.filter_commits(commits, [], None)
    k = analysis.knowledge(commits, counts)
    assert k.bus_factor >= 1
    owners = {name for name, _ in k.top_authors}
    assert "Alice" in owners
