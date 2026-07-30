# Owner TODOs — milestone 4, the compiled scheduler core

Mode: [m4_mode.md](m4_mode.md). You build the thesis code — C++ core first, then a Go
gRPC wrapper around the same core. This session architects, tutors, and reviews; it
never writes the compiled code. Every TODO is ≤ ~90 focused minutes, one concept,
with a runnable acceptance check so *you* know when you're done. Stuck 30+ minutes →
ask; you get a smaller hint first, a walkthrough second, code only as a last resort.
Your commits get real reviews; findings come back as fix-TODOs.

## The seam, in one picture

```
sim (Python, exists)                      you build
┌──────────────────────────┐   pybind11   ┌──────────────────────┐
│ runner → server          │◄────────────►│ tracon_core (C++)    │
│   policy.select(queue,k) │  RequestView │   select() → indices │
└──────────────────────────┘   in, k out  └──────────┬───────────┘
                                                     │ same decision core
                                          ┌──────────▼───────────┐
                                          │ Go gRPC service      │  phase B
                                          │   Select() RPC       │
                                          └──────────────────────┘
```

The sim's policy protocol is `select(queue: list[Request], k: int) -> list[Request]`
(`src/tracon/sim/policies.py`). The C++ core implements the *decision*: request
descriptors in, selected queue positions out. A thin Python adapter (which you also
write — it is part of the seam) converts between the two. The Go service wraps the
identical core later, so the RPC wraps something real.

Why the decision function is worth compiling: it runs on every dispatch, it must be
deterministic, and in the phase-C comparison it executes millions of times per sweep.
It is also the thesis artifact — the scheduler *is* this function plus its state.

## Ladder

| # | concept | deliverable | status |
|---|---|---|---|
| 1 | toolchain: C++ → importable Python module | `tracon_core` builds via uv; stable-argsort FIFO primitive | tonight |
| 2 | a data contract across a language boundary | `RequestView`, `select()`, `CorePolicy` adapter, `core-fifo` parity | |
| 3 | priority scheduling under heavy tails | oracle-SJF + starvation guard (`core-sjf`) | |
| 4 | stateful policies + estimation | stream table, EWMA estimates (`core-sjf-est`) | |
| 5 | performance claims with methodology | determinism check + selection microbench | |
| — | **C++ MVP done** — comparison can run end-to-end on core policies | | |
| 6 | C as the lingua franca (ABI) | `extern "C"` wrapper + shared-lib target | phase B |
| 7 | cgo | Go module calling the core; golden-file parity | phase B |
| 8 | service definition | proto + gRPC `Select` server | phase B |
| 9 | the full loop | Python gRPC client policy; end-to-end parity + measured RPC overhead | phase B |

Phase B gets sized TODO-by-TODO once phase A lands — sequencing rule from
[m4_mode.md](m4_mode.md): the wrapper must wrap something real.

---

## TODO-1 — toolchain: a C++ module Python can import *(tonight, ~60–90 min)*

**Concept:** how a C++ translation unit becomes a Python extension — pybind11's
module macro, STL type casters, CMake, and a build backend (scikit-build-core) so
`uv sync` compiles it like any other dependency.

**Build:** a new workspace member `core/` producing module `tracon_core` exposing:

- `version() -> str` — any non-empty string, e.g. `"0.1.0"`.
- `select_fifo(ready_ms: list[float], k: int) -> list[int]` — indices of the k
  oldest entries, oldest first, **stable on ties** (equal `ready_ms` → lower index
  first). This is a stable argsort truncated to k — FIFO's decision rule as a pure
  function, and the primitive TODO-2 reuses. `k` larger than the queue returns
  everything; an empty queue returns `[]`.

**Suggested shape** (hints, not prescriptions — your layout choices are yours):

```
core/
  pyproject.toml     # name = "tracon-core"; build backend scikit_build_core
  CMakeLists.txt     # find pybind11; pybind11_add_module(tracon_core src/core.cpp)
  src/core.cpp       # PYBIND11_MODULE(tracon_core, m)
```

