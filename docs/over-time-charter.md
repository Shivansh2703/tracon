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

Built this night by an overnight seat, on branch `build-third-leg`, from the owner's 08-14
ruling that the third leg gets built before the suite launch. Was a spec-only repo (13
commits of wayfinder work, no code) until then. **Not merged to `main` — that is the owner's.**

Repo is **local-only, no remote** (measured 2026-08-22). Nothing here has ever been published.
