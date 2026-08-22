"""Adapters: map a public agent-trajectory corpus into the study's own schema.

The point of this package is *not* to write a second analysis. It is to make
foreign data readable by ``agentfail.loader`` so that the identical code in
``agentfail.analyses`` runs over it. Every adapter's only job is to emit an
``events.jsonl`` + ``manifest.json`` pair that the existing loader accepts.

Two rules every adapter here obeys:

1. **Never invent a field.** If a corpus has no wall-clock timing, the emitted
   ``duration_ms`` is ``None`` and the long-tail analysis reports zero timed
   calls — it does not get a fabricated stand-in. If it has no per-call token
   accounting, no ``api_call`` usage is emitted and the context analysis reports
   the calls as unjoinable. A finding that cannot be tested on a corpus must
   come out of the pipeline as *untestable*, not as a plausible number.
2. **Use the same fingerprint.** ``args_shape`` is reproduced bit-for-bit from
   tracon's privacy module (see ``shape``), because the study's repeat-run
   bracket is defined in terms of it. Public corpora ship full arguments, so
   adapters can *additionally* emit an exact-argument encoding — see
   ``ShapeMode`` — which lets the same looping analysis be run twice and the
   width of the study's bracket be checked against ground truth for the first
   time.
"""

from __future__ import annotations

from ._emit import ExportWriter, ShapeMode, exact_signature, shape

REGISTRY: dict[str, str] = {}


def register(name: str, module: str) -> None:
    REGISTRY[name] = module


register("sweagent", "agentfail.adapters.sweagent")
register("openhands", "agentfail.adapters.openhands")

__all__ = ["ExportWriter", "ShapeMode", "exact_signature", "shape", "REGISTRY", "register"]
