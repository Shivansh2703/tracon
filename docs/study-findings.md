# How agentic coding sessions actually fail

An empirical failure-mode analysis of 85,104 tool calls across 1,854 real agent runs.

*Generated from `results/study.json`. Every figure below is reproduced by
`python -m agentfail report --trace <export>`; nothing is transcribed by hand.*

---

## Read this before any number

**This is one developer's corpus.** Every session is one person's own, on his own
software projects, in one harness (Claude Code), with his prompting style and his habit of
running large subagent fleets. It is not a sample of "agents in the wild" and it cannot be
generalised to other operators, other domains, or other tools without new data. The
sample is large; it is not representative.

Six limitations, stated once, applying to everything that follows:

1. **Single operator.** One person's prompting, one person's risk tolerance, one person's tooling.
2. **Single harness.** Claude Code, 24 versions across the window. No other agent framework.
3. **Single domain.** His own repos - software engineering, not customer support, not agentic RPA.
4. **Content-stripped by design.** The export retains shapes, sizes, ids and timings. It retains
   no prompt text, no tool arguments, no outputs. This is a privacy posture, and it is the single
   biggest constraint on what can be asked. Several questions below die on it, and that is reported
   rather than worked around.
5. **Observational.** No interventions, no control group, no ground truth for whether any task was
   done *correctly*. "Completed" throughout means *the run finished*, never *the run was right*.
6. **Survivorship.** Transcripts deleted or never written are invisible.

The headline result is a negative one, and it is reported as a negative one.

---

## Method

**Corpus.** A tracon trace export (`export-2026-07-30`, schema v1): 201,705 normalized
events from 1,857 raw transcript files, privacy-stripped at export time. Spans 30.2 days
across 11 distinct projects.

| | |
|---|---|
| Tool calls | 85,104 |
| Model API calls | 88,897 |
| Streams (units of execution) | 1,854 |
| - main sessions | 228 |
| - subagent runs | 1,626 |
| Human prompt arrivals | 4,951 |
| Turns | 4,390 |
| Context compactions | 38 |
| Distinct tools | 64 |
| Model families observed | 5 (Sonnet 50,663 calls / Fable 18,580 / Opus 4.8 12,502 / Opus 5 5,027 / Haiku 2,935) |

**Unit of analysis.** A *stream* is one agentic execution: a main session, or a single
subagent run, keyed `(session_uuid, agent_id)`. Analyses run per stream. Merging a
subagent's calls into its parent's would manufacture repetition that never occurred in any
one reasoning loop.

**Statistics.** Every rate carries a Wilson 95% interval (chosen over the normal
approximation because several rates here sit near zero). Comparisons use a two-sided
two-proportion z-test. The context-pressure question uses a Cochran-Armitage trend test, so
that a flat curve is called flat on evidence rather than by eyeballing.

**Reproduction.** `python -m agentfail report --trace <export-dir> --json results/study.json`.
Runs in ~3s. `--check results/study.json` re-runs and fails on any drift.

---

## Q1 - Looping and non-termination

> *"A model looping instead of terminating"* - the failure mode named in live job postings.

### The measurement problem, first

Tool arguments are stripped to a depth-1 **shape**: key names, value types, string lengths.
A `Bash` call becomes `command:s78`. Two *different* 78-character shell commands share that
shape. **"The agent repeated the same call" is therefore not directly observable**, and this
study reports a bracket rather than inventing a point estimate:

- **Upper bound** - consecutive calls sharing `(tool, args_shape)`. Contains every true repeat,
  plus an unknown number of shape collisions.
- **Lower bound** - the same, additionally requiring identical `result_chars`. A repeated call
  returning an identically-sized result is near-certainly a genuine repeat, but this misses real
  repeats whose output changed between attempts (`git status` twice around an edit).

The truth lies between. Both are carried everywhere; neither is collapsed into a headline.

### Result: looping is rare, shallow, and not a failure signature

| Measure | Lower bound | Upper bound |
|---|---|---|
| Tool calls inside a repeat run | **1.29%** [1.22-1.37] (1,098) | **3.57%** [3.45-3.70] (3,037) |
| Streams with any repeat run | 10.62% [9.29-12.12] (194/1,826) | 32.48% [30.37-34.66] (593/1,826) |
| Streams with a "stuck" run (>=5 identical calls) | **1.15%** [0.75-1.75] (21/1,826) | **2.08%** [1.52-2.84] (38/1,826) |

Run-length distribution (upper bound, n=1,234 runs): **p50 = 2, p90 = 4, p99 = 10, max = 34.**
980 of 1,234 runs are length 2 - a repeat of two, which is ordinarily *checking something twice*,
not a loop.

