# How agentic coding sessions actually fail

An empirical failure-mode analysis of 85,104 tool calls across 1,854 real agent runs.

*Generated from `docs/results/study.json`. Every figure about **this** corpus is reproduced by
`tracon study report --trace <export>`; nothing about it is transcribed by hand.
Figures about the **public replication corpus** are transcribed verbatim from
`docs/study-replication.md` and are marked as such wherever they appear.*

**Status (2026-08-03): externally replicated, and one finding's scope corrected.**
94,059 tool calls from 3,895 headless runs by 13 models in a different harness were run
through these same analyses (`docs/study-replication.md`). Finding 2 replicated far more
strongly and has dropped its operator caveat. Finding 3 is **false as stated about
"agents"** and has been restated as a claim about *frontier models*. Finding 1 is not
testable on any public corpus. One factual error in Q4 was found and is corrected below.

---

## Read this before any number

**This is one developer's corpus.** Every session is one person's own, on his own
software projects, in one harness (Claude Code), with his prompting style and his habit of
running large subagent fleets. It is not a sample of "agents in the wild" and it cannot be
generalised to other operators, other domains, or other tools without new data. The
sample is large; it is not representative.

Six limitations, stated once, applying to everything that follows:

1. ~~**Single operator.**~~ **Answered externally (2026-08-03).** One person's prompting, one
   person's risk tolerance, one person's tooling - but the behaviour reproduces in a headless
   harness with no operator at all (`docs/study-replication.md`). What replaces it is **single
   production corpus**: every public agent dataset is short, step-capped benchmark output, and
   there is no public corpus of real production agent sessions at all.
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

**Reproduction.** `tracon study report --trace <export-dir> --json docs/results/study.json`.
Runs in ~3s. `--check docs/results/study.json` re-runs and fails on any drift.

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

One subtlety worth stating because it looks like an inconsistency: the lower bound splits a run
wherever `result_chars` changes, so it can report *more, shorter* runs over the same calls than
the upper bound does. The quantity that is guaranteed monotone between the bounds is *calls
inside a repeat run*, which is what the headline uses. Run-length distributions below are
quoted from the upper bound only.

### Result in this corpus: looping is rare, shallow, and not a failure signature

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

> **Finding (scope corrected 2026-08-03): *frontier models* do not meaningfully loop.**
> In this corpus - which ran Anthropic frontier models throughout - between 1.2% and 2.1% of
> runs contain anything a human would call stuck, and the deepest example is legitimate
> pagination. If you are building loop-detection **for a frontier-model workload**, you are
> building for a failure mode that occurs in roughly 1 run in 60, and your detector's
> false-positive rate will likely exceed the phenomenon.
>
> **Stated about "agents" this is false, and the earlier version of this document stated it
> that way.** See below.

### What the replication did to this finding

*Figures transcribed from `docs/study-replication.md`.*

The same analyses were run over 94,059 tool calls from 3,895 headless OpenHands runs on
SWE-bench Lite, by 13 models from six vendors. **Corpus-wide, this finding is contradicted:**

| | Original | Public | Test |
|---|---|---|---|
| Calls inside a repeat run | 1.29% - 3.57% | **7.49% - 19.48%** | |
| Runs with a stuck (>=5) run | 1.15% - 2.08% | **11.93% - 25.01%** | |
| Blind identical retry after an error | **1.76%** (50/2,843) | **16.12%** (4,657/28,886) | z = 20.6, p = 6.5e-94 |
| Adaptive next action | 96.94% | 80.10% | |

**But the 13 models do not agree with each other**, and that is the whole result. Blind-retry
rate spans **0.7% to 31.9%** inside one harness - a wider gap than between the two corpora -
and the three frontier Claude runs sit at the bottom of it:

| Model run | Calls | Blind retry % | Stuck runs % (lo-hi) |
|---|---|---|---|
| claude-3-5-sonnet (v2.2) | 7,531 | **0.7** | 0.0 - 2.7 |
| claude-3-5-haiku (v2.1) | 9,334 | **1.2** | 0.3 - 1.0 |
| claude-3-5-sonnet (v2.1) | 7,997 | **1.8** | 0.3 - 3.3 |
| gpt-4o | 7,109 | 13.5 | 11.7 - 36.3 |
| qwen-2.5-72b | 5,632 | 20.1 | 21.7 - 43.7 |
| deepseek-v2.5 | 5,537 | 28.1 | 28.0 - 56.0 |
| llama-3.3-70b | 14,224 | **31.9** | 41.1 - 41.1 |
| *(this corpus, for reference)* | *85,104* | *1.76* | *1.15 - 2.08* |

Those frontier numbers are statistically indistinguishable from this corpus's 1.76% and
1.15-2.08% - in a different harness, on a different workload, with no human present.
**The low loop rate was measuring the model, not the operator.**

