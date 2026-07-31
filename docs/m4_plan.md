# Milestone 4 build plan — scheduler policies + measured comparison

Supersedes `owner_todos.md` (the owner-implements ladder): per the 2026-07-30 late
directive, the session builds everything. The technical ladder is unchanged — it is
now the build order. Goal: the headline result — dependency- and session-aware
scheduling vs the FIFO + dynamic-batching baseline, measured on the real traces.

## The seam, in one picture

```
sim (Python)                              compiled core
┌──────────────────────────┐   pybind11   ┌──────────────────────┐
│ runner → server          │◄────────────►│ tracon_core (C++)    │
│   policy.select(queue,k) │  RequestView │   select() → indices │
└──────────────────────────┘   in, k out  └──────────┬───────────┘
                                                     │ same decision core (C ABI)
                                          ┌──────────▼───────────┐
                                          │ Go gRPC service      │
                                          │   Select() RPC       │
                                          └──────────────────────┘
```

Plain data crosses the boundary (`RequestView`: ids and times), object graphs don't.
Selection logic lives only in the core; the Python adapter never reorders or filters.
Every policy exists twice — Python prototype (golden behavior) and C++ port — and
parity between the two is a standing test, as is byte-identical determinism.

## Phases

- **A — C++ seam + classic policies.** `core/` workspace member (scikit-build-core +
  pybind11) building `tracon_core`: stable-argsort FIFO, `RequestView`, oracle-SJF
  with a starvation guard. Python prototypes + `core-*` adapters registered in
  `make_policy`. Gates: `fifo` vs `core-fifo` byte-identical modulo policy name on
  the real export; selection-level parity on randomized queues; determinism.
- **B — dependency-aware policy.** The runner starts counting *blocked waiters* per
  chain (a queued next turn that already arrived; a parent blocked on a sync spawn).
  `unblock` policy: serve the request whose completion unblocks the most waiting
  work. Direct counts only (no transitive closure) — documented limitation.
- **C — load harness.** Workload replication with deterministic phase offsets (the
  M3 methodology finding: time compression stresses intra-session self-gating, not
  the server). R replicas, stream keys namespaced, arrivals offset; sweep runner
  producing the comparison tables.
- **D — session/context-affinity.** Executors gain identity + a resident-stream set
  (LRU); serving a stream on an executor where its context is cold adds a penalty
  swept as a stated parameter (grounded qualitatively in the 98.9%-cached finding —
  we do not invent a per-token number). Affinity-aware selection/placement; with
  penalty 0 the server must reproduce M3 exactly (the fidelity gate stands).
- **E — Go gRPC service.** C ABI (`extern "C"`, no STL across), shared-lib target;
  Go server via cgo; `Select` RPC; Python client policy; end-to-end parity vs the
  pybind11 path + measured localhost RPC overhead.
- **F — the comparison.** Policy × load-multiplier sweep, tables with p50/p95/p99
  turn latency + queue waits + utilization, methodology and hardware stated, docs
  updated, codex review, milestone commit.

## Standing gates (every phase)

- Full suite green; ruff + format + (no new) ty diagnostics.
- Byte-identical re-runs (`shasum` on results JSON).
- Fidelity: validation mode (`executors=inf`, compress 1.0, penalty 0) stays at
  0.0% median / 0.1% p90 error vs traced latency.
- Claim discipline: every number in docs measured, hardware + methodology stated.
