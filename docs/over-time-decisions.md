# DECISIONS

Append-only record of owner rulings for agent-obs, and of seat decisions taken in his absence.
Dated, with verbatim quotes. Never archived, never summarized, never compacted.

Format: date · ruling or seat decision · verbatim quote where one exists · plain interpretation.

**Owner rulings and seat decisions are different things and are always labelled as such.** A
seat decision is reversible, was taken because work could not proceed without one, and is
recorded here so he can overturn it cheaply. It never covers anything that affects other
people.

---

## Owner rulings that govern this repo

### 2026-08-04 — the suite

Verbatim (owner, idea-batch review, on the agent black-box/observability idea):

> "v good could be packaged all together w tracon and agentfail"

This repo is the third piece of that suite. Full entry lives in `../DECISIONS.md` — one home
for the ruling.

### 2026-08-07 — the suite is a launch direction

Verbatim (owner, Iris chat):

> "tracon can be launched w agent-obs and agentfail packaged together"

### 2026-08-14 — the third leg gets built first

Verbatim (owner, Iris chat):

> "tracon we buildin the third leg."

Ruling on the launch question: build agent-obs **before** the suite launch; ship-the-pair-now
is rejected. This is the ruling the 2026-08-22 build executes.

### 2026-08-14 — tracon and agent-radar are a 1-2 punch

Verbatim (owner, Iris chat):

> "tracon and agent-radar are a 1-2 punch both are good on their own but better together."

Standing strategic frame. agent-radar owns the **live** session; this repo and `tracon doctor`
own **measurement after the fact**. agent-obs must not grow a live-watch mode — that is
agent-radar's lane, and the closed spec map already ruled it out.

### 2026-08-22 00:2x — release for the overnight build

Verbatim (owner, Iris chat):

> "Ok good spawn the vyuha ... and tracon seats push nav2 for later"

Release for an unattended overnight seat, owner asleep. No tab interview. Seat decisions stay
labelled as seat decisions; owner rulings owed stay owed.

---

## 2026-08-22 — seat decisions taken on the overnight build

All four are **seat decisions, not owner rulings** — reversible, and recorded here so they can
be overturned cheaply.

### 1. What agent-obs *is*: the fleet-over-time leg

The problem this had to solve first: the wedge map in `.scratch/` closed 2026-08-14 with
**"THE BUILD IS DONE"**, because the thing it chose to build shipped as `tracon doctor`, inside
tracon, per its own ticket 13 ("the tool lives in tracon, the public repo"). Read alone, that
says there is nothing left to build here.

But the same day's kill-criteria ruling scoped itself explicitly so as **not** to touch "the
same-day 'we buildin the third leg' ruling" (`../DECISIONS.md`). And `tracon doctor` is a
subcommand of leg one: it does not give a three-legged suite a third leg. So the ruling stands
and something had to be built.

The seat built the thing **neither existing leg does**, rather than a second doctor:

| leg | question it answers |
|---|---|
| `agentfail` | what do 85k real tool calls say about how agent runs fail? |
| `tracon doctor` | what happened in **this one** corpus, against published base rates? |
| **agent-obs** | **is my fleet getting worse, and which seat is responsible?** |

Two capabilities follow from that sentence and nothing else was built: **movement across N
corpora over time**, and a **gate** that exits non-zero when a metric genuinely regresses.

**Why this and not something else** — the honest version. Demand evidence for a gate is on
record in the wedge map's ticket 10: someone built an eval-as-CI-gate in-house because nothing
sold them one. That is thin — one data point, and it is about evals rather than fleet health.
The seat judged it better than the alternatives (a trace *standard* has one producer and one
consumer, which makes it a schema wearing a costume; a multi-operator view needs the aggregate
ruling he still owes). **If he disagrees with the framing, the code is 816 lines and the
framing is one README — this is cheap to redirect.**

### 2. It lives in this repo, on a branch, not inside tracon

The boot brief put the seat in a tracon worktree, on the premise that agent-obs was a README
stub inside tracon. **Measured, and it is not**: agent-obs is its own git repo with 13 commits
and no remote, and `tracon/.gitignore` ignores it. So the build happened here, on
`build-third-leg`, with `main` untouched for the owner to merge.

**Where the suite finally lives — monorepo, three repos under one umbrella, or the tool folded
into tracon the way `doctor` was — is NOT settled by this.** That is the closed spec map's
ticket 04, still unanswered, and it is a packaging and positioning call, not an engineering one.

### 3. Statistics are copied from agentfail, not imported

`stats.py` lifts `wilson`, `normal_sf` and `two_proportion_test` verbatim from
`../agentfail/src/agentfail/stats.py`. The two packages deliberately do not depend on each
other — agentfail is unpublished and local-only, and a tool meant for strangers cannot depend
on a repo they do not have. Forty lines of textbook statistics duplicated is the cheaper of the
two wrongs. The copy is kept in sync by hand.

### 4. The gate uses a significance test, not a threshold, wherever it can

Corpora differ in size. A gate that fires because a rate moved from 2/20 to 3/20 is worse than
no gate, because people turn off gates that cry wolf. So rate metrics — which have a real
numerator and denominator — gate on a **two-proportion test at p < 0.05 in the worsening
direction**, and metrics with no n (p95 duration, long-tail share) gate on relative change with
an absolute floor, and **say in the output which rule fired**. Metrics with no obviously-bad
direction (tool share of busy time, cache-read share) are reported and never gated.

---

## Owed by the owner — deliberately not taken by the seat

1. **What may be done with an aggregate a stranger sends** — publish it, combine it into a
   public base-rate table, name contributors. Carried forward from 2026-08-14, still owed. It
   affects other people, so no keep-going instruction covers it. Until it is answered,
   agent-obs stays strictly single-operator: everything it computes stays on the machine.
2. **The name.** `agent-obs` is a working name from the spec phase. Naming and registration
   are his alone.
3. **Where the suite lives and how it is packaged** — see seat decision 2 above.
4. **AI trailers in this repo's history, and in agentfail's.** Measured 2026-08-22:
   `tracon` (public) is **clean — 0 of 41 commits**. But **agent-obs carries them in 2 of 13
   commits** and **agentfail in 3 of 11**, from before the no-agent-attribution rule was
   applied to them. If either repo is ever published as part of the suite, that history goes
   with it. Rewriting history is destructive and is his call, never a seat's. Flagged now
   rather than discovered on launch day.
