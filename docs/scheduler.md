# The scheduler: compiled core, policies, measured comparison

> **Correction — the −36% p95 headline below is withdrawn.**
>
> A later replication found the policy advantage is **not reproducible under its own
> replication seed**. Re-running the same configuration across seeds spread the result
> from −14% to −39% (sd ≈ 12 points), and a capacity sweep produced 0% median Δp95 —
> the effect is seed noise, not a measured latency win.
>
> The mechanism claims in this document still hold: the warm-rate and ordering effects
> are real and reproducible. The **percentage latency figures are not**.
> Do not quote −36%, or any percentage, as a latency result.

Milestone 4. The decision core is C++ compiled twice from one header
(`core/src/kernels.hpp`): as a pybind11 module (`tracon_core`) the simulator
calls in-process, and into the Go gRPC service (`go/cmd/traconsvc`) via cgo.
Both transports make identical decisions by construction, and full-simulation
parity between them is a standing test (`tests/test_grpc_seam.py`).

```
sim (Python)                              one kernel header, two transports
┌──────────────────────────┐   pybind11   ┌──────────────────────┐
│ runner → server          │◄────────────►│ tracon_core (C++)    │
│   policy.select(queue,k) │  RequestView │   kernels.hpp        │
└──────────────────────────┘   in, k out  └──────────┬───────────┘
                                               cgo   │ same decisions
                                          ┌──────────▼───────────┐
                                          │ traconsvc (Go gRPC)  │
                                          │   Select() RPC       │
                                          └──────────────────────┘
```

Plain data crosses every seam — `RequestView` (ids, times, waiter count, warm
bit) in, queue positions out. Adapters never reorder or filter; selection logic
exists only in the kernels. Every policy also has a Python prototype, and
selection-level + full-simulation parity between prototype and kernel is tested
on randomized queues and on the full trace corpus.

## Policies

| policy | orders by | reads oracle? |
|---|---|---|
| `fifo` | ready time (the baseline a dynamic-batching front end runs) | no |
| `sjf` | traced service time | **yes — labeled oracle**; the clairvoyant upper bound for size-based ordering |
| `unblock` | blocked-waiter count (dependency-aware) | no |
| `affinity` | context warmth on a free executor (session-aware) | no |
| `tracon` | waiters first, warmth second, FIFO last — the flagship | no |

All non-FIFO policies carry the same starvation guard: any request waiting
≥ 60s jumps the line oldest-first. The guard is a backstop sized above the
baseline's p95 queue wait at native load (11.9s); a tight guard collapses every
priority policy back into FIFO (a bug the parity suite caught in development).

**The two signals.** *Waiters*: the runner counts chains provably blocked on a
request's chain — a same-stream next turn whose arrival already fired (74% of
real prompts arrive while the agent is busy), and a parent gated on a sync
spawn. Counts are read live at selection time, not snapshotted at submit;
direct edges only, no transitive closure. *Warmth*: the backend gives each
executor an LRU of `resident_streams` contexts; a stream is warm if resident on
a currently-free executor. Serving a cold stream adds `cold_penalty_ms` to its
service time — a **sensitivity parameter, not a measured constant** (grounded
qualitatively in the characterization finding that the median model call reads
98.9% of its input from cache; we do not invent a per-token reload rate). With
penalty 0 the backend reproduces the milestone-3 model exactly, byte for byte.

## Load methodology

Time compression stresses intra-session self-gating, not the server
(milestone-3 finding), so load scales by **workload replication**: R copies of
the full month as independent sessions, each rigidly phase-shifted by a
deterministic offset drawn uniformly over the trace span (fixed seed; re-runs
byte-identical). Offsets don't wrap, so R replicas spread over up to 2× the
span and raise offered load by ~R/2 — utilization is reported per row rather
than inferred from R. Chains, gaps, and spawn structure are untouched: only
concurrency multiplies, the way a serving fleet actually experiences it.

## Results — ordering under contention

Single executor, dynamic batching (batch 8 / 10ms), no cold penalty. Turn
latency in seconds; every row completes all turns.

