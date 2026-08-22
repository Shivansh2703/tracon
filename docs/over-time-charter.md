# agent-obs — project instructions

The **fleet-over-time** leg of the tracon suite. `tracon doctor` tells you what happened in
one corpus; `agentfail` tells you what 85k tool calls say about how agent runs fail;
**agent-obs tells you whether your fleet got worse, and which seat is responsible.**

Input is a tracon trace export directory (`events.jsonl` + `manifest.json`) — content-free by
construction. Two or more of them, captured at different times, are the whole subject.

`agent-obs` is a **working name**. Naming, domains, and package registration are the owner's
alone; no seat registers anything, ever.

## Truth sources (read before working)

- `DECISIONS.md` here — owner rulings and labelled seat decisions for this repo.
- `../DECISIONS.md` (tracon) — the suite-level rulings. Its tail wins over any summary.
- `../CLAUDE.md` (tracon) — **the enforcement list for the banned numbers lives there, and
  only there.** One home per rule; this file points at it rather than restating it.
- `.scratch/` — the two closed wayfinder maps that produced this repo. **Historical.** The
  wedge map's conclusions are on record in `../DECISIONS.md`; read the maps for reasoning,
  never for current state.

## Laws

- **No AI trailers, no agent attribution, in any commit.** Inherited from the owner's standing
  no-agent-public-contributions rule. See the flagged finding in `DECISIONS.md` (2026-08-22):
  two commits already in this repo's history carry them, from before the rule was applied here.
- **Banned numbers never appear anywhere**, launch copy included. The list is in
  `../CLAUDE.md`. Any new number needs a cited measurement from a run the seat executed.
- **No network calls, ever** — not optional, not behind a flag. Same guarantee as tracon.
  A tool that reads your transcripts earns trust by being unable to phone home, not by
  promising not to.
- **Zero third-party runtime dependencies.** stdlib only, matching agentfail. `pytest` and
  `ruff` are dev tools.
- **No content in, no content out.** Never add a field that could carry a path, a prompt, a
  branch, a repo name, or a tool argument. Agent-type names are **user-chosen**: they stay
  local, they never enter anything designed to be shared.
- Owner merges his own branches — never self-merge to `main`.
- Path-staged commits only; one logical change per commit.

## Gates

```sh
../.venv/bin/python -m pytest -q     # all green
../.venv/bin/ruff check .            # zero findings
```

Plus, for anything that changes a detector: a **mutation-bite check** — reinstate the bug,
watch the test fail, revert. A test that has never been seen to fail is not evidence.

## Current state (2026-08-22)

Built overnight from the owner's 08-14 ruling that the third leg gets built before the suite
launch. Was a spec-only repo (13 commits of wayfinder work, no code) until then.

**On branch `build-third-leg`, five commits, not merged — merging is the owner's.**

What runs: `agent-obs track` (movement across N corpora) and `agent-obs check` (the gate).
**41 tests, ruff clean.** Verified as an actual package, not just an importable directory —
installs from a clean `git archive` into a throwaway venv and the console script runs.

Three independent review cycles, one of which **bounced** and was right to: the corrected
numerator was first derived by subtraction, which silently rendered a negative percentage and
crashed the gate on a `ValueError` once that reached the statistics. Counting directly on
mutually exclusive branches makes the bad value unconstructable rather than clamped away.
Every load-bearing detector has been mutation-bitten — broken, watched to fail a *named* test,
restored.

**The finding this leg produced on its first real run** is the thing to know before quoting any
unaccounted-run number: roughly half of them in the August corpora are runs whose outcome the
export never captured, not runs that died. See `../DECISIONS.md` (2026-08-22) for the evidence
and for what is still owed to the owner — the root-cause repair belongs in tracon's exporter
and is a schema change, which is not a seat's call.

Repo is **local-only, no remote** (measured 2026-08-22). Nothing here has ever been published.
