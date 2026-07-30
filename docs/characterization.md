# Characterizing a real agentic coding workload

**Corpus:** every Claude Code transcript produced on one active development machine
(Apple M2, 8 cores, 16 GB, macOS) over 30 days of daily multi-agent work — 231
interactive sessions, 1,626 subagent runs, ~339k transcript lines spanning 24 Claude
Code releases (2.1.195–2.1.220). Traces were extracted with `tracon export`
(payload-stripped: timing, structure, ids, and token counts survive; no message
content, tool arguments, results, or file paths do) and analyzed with
`tracon characterize`. Every number below is computed from the event log; nothing is
sampled or estimated. Figures cite the 2026-07-30 export; regenerate with the two
commands above.

## Findings

**1. The model is not the bottleneck — tool execution is.**
Across 85k completed tool calls, tool execution accounts for 246 hours against 64
hours of model streaming: **79% of busy time is spent waiting on tools**, not on the
LLM. A scheduler that optimizes GPU batching alone is optimizing the smaller share.

**2. Tool latency is extremely heavy-tailed.**
The median tool call finishes in 1.3s, but p99 is 2.7 minutes:

| threshold | share of calls | share of tool time |
|---|---|---|
| ≥10s | 8.8% | 86.9% |
| ≥30s | 5.1% | 81.0% |
| ≥60s | **3.7%** | **75.1%** |

This independently reproduces TraceLab's published finding (arXiv 2606.30560: calls
over one minute are 4% of tool calls but 85% of tool-call time) on a completely
separate, personally-generated corpus. Shell commands dominate: Bash is 62% of calls
and 87% of tool time.

**3. Work arrives while the system is busy.**
Users don't wait for idle prompts: **74% of prompts were typed while the agent was
still working** and delivered from the input queue (2,422 of 3,269 arrivals; 6,914
enqueues, of which 3,721 were removed before delivery). Median intra-session prompt
gap is 3 minutes. Head-of-line blocking is therefore directly user-visible: a slow
tool call delays already-queued work.

**4. Execution is overwhelmingly sequential chains, lightly parallel bursts.**
91% of model calls issue at least one tool call, but only 4% of tool-issuing calls
fan out to 2+ parallel tools (max observed fan-out: 10), and only 4% of tool calls
overlap another call in the same stream. The workload is long dependency *chains*
punctuated by occasional fan-out — exactly the structure FIFO schedulers serve worst,
since one slow link stalls the entire chain (SAGA, arXiv 2605.00528, measures 3–8×
end-to-end inflation when chained calls are treated as independent).

**5. Sessions are deeply nested, half-background agent trees.**
76 of 231 sessions spawn subagents (median 10 per spawning session, max 276), with
spawn depth reaching 4. 45% of agents run in the background; **53% of turns end with
background agents still running**, and 1,648 agent-minutes was the longest single
run. Completion notification lag (parent idle-wait after a background agent
finishes) is small — p50 2s, p95 20s.

**6. Context warmth is the norm, and it is enormous.**
Prompt-cache reads are 12.1B tokens against 9.1M uncached input tokens: the median
model call reads **98.9% of its input from cache**. Session context locality is not
a nice-to-have — it is the dominant regime, and any scheduler that moves work away
from its warm context pays for rebuilding nearly the entire input.

## What this implies for the scheduler

The simulator and policies (milestones 3–4) must model, at minimum:

- **Heavy-tailed service times** for tools (log-scale distributions, not means);
- **Dependency chains** as the primary structure, with occasional parallel fan-out;
- **Two agent classes** (foreground sync vs background) with different blocking
  semantics;
- **Arrival-during-service** (queued prompts), so head-of-line blocking is scored
  against work that is already waiting;
- **Context affinity** with a measured cost model for cold-context placement.

## Limitations

Single machine, single user, one CLI agent stack — an unusually agent-heavy workflow
(the dev-team seat system) rather than a population average. Bash aggregates many
underlying activities (builds, tests, git, long-running dev servers) into one tool
name. 325 of 1,626 agents have unknown end status (killed sessions or runs still
open at export time). Durations above ~1 hour are kept as-is; simulation runs should
state their winsorization policy explicitly.