| load | policy | p50 | p95 | p99 | queue p95 | util |
|---|---|---|---|---|---|---|
| 1x | fifo | 148.3s | 1,579.6s | 5,446.2s | 11.9s | 0.084 |
| 1x | core-sjf | 148.1s | 1,579.6s | 5,446.2s | 12.0s | 0.084 |
| 1x | core-unblock | 148.0s | 1,579.6s | 5,446.2s | 11.9s | 0.084 |
| 1x | core-tracon | 148.1s | 1,579.6s | 5,446.2s | 12.0s | 0.084 |
| 8x | fifo | 310.4s | 3,763.8s | 7,512.4s | 27.7s | 0.309 |
| 8x | core-sjf | 292.5s | 2,886.0s | 6,081.5s | 24.6s | 0.307 |
| 8x | core-unblock | 304.0s | 3,269.4s | 6,396.7s | 28.8s | 0.309 |
| 8x | core-tracon | 306.2s | 3,258.0s | 6,461.2s | 28.5s | 0.309 |
| 16x | fifo | 932.3s | 21,587.6s | 46,991.0s | 126.2s | 0.531 |
| 16x | core-sjf | 584.3s | 9,118.7s | 24,161.9s | 79.3s | 0.519 |
| 16x | core-unblock | 841.4s | 17,504.9s | 38,239.1s | 134.4s | 0.530 |
| 16x | core-tracon | 842.1s | 17,574.8s | 38,353.0s | 132.9s | 0.530 |

At native load (1x) the machine averages 8% of one executor — ordering cannot
matter, and doesn't. Under replicated load the story is the tail: at 16x,
oracle-SJF cuts p50 by 37% and p95 by 58% — the clairvoyant bound for
size-based ordering. Dependency awareness alone (`unblock`, and `tracon`
without a cold penalty to exploit) takes p95 down 19% with no oracle
knowledge, purely by serving provably-blocking work first.

## Results — context affinity

2 executors, 32x load, `resident_streams` 64 per executor, cold penalty swept.
`sjf` shown as the oracle reference.

| penalty | policy | p50 | p95 | p99 | queue p95 | util | warm |
|---|---|---|---|---|---|---|---|
| 0 | fifo | 372.4s | 5,577.8s | 14,533.6s | 35.4s | 0.564 | 92% |
| 0 | core-sjf | 262.5s | 2,376.7s | 5,862.0s | 15.2s | 0.556 | 95% |
| 0 | core-affinity | 371.0s | 5,329.0s | 14,522.7s | 35.7s | 0.564 | 95% |
| 0 | core-tracon | 348.7s | 3,892.1s | 9,973.3s | 44.5s | 0.564 | 94% |
| 2s | fifo | 413.7s | 8,118.8s | 22,495.4s | 53.0s | 0.575 | 90% |
| 2s | core-sjf | 284.1s | 3,068.8s | 8,147.6s | 17.0s | 0.566 | 94% |
| 2s | core-affinity | 393.0s | 6,459.9s | 18,177.2s | 44.4s | 0.573 | 94% |
| 2s | core-tracon | 378.4s | 5,209.6s | 16,372.5s | 63.9s | 0.574 | 92% |
| 10s | fifo | 84,072.9s | 1,151,433.8s | 1,812,497.6s | 3,508.0s | 0.759 | 23% |
| 10s | core-sjf | 73,564.2s | 1,098,679.2s | 1,728,135.5s | 3,372.6s | 0.749 | 27% |
| 10s | core-affinity | 71,977.5s | 1,087,623.3s | 1,713,951.0s | 3,355.6s | 0.749 | 27% |
| 10s | core-tracon | 74,249.3s | 1,101,814.5s | 1,734,424.4s | 3,372.3s | 0.751 | 26% |

