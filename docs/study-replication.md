# Replicating the three findings on public data

`docs/FINDINGS.md` names its own worst weakness: **n = 1 operator.** One developer,
one harness, one prompting style. Its own guess at the explanation for "agents rarely
loop and handle errors well" was that this particular operator is good, and that the
low loop rate might be measuring *him*.

This document tests that on somebody else's data: 94,059 tool calls from 3,895 agent
runs by **thirteen different models** in a **different harness** (OpenHands CodeActAgent)
on a **different workload** (SWE-bench Lite), with **no human in the loop at all**.

**The short version.** The operator hypothesis is wrong, and the answer is more
interesting than either "it replicated" or "it didn't":

| # | Finding | Verdict |
|---|---|---|
| 1 | Elapsed time predicts tool failure | **Directionally replicates, but not fairly testable.** Same sign, p = 0.0015 — on a long tail the benchmark harness has truncated to 0.22% of calls, and it does not survive the sensitivity check. |
| 2 | No context-pressure effect | **Replicates, and more strongly.** z = −10.80 across 47,545 joined calls: failures fall as context fills, as in the original. One of the two tools runs the other way. |
| 3 | Looping barely exists | **Contradicted corpus-wide — and replicated exactly on the frontier models in it.** Blind retry 16.1% overall vs 1.76%; but 1.8% and 0.7% on the two Claude Sonnet runs. |

Finding 3 is the one that would have embarrassed anyone quoting the study as a
general claim, and it is also the one that answers the study's own question.
**What the original corpus measured was not its operator. It was its model.**

Everything below is produced by the **unmodified analyses** in `src/agentfail/analyses/`.
Only the loading layer is new. Reproduce with:

```
python -m agentfail adapt --adapter openhands --out <export> <output.jsonl files>
python -m agentfail report --trace <export> --json <result.json>
python scripts/replicate.py --public <result.json> ...
```

---

## 1. What public data actually exists

Three parallel surveys checked every candidate that publishes anything, verifying at
source rather than from memory. **The overwhelming answer is that agent benchmarks
publish scores, and only scores.** Of everything checked, exactly one corpus carries
all four fields these findings need — per-call wall-clock timing, tool identity, a
success/failure signal, and per-call context tokens.

| Source | Raw per-call records | Timing | Tool id | Error flag | Tokens | Usable |
|---|---|---|---|---|---|---|
| **OpenHands eval outputs** (`OpenHands/openhands-evaluation-outputs`) | yes, `output.jsonl` | **yes** — action/observation timestamp pair | yes | yes — `extras.exit_code` | **yes** — per call | **primary corpus** |
| **Terminal-Bench 2.0 leaderboard** (`harborframework/terminal-bench-2-leaderboard`) | yes, `trajectory.json` | per **step**, not per call | yes | **no** | yes | rejected, see below |
| SWE-bench `experiments` `.traj` (public S3) | yes | no | yes | episode-level only | episode-level only | no |
| `nebius/SWE-agent-trajectories` (80k trajectories) | text blobs | no | no | no | no | no |
| `SWE-bench/SWE-smith-trajectories` (5k) | text blobs | no | no | task-level | no | no |
| JetBrains SWE-bench trajectories | text blobs | no | no | task-level | no | no |
| τ-bench `historical_trajectories` (800) | `{role, content}` | no | no | task reward only | cost in $, not tokens | no |
| Mind2Web | per-step actions | no | text only | no | no | no |
| AgentGym / AgentTrek / DCAgent terminus-2 | ShareGPT-style | no | no | no | no | no |
| Aider benchmark | **nothing published** — results land in an unpublished local dir; only aggregate YAML ships | — | — | — | — | no |
| HAL leaderboard traces (`agent-evals/hal_traces`) | **`.json.encrypted`** | — | — | — | — | no |
| LangSmith / Weave / Braintrust public traces | none found; LangSmith requires an account | — | — | — | — | no |

Two entries deserve their reasons stated rather than a cell in a table.

**Terminal-Bench 2.0 was the most promising rejection.** It publishes ~121 GB of real
submissions from dozens of agent/model combinations with per-step ISO timestamps and
per-step token counts. It was dropped on two grounds, both measured in a downloaded
`trajectory.json` (schema `ATIF-v1.6`): its steps carry **no error signal of any kind**
— a `terminus-2` step is keystrokes into a terminal, and the observation is raw screen
text with no status field — and its timestamp gap is the whole agent turn (model latency
plus tool execution), not tool duration. Findings 1 and 3 both need an error flag.
Forcing them onto this corpus would have meant inventing one.

