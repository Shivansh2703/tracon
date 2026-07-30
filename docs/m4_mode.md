# M4 mode change — OWNER BUILDS (Shivansh, 2026-07-30 evening)

Owner verbatim: "i want to be very very involved w building this. esp the c++ and go grpc.
instead of j driving it i want you to tell me todos and i will do my best to implement them."

This is the M4 **go**, with a role flip. Session becomes **architect / tutor / reviewer** —
never the implementer of the thesis code.

## Division of labor

- **Session builds:** Python-side policy *prototypes* + the experiment harness (instrument
  work — fast iteration belongs to the sim owner). These de-risk the design before he
  hand-builds it for real.
- **Owner builds:** the compiled core — **C++ scheduler core first (pybind11 seam to the
  sim), then a Go gRPC service wrapper around the same core.** Both languages are in scope
  by his explicit ask; sequence C++ → Go so the gRPC wrapper wraps something real.

## TODO rules

- Small: each TODO ≤ ~90 focused minutes. One concept per TODO.
- **Acceptance test first**: every TODO ships with a runnable check ("this pytest passes",
  "byte-identical re-run holds", "sim result matches the Python prototype within X") so he
  knows himself when he's done — no vibes.
- Hints, interfaces, and references — **never finished code**. If he's stuck 30+ min, he
  asks; the answer is a smaller hint, then a walkthrough, only then code as last resort.
- Write TODOs to `docs/owner_todos.md`, numbered, with a `## done log` he appends to.
- His commits get REAL reviews — same bar as any seat's work, teaching-grade comments,
  findings become his fix-TODOs. Never silently rewrite his code.
- status-log continues as `tracon` (BLOCKED lines when waiting on his next commit are fine
  and expected).

## First deliverable on unblock

Produce `docs/owner_todos.md` with the ladder through the C++ core MVP (seam interface,
core data structures, first policy port, determinism harness hookup), TODO-1 ready to
start tonight, and the Python policy-prototype work you'll run in parallel.
