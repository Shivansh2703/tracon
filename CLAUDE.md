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

## Current state (2026-08-07 — per the DECISIONS.md tail, which wins over this section)
Archived locally by the owner's 2026-08-04 ruling; the public GitHub repo stays up.
M4 code is in the repo, but its −36% p95 headline is **WITHDRAWN** — do not repeat it.
Suite story reopened 2026-08-07 as a launch direction: tracon + agentfail + agent-obs
packaged together. agent-obs is a README stub only, so the suite has a missing third leg;
the owner owes a decision on build-agent-obs-first vs launch-the-pair. Suite launch slots
September or later (August is booked, one launch per week).
tracon.dev + PyPI name claims are the owner's move — never register anything.