**Not checked, and flagged as unchecked rather than absent:** official AgentBench (THUDM)
raw logs, OpenAI Evals / Anthropic published eval artifacts, W&B Weave and Braintrust
public projects.

**The gap worth naming:** there is **no public corpus of real production agent sessions
at all.** Everything usable is benchmark output. The original study's corpus is, as far
as this survey found, of a kind that does not exist publicly — which is both why it was
worth collecting and why this replication cannot fully close its limitation.

---

## 2. The corpora, and how far apart they are

| | Original | Public |
|---|---|---|
| Source | one developer's Claude Code sessions | OpenHands CodeActAgent, SWE-bench Lite test |
| Tool calls | 85,104 | 94,059 |
| Runs | 1,854 | 3,895 |
| Operators | 1 | 0 — fully headless |
| Models | 5 (all Anthropic) | 13 (Anthropic, OpenAI, Meta, DeepSeek, Alibaba, Google) |
| Distinct tools | 64 | 3 (`run`, `run_ipython`, `browse_interactive`) |
| Task scoping | open-ended, human-directed, multi-day | one bug per run, 30 or 100 step cap |
| Ground truth | **none** | **SWE-bench verdict on 2,253 runs** |
| Median tool duration | 1,262 ms | 275 ms |
| Longest tool call | 1,758.8 min | 24.2 min |

These are not the same thing and the differences are load-bearing, not footnotes:

- **The step cap is a different world.** A benchmark run is stopped at 30 or 100
  iterations. 42% of these runs ended by hitting that cap or by the harness's own
  stuck-detector, versus a corpus where the operator decides when a session ends —
  and, as `FINDINGS.md` says, may intervene invisibly early.
- **The tail is truncated by construction.** The original corpus contains a 29-hour
  `Bash` call. The longest call anywhere in the public corpus is 24 minutes, and
  99% of calls finish in 7.5 seconds. Finding 1 is a claim about a tail that the
  benchmark harness does not permit to exist.
- **No human means no human-wait.** 4.3% of the original's ≥60s calls are the agent
  waiting on a person. That category is empty here, which *helps* the comparison.
- **Three tools versus sixty-four.** No `WebSearch`, no subagents, no `SendMessage`.

---

## 3. Finding 1 — elapsed time predicts tool failure

> *Original: 10.21% error at ≥60s vs 3.07% below, 3.3×, z = 21.9, p ≈ 1.5e-106.*

| | ≥60s | <60s | Enrichment | Test |
|---|---|---|---|---|
| Original | **10.21%** [9.20–11.32] (322/3,153) | **3.07%** [2.95–3.19] (2,514/81,913) | 3.33× | z = 21.93, p = 1.5e-106 |
| Public | **40.87%** [34.41–47.65] (85/208) | **30.69%** [30.39–30.98] (28,801/93,851) | 1.33× | z = 3.18, **p = 0.0015** |

The sign is the same and the result is significant. It is still reported here as
**directionally replicated but not fairly testable**, for three reasons stated in
preference to a cleaner-sounding verdict:

1. **The tail barely exists.** 208 calls out of 94,059 reach 60 seconds — 0.22%, against
   3.71% in the original. The harness caps command execution; p99 is 7.5 seconds.
2. **The effect is much weaker where it can be measured.** 1.33× against 3.33×.
3. **It does not survive the sensitivity check.** Restricted to shell calls, where every
   error is a real process exit code and none is inferred from output text, the
   enrichment falls to **1.05× (41.54% vs 39.58%, p = 0.58)** — indistinguishable.

There is also a mechanism worth naming that cuts *against* the original's reading. In
this harness a long-running command is frequently long *because* it is about to be
killed by a timeout, and the timeout is itself recorded as a non-zero exit. Some of the
"slow calls fail more" signal here is the harness's own timeout policy showing up twice.
The original corpus has no such cap, so its 3.3× is not explained this way — but nothing
in the public data corroborates it either.

**Verdict: cannot be confirmed or refuted externally.** Testing it needs production
traces with an untruncated tail, which no public corpus provides.

---

## 4. Finding 2 — no context-pressure effect

> *Original: z = −2.33, p = 0.020, a weak trend running opposite to the folk claim,
> dying under stratification.*

