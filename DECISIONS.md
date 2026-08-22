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

**Claim constraint, established the same day by running that falsifier** (measured, not
argued): the 16.5%-of-subagent-runs-unaccounted figure **must not be presented as
generalizing beyond this machine**, in launch copy or anywhere else, until a second
multi-agent, untruncated corpus says otherwise. The only public corpus available
(OpenHands, 13 models) cannot test it — it has **zero** subagent stubs, so the phenomenon is
structurally absent rather than rare; it reports 0.00% non-matched tool calls against 0.02%
on a real corpus, which is a harness signature; and its tool-duration maxima cluster just
above 300,000 ms, i.e. a truncated tail — the same wall agentfail hit on its elapsed-time
finding. This constraint is the same discipline that produced the two withdrawals, applied
before the claim was made rather than after.

## 2026-08-14 (session close) — the first build is chosen

Owner instruction, typed verbatim: **"keep going"**.

Owner's pick on what gets built first, recorded as a selection: **a local, zero-config
command anyone with Claude Code runs on their own machine** — reads their transcripts
locally, uploads nothing, reports their hung runs / unaccounted runs / long tail / spend
shape against the published base rates, and can emit an opt-in **statistics-only** aggregate
they send back.

Chosen over publishing the study first (which ticket 12 had just established would be n=1
and unreplicable — the failure mode behind both of this repo's withdrawn headlines) and over
fixing the foundations alone (necessary work, already inside the chosen option).

Rationale of record: **every install is a potential second corpus.** It is the only option
that attacks the evidence wall rather than routing around it.

**Build order is fixed and not negotiable:** (1) fix the exporter's five-line-type format
drift — a tool that exits 2 on a stranger's first run is dead on arrival, and whether this
is an afternoon or a fight is itself the answer to whether transcript scraping is durable;
(2) corpus id and schema version, **not** an operator identity; (3) the report path, reusing
`characterize` and agentfail's one-JSON-generates-everything pattern with its `--check`
gate; (4) the aggregate emitter last, behind a tested privacy invariant.

**Two blockers dissolved rather than solved:** the machine-local salt and the absent
operator-identity field were both artifacts of assuming a pooled *event* corpus. Statistics
travel; events do not; the privacy guarantee gets stronger as a result.

**Still owed by the owner before any code:** repo, visibility, name and licence. `tracon` is
PUBLIC and carries a withdrawn headline this tool has nothing to do with, so the repo choice
is a real one. Naming and any registration remain his alone, as always.

## 2026-08-14 — command name, and the retraction banner

Owner, typed verbatim: **"sure doctor it is. strip"**

1. **The command is `tracon doctor`** — a subcommand alongside `export`, `characterize`,
   `simulate`, `sweep`. The standalone product name from the closed map is moot; the tool
   ships inside the existing public repo, so no brand and no registration is involved.
2. **Strip the withdrawn figures from the retraction banner in `docs/scheduler.md`.** The
   seat recommended keeping them (a retraction is harder to find if you cannot search the
   number it retracts); the owner ruled strip and the ruling stands. The banner now
   describes the withdrawal — the seed spread, the null capacity sweep, the surviving
   mechanism claims — without printing any of the dead digits.

**Verified after the edit:** zero occurrences of the withdrawn or debunked figures remain
anywhere in `docs/`.

**Deliberately NOT stripped, flagged rather than assumed:** `CLAUDE.md` and `AGENTS.md`
still name both banned figures, because they are the enforcement list — a ban that does not
say what is banned cannot be checked by any future seat, and those files are not
public-facing prose. `DECISIONS.md` likewise retains them because it is append-only by law
and is never rewritten. If the owner wants those stripped too, that is a separate ruling.

## 2026-08-14 — `tracon doctor` shipped, all four steps

Owner, typed verbatim: **"go"**, then **"just keep going until you done"**.

`tracon doctor` exists and runs. Zero-config: with no argument it exports from
`~/.claude/projects` into a temp directory, reports, and discards it. It reports runs that
ended with no recorded outcome, tool calls that never returned, the long tail, and the shape
of token spend — printed beside reference figures, each labelled with whether it replicated.

Four steps, all verified rather than asserted:
1. **Exporter drift fixed** — five line types and one system subtype added since July;
   full corpus now exports at **exit 0** with an empty anomalies block.
2. **`corpus_id` + tokenized `root`** — the manifest no longer stores an absolute path
   carrying a username.
3. **The report path** — `tracon doctor`, with `--json`.
4. **The aggregate** — `tracon doctor --share`, 1,000 bytes on the reference corpus.

**80 tests pass, ruff clean.** Two detectors were mutation-checked: reinstating a literal
root fails its test; treating every non-null status as accounted fails the suite.

**Seat decision taken under "just keep going", reversible, recorded as a seat decision and
not an owner ruling:** the aggregate is scalars plus an **allow-list** of Claude Code
built-in tool names, everything else collapsing to `other`. The allow-list proved
load-bearing rather than tidy — the real corpus put 976 minutes of `mcp__claude-in-chrome__*`
time into `other`, and a naive "statistics only, no free text" rule would have shipped the
name of an installed browser extension. Custom agent types are user-named
(`opus-med`, `sonnet-med` are this operator's own), so agent types do not travel at all.
**tracon makes no network calls; the user carries the file.**

**Durability question, answered:** transcript scraping is a **chore, not a structural
warning** — the drift fix took about twenty minutes. The finding underneath it was worth
more: `pr-link` and `custom-title` carry identifying content, and the obvious "just handle
the new types" repair would have put a GitHub repository and user-typed session names into
an export whose whole guarantee is that content does not survive capture.

**Owed by the owner, deliberately not taken by the seat:** what may be *done* with an
aggregate a stranger sends — publish it, combine it into a public base-rate table, name
contributors. That affects other people, so no keep-going instruction covers it, and it
belongs inside the `--share` notice so a contributor reads it before deciding.

- 2026-08-14 21:2x (Iris chat, owner verbatim): "tracon and agent-radar are a 1-2 punch both are good on their own but better together." — standing strategic frame: the two ship as complements (radar = live eyes in the editor, tracon doctor/monitor = measurement + evidence on the same failure classes); future direction work treats them as one story, two tools. Same entry mirrored in agent-radar DECISIONS.md.

- 2026-08-22 00:2x (Iris chat, owner verbatim): "Ok good spawn the vyuha ... and tracon seats push nav2 for later" — RELEASE for the third-leg seat: build agent-obs (the 08-14 ruling) overnight, unattended, owner asleep; these words are the release, no tab interview tonight. Seat decisions stay labeled as seat decisions; owner rulings owed (e.g. what may be done with a shared aggregate) stay owed, not taken.

## 2026-08-22 — HALF THE UNACCOUNTED-RUN FIGURE IS AN ARTIFACT

**This is a correction to a number already on record in this file and printed to users by
`tracon doctor`. It was found by the third leg on its first run against real data, and it is
recorded here before anything is done about it.**

The claim on record is that **16.5% of subagent runs end with no recorded outcome** — not
success, not failure, unaccounted. It is the measurement the whole silent-failure wedge rests
on. A share of it cannot mean what it appears to mean.

**What was measured, and how.** The new per-seat breakdown printed `workflow-subagent: 106 of
106 = 100.00% unaccounted`. Exactly 100% is not what behaviour looks like; it is what structure
looks like. The hypothesis was then handed to an agent told to **refute** it, not confirm it.

It survived. The decisive fact, MEASURED on disk: **all 106 workflow-worker meta files have no
`toolUseId` key at all.** The exporter resolves a subagent's end status either from a
task-notification in the parent transcript or from a matched synchronous `tool_result` keyed by
that id. With the key absent, both branches are unreachable, and every workflow worker falls
through to `unknown` unconditionally. Zero of 106 resolving is the only outcome that code path
can produce.

Their outcomes are not missing from the machine — they are in `journal.jsonl`, which the
exporter deliberately does not walk. MEASURED: all 106 have both a `started` and a `result`
record, so **all 106 finished**. What the journal does not carry, in its structure, is a
success/failure flag — so it settles "did it finish", not "did it succeed".

**How much of the headline this is** (MEASURED, streamed over each export):

| export | raw unaccounted | of which structurally unresolvable | corrected rate |
|---|---|---|---|
| export-2026-07-30 | 331/1626 = **20.36%** | 98 (29.6%) | 233/1528 = **15.25%** |
| export-2026-08-14 | 205/1239 = **16.55%** | 106 (51.7%) | 99/1133 = **8.74%** |
| export-2026-08-14b | 205/1253 = **16.36%** | 106 (51.7%) | 99/1147 = **8.63%** |

**Half the August figure, and a third of the July one, is a file nobody opened.** The artifact
is fully isolated: MEASURED, no run of any other agent type carries a non-null `workflow`, so
the 7–17% unaccounted rates on the ordinary seat types are untouched and remain a real,
separate phenomenon.

**What the seat did about it, and what it deliberately did not.**

DID, because it is the seat's own deliverable and it would otherwise lie to a user on first
run: agent-obs now separates structurally-unresolvable runs from unaccounted ones, keys off the
`workflow` field rather than a user-chosen type name, reports the raw and corrected rates side
by side, and gates on the corrected one. The raw figure is kept and kept identical to doctor's,
because two tools in one suite must not print different values for the same named quantity.

**DID NOT — owed to him:**

1. **The root-cause fix belongs in the exporter, not in one consumer.** Every leg reads the same
   export; patching only the tool that noticed leaves doctor and agentfail still reporting it.
   The real repair is for the export to distinguish "no outcome recorded" from "outcome not
   capturable here" — which is a **schema change**, invalidating comparisons against existing
   exports and touching agentfail's loader. That blast radius is not a seat's call at 1am.
2. **`tracon doctor` still prints 16.5% as a reference figure to strangers.** It is not *false* —
   the runs genuinely have no outcome in the export, which is what the text says — but a reader
   will take it as a fleet problem, and half of it is not. The minimum honest repair is an
   in-band caveat, not a number change. Not taken, because it is public-facing copy on the
   suite's front door.
3. **A cross-leg inconsistency this exposed.** agentfail's termination analysis already calls
   `end_status: unknown` **"missing data, not a failure"** and excludes it from its denominators.
   doctor headlines the same quantity as a finding. Both are defensible alone; together in one
   launched suite they are a question someone will ask. Owed as a positioning call.

**Method note, stated because it is the reason this was caught at all:** the figure was not
questioned by reading the code. It was questioned because a per-seat breakdown made a
suspiciously round number visible, and the round number was then handed to an adversary rather
than to a confirmer. The two withdrawn headlines in this file were both found the same way,
late. This one was found on day one of the tool that surfaces it.

- 2026-08-22 01:4x (Iris chat, owner verbatim): **"Make the whole project tracon"** — RULING, after Iris described the three-tool shape (tracon/doctor · agentfail · agent-obs): one project, one repo, one name. The study and the over-time tool fold INTO tracon as parts of it; "agentfail" and "agent-obs" cease to be separate projects or names. Iris's reading of scope, not his words: history-preserving fold on a branch, no push, public-repo laws (no trailers, banned numbers) bind.

## 2026-08-22 — THE FOLD, executed

Branch `wt-fold`, **unmerged — the owner merges.** This section is the record of what
was done to this repo's tree and history on that ruling.

**What moved.** Two separate local-only git repos, nested here and gitignored, are now
part of this tree:

| was | is |
|---|---|
| `agentfail/src/agentfail/` | `src/tracon/study/` |
| `agentfail/tests/` | `tests/study/` |
| `agentfail/docs/FINDINGS.md` · `REPLICATION.md` · `site/index.html` | `docs/study-findings.md` · `study-replication.md` · `study-findings.html` |
| `agentfail/results/study.json` | `docs/results/study.json` |
| `agentfail/scripts/{check_findings,replicate}.py` | `scripts/study_{check_findings,replicate}.py` |
| `agent-obs/src/agent_obs/` | `src/tracon/overtime/` |
| `agent-obs/tests/` | `tests/overtime/` |
| both `README.md`s | `docs/study.md` · `docs/over-time.md` |

`tracon study` and `tracon over-time` are subcommands beside `tracon doctor`; one
pyproject, one console script, one lint config, one DECISIONS.md.

**Method, and why not `git subtree`.** The imported history had to be **rewritten**, not
preserved verbatim: three commits in the study's history and two in the over-time view's
carried AI-attribution trailers, flagged for the owner on 2026-08-14 and again on
2026-08-22 as a launch-day problem. `git-filter-repo` stripped them in the same pass that
moved the paths, so nothing carrying agent attribution enters this public repo's history.
Verified after the fold by grepping the whole branch for real trailer lines: **zero**.
Author identity was already clean — every commit in both repos is the owner's.

**Seat decisions taken on the fold. All five are seat decisions, not owner rulings —
reversible, and recorded here so they can be overturned cheaply.**

1. **The package directories were renamed** (`agentfail` → `study`, `agent_obs` →
   `overtime`) because they had to move inside the `tracon` package to be part of it, and
   the old names are the project names he just retired. **Module names inside them are
   untouched** — `loader`, `stats`, `analyses/`, `corpus`, `gate`, `track` — because
   renaming those is churn with no reader on the other end.
2. **The over-time repo's `.scratch/` was excluded from the import**, and the twelve
   spec-only commits that touched nothing else pruned with it. Those are two closed
   wayfinder maps holding competitive positioning, named third parties, first-person
   quotes lifted from practitioners, and an inventory of the owner's own assets. **This
   repo is public**, and its `.gitignore` already says planning scratch is never
   published. The files are untouched in the nested repo's `.git`, which is the only copy
   — so **do not delete `agent-obs/` without deciding what happens to them.** Their
   conclusions are already on record in this file.
3. **One copy of the statistics.** `agent_obs/stats.py` was a hand-synced copy of the
   study's `wilson` / `normal_sf` / `two_proportion_test`, kept separate because the two
   packages could not depend on each other (seat decision 3 of the overnight build,
   below). They are one package now, so the copy is deleted and the gate imports the
   original. A hand-synced copy of a significance test is a wrong number waiting to
   happen.
4. **Lint exemptions rather than a refactor.** The study never ran a linter in its own
   repo; bringing it under this repo's `select = ["ALL"]` produced 188 findings. 164 were
   fixed. The remainder are granted per directory with a reason each, and only for rules
   that would mean restructuring analysis code whose numbers are published and whose shape
   the tests pin — the same exemptions this repo already grants the exporter, for the same
   reason.
5. **The study's `--trace` no longer defaults to a path on the author's own machine.**
   It defaulted to `~/Personal/infinity/tracon/traces/export-2026-07-30`, which was
   harmless in a local-only repo and is not in a public one. `report` without `--trace`
   now says so and names `tracon export`.

**Verified, measured rather than asserted, at the tip of the branch:**

- **282 tests green** — 80 tracon, 161 study, 41 over-time — and **`ruff check .` reports
  zero findings** across the whole tree. Coverage 92.65%.
- The study, run through the new entry point over the real 2026-07-30 corpus, reproduces
  its **published** figures exactly: 85,104 tool calls, 3.341% tool error rate,
  1.29%–3.569% repeat-run bracket, 75.08% of tool time in the >=60s tail, trend z = -2.33
  p = 0.020. `tracon study report --check docs/results/study.json` exits 0, and
  `scripts/study_check_findings.py` passes all seven numeric assertions.
- `tracon over-time track` over all three real corpora prints the same raw
  (20.36 / 16.55 / 16.36) and corrected (15.25 / 8.74 / 8.63) unaccounted rates already on
  record above.
- No banned figure appears anywhere in the imported code, docs or history.

**Carried over from the two folded repos' own `DECISIONS.md` files, now deleted — one
project has one decisions log.** Their owner rulings were already recorded above. What was
only in theirs:

- **The study's 2026-08-04 ruling, "fine as own project (unsure if a product though)", is
  SUPERSEDED** by "Make the whole project tracon". Recorded as superseded, not deleted.
- **The four seat decisions taken on the 2026-08-22 overnight build of the over-time
  view** stand unchanged and are still reversible: (1) it is the *fleet-over-time* leg —
  movement across N corpora plus a gate — built because neither `doctor` nor the study
  answers "is it getting worse"; (2) it was built in its own repo on a branch, explicitly
  **not** settling where the tools finally live — which is what this fold now settles;
  (3) the statistics were copied rather than imported, **superseded by fold decision 3
  above**; (4) the gate uses a two-proportion test rather than a threshold wherever the
  metric is a real proportion, and never flags an improvement.

**Owed by the owner. Unchanged by this fold, and still owed:**

1. **What may be done with an aggregate a stranger sends** — publish it, pool it into a
   public base-rate table, name contributors. Carried since 2026-08-14. It affects other
   people, so no keep-going instruction covers it.
2. **The root-cause repair for the unaccounted-run artifact** is a schema change in the
   exporter that would invalidate existing exports and touch the study's loader.
3. **`tracon doctor` still prints the uncorrected figure** on a public front door.
4. **The cross-command inconsistency**: the study calls `end_status: unknown` "missing
   data, not a failure" and excludes it from its denominators; `doctor` headlines the same
   quantity as a finding.
5. **Removing the two leftover working directories** (`agentfail/`, `agent-obs/`) once
   this branch is merged — see seat decision 2 before deleting `agent-obs/.git`.
6. **The name** — `over-time` is this seat's subcommand name, not a product name. Naming,
   domains and package registration are his alone.