Four regimes, all measured: with **no penalty**, warmth is free so `affinity`
barely moves the needle, while `tracon`'s dependency term already cuts p95 by
30% — pure ordering. With the cache **thrashing** (resident 4 vs hundreds of
active streams — the 1-executor sweeps), selection order can't preserve
residency and warm rates pin near 16% for every policy. In the regime real
prefix-cache fleets target, **cache ≈ working set with a real reload cost**,
warm-first selection preserves residency FIFO squanders: at a 2s penalty
`affinity` lifts the warm rate 90→94% and cuts p95 by 20%, and `tracon`
compounds dependency + session awareness to **−36% p95 / −27% p99 vs FIFO**
with no oracle knowledge. Oracle-SJF stays the upper bound at −62% p95.
(**Withdrawn — see the correction at the top of this document. These percentages do
not reproduce across replication seeds and should not be quoted.**) And at
a 10s penalty this configuration is **past saturation**: reload work exceeds
spare capacity, queues grow without bound over the trace window (p50 in the
tens of thousands of seconds), residency churns until warm rates collapse to
~25%, and every policy compresses to within a few percent of FIFO — past the
stability point, scheduling cannot rescue an over-committed fleet; capacity
can. Reported as measured; the interesting operating regimes are the first
three.

## Seam overhead

Selection cost for the `tracon` kernel, median/p95 µs per call over 2,000
iterations per depth (Apple M2, 8 cores, 16 GB; localhost gRPC):

| queue depth | pybind11 µs/call (p50/p95) | gRPC µs/call (p50/p95) |
|---|---|---|
| 10 | 0.9 / 1.0 | 215.1 / 380.9 |
| 64 | 3.3 / 3.5 | 236.0 / 406.8 |
| 256 | 12.7 / 19.5 | 252.6 / 450.7 |
| 1024 | 52.1 / 56.2 | 416.7 / 632.3 |

Per-decision cost is small against the 10ms batching window at these depths on
localhost; the numbers above are what the benchmark measures and nothing more.
The DES does not charge real RPC time to simulated time, and a non-local or
contended network changes the picture — deploying out-of-process means paying
the measured per-call cost on every dispatch.
Regenerate: `go/bin/traconsvc &` then `uv run python scripts/bench_seam.py`.

## Gates

What the checked-in suite enforces on every run:

- **Parity**: Python prototype == C++ kernel for all five policies on 300
  randomized queues per run, and prototype == kernel == gRPC transport over
  full simulations of synthetic contended fixtures. The gRPC gate builds the
  Go service on demand — a broken build fails the suite (it skips only when no
  Go toolchain is installed).
- **Determinism**: repeated full simulations byte-identical (synthetic
  fixtures; `core-sjf`, `core-tracon`, and the gRPC path).

What was additionally measured on the full 30-day corpus for this milestone
(one-off runs, commands in this doc; deterministic to re-run):

- **Fidelity**: validation-mode replay reproduces traced turn latency at 0.0%
  median / 0.1% p90 error after all milestone-4 backend changes.
- **Full-corpus parity**: `fifo` == `core-fifo`, `sjf` == `core-sjf`, and
  `unblock` == `core-unblock` produce identical result JSON modulo the policy
  name; `core-sjf` re-runs byte-identical (shasum).
- **M3 equivalence**: with penalty 0, the milestone-4 backend's results equal
  the pre-affinity backend's on the full corpus after excluding the fields
  that did not exist before (`cold_penalty_ms`, `resident_streams`,
  `context`).

## Limitations

Service times stay exogenous (no batch-size effect on latency); the cold
penalty is uniform per serve rather than proportional to context length;
waiter counting stops at direct edges (no transitive closure through spawn
trees); replication multiplies one user's workload rather than sampling a
population. A batch executes on a single executor, so a mixed-stream batch
whose members are warm on *different* executors still pays cold penalties for
the minority — warmth at selection time is optimistic for mixed batches (the
behavior is pinned in `tests/test_affinity.py`). The affinity result is
conditional on cache ≈ working set — stated as such above, with the thrash
regime reported alongside.

## Reproduce

The raw result JSONs behind every table row are checked in under
`docs/results/` (aggregates only — traces never leave the machine). Regenerate:

```
tracon export
tracon sweep traces/export-<date> --policies fifo,core-sjf,core-unblock,core-tracon \
    --replicates 1,8,16 --out docs/results/m4-ordering.json
tracon sweep traces/export-<date> --policies fifo,core-sjf,core-affinity,core-tracon \
    --replicates 32 --executors 2 --resident 64 --cold-penalty 2000 \
    --out docs/results/m4-affinity-p2000.json   # likewise --cold-penalty 0 / 10000
```

Hardware for all numbers: Apple M2, 8 cores, 16 GB, macOS; single-threaded
simulation; ~4s per 1x run, ~90s per 32x run.
