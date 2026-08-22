# tracon — project instructions

Dependency- and session-aware scheduler for agent workloads; context transfer is a
first-class concern. Since the owner's 2026-08-22 ruling **"Make the whole project
tracon"** it is also the measurement built on the same traces: `doctor` (what happened),
`study` (why runs fail), `over-time` (is it getting worse). One project, one repo, one
name — there is no suite of separate tools any more.

GitHub `Shivansh2703/tracon` is **PUBLIC** (measured 2026-08-10) — so no AI trailers or
agent attribution in commits here, per the owner's standing no-agent-public-contributions
rule. Archived locally per the 2026-08-04 ruling; see Current state below before assuming
this is an active build lane.

## Truth sources (read before working)
- `DECISIONS.md` / README here — engineering rulings and milestone state. **One decisions
  log for the whole project**; the two folded repos' own logs were merged into it and
  deleted 2026-08-22.
- `docs/study.md` and `docs/over-time.md` — what those two commands are, and the method
  notes to read before quoting any of their numbers.
- Product/pitch material lives in the vault: `daisy/30_Projects/30.1_Current/30.1.6_Tracon/`.

## Laws
- **Banned numbers — never cite these anywhere, launch copy included:** the
  90.6%-latency figure (DEBUNKED, 2026-07-29 audit) and the **withdrawn −36% / −27%
  p95 headline** (DECISIONS.md 2026-08-07). The pitch runs on: SAGA 3–8× and TraceLab
  "4% of calls / 85% of time". Any new number needs a cited measurement from a run you
  executed.
- Stack ruling (owner 2026-07-27): Python simulator + C++/Go core. Don't relitigate.
- **No network calls, ever** — not optional, not behind a flag. A tool that reads your
  transcripts earns trust by being unable to phone home, not by promising not to. Applies
  to every command, `--share` included: it writes a file and prints it, and sends nothing.
- **No content in, no content out.** Never add a field to an export, a report or an
  aggregate that could carry a path, a prompt, a branch, a repo name or a tool argument.
  Agent-type names are **user-chosen**: they stay local and never enter anything designed
  to be shared.
- **The measurement path stays standard-library only** (`trace/`, `doctor.py`, `study/`,
  `overtime/`). grpcio and the compiled core belong to the scheduler.
- **Two commands must never print different values for the same named quantity.**
  `doctor` and `over-time` report on the same corpora side by side; their quantile
  definitions are pinned to each other on purpose.
- **No live watching** — that is agent-radar's lane. Everything here is measurement after
  the fact.
- **Planning scratch is never published.** Wayfinder maps, wedge analysis, competitive
  positioning: local only, and `.gitignore` says so. This repo is public.
- Owner merges his own PRs — never self-merge to main.
- Path-staged commits only; one logical change per commit.

## Current state (2026-08-22 — per the DECISIONS.md tail, which wins over this section)
Archived locally by the owner's 2026-08-04 ruling; the public GitHub repo stays up.
M4 code is in the repo, but its p95 headline is **WITHDRAWN** — see the Laws above for the
figures that are banned, and never repeat them.

**`tracon doctor` shipped 2026-08-14** — zero-config local diagnosis of your own transcripts,
with `--json` and a statistics-only `--share`. It makes no network calls.

**The fold landed 2026-08-22 on `wt-fold`, unmerged — the owner merges.** What were two
separate local-only repos nested here and gitignored (`agentfail`, `agent-obs`) are now
`src/tracon/study/` and `src/tracon/overtime/`, imported with their history through
git-filter-repo, which also stripped the five AI-attribution trailers that history carried.
`tracon study` and `tracon over-time` sit beside `tracon doctor`; there is one pyproject and
one console script. Their old working directories still sit in the checkout with their own
`.git` — **removing them is the owner's step, after he merges**, and the over-time repo's
`.scratch/` (deliberately not imported) is the only copy of those two closed wayfinder maps.

**Where the tests and gates live now:** `tests/study/` (161), `tests/overtime/` (41), the
rest at `tests/` (80). Gate: `pytest -q` all green and `ruff check .` zero findings, both
run from the repo root.

**Live correction, read before quoting any unaccounted-run figure:** roughly half the
"16.5% of subagent runs end with no recorded outcome" headline is a measurement artifact —
workflow workers cannot resolve an end status through the exporter at all. Corrected rates and
the full evidence are in the DECISIONS.md tail. `tracon doctor` still prints the uncorrected
figure; repairing that is owed to the owner, not taken by a seat.

Launch slots September or later (August is booked, one launch per week).
tracon.dev + PyPI name claims are the owner's move — never register anything.

## Instructions for all coding agents (folded in from AGENTS.md, 2026-08-17)

Every rule in this file applies to you, whichever CLI you are. `AGENTS.md` is now a symlink to
this file so Codex picks it up too.

- Create and modify files with your editor tools (write/edit), never shell heredocs or
  redirection.
