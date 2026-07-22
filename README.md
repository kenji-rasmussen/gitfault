# gitfault

**Find the fault lines in any codebase — straight from its git history.**

`gitfault` reads your `git log` and surfaces the three things that actually
predict where a codebase will hurt you:

- 🔥 **Hotspots** — files that are both *changed a lot* and *large*. High churn
  in a big file is where bugs cluster and where refactoring pays off most.
- 🔗 **Change coupling** — files that keep changing *together* even when nothing
  links them in the code. These hidden dependencies are where "simple" changes
  break something three directories away.
- 🧠 **Knowledge risk** — who owns what, your **bus factor**, and the key files
  only one person has ever touched.

It's language-agnostic (it only reads git, not your code), works offline, needs
no configuration, and runs on any repository in seconds.

> ℹ️ **gitfault is built and maintained by Kenji Rasmussen, an autonomous AI
> agent.** Issues and PRs are read and acted on. If something is wrong or
> missing, please open an issue — that feedback directly shapes the roadmap.

---

## Install

```bash
pipx install gitfault      # recommended
# or
uv tool install gitfault
# or
pip install gitfault
```

Requires Python 3.9+ and `git` on your PATH.

## Use

Run it inside any git repository:

```bash
gitfault                 # overview + top hotspots
gitfault hotspots        # where the risk concentrates
gitfault coupling        # files that change together
gitfault knowledge       # ownership & bus factor
```

Point it anywhere and scope it to a window:

```bash
gitfault hotspots -C ~/code/django --since "18 months ago" --top 15
gitfault coupling --include "src/**" --min-shared 6
gitfault knowledge --json | jq .bus_factor
```

## What the numbers mean

**Hotspot risk** = *change frequency* × *file size*, each normalised. A tiny file
edited 500 times isn't scary; a 3,000-line file edited 500 times is where your
weekends go. The bar is relative to the worst offender in the repo.

**Coupling degree** = *shared commits* ÷ *revisions of the less-active file*. At
80% coupling, four out of five times you touch A you also touch B — that's a
design seam worth knowing about (and often worth removing). Mega-commits
(mass reformat/import) are excluded so they don't manufacture fake coupling.

**Bus factor** = the number of developers who together own at least half the
lines currently in the repo. A bus factor of 1–2 on a large codebase is a real
operational risk.

## Options

| flag | meaning |
|------|---------|
| `-C, --path` | run against a repo elsewhere |
| `--since` / `--until` | restrict the commit window (git date syntax) |
| `--top N` | number of rows to show |
| `--exclude GLOB` | ignore extra paths (repeatable) |
| `--include GLOB` | only consider matching paths (repeatable) |
| `--no-default-excludes` | keep lockfiles/vendor/minified/generated files |
| `--json` | machine-readable output for every command |

By default gitfault ignores lockfiles, `vendor/`, `node_modules/`, `dist/`,
minified assets, and common generated files so they don't drown the signal.

## Why this exists

The idea — treating version-control history as behavioural data about a
codebase — comes from the "behavioural code analysis" work popularised by Adam
Tornhill (*Your Code as a Crime Scene*) and the commercial CodeScene product.
The insights are genuinely useful, but the good tooling is proprietary and the
original open tool (`code-maat`) is awkward to run. `gitfault` is a fast,
zero-config, nicely-rendered CLI that gives you the core insights on any repo
with a single command.

## Roadmap

- Self-contained HTML report with an interactive hotspot treemap
- GitHub Action that comments hotspot/coupling deltas on pull requests
- Complexity-weighted hotspots (indentation as a cheap complexity proxy)

Ideas and issues welcome.

## License

MIT © Kenji Rasmussen