plus, in the root `pyproject.toml`: `tracon-core` added to `[project] dependencies`,
a `[tool.uv.workspace]` with `members = ["core"]`, and `[tool.uv.sources]` mapping
`tracon-core = { workspace = true }`.

**Hints**

- Compiler is Xcode CLT clang (`c++ --version` to confirm it's there). C++20.
- Sort *indices*, not values: `std::iota` over `0..n`, then `std::stable_sort` with
  a comparator reading `ready_ms[i]`. ~6 lines. `std::stable_sort` (not `std::sort`)
  is what makes the tie-break rule hold — that determinism is load-bearing for the
  whole project (byte-identical re-runs are the repo's standing gate).
- `#include <pybind11/stl.h>` is what converts `list[float]` ↔ `std::vector<double>`.
  Forgetting it is the classic first error — it fails at *call* time with a
  TypeError, not at build time.
- References: pybind11 docs → "First steps", then "Build systems → Building with
  scikit-build-core" (has a complete minimal example); uv docs → "Workspaces".
- **Fallback** if the uv ↔ scikit-build-core integration fights you past ~30 min:
  build directly (`cmake -S core -B core/build && cmake --build core/build`) and
  copy the produced `.so` into `src/tracon/` so the import works tonight; fold it
  into the workspace properly as step one of TODO-2. The concept of the night is
  the C++-to-Python seam, not packaging archaeology.

**Acceptance** — the test is already in the repo and skips until your module exists:

```
uv run pytest tests/test_core_seam.py -v --no-cov
```

Before you start it reports the file as skipped; done is `4 passed` — and the whole
suite still green (`uv run pytest`). The tests assert: `version()` returns a
non-empty string; `select_fifo` returns oldest-first indices with stable ties on a
hand-checked queue; edge cases (empty queue, k = 0, k > queue length) hold; and on
200 randomized tie-heavy queues the result matches a reference stable argsort
computed in Python. (`--no-cov` because the file alone exercises none of the Python
package and would trip the suite-wide coverage floor.)

---

## TODO-2 — the seam contract: RequestView in, indices out *(~90 min)*

**Concept:** designing a data contract across a language boundary. Plain data
crosses; object graphs don't. The Python `Request` (with its callback and stream
tuple) stays home — the core sees only what a scheduling decision needs.

**Build:**

- C++ `struct RequestView { std::int64_t req; std::int32_t stream; double ready_ms;
  double service_ms; }` — bind it with `py::class_` (constructor + field access).
- `select(const std::vector<RequestView>& queue, int k) -> std::vector<size_t>` —
  returns *queue positions*, FIFO rule, reusing TODO-1's argsort primitive.
- Python `CorePolicy` in `policies.py` implementing the `Policy` protocol: intern
  each `StreamKey` to an int (a plain dict on the adapter), build the views, call
  the core, map returned positions back to `Request` objects. Register it in
  `make_policy` as `core-fifo`.
- Adapter rule (this is the review bar): the adapter never reorders, filters, or
  decides anything. Selection logic lives only in C++ — otherwise parity proves
  nothing about the core.

Design question to settle *before* coding (30 seconds of thought, big consequences):
one bound struct vs four parallel arrays across the boundary. Struct is cleaner and
self-documenting; arrays are faster to marshal. Our queues are small (the M3
baseline dispatches batches of ~1, queue depth rarely exceeds tens), so cleanliness
wins tonight — but know why you chose.

**Acceptance**

- Parity on the real export, byte-identical modulo the policy name:

  ```
  uv run tracon simulate traces/export-2026-07-30 --policy fifo      --out /tmp/a.json
  uv run tracon simulate traces/export-2026-07-30 --policy core-fifo --out /tmp/b.json
  uv run python -c "
  import json; a, b = (json.load(open(p)) for p in ('/tmp/a.json', '/tmp/b.json'))
  a['config']['policy'] = b['config']['policy'] = '-'
  assert a == b, 'diverged'; print('parity ok')"
  ```

- A pytest parity test on a synthetic workload (ships when this TODO opens) passes,
  and the suite stays green.

---

## TODO-3 — first real policy: oracle-SJF with a starvation guard *(~60–90 min)*

**Concept:** priority scheduling under heavy-tailed service times, and the
latency-vs-fairness tradeoff. The characterization's finding 2 is why SJF matters
here: the tail owns the time, so letting short work jump long work cuts median
latency — at the cost of starving the long jobs unless you guard.

**Build:** `core-sjf` — pick the k smallest `service_ms`; ties break by ready order
(stable, again). Guard: any request whose wait (`now - ready_ms`) exceeds a
`starve_ms` parameter jumps to the front, oldest first. `select` grows a `now`
argument to make waits computable — that's a seam change, version the thought in
your commit message. Label it **oracle**-SJF in code comments and results: it reads
the traced service time, which a real server only estimates. The honest labeling is
part of the thesis' claim discipline.

**Acceptance:** selection-level parity with the session's Python `sjf` prototype
(P1 below — it will exist before you get here) on randomized queues, plus full-sim
parity `sjf` vs `core-sjf` on the real export (same modulo-name check as TODO-2),
plus determinism: the same command twice → byte-identical output files.

---

## TODO-4 — stream table + estimated-SJF *(~90 min)*

**Concept:** stateful policies and online estimation — and the oracle→estimate gap,
which is the difference between a claim reviewers laugh at and one they cite.

**Build:** the core gains state: a stream table (per-stream EWMA of observed service
time, observation count, last-seen). New seam call `observe(stream, service_ms)`
invoked on each completion — the sim-side hook lands with the session's harness
work, coordinate when you get here. `core-sjf-est` selects on estimates; requests
from never-seen streams need a bootstrap value (global running median, or
optimistic-small — pick one and write down why; this choice is measurable and makes
a nice sentence in the writeup).

**Acceptance:** EWMA unit tests — a fixed observation sequence produces
hand-computed estimates; unseen-stream bootstrap behaves as documented; determinism
holds (state updates must not depend on iteration order of anything unordered).
Full-sim run on the real export completes and produces a `core-sjf-est` results row.

---

## TODO-5 — determinism + selection microbench *(~45–60 min)*

**Concept:** performance claims with stated methodology — the repo's standing rule:
every number measured, hardware and method stated.

**Build:** a re-run determinism check (two consecutive full sims, `shasum` equal —
one small script) and a selection microbenchmark: µs per `select()` call at queue
depths 10 / 100 / 1,000 / 10,000, warmed up, median of many iterations, Apple M2
stated. The bench harness skeleton comes from the session (P2); you fill in and run.

**Acceptance:** both scripts run clean; numbers land in the done log below and later
in the milestone doc. No target thresholds — the claim is the measurement itself.

---

## Phase B outline — Go gRPC service *(sized when phase A lands)*

- **TODO-6, C ABI:** `extern "C"` flat wrapper over the core (no STL types cross),
  plus a shared-library CMake target. Concept: why C is the FFI lingua franca and
  what ABI stability means.
- **TODO-7, cgo:** Go module linking the shared lib; parity test against golden
  fixtures generated by the pytest suite.
- **TODO-8, the service:** proto (`Select(SelectRequest) returns (SelectResponse)`)
  + gRPC server, stateless first; `observe` streaming comes only if phase C needs it.
- **TODO-9, the loop closed:** Python client policy `grpc-fifo`; end-to-end parity
  (sim via gRPC == sim via pybind11) and measured localhost RPC overhead per call —
  the honest cost of pulling the scheduler out of process.

## Parallel work — session's lane (runs while you build)

- **P1 — Python policy prototypes** in `policies.py` (`sjf`, `sjf-est`, `affinity`,
  `unblock`) with tests. These are the golden behavior your ports must match; `sjf`
  lands before your TODO-3.
- **P2 — experiment harness:** workload replication with phase offsets (the M3
  methodology finding — compression stresses self-gating, not the server), sweep
  runner, comparison tables, bench skeleton for TODO-5.
- **P3 — context-affinity cost model** in the server (a cold-context penalty grounded
  in the 98.9%-cached finding), so affinity policies have a measurable prize. Design
  note first, for your review, before any code.

## done log

<!-- append: date · TODO · what shipped (commit) · surprises / what you learned -->
