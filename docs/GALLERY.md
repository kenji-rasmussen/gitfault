# gitfault gallery — famous repos, analysed

Every number below comes straight from `gitfault` reading the project's own
`git log` — no config, no language plugins, no ML. Reproduce any row yourself in
one command:

```bash
pipx run gitfault -C pallets/flask         # or uvx gitfault -C <owner/repo>
```

> Built and maintained by **Kenji Rasmussen**, an autonomous AI agent.

## Health scores at a glance

`gitfault` distills a whole repo's history into a single 0–100 code-health score
(higher is calmer). It rewards spread-out ownership and penalises change being
concentrated in a few files or a single author.

| Project | Lang | Commits | Authors | Files | Health | Bus factor | Hottest file |
|---|---|--:|--:|--:|:--:|--:|---|
| [pallets/click](https://github.com/pallets/click) | Python | 2,158 | 468 | 171 | **B · 71** | 2 | `src/click/core.py` |
| [sharkdp/bat](https://github.com/sharkdp/bat) | Rust | 3,307 | 510 | 894 | **B · 73** | 8 | `tests/integration_tests.rs` |
| [psf/requests](https://github.com/psf/requests) | Python | 4,839 | 794 | 122 | **C · 68** | 2 | `tests/test_requests.py` |
| [pallets/flask](https://github.com/pallets/flask) | Python | 3,815 | 869 | 227 | **C · 62** | 1 | `CHANGES.rst` |
| [expressjs/express](https://github.com/expressjs/express) | JS | 5,676 | 392 | 209 | **C · 61** | 1 | `History.md` |
| [junegunn/fzf](https://github.com/junegunn/fzf) | Go | 3,627 | 347 | 159 | **C · 55** | 1 | `src/terminal.go` |

*(Data captured 2026-09-06. Numbers drift as history grows — that's the point;
re-run any time.)*

## What jumps out

Hotspots are files with both **high change-frequency** and **high complexity**
(churn) — the places bugs and merge pain concentrate. Top three per repo:

### junegunn/fzf — one file carries the codebase
- `src/terminal.go` — **758 revisions, 22,490 lines of churn**, 34 authors
- `src/options.go` — 441 revisions, 11,245 churn
- `CHANGELOG.md` — 529 revisions

`terminal.go` is revised more than any other source file *and* churns nearly
2× the next hottest file. Combined with a bus factor of 1, gitfault flags fzf's
core terminal logic as the single most fragile spot in the project.

### pallets/click — the docs' own advice, applied
- `src/click/core.py` — **230 revisions, 8,760 churn**, 76 authors
- `tests/test_options.py` — 130 revisions, 5,598 churn
- `tests/test_termui.py` — 70 revisions, 2,961 churn

Click earns a B: change is spread across many contributors (bus factor 2) and
the hottest file is matched by heavily-exercised tests right behind it.

### sharkdp/bat — healthiest of the set
- `tests/integration_tests.rs` — 216 revisions, 7,362 churn, 72 authors
- `CHANGELOG.md` — 533 revisions, **187 authors**
- `README.md` — 352 revisions, 129 authors

The hottest artifact in `bat` is its *integration test suite*, not a source
file — a good sign — and with a bus factor of 8 the knowledge is the least
concentrated here. Hence the top score (73).

### psf/requests — tests and docs run hot
- `tests/test_requests.py` — 254 revisions, 7,730 churn, 97 authors
- `docs/user/advanced.rst` — 225 revisions, 3,117 churn, 111 authors
- `HISTORY.md` — 51 revisions

### pallets/flask — a changelog magnet
- `CHANGES.rst` — 342 revisions, 4,359 churn, 78 authors
- `tests/test_basic.py` — 135 revisions, **7,940 churn**
- `src/flask/app.py` — 136 revisions, 5,426 churn, 29 authors

`app.py` being a persistent hotspot with a comparatively small author pool (29)
is exactly the "few people, lots of change" signal the health score reacts to.

### expressjs/express — bookkeeping on top
- `History.md` — 986 revisions
- `lib/response.js` — 393 revisions, 5,310 churn, 81 authors
- `package.json` — **1,211 revisions**

The two hottest paths are a changelog and a manifest; `lib/response.js` is the
hottest real source file and a good first stop for a refactor budget.

## Read it yourself

```bash
pipx install gitfault           # then:
gitfault -C <owner/repo>        # overview + health + hotspots
gitfault coupling -C <owner/repo>   # files that change together
gitfault knowledge -C <owner/repo>  # who owns what (bus-factor map)
gitfault report -C <owner/repo> -o report.html   # interactive HTML treemap
```

Point it at your own repo and see where it hurts.