The longest run in the entire corpus (34 consecutive `WebFetch` calls, identical URL length,
zero errors) is on inspection a paginated crawl, not a stuck agent. **The most extreme apparent
"loop" in 85,104 calls is a false positive of the detector.** Repeat runs are dominated by `Read`
(676 runs) and `Bash` (381) - sequential file inspection, the shape of normal work.

**Does a stuck run predict a bad ending?** Among 1,625 subagent runs: 0 of 24 runs containing a
stuck run ended `failed`/`killed`, versus 25 of 1,601 without. **No predictive signal - and with
only 25 hard failures corpus-wide, this comparison is underpowered by construction and cannot
rule out a real effect.**

> **Finding (boring, and reported boring): agents in this corpus do not meaningfully loop.**
> Between 1.2% and 2.1% of runs contain anything a human would call stuck, and the deepest
> example is legitimate pagination. If you are building loop-detection for this workload, you
> are building for a failure mode that occurs in roughly 1 run in 60 - and your detector's
> false-positive rate will likely exceed the phenomenon.

---

## Q2 - Tool failures and what the agent does next

**Overall tool-call error rate: 3.34%** [3.22-3.46] (2,843 / 85,104).

| Tool | n | Error rate |
|---|---|---|
| Edit | 7,771 | **6.12%** [5.61-6.68] |
| AskUserQuestion | 246 | 6.91% [4.36-10.79] |
| Write | 1,910 | 3.67% [2.91-4.61] |
| Bash | 53,155 | 3.61% [3.45-3.77] |
| WebFetch | 617 | 3.08% [1.98-4.76] |
| Skill | 246 | 2.85% [1.39-5.76] |
| Read | 12,016 | 1.22% [1.04-1.44] |
| Agent | 1,596 | 1.06% [0.67-1.70] |
| SendMessage | 3,207 | 0.12% [0.05-0.32] |
| WebSearch | 828 | 0.00% [0-0.46] |
| ToolSearch | 1,074 | 0.00% [0-0.36] |

`Edit` is the most error-prone tool in real use at nearly 2x the `Bash` rate - the string-match
precondition (`old_string` must match exactly and uniquely) fails often enough to be the single
largest recoverable-error source after raw shell.

### What follows a failed call

Structure of the very next tool call after an error (n = 2,843):

| Next action | Share |
|---|---|
| Same tool, **different** arguments | **64.23%** [62.45-65.97] (1,826) |
| Switched to a different tool | 32.71% [31.01-34.46] (930) |
| **Identical retry** (same tool, same shape) | **1.76%** [1.34-2.31] (50) |
| No further tool call in the stream | 1.30% [0.95-1.79] (37) |

And the model response that consumed the failed result (n = 2,843):

| | Share |
|---|---|
| Kept acting (issued another tool) | **95.78%** (2,723) |
| Text-only response - stopped working | 3.87% (110) |
| No further model call at all | 0.35% (10) |

> **Finding: error handling is the strongest behaviour in this corpus.** After a tool failure
> the agent adapts - different arguments or a different tool - in 96.9% of cases, and retries
> blindly in 1.76%. The "dumb retry loop" is essentially absent (50 occurrences in 85,104 calls).

### The money question: does it proceed on a failed result?

This is what the market screens for, and **the traces cannot answer it directly.** Whether the
model's next sentence acknowledged the error, or silently built on a broken result, is a fact
about content - and content is stripped. What can be measured is one structural proxy:

**Runs that reported `completed` while their trace still held an error never demonstrably
resolved: 6.27%** [5.07-7.74] (80 / 1,276 completed subagent runs).
Runs whose *final* tool call errored and still reported completed: **1.65%** [1.08-2.50] (21/1,276).

For contrast, the same proxy on runs that ended `failed` is 26.3% (5/19) and `killed` 33.3% (2/6) -
the proxy does track badness, which is weak evidence it is measuring something real.

**Caveats that materially weaken this number, in both directions.** "Resolved" is defined as a
later success of the *same tool* in the same stream - generous, so 6.27% is a floor on
unresolved errors but an over-count of *ignored* ones, since an agent may have correctly reported
the failure as a limitation in its final message. That message is not in the export.

> **Honest verdict: 6.27% is the most interesting number in this study and the least safe.**
> It is a structural proxy for "declared success with unfinished business", not an observation
> of an agent proceeding on a failed result. Anyone quoting it should quote the caveat with it.

---

## Q3 - The long tail: 3.7% of calls, 75% of the wall clock

