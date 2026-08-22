# tracon — project instructions

Dependency- and session-aware scheduler for agent workloads; context transfer is a
first-class concern. GitHub `Shivansh2703/tracon` is **PUBLIC** (measured 2026-08-10) —
so no AI trailers or agent attribution in commits here, per the owner's standing
no-agent-public-contributions rule. Archived locally per the 2026-08-04 ruling; see
Current state below before assuming this is an active build lane.

## Truth sources (read before working)
- `DECISIONS.md` / README here — engineering rulings and milestone state.
- Product/pitch material lives in the vault: `daisy/30_Projects/30.1_Current/30.1.6_Tracon/`.

## Laws
- **Banned numbers — never cite these anywhere, launch copy included:** the
  90.6%-latency figure (DEBUNKED, 2026-07-29 audit) and the **withdrawn −36% / −27%
  p95 headline** (DECISIONS.md 2026-08-07). The pitch runs on: SAGA 3–8× and TraceLab
  "4% of calls / 85% of time". Any new number needs a cited measurement from a run you
  executed.
- Stack ruling (owner 2026-07-27): Python simulator + C++/Go core. Don't relitigate.
- Owner merges his own PRs — never self-merge to main.
- Path-staged commits only; one logical change per commit.

## Current state (2026-08-22 — per the DECISIONS.md tail, which wins over this section)
Archived locally by the owner's 2026-08-04 ruling; the public GitHub repo stays up.
M4 code is in the repo, but its p95 headline is **WITHDRAWN** — see the Laws above for the
figures that are banned, and never repeat them.

**`tracon doctor` shipped 2026-08-14** — zero-config local diagnosis of your own transcripts,
with `--json` and a statistics-only `--share`. It makes no network calls.

**The suite's three legs, and where each lives.** tracon (this repo, PUBLIC) · agentfail and
agent-obs (both **separate local-only git repos nested here and gitignored** — they are not
part of this tree, and neither has ever been published). The owner's 08-14 ruling was to build
the third leg before the suite launch; **agent-obs was built 2026-08-22** on branch
`build-third-leg` in its own repo — the fleet-over-time view: what moved between exports, and
which seat is responsible. Unmerged; the owner merges.

**Live correction, read before quoting any unaccounted-run figure:** roughly half the
"16.5% of subagent runs end with no recorded outcome" headline is a measurement artifact —
workflow workers cannot resolve an end status through the exporter at all. Corrected rates and
the full evidence are in the DECISIONS.md tail. `tracon doctor` still prints the uncorrected
figure; repairing that is owed to the owner, not taken by a seat.

Suite launch slots September or later (August is booked, one launch per week).
tracon.dev + PyPI name claims are the owner's move — never register anything.

## Instructions for all coding agents (folded in from AGENTS.md, 2026-08-17)

Every rule in this file applies to you, whichever CLI you are. `AGENTS.md` is now a symlink to
this file so Codex picks it up too.

- Create and modify files with your editor tools (write/edit), never shell heredocs or
  redirection.
