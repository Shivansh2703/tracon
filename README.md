# tracon

> A TRACON doesn't fly the planes — it decides who goes when.

**Dependency- and session-aware scheduling for agentic LLM workloads.**

Conventional serving schedulers treat requests as independent one-shot inferences.
Agent workloads aren't: they are dependency graphs with sessions, and tool
execution — not GPU time — dominates end-to-end latency. One slow tool call
head-of-line-blocks everything behind it, and a session's context has locality
that schedulers currently ignore.

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

Early. Build order:

1. ~~Offline trace exporter~~ — done (payload-stripped: timing and structure
   survive, content doesn't; `tracon export`)
2. Workload characterization of the exported traces
3. Simulator + FIFO/dynamic-batching baseline (Python)
4. Scheduler policies (compiled core) + measured comparison

## Stack

Python for traces, simulation, and analysis; compiled core for the scheduler
hot path.