Confirmed on this corpus: **3,153 calls >=60s (3.71% of calls) hold 75.08% of all tool time**
(246.1 tool-hours total). The reliability question is what they *are*. Classification is
structural - by tool identity and outcome, never by guessing intent.

| Threshold | Calls | % of calls | % of tool time | Heavy work | **Errored** | Waiting on human | Waiting on agent |
|---|---|---|---|---|---|---|---|
| >=10s | 7,507 | 8.83% | 86.88% | 85.6% | 8.3% | 3.2% | 2.9% |
| >=30s | 4,360 | 5.13% | 80.94% | 82.4% | 9.5% | 4.3% | 3.8% |
| **>=60s** | **3,153** | **3.71%** | **75.08%** | **81.4%** | **10.2%** | **4.3%** | **4.1%** |
| >=5min | 396 | 0.47% | 36.94% | 71.0% | 16.7% | 5.8% | 6.6% |
| >=10min | 90 | 0.11% | 23.14% | 46.7% | **27.8%** | 13.3% | 12.2% |
| >=30min | 8 | 0.01% | 16.29% | 37.5% | 50.0% | - | 12.5% |

Two things fall out, one expected and one not.

**Expected: the bulk of the tail is real work.** At the >=60s threshold, 81% of calls are
successful non-waiting work - builds, test suites, installs. `Bash` is 2,835 of the 3,153. The
long tail is mostly a *scheduling* fact, not a reliability one.

**Not expected: slowness is a strong failure signal, and it sharpens monotonically.**
Calls >=60s error at **10.21%** [9.20-11.32] versus **3.07%** [2.95-3.19] for calls under 60s -
a 3.3x enrichment, **z = 21.9, p ~ 1.5e-106** (n = 3,153 vs 81,913). By >=10 minutes, 27.8%
of calls are errors (n=90). By >=30 minutes, half are (n=8 - too small to lean on).

> **Finding: elapsed time is the single best cheap predictor of tool failure available in this
> data.** It needs no model, no content, no semantics - just a clock. A tool call that has been
> running 10 minutes is roughly 9x likelier to end in an error than a typical call.

Also worth naming: **4.3% of >=60s calls are the agent waiting on a human** (`AskUserQuestion`,
`ExitPlanMode` - 147 calls). Any latency budget that counts these as agent slowness is measuring
the operator's response time and calling it a model problem.

**Extreme tail.** The single longest call in the corpus is a `Bash` invocation running
**1,758.8 minutes (29.3 hours)** that returned *successfully* with a 49-character result - a
hung process nobody's watchdog caught. **25 calls (0.029%) never returned at all** (no
`tool_result` on disk - the stream died mid-call); 23 of the 25 are `Bash`.

---

## Q4 - Do failures cluster near context limits or compaction?

The folk claim is that agents degrade as context fills. This corpus can test it: every tool call
joins back to the model call that issued it, which reports exactly how many input tokens the
model was holding (81,979 of 85,104 calls join successfully).

**Error rate does not rise with context size. It falls slightly.**

Unstratified Cochran-Armitage trend across 13 bins of 25k tokens: **z = -2.33, p = 0.020** -
i.e. a weak *negative* trend. Before anyone reads that as "bigger context is safer", the obvious
confound: tool mix shifts hard with context size (`Read` falls from 45.7% of calls in the 0-25k
bin to 11.8% at 300k+, while `Edit` rises from ~4% to ~16%), and tools have very different error
rates. Stratifying inside single tools:

| | Calls | Trend test |
|---|---|---|
| Bash | 11,967 | z = -1.84, p = 0.066 (n.s.) |
| Edit | 3,660 | z = -1.03, p = 0.303 (n.s.) |
| Read | 5,732 | z = -2.35, p = 0.019 |

**The effect does not survive stratification in the two largest tools.** One of three tools shows
a weak negative trend at p = 0.019, uncorrected for three comparisons.

> **Finding (negative, and the most solidly-powered claim in this study): there is no evidence
> that tool-call failures increase with context pressure in this corpus, across 81,979 joined
> calls spanning 0 to 300k+ tokens. Any weak trend present runs in the *opposite* direction to
> the folk claim and does not survive controlling for tool mix.**

**Compaction is unanswerable here for lack of data.** Only **38 compaction events** exist
corpus-wide (33 manual, 5 automatic) across 26 streams. Error rate in the 10 minutes after a
compaction: 3.87% (27/698) versus a 3.34% baseline - **p = 0.44, indistinguishable**. With 38
events this comparison can rule out a large effect and nothing smaller. **Reported as
underpowered, not as null.**

---

## Q5 - Premature confidence: unanswerable from this data

> *"A model deciding it has enough information when it doesn't."*

