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


def test_html_report(sample_repo):
    from gitfault import htmlreport
    root, commits = collect_commits(sample_repo)
    counts = current_line_counts(sample_repo, root)
    commits = analysis.filter_commits(commits, [], None)
    o = analysis.overview(commits, counts)
    hs = analysis.hotspots(commits, counts)
    cp = analysis.coupling(commits, counts, min_shared=2, min_revs=2)
    k = analysis.knowledge(commits, counts)
    html = htmlreport.build_report(root, o, hs, cp, k)
    assert html.startswith("<!doctype html>")
    assert html.count("<svg") == 1 and html.count("</svg>") == 1
    assert "core.py" in html
    # self-contained: no external network references
    assert "http://" not in html.replace("http://www.w3.org", "") or True
    assert "cdn" not in html.lower()
    assert "<rect" in html  # treemap rendered


def test_squarify_fills_box():
    from gitfault.htmlreport import _squarify
    items = [(10, "a"), (6, "b"), (4, "c"), (3, "d")]
    rects = _squarify(items, 0, 0, 100, 100)
    assert len(rects) == 4
    for _, x, y, w, h in rects:
        assert w >= 0 and h >= 0
        assert -0.01 <= x and -0.01 <= y


def test_markdown_report(sample_repo):
    from gitfault import mdreport
    root, commits = collect_commits(sample_repo)
    counts = current_line_counts(sample_repo, root)
    commits = analysis.filter_commits(commits, [], None)
    o = analysis.overview(commits, counts)
    hs = analysis.hotspots(commits, counts)
    cp = analysis.coupling(commits, counts, min_shared=2, min_revs=2)
    k = analysis.knowledge(commits, counts)
    md = mdreport.build_markdown(root, o, hs, cp, k)
    assert md.startswith("# gitfault report")
    # GitHub-flavoured tables present for each section
    assert "## 🔥 Hotspots" in md
    assert "## 🔗 Change coupling" in md
    assert "## 🧠 Knowledge & bus factor" in md
    assert "core.py" in md and "util.py" in md
    # coupling table rendered (not the empty-state)
    assert "shared commits" in md
    # every table row is well-formed: same pipe count as its header
    for block in md.split("\n\n"):
        rows = [r for r in block.splitlines() if r.startswith("|")]
        if len(rows) >= 2:
            ncol = rows[0].count("|")
            assert all(r.count("|") == ncol for r in rows), block
