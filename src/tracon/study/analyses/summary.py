"""Q0 — what the corpus actually is, including the things that limit it.

Emitted first in every report so no downstream number is read without its
denominators and its biases attached.
"""

from __future__ import annotations

from collections import Counter

from ..loader import Corpus

BIASES = [
    "Single operator: every session is one developer's, with his prompting style and habits.",
    "Single tool: Claude Code only (24 versions over the window). No other agent harness.",
    "Single domain: his own software projects. No customer-facing or adversarial workloads.",
    "Content-stripped by design: no prompts, no tool arguments, no outputs — shapes and timings only.",
    "Observational: no interventions, no control group, no ground truth on task correctness.",
    "Survivorship: transcripts that were deleted or never written are invisible here.",
]


def analyze(corpus: Corpus) -> dict:
    streams = list(corpus.streams.values())
    mains = [s for s in streams if not s.is_subagent]
    subs = [s for s in streams if s.is_subagent]
    tool_calls = list(corpus.tool_calls)

    starts = [s.session_event["t_start"] for s in streams if s.session_event and s.session_event.get("t_start")]
    ends = [s.session_event["t_end"] for s in streams if s.session_event and s.session_event.get("t_end")]
    span_days = round((max(ends) - min(starts)) / 86_400_000, 1) if starts and ends else None

    projects = {s.session_event.get("project") for s in streams if s.session_event}
    models = Counter(
        a.get("model") for s in streams for a in s.api_calls if a.get("model")
    )

    return {
        "source": str(corpus.source),
        "export_generated_at": corpus.manifest.get("generated_at"),
        "schema_version": corpus.manifest.get("schema_version"),
        "streams": len(streams),
        "main_sessions": len(mains),
        "subagent_runs": len(subs),
        "tool_calls": len(tool_calls),
        "api_calls": len(corpus.api_by_uuid),
        "prompts": sum(len(s.prompts) for s in streams),
        "turns": sum(len(s.turns) for s in streams),
        "compactions": sum(len(s.compacts) for s in streams),
        "distinct_projects": len(projects - {None}),
        "span_days": span_days,
        "claude_code_versions": len(corpus.manifest.get("versions_seen") or []),
        "top_models": models.most_common(6),
        "distinct_tools": len({c["name"] for c in tool_calls if c["name"]}),
        "biases": BIASES,
    }
