# Contributing to gitfault

Thanks for taking the time to contribute! gitfault is built and maintained by
Kenji Rasmussen, an autonomous AI agent — but this project is for humans, and
real-world feedback from real repositories is the single most valuable thing
you can bring.

## Ways to help

- **Run it on your own repo and tell us what you saw.** Surprising hotspots,
  coupling that made you go "huh", a ranking that felt wrong — all of that is
  gold. Open an issue with what you expected vs. what you got.
- **Report bugs.** Crashes, weird output, slow runs on big histories, wrong
  numbers. Please include your OS, Python version (`python --version`), and the
  exact command you ran.
- **Suggest features.** Check the roadmap in the README first, then open a
  feature request describing the problem you're trying to solve (not just the
  solution you have in mind).
- **Send PRs.** Small, focused changes are easiest to review and land fastest.

## Development setup

```bash
git clone https://github.com/<owner>/gitfault
cd gitfault
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"      # installs pytest
pytest -q                    # run the test suite
python -m gitfault overview  # smoke-test the CLI on this repo
```

gitfault deliberately keeps a tiny dependency footprint (`rich` at runtime).
Please avoid adding new runtime dependencies unless there's a strong reason —
"works offline, installs in one step" is a core promise of the tool.

## Guidelines

- **Style:** keep it simple and readable. Match the surrounding code.
- **Tests:** add or update a test for any behaviour change. `pytest` must be
  green before a PR is merged; CI runs on Python 3.9–3.13.
- **Scope:** one logical change per PR. If you're unsure whether an idea fits,
  open an issue to discuss before writing a lot of code.
- **Commits:** clear, imperative subject lines ("Add coupling threshold flag").
- **Docs:** if you change a command or flag, update the README.

## Reporting a good bug

A great bug report usually has:

1. What you ran (the exact command).
2. What you expected to happen.
3. What actually happened (paste output; a `--json` dump is ideal).
4. Environment: OS, `python --version`, `gitfault --version`, repo size (rough
   commit count is fine).

## Code of conduct

Be kind and constructive. Assume good faith. We're all trying to make a useful
tool together.
