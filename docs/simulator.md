# Trace-driven simulation: model, validation, baseline

`tracon simulate` replays the exported traces through a discrete-event simulation of
an LLM serving backend, so scheduling policies can be compared on identical, real
workloads. All numbers below are from the 2026-07-30 export (231 sessions, 1,649
agent runs, 30 days; see [characterization](characterization.md)).

## Model

- **Turn** — the schedulable job: a prompt arrival (or agent spawn) followed by the
  traced chain of model steps. Each step occupies the backend for its traced service
  time, then launches the tool calls it issued; the next step is ready when they
  join. Main-stream turns release at traced arrival times and serialize within
  their session; seat-agent streams split into a spawn turn plus continuation turns
  at injected-prompt boundaries.
- **Backend** — Triton-style dynamic batching: requests queue when ready; an
  executor takes a batch at `max_batch` or when the oldest request has waited
  `max_wait`; the batch occupies it for the max member service time. `executors`,
  `max_batch`, `max_wait` are the capacity knobs; `inf` executors = validation mode.
- **Tools** — exogenous delays with traced durations. Agent spawns instead release
  a child job: a sync spawn gates its parent tool on the child's first-turn
  completion; a background spawn only consumes backend capacity. Spawns whose
  traced parent wait is far shorter than the child's chain (async launches that
  don't set `run_in_background`) are reclassified background — the trace is ground
  truth for whether the parent waited.
- **Gaps** — traced client-side dead time between steps (permission-prompt waits,
  API retry/backoff, machine asleep) replays as exogenous delay. Without this the
  replay runs ~3x faster than reality; no scheduling policy can compress it, so it
  is workload, not slack.

## Validation (the gate for every later comparison)

At infinite capacity and native timing, simulated turn latency must reproduce the
traced latency. Result over 2,489 turns: **median absolute relative error 0.0%,
p90 0.1%**. Three modeling errors were found and fixed by this gate — missing
inter-step gaps (replay 3x too fast), seat-agent lifetimes gating their spawn
(25,000% tail error), and de-facto background launches treated as sync. The
residual is the modeling-error floor under any policy delta reported later.

## FIFO + dynamic batching baseline (native load)

| executors | turn p50 | turn p95 | queue-wait p95 | utilization | mean batch |
|---|---|---|---|---|---|
| inf | 114.6s | 1,411s | 0 | — | 1.0 |
| 4 | 114.9s | 1,413s | 0.01s | 2.2% | 1.01 |
| 2 | 115.2s | 1,439s | 0.50s | 4.4% | 1.03 |
| 1 | 148.3s | 1,580s | 11.9s | 8.4% | 1.14 |

One month of single-machine traces averages well under one executor of demand —
contention at native load is real but mild (p50 +29% on one executor), concentrated
in multi-agent bursts.

## The load knob, and a finding

Time compression (denser arrivals, unchanged chains) mostly stresses **intra-session
self-gating**, not the server: at 10x, queue-wait p95 is 85s while turn p50 grows
24x (148s → 3,612s on one executor) — turns queue behind their own session's
previous turn, not behind other sessions' work. That mirrors the
characterization finding that 74% of prompts arrive while the agent is busy, but it
makes compression the wrong knob for backend contention. The policy comparison
(milestone 4) will scale load by **replicating the workload with phase offsets**,
which multiplies concurrent independent sessions the way a serving fleet actually
experiences them; compression stays as a secondary, documented knob.

## Limitations

Service times are exogenous (no batch-size effect on latency, no token-level cost
model); tool durations don't change under contention; the backend is slot-based,
not KV-cache-aware — context affinity costs enter with the milestone-4 policies.
Events sharing an exact timestamp process in registration order, so a request
becoming ready precisely at a batch deadline may land in either batch — a
millisecond-scale tie-break semantic, deterministic per run. The sim package was
independently reviewed (8 findings: 1 high, 4 medium, 2 low fixed with regression
tests; the tie-break noted here accepted as-is). Hardware for all runs: Apple M2,
8 cores, 16 GB (simulation wall-clock ~4s per run; determinism verified by
byte-identical re-runs).