| | Joined calls | Unstratified trend |
|---|---|---|
| Original | 25,199 (13 bins) | z = **−2.33**, p = 0.020 |
| Public | 47,545 (6 bins) | z = **−10.80**, p = 3.4e-27 |

Error rate by context bin:

| | 0–25k | 25–50k | 50–75k | 75–100k | 100–125k | 125–150k | 150–175k |
|---|---|---|---|---|---|---|---|
| Original | 1.6% | 2.5% | 3.6% | 3.1% | 2.9% | 2.7% | 3.2% |
| Public | 30.7% | 29.5% | 25.5% | 22.2% | 22.5% | 24.4% | 19.6% |

**The folk claim fails in both corpora.** In neither does the error rate climb as the
context window fills; in both the fitted trend points the other way, and in the public
corpus it does so across nearly twice as many calls with 25 orders of magnitude more
confidence. This is the finding that replicates cleanly, and it is the one the study
called its most solidly-powered.

Two honest complications, both of which the public data can see and the original cannot:

**Stratification splits, it does not simply survive.** The original's effect vanished
inside its two largest tools. Here, inside single tools:

| Tool | n | Trend |
|---|---|---|
| `run_ipython` (edits, cells) | 28,528 | z = **−15.97**, p = 2.0e-57 |
| `run` (shell) | 19,017 | z = **+3.42**, p = 0.00063 |

So one of the two tools *does* show failures rising with context. But its bin curve is
**not monotone** — 32.1% → 37.0% → 38.2% → 32.3% → 30.0% — it humps at 50–75k and then
falls. A linear trend test is a poor summary of a hump, and the positive z is a fitting
artefact of the bins' weights more than a real gradient.

**Both corpora hump in the same place.** The original also climbs over its first three
bins (1.6% → 2.5% → 3.6%, a 2.25× rise) before flattening. That shared shape — errors
rising over roughly the first 50–75k of context, then falling or flattening — is more
interesting than either corpus's overall sign, and neither study is powered to say
whether it is a real effect or a shift in what the agent is doing at that stage.

**Verdict: replicates.** The claim "agent tool failures increase as the context window
fills" is not supported in either corpus. The claim "there is *no* relationship" is
weaker than the aggregate trend statistic makes it look, in both.

**A correction to the original fell out of this.** `FINDINGS.md` stated that 81,979 of
85,104 calls join to a context size. They do not: **25,199 (29.6%) do**, and the other
59,905 reference an `api_call` that is absent from the export. The joinable subset is
also not random — 22.5% of `Bash` calls join against 47.7% of `Read`, and joined calls
carry a *lower* error rate (2.79%) than unjoined ones (3.57%). The direction of the
original result is unaffected; the claim that this was its best-powered finding is not.
`FINDINGS.md` has been corrected. (The public corpus joins 47,545 of 94,059 for a known
and benign reason: eight of the thirteen runs predate per-call token accounting, and
those calls are deliberately emitted unjoinable rather than binned at zero.)

**Compaction remains unanswerable.** The original had 38 events. The public corpus has
none at all — OpenHands does not compact, it errors out (12 runs died on a
`ContextWindowExceededError`). Dropped rather than forced.

---

## 5. Finding 3 — looping barely exists

> *Original: 1.15–2.08% of runs contain a stuck repeat; blind identical retry follows
> 1.76% of errors; adaptive response follows 96.9%.*

| | Original | Public | Test |
|---|---|---|---|
| Calls inside a repeat run | 1.29% – 3.57% | **7.49% – 19.48%** | |
| Runs with a stuck (≥5) run | 1.15% – 2.08% | **11.93% – 25.01%** | |
| Blind identical retry after an error | **1.76%** (50/2,843) | **16.12%** (4,657/28,886) | z = 20.6, p = 6.5e-94 |
| Adaptive next action | 96.94% | 80.10% | |
| Bad ending given a stuck run | 0.00% (0/24) | **75.33%** (733/973) | |
| Bad ending, no stuck run | 1.56% (25/1,601) | 30.48% (889/2,917) | |

**Corpus-wide this is a flat contradiction.** Blind retry is nine times higher. Stuck
runs are ten times more common, and unlike in the original — where the comparison was
too underpowered to say anything — they are here a *strong* predictor of a bad ending.
The study's advice, "you are building a detector for a failure mode that occurs in
1 run in 60", is false for this corpus, where it is closer to 1 in 5.

An independent check corroborates it: OpenHands ships its own stuck-loop detector, and
it fired on **642 runs (16.5%)** entirely independently of the repeat detector used here.

