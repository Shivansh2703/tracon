# Tracon — Decisions Log

## 2026-08-04
**Archive ruling** — "archive tracon we can always repackage later w the new tool"

Interpretation: repo archived locally; the suite story (tracon+agentfail+observability) parks until repackaged around the future observability tool; public GitHub repo stays up.

"tracon can be launched w agent-obs and agentfail packaged together" (owner, 2026-08-07 in Iris chat — reopens the parked suite story as a LAUNCH direction: tracon + agentfail + agent-obs packaged as one story. Iris measured same turn: agentfail is substantial (src/tests/results/site), agent-obs is a README stub only — the suite as stated has a missing third leg; owner decision owed on build-agent-obs-first vs launch-the-pair. Banned-numbers law binds any launch copy: never 90.6%, never the withdrawn −36%/−27%; safe list = the gtm roadmap's numbers card. Calendar: August is booked by the orphan→radar→chute trio, one-launch-per-week rule — suite slots September+.)

- 2026-08-14 (Iris chat, owner verbatim): "tracon we buildin the third leg." — RULING on the launch question: build agent-obs (the third leg) BEFORE the suite launch; ship-the-pair-now is rejected. Unblocks the suite-launch sequencing that had waited on this call since 08-07.

- 2026-08-14 (Iris chat, owner verbatim, second ruling same day): "open a tracon sesh we have good tools and good data lets point it as something useful" — a direction-setting seat is spawned on this; its tab interview with the owner sets the goal.

## 2026-08-14 — tracon-dir seat, owner interview in tab

Owner verbatim (typed in the seat's tab, in order):

1. **"what ab yc collaboaring on an agent system idea? can this be rubbed into tracon"**
2. **"use /wayfinder first to iron out details"**

The rest of the interview ran as tab option-selections, not typed words. Recorded below
**as selections** — the option labels are the seat's wording that the owner chose, and
must never be requoted as his own phrasing:

3. YC angle → *"Research the multiplayer wedge properly"* — scope what a multiplayer-by-
   default product on the corpus would be, and whether it is a company or a feature,
   before building.
4. Direction → *"Yes — build with a multiplayer shape in mind"* — a team as the subject,
   not one operator.
5. Destination → *"Redraw it — destination is a venture decision"* — a fresh wayfinder
   effort, not a resumption of the agent-obs spec map, which closes.
6. Subject → *"The multiplayer wedge specifically"* — not productizing the suite as it
   stands.
7. Endpoint → *"At the decision, with evidence"* — acting on it is a fresh effort.
8. "Go" means → *"Build it and see, decide later"*.

**Seat reconciliation, flagged to the owner in the same turn and approved with the plan:**
(7) and (8) conflict with the literal reading of (5) — if "go" means build and defer, the
map cannot be deciding whether this is a company. Destination therefore renamed to what
(3)–(8) compose into: *decide whether the multiplayer wedge is real, and fix what gets
built first*, with the company decision and any YC application ruled **out of scope**
(they return only if the destination is redrawn).

**Standing rulings this effort deliberately reverses** — logged as reversals, not drift.
The owner was shown the cost of each and chose it:
- the GTM roadmap's "monetization: none, ever, in this shape";
- agentfail's 2026-08-04 "fine as own project (unsure if a product though)" /
  productization-undecided posture;
- `GOALS.md` #5's framing of tracon as purely instrumental to #1.

**Correction of record — measured at source by this seat, 2026-08-14:** YC's Fall 2026
RFS entry *"Multiplayer AI"* (Aaron Epstein) is about **multiple humans sharing one
agent**, not multiple agents. Verbatim: *"AI agents are the most powerful new tool a team
has, but it's the one thing people still use by themselves."* The 2026-08-14 vault reels
sweep classified it as "multiplayer-agents → tracon lane"; that reading is wrong and the
vault entry needs correcting (Iris's lane — flagged, not edited by this seat). Also
re-measured the same day: Fall 2026's regular deadline (July 27) has passed, late
applications are accepted with no promised response timing, the batch runs
October–December in San Francisco, and Winter 2027's deadline remains unpublished —
consistent with `mma-app/docs/yc_readiness_checklist_2026-08-10.md`, which stands and is
not to be redone.

## 2026-08-14 (later) — the multiplayer wedge is dead; the hunt continues

Owner ruling in tab, on whether four vendors already shipping human session sharing kills
the wedge. Selection, recorded as a selection: **"It kills it — a feature four vendors ship
isn't a company."** Warp, Sourcegraph Amp (2026-07-22), Zed's Delta (2026-08-13) and GitHub
Copilot all ship it; three own both runtime and client; Anthropic's Claude Cowork states
*"Sessions can't be shared with others"* as a gap rather than a design stance.

The kill is scoped to the multiplayer wedge only. It does not touch the corpus decay, the
exporter's format drift, or the same-day "we buildin the third leg" ruling.

Owner then typed, verbatim, in the same turn:

> **"well lets keep going and trying to find the real wedge for tracon"**

This **supersedes** a menu selection of "back to spec-first" made moments earlier in the
same turn; both are on the record. The wayfinder map's destination generalizes from *the
multiplayer wedge* to *a wedge for tracon's assets, or evidence there isn't one*.

**Method correction, now binding on the effort** — the lesson the dead candidate bought:
start from where money is already being spent and pain is already articulated, then ask
which asset touches it. The first candidate was picked supply-first from an RFS paragraph
and demand was hunted afterwards; it was never found.

**Measured the same day, and the most durable result this project has produced:** a fresh
export (`export-2026-08-14`, sharing no transcripts with the July one — the rolling delete
removed the overlap) independently **replicates** two July findings to the digit. Tool
execution is 79% of busy time, and the median model call reads 99.1% of its input from
cache (July: 98.9%). Given two withdrawn headlines in this repo's history, a figure that
replicates on an independent corpus is worth more than a larger one that does not.

## 2026-08-14 (later still) — the wedge is chosen

Owner instruction, typed verbatim: **"well do it then big dawg"** — resolve the wedge
ticket rather than hold it for another session.

Owner's pick, recorded as a selection: **silent-failure detection on production agent
traces** —

> *"Teams running coding agents in production can't see which runs hung, looped, or ended
> with no outcome — or what those cost; we find them in the traces they already generate,
> and report measured base rates instead of a dashboard."*

Chosen over two alternatives that were drafted and argued: the rehydration-bill angle
(biggest number on the map — 11.7B cache-read against 1.4M raw input — but a cost tool has
to beat "switch to the flat-rate plan", and that is what people actually did), and the
counterfactual simulator (by far the most differentiated asset, and the only one that makes
the C++ core and Go service load-bearing, but with zero demand evidence anywhere). The pick
was recommended partly because it **fails safe**: if it dies as a product, a publishable
measurement is still left behind.

**Seam recorded at the moment of the decision, not after:** the sentence has two halves with
unequal evidence. *Hung, looped, and what it cost* is documented in strangers' own words
with dollars attached. *Ended with no outcome* is measured on exactly one machine — the
owner's, at 16.5% of subagent runs — and the demand research went looking for first-person
accounts of silent agent failure and found none. The unaccounted runs are plausibly the
mechanism behind the documented bills, but that is a hypothesis about causation, not an
established fact, and the wedge must not be pitched as though both halves are equally
evidenced. Falsifier ticketed with a decision rule pre-registered before the evidence.
