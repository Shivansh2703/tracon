# tracon — project instructions

Dependency- and session-aware scheduler for agent workloads; context transfer is a
first-class concern. PRIVATE repo (Shivansh2703/tracon). Career-flagship lane — outranks
hobby projects in the queue.

## Truth sources (read before working)
- `DECISIONS.md` / README here — engineering rulings and milestone state.
- Product/pitch material lives in the vault: `daisy/30_Projects/30.1_Current/30.1.6_Tracon/`.

## Laws
- **NEVER cite the 90.6%-latency figure — it is DEBUNKED** (2026-07-29 audit). The pitch
  runs on: SAGA 3–8× and TraceLab "4% of calls / 85% of time". Any new number needs a
  cited measurement from a run you executed.
- Stack ruling (owner 2026-07-27): Python simulator + C++/Go core. Don't relitigate.
- Owner merges his own PRs — never self-merge to main.
- Path-staged commits only; one logical change per commit.

## Current state (2026-08-01)
M4 shipped (−36% p95 headline, measured). PR #1 awaits the owner's merge click.
tracon.dev + PyPI name claims are the owner's move — never register anything.