**This corpus cannot measure this, and no number in this study should be read as if it does.**

The claim has two components: what the agent concluded, and whether that conclusion was
warranted. The export holds neither - content is stripped by design, and there is no ground
truth anywhere in the corpus for whether a task was done correctly. No amount of cleverness with
timings and shapes recovers a judgement about the sufficiency of evidence.

The one shape that can be measured, offered as a bound on *suspicion* rather than a failure rate:
**2.04%** [1.39-2.97] of completed subagent runs (26/1,276) finished with <=2 tool calls. The
distribution of evidence-gathering among completed runs is otherwise healthy - 1,065 of 1,276
made 10+ tool calls (median 24 calls per run, p95 113, max 1,054). A run that made two tool calls
may have been given a two-tool-call task; nothing here distinguishes that from a run that gave up
early.

> **Reporting an unanswerable question as unanswerable is the result.** A soft proxy dressed as
> a measurement of premature confidence would be the single easiest number in this study to
> fabricate, and the one most likely to be believed.

---

## Q6 - Recovery: does a run that goes wrong come back?

Scoped to the 1,626 subagent runs, the only executions carrying a machine-recorded outcome
(main sessions have no completion record - a human closed them).

| End status | Share |
|---|---|
| completed | 78.48% [76.41-80.40] (1,276) |
| **unknown** | 19.99% [18.12-22.00] (325) |
| failed | 1.17% [0.75-1.82] (19) |
| killed | 0.37% [0.17-0.80] (6) |

**Hard failure rate: 1.54%** [1.04-2.26] (25/1,626). `unknown` is *missing data*, not failure -
usually a synchronous run consumed inline, or a parent that ended first.

**The naive recovery comparison is a trap, and this study fell into it before catching it.**
Raw completion rate for runs containing a tool error is 83.8% versus 73.3% for clean runs
(p = 2.4e-7) - apparently *errors help*. They do not. `unknown` is unevenly distributed:
25.98% of clean runs have no recorded outcome versus 13.84% of error-containing runs, because
short synchronous runs are both less likely to hit an error and less likely to emit a
notification. The comparison was measuring observability.

Restricted to runs whose outcome was actually recorded:

| | Completion rate |
|---|---|
| Runs containing >=1 tool error | **97.27%** [95.78-98.25] (678/697) |
| Runs with no tool error | **99.01%** [97.85-99.54] (598/604) |

**z = -2.27, p = 0.023.**

> **Finding: recovery is the norm, and the cost of an error is small but real.** Hitting a tool
> error costs a run roughly **1.7 percentage points** of completion probability (97.3% vs 99.0%).
> Agents in this corpus overwhelmingly recover without human intervention.
>
> The load-bearing caveat: `completed` means the run *finished and reported*, not that its work
> was correct. This measures survival, not success. A run that recovered from an error and then
> produced a wrong answer is counted here as a recovery.

---

## What this study is worth

**The three findings I'd stand behind:**

1. **Elapsed time predicts tool failure, strongly and cheaply.** 10.21% vs 3.07% error rate above
   and below 60 seconds (n = 3,153 / 81,913, p ~ 1e-106), sharpening to 27.8% past ten minutes.
   Actionable without any model in the loop.
2. **No context-pressure effect.** Across 81,979 calls spanning 0-300k+ tokens, failures do not
   rise with context, and the weak trend that exists points the other way and dies under
   stratification. This contradicts a widely-repeated claim.
3. **Looping barely exists, and error handling is excellent.** 1.15-2.08% of runs contain a stuck
   repeat; blind identical retry follows 1.76% of errors; adaptive response follows 96.9%.

**What the data could not answer:** premature confidence (content stripped, no ground truth);
whether an agent proceeded on a failed result *in substance* rather than in structure; anything
about compaction (38 events); whether a `completed` run was actually *correct* at any point in
this document.

**Where this is weakest**, in the order a skeptic will find it:

- **n = 1 operator.** The most likely explanation for "agents rarely loop and handle errors well"
  is that this particular operator's harness, models and prompting are good, and/or that he
  intervenes early on sessions going wrong - intervention that is invisible in the trace. The
  low loop rate may partly measure *him*, not the agents.
- **Shape-level repeat detection** carries a 2.8x spread between its bounds. That spread is the
  honest width of the uncertainty, and it is wide.
- **The 6.27% unresolved-error figure** is a proxy with defensible objections in both directions.
- **`completed` != correct**, everywhere, with no way to close the gap from this data.
- **Multiple comparisons** are uncorrected throughout; the two results at p ~ 0.02 should be read
  as suggestive, not established.