### But the corpus is thirteen models, and they do not agree

| Model run | Calls | Error % | Blind retry % | Stuck runs % (lo–hi) | Finished % |
|---|---|---|---|---|---|
| claude-3-5-sonnet (v2.2) | 7,531 | 14.3 | **0.7** | 0.0 – 2.7 | 92.6 |
| claude-3-5-haiku (v2.1) | 9,334 | 22.3 | **1.2** | 0.3 – 1.0 | 55.5 |
| **claude-3-5-sonnet (v2.1)** | 7,997 | 14.9 | **1.8** | **0.3 – 3.3** | 93.3 |
| claude-3-5-sonnet@20240620 | 6,612 | 27.2 | 6.3 | 0.0 – 30.7 | 65.7 |
| llama-3.2-90b | 5,307 | 33.2 | 8.6 | 5.7 – 26.9 | 67.7 |
| llama-3.1-70b | 5,159 | 37.8 | 9.9 | 3.3 – 11.3 | 78.7 |
| o1-mini | 4,504 | 32.7 | 10.8 | 2.0 – 14.2 | 98.3 |
| deepseek-chat (v2.2) | 8,459 | 28.1 | 12.6 | 27.7 – 30.7 | 24.0 |
| gpt-4o | 7,109 | 29.5 | 13.5 | 11.7 – 36.3 | 34.7 |
| gpt-4o-mini | 6,654 | 40.6 | 13.7 | 13.0 – 27.0 | 36.7 |
| qwen-2.5-72b | 5,632 | 34.4 | 20.1 | 21.7 – 43.7 | 34.3 |
| deepseek-v2.5 | 5,537 | 22.7 | 28.1 | 28.0 – 56.0 | 32.7 |
| llama-3.3-70b | 14,224 | 50.5 | 31.9 | 41.1 – 41.1 | 44.3 |
| *(original corpus, for reference)* | *85,104* | *3.3* | ***1.76*** | ***1.15 – 2.08*** | *78.5* |

**Blind-retry rate spans 0.7% to 31.9% across models inside one harness** — a 45×
range, wider than the gap between the two corpora. And the three runs at the top of
the table are the frontier Claude models, whose numbers are **indistinguishable from
the original corpus**: 1.8% and 0.7% blind retry against 1.76%; 0.3–3.3% stuck runs
against 1.15–2.08%.

That is the answer to the study's own stated weakness. The original corpus ran
Anthropic frontier models throughout. In a different harness, a different workload, a
different prompting style and with no operator present at all, those same models
produce the same numbers. **The low loop rate was measuring the model, not the man.**

What the study got wrong was not the measurement but the scope of the claim. "Agents
do not meaningfully loop" is false. "Frontier models in a tool-use loop do not
meaningfully loop, and weaker ones very much do" holds in both corpora.

### How wide is the shape-collision bracket, really?

The original cannot observe repeats directly — its arguments are stripped to a shape
like `command:s78`, so two different 78-character commands are indistinguishable, and
it reports a bracket instead of a number. **The public corpus has the real arguments,**
so the identical looping analysis can be run twice: once over the study's own lossy
fingerprint, once over a hash of the actual arguments.