**And now there is ground truth, which this corpus never had.** SWE-bench scores 2,253 of
the public runs against the repository's own tests. A stuck repeat run cuts resolution from
**38.58%** [36.33-40.89] (674/1,747) to **14.43%** [11.63-17.76] (73/506), z = -10.16,
**p = 2.9e-24**. A harness-flagged loop cuts it to 6.87% (34/495). So the advice above is
conditional rather than wrong: **loop detection is genuinely not worth building for a
frontier-model workload, and is worth building for a mixed-model one** - where the phenomenon
is 1 run in 5 and each occurrence costs most of the run's chance of being right.

**The bracket is now calibrated.** The public corpus keeps real tool arguments, so the same
looping analysis was run twice - once over this study's lossy shape fingerprint, once over a
hash of the actual arguments. Truth landed **74% of the way from the lower bound to the
upper** (7.49% lower / **16.42% exact** / 19.48% upper). Anyone reading `1.29% - 3.57%` as
"probably about 1.3%" is reading it wrong: **quote the upper bound as the working estimate.**
(The collision rate depends on argument-length distribution, so this calibrates the method,
not this corpus's specific numbers.)

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
>
> **Scope, same correction as Q1.** This is a property of the models, not of agents generally.
> Across 13 models headless, adaptive response falls to 80.10% and blind retry rises to 16.12%
> - but the frontier Claude runs in that corpus retry blindly at 0.7-1.8%, matching this
> corpus. Read it as *frontier models handle errors well*, never as *agents do*.

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
>
> **Untestable externally, and reported as untestable.** *(transcribed from
> `docs/study-replication.md`)* The public benchmark harness caps command duration, so its >=60s
> tail is **0.22%** of calls against **3.71%** here - 208 calls out of 94,059. The sign there
> is the same (40.87% vs 30.69%, 1.33x, z = 3.18, p = 0.0015) but the effect dies under the
> shell-only sensitivity check: **1.05x (41.54% vs 39.58%, p = 0.58)**. Neither confirmed nor
> refuted; **this finding remains scoped to this corpus** until somebody publishes production
> traces with an untruncated tail.

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
model was holding.

**Correction (2026-08-03, from the external replication).** An earlier draft of this
section claimed 81,979 of 85,104 calls join successfully. That figure is wrong and was
never what the code computed: **25,199 calls (29.6%) join**, and the other 59,905 carry
an `api_uuid` that appears nowhere in the export as an `api_call`. Worse, the joinable
subset is not random — 22.5% of `Bash` calls join versus 47.7% of `Read`, and joined
calls carry a lower error rate (2.79%) than unjoined ones (3.57%). Everything below is
computed on that 30% subset. See `docs/study-replication.md`.

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

> **Finding (negative, and the study's strongest result - because it replicated, not because
> of its own n): there is no evidence that tool-call failures increase with context pressure
> in this corpus, across 25,199 joined calls spanning 0 to 300k+ tokens. Any weak trend present
> runs in the *opposite* direction to the folk claim and does not survive controlling for tool
> mix.**
>
> **This finding replicates externally, far more strongly** *(transcribed from
> `docs/study-replication.md`)* — **z = -10.80, p = 3.4e-27 across 47,545 joined calls** from 13
> models in a different harness with no operator present, against z = -2.33 here. Error rate
> by context bin there runs 30.7% → 29.5% → 25.5% → 22.2% → 22.5% → 24.4% → 19.6%. **It is the
> one finding here that no longer needs a single-operator caveat at all.**
>
> Two honest complications the public data can see and this corpus cannot. Inside single tools
> the effect *splits* rather than simply surviving: `run_ipython` (n = 28,528) gives z = -15.97,
> while `run` (shell, n = 19,017) gives z = **+3.42**, p = 0.00063 - the one curve that rises.
> But that curve is not monotone (32.1% → 37.0% → 38.2% → 32.3% → 30.0%): it humps at 50-75k
> and then falls, and a linear trend test is a poor summary of a hump. **Both corpora hump in
> the same place** - this one climbs 1.6% → 2.5% → 3.6% over its first three bins before
> flattening. That shared shape is more interesting than either corpus's overall sign, and
> neither study is powered to say whether it is real degradation or a shift in what the agent
> is doing at that stage.
>
> One thing this is *not*: **this study's best-powered claim.** That description belonged to
> the retracted 81,979 figure, and the honest denominator is 25,199 from a subset that
> under-represents `Bash` and under-represents errors. Its strength comes from the external
> corpus, not from this one.

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

**The three findings I'd stand behind**, ordered by how well they survived being tested on
somebody else's data:

1. **No context-pressure effect - the strongest result here.** Across 25,199 joined calls
   spanning 0-300k+ tokens, failures do not rise with context, and the weak trend that exists
   points the other way and dies under stratification. This contradicts a widely-repeated claim.
   **Replicated externally on 47,545 calls from 13 models in another harness with no operator
   present, at z = -10.80 against -2.33 here** - roughly five times the test statistic, in a
   corpus that shares nothing with this one but the analysis code. **It carries no caveat about
   operator, harness or model family any more.** Its strength is the replication; its own
   denominator is a biased 30% subset (see Q4).
2. **Frontier models barely loop, and handle errors excellently** - a claim about *models*, not
   about *agents*. 1.15-2.08% of runs contain a stuck repeat; blind identical retry follows
   1.76% of errors; adaptive response follows 96.9%.

   **Scope corrected by the replication, and this is the correction that matters.** Stated as a
   claim about agents it is false: across 3,895 headless runs by 13 models, blind retry is
   **16.12%** (z = 20.6, p = 6.5e-94) and stuck runs are 11.93-25.01%. But blind retry spans
   **0.7% to 31.9% across models inside that one harness**, and the frontier Claude runs land at
   1.8%, 1.2% and 0.7%, with stuck runs at 0.3-3.3% - indistinguishable from the figures here,
   in a different harness, on a different workload, with no human present. **The low loop rate
   was measuring the model, not the operator.** New ground truth makes the advice conditional
   rather than wrong: a stuck repeat run cuts SWE-bench resolution from **38.6% to 14.4%**
   (p = 2.9e-24), so loop detection is genuinely not worth building for a frontier-model
   workload and *is* worth building for a mixed-model one.
3. **Elapsed time predicts tool failure, strongly and cheaply.** 10.21% vs 3.07% error rate above
   and below 60 seconds (n = 3,153 / 81,913, p ~ 1e-106), sharpening to 27.8% past ten minutes.
   Actionable without any model in the loop. **Neither confirmed nor refuted externally, and
   claimed as neither:** the benchmark harness caps command duration, so its tail is 0.22% of
   calls against 3.71% here, and the effect dies under a shell-only sensitivity check (1.05x,
   p = 0.58). **Still scoped to this corpus** (`docs/study-replication.md`).

**A near-miss worth publishing, because it is the strongest evidence this study is being run
honestly.** The replication's first adapter silently skipped the eight of thirteen runs that
store history as `[action, observation]` pairs rather than a flat list. **2,398 of 3,895 runs
registered zero tool calls, and every headline number was quietly computed from the five newest
runs.** It raised no error and the output looked entirely plausible. It was caught only by
noticing that `streams_with_tool_calls` was 1,497 when the corpus had 3,895 streams. That is
precisely the bug class this project exists to find - a silent, plausible, wrong number - found
inside this project's own analysis. A regression test pins it now; the general point stands, and
every figure in `docs/study-replication.md` depends on one loading layer.

**What the data could not answer:** premature confidence (content stripped, no ground truth);
whether an agent proceeded on a failed result *in substance* rather than in structure; anything
about compaction (38 events); whether a `completed` run was actually *correct* at any point in
this document.

**Where this is weakest**, in the order a skeptic will find it:

- **~~n = 1 operator.~~ Tested externally and largely answered - see `docs/study-replication.md`.**
  The suspicion was that the low loop rate measured this operator rather than the agents. It
  does not: the same models reproduce it in a headless harness on a different workload with no
  human in the loop. What remains is **n = 1 production corpus** - every public dataset is
  benchmark output, short and step-capped, so nothing external speaks to open-ended multi-day
  sessions. Closing that needs a second operator's telemetry, not more benchmarks.
- **`n = 1 production corpus`, and that gap is itself a finding.** Three independent surveys of
  every public candidate found exactly one corpus carrying the four fields these questions need
  (per-call timing, tool identity, an error flag, per-call context tokens), and it is a
  benchmark. **There is no public corpus of real production agent sessions at all.** Agent
  benchmarks publish scores; nobody publishes traces. That is worth stating as a result rather
  than as a lament: the reason a study like this one is rare is that the raw material does not
  exist publicly, and four fields per tool call would fix it.
- **Every number here depends on a loading layer that can fail silently**, and one such failure
  was caught during the replication (see above). This is stated in the weaknesses list rather
  than buried in a methods note because it nearly invalidated a whole document without raising
  a single error.
- **Shape-level repeat detection** carries a 2.8x spread between its bounds. That spread is the
  honest width of the uncertainty, and it is wide. The replication calibrates it for the first
  time against real arguments: on that corpus the truth sat 74% of the way from the lower bound
  to the upper, so **the upper bound is the better working estimate**, not the midpoint.
- **The 6.27% unresolved-error figure** is a proxy with defensible objections in both directions.
- **`completed` != correct**, everywhere, with no way to close the gap from this data.
- **Multiple comparisons** are uncorrected throughout; the two results at p ~ 0.02 should be read
  as suggestive, not established.
