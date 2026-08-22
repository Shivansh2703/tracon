# tracon

> A TRACON doesn't fly the planes — it decides who goes when.

**Dependency- and session-aware scheduling for agentic LLM workloads — and the
measurement it is built on.**

Conventional serving schedulers treat requests as independent one-shot inferences.
Agent workloads aren't: they are dependency graphs with sessions, and tool
execution — not GPU time — dominates end-to-end latency. One slow tool call
head-of-line-blocks everything behind it, and a session's context has locality
that schedulers currently ignore.

None of that is arguable from first principles, so tracon measures it first.
One command exports your own agent transcripts into a content-free trace, and
everything else — the diagnosis, the failure study, the regression gate and the
scheduler simulation — reads that same export.

## Three questions, one export

```sh
tracon export                     # your transcripts -> a content-free trace export
```

| | question it answers | |
|---|---|---|
| `tracon doctor` | **what happened** in this corpus, against published base rates | zero-config; no export needed |
| `tracon study` | **why agent runs fail** — 85,104 real tool calls, six questions, three of them negative | [the study](docs/study.md) |
| `tracon over-time` | **is it getting worse**, and which seat is responsible | [movement + a CI gate](docs/over-time.md) |

`doctor` gives you today's numbers. `study` is the empirical base rate they are
read against. `over-time` says whether today is worse than last month, and
exits non-zero when a number genuinely regressed.

**Everything runs locally and makes no network calls** — not optionally, not
behind a flag. The export is content-free by construction: shapes, sizes, ids
and timings survive capture; prompts, tool arguments, paths and outputs do not.
`tracon doctor --share` writes a statistics-only aggregate to a file and prints
it before you read it; nothing is ever sent.

## The scheduler

tracon schedules the graph instead of the request:

- **Trace-driven** — built from real coding-agent traces captured on a live
  multi-agent development machine, not synthetic workloads.
- **Dependency-aware** — knows which requests block which, and protects the
  critical path.
- **Session/context-aware** — models context locality: keeping an agent's
  requests where its context is warm, and the cost of moving or rebuilding it.
- **Measured** — every policy is evaluated in a trace-driven discrete-event
  simulation against a FIFO + dynamic-batching baseline. The comparison is the
  result; methodology and hardware stated with every number.

## Status

1. ~~Offline trace exporter~~ — done (payload-stripped: timing and structure
   survive, content doesn't; `tracon export`)
2. ~~Workload characterization~~ — done (`tracon characterize`;
   [findings](docs/characterization.md): 79% of busy time is tool execution,
   3.7% of calls hold 75% of tool time, 74% of prompts arrive while busy,
   median model call reads 98.9% of input from cache)
3. ~~Simulator + FIFO/dynamic-batching baseline~~ — done (`tracon simulate`;
   [model + validation](docs/simulator.md): trace replay reproduces observed
   turn latency with 0.0% median / 0.1% p90 error at infinite capacity)
4. ~~Scheduler policies (compiled core) + measured comparison~~ — done
   (`tracon sweep`; [core, policies, results](docs/scheduler.md): at 16x
   replicated load the dependency+context-aware `tracon` policy cuts p95 turn
   latency vs FIFO with no oracle knowledge; oracle-SJF bounds the size-based
   win at −58% p95; full parity + determinism gates)
5. ~~Diagnosis, failure study and the over-time gate~~ — done (`tracon doctor`,
   `tracon study`, `tracon over-time`; the study replicates on an independent
   94,059-call public corpus — [what survived](docs/study-replication.md))

## Stack

Python for traces, simulation, and analysis. The scheduling decision core is
C++ (`core/`, one kernel header) compiled twice: a pybind11 module the
simulator calls in-process, and a Go gRPC service (`go/`) via cgo — identical
decisions on both transports, verified end-to-end. Measured per-decision cost:
1–52µs in-process, 215–417µs over localhost gRPC by queue depth
([method + caveats](docs/scheduler.md)).