| | Calls inside a repeat run |
|---|---|
| Shape lower bound (the study's method) | 7.49% |
| **Exact arguments (ground truth)** | **16.42%** |
| Shape upper bound (the study's method) | 19.48% |

The truth lands **74% of the way** from the lower bound to the upper: the lower bound
understates by 8.9pp, the upper overstates by 3.1pp. So on this corpus the study's
bracket does contain the truth — but the truth sits far nearer the *upper* bound, and
anyone reading `1.29% – 3.57%` as "probably around 1.3%" would be reading it wrong.
This is the first empirical calibration of that bracket, and it argues for quoting the
upper bound as the working estimate.

*(Caveat: the collision rate depends on the argument-length distribution, and a corpus
with three tools has more shape collisions than one with sixty-four. This calibrates
the method, not the original's specific numbers.)*

---

## 6. Extension: does any of this predict a *wrong* answer?

`FINDINGS.md` repeats on every result that `completed` means *the run finished*, never
*the run was right*, and that there is no ground truth anywhere in its corpus. SWE-bench
scores each run against the repository's own tests. 2,253 of the 3,895 runs carry a
verdict; 33.16% [31.24–35.13] resolved their bug.

| Runs that… | Resolved | Test |
|---|---|---|
| contain a stuck repeat run | **14.43%** [11.63–17.76] (73/506) | z = −10.16, **p = 2.9e-24** |
| contain no stuck repeat run | 38.58% [36.33–40.89] (674/1,747) | |
| were flagged looping by the harness | **6.87%** [4.96–9.45] (34/495) | z = −14.06, **p = 6.3e-45** |
| were not | 40.56% [38.29–42.87] (713/1,758) | |
| contain ≥1 tool error | 32.19% [30.14–34.31] (618/1,920) | z = −2.34, p = 0.019 |
| contain no tool error | 38.74% [33.66–44.07] (129/333) | |

**A stuck repeat cuts the chance of a correct answer by 2.7×; a harness-flagged loop by
6×. A tool error barely matters** — 32% versus 39%, at p = 0.019 uncorrected, consistent
with the original's finding that error handling is not where runs die.

This makes the study's advice conditional rather than wrong. Loop detection is not worth
building for a frontier-model workload, where the phenomenon is 1 run in 60. It is worth
building for a mixed-model one, where it is 1 in 5 and each occurrence costs most of the
run's chance of being right.

---

## 7. Threats to this comparison

- **The public corpus is a benchmark.** Short, single-goal, step-capped, no human.
  Every divergence has this as a candidate explanation, and for Finding 1 it is almost
  certainly the whole explanation.
- **Two of the three findings rest partly on an inferred error flag.** The editor tools
  have no status field; failures are read off the observation body with an enumerated
  marker list (`EDITOR_ERROR_MARKERS`). Every marker's hits are counted in the export
  manifest, and a shell-only sensitivity corpus — where every error is a real exit code
  — is reported alongside. Finding 3 gets *stronger* under it (blind retry 48%), Finding 2
  flips sign, Finding 1 dies.
- **Model era.** These runs are from late 2024 and early 2025; the original corpus is
  mid-2026. Some of the 13-model spread is vintage, not architecture.
- **Not the same tools.** Three versus sixty-four, and no tool is literally shared.
  A `run_ipython` edit is not a Claude Code `Edit`.
- **`end_status` is inferred, and its labels do not line up.** The harness records
  hitting the step cap as an *error*, so those runs land in `failed`, not `killed`;
  `killed` never occurs in this corpus. `failed` here therefore means "stopped by the
  harness" (913 step-cap, 675 stuck-detector, 12 context-window, the rest crashes) and
  not the study's "the run reported failure". `completed` means the agent called
  `finish` — still not a claim that its work was right, which is why §6 exists.
- **Adapter risk is real, and one instance of it was caught.** Eight of the thirteen
  runs store history as `[action, observation]` pairs rather than a flat list. The first
  version of the adapter silently skipped them, leaving 2,398 of 3,895 runs with zero
  tool calls and every headline quietly computed from the five newest runs. It raised
  nothing; it was caught by noticing that `streams_with_tool_calls` was 1,497 when the
  corpus had 3,895 streams. `tests/test_adapter_openhands.py` pins it now, but the
  general point stands: an adapter fails quietly, and every number here depends on one.
- **Multiple comparisons are uncorrected**, as in the original.

---

## 8. Verdict on generality

**The study may now claim more than one operator, and must still claim less than
"agents".**

What is now defensible:

- **Finding 2 generalises.** The context-pressure claim it contradicts is contradicted
  in a second corpus, a different harness, and thirteen models — with far more power.
  This no longer needs an operator caveat.
- **Finding 3 generalises with its scope corrected.** The low loop rate is a property
  of the models, not the operator: frontier Claude models reproduce it to within noise
  in a headless harness. Stated as a claim about *agents in general* it is false, and
  the public data would have embarrassed anyone who said so.
- **Finding 1 remains scoped to the original corpus.** No public data can currently
  test it, because no public corpus has an untruncated tail.

What has *not* been closed: every corpus available is a benchmark. Nothing here speaks
to open-ended, human-directed, multi-day production sessions except the original itself.
The `n = 1 operator` limitation is narrowed — the findings are not artefacts of one
person's prompting — but `n = 1 production corpus` stands, and will until somebody
publishes real session telemetry.

**Concretely, what would close it:** an export of production agent sessions from a
second operator or organisation carrying, per tool call, a start and end timestamp, the
tool name, a success/failure flag, and the issuing model call's input-token count. That
is four fields. The study's own export format is one such schema and is already
content-stripped for privacy. Nothing in the public landscape provides it today.
