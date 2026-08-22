"""Load a tracon trace export into per-stream event sequences.

The export is one JSON object per line with an ``ev`` discriminator (see
tracon's ``src/tracon/trace/schema.py``). This module is deliberately dumb: it
reads, groups, and sorts. Every judgement about what an event *means* lives in
``agentfail.analyses`` so it can be tested in isolation.

A **stream** is the unit of agentic execution: one main session, or one
subagent run. It is keyed ``(session_uuid, agent_id_or_None)``. Analyses run
per stream because a subagent's tool calls are its own reasoning loop, not the
parent's — merging them would manufacture repeats that never happened.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

StreamKey = tuple[str, str | None]

EVENT_TYPES = (
    "session",
    "prompt",
    "api_call",
    "tool_call",
    "notification",
    "turn",
    "compact",
    "queue_op",
)


def _sort_ts(event: dict) -> int:
    """Order key. Tool calls whose issuing line was lost (``orphan_result``)
    have no ``ts``; they still have a result time, so they can be placed."""
    return event.get("ts") or event.get("ts_result") or 0


@dataclass
class Stream:
    """One agentic execution: a main session or a single subagent run."""

    key: StreamKey
    session_event: dict | None = None
    tool_calls: list[dict] = field(default_factory=list)
    api_calls: list[dict] = field(default_factory=list)
    compacts: list[dict] = field(default_factory=list)
    turns: list[dict] = field(default_factory=list)
    prompts: list[dict] = field(default_factory=list)

    @property
    def is_subagent(self) -> bool:
        return self.key[1] is not None

    @property
    def end_status(self) -> str | None:
        """Only subagents carry one; a main session has no completion record."""
        return (self.session_event or {}).get("end_status")

    @property
    def agent_type(self) -> str | None:
        return (self.session_event or {}).get("agent_type")

    def sort(self) -> None:
        for seq in (self.tool_calls, self.api_calls, self.compacts, self.turns, self.prompts):
            seq.sort(key=_sort_ts)


@dataclass
class Corpus:
    """Every stream in one export, plus the manifest and lookup indexes."""

    streams: dict[StreamKey, Stream]
    manifest: dict
    api_by_uuid: dict[str, dict]
    notifications: list[dict]
    source: Path

    @property
    def tool_calls(self) -> Iterator[dict]:
        for stream in self.streams.values():
            yield from stream.tool_calls

    @property
    def subagent_streams(self) -> list[Stream]:
        return [s for s in self.streams.values() if s.is_subagent]

    def context_tokens(self, tool_call: dict) -> int | None:
        """Size of the context the model was holding when it issued this call.

        Sum of cached-read, fresh-input and cache-creation input tokens on the
        issuing ``api_call``. Returns None when the call cannot be joined back
        to its api_call (orphan results, and background spawn acks).
        """
        api = self.api_by_uuid.get(tool_call.get("api_uuid") or "")
        if api is None:
            return None
        usage = api.get("usage") or {}
        return (
            (usage.get("cache_read") or 0)
            + (usage.get("in") or 0)
            + (usage.get("cache_create") or 0)
        )


_BUCKETS = {
    "session": "session_event",
    "tool_call": "tool_calls",
    "api_call": "api_calls",
    "compact": "compacts",
    "turn": "turns",
    "prompt": "prompts",
}


def load(export_dir: str | Path) -> Corpus:
    """Read ``<export_dir>/events.jsonl`` (+ manifest) into a Corpus."""
    export_dir = Path(export_dir).expanduser()
    events_path = export_dir / "events.jsonl"
    if not events_path.exists():
        raise FileNotFoundError(
            f"no events.jsonl under {export_dir} — point --trace at a tracon export directory"
        )

    streams: dict[StreamKey, Stream] = {}
    api_by_uuid: dict[str, dict] = {}
    notifications: list[dict] = []

    def stream_for(key: StreamKey) -> Stream:
        found = streams.get(key)
        if found is None:
            found = streams[key] = Stream(key=key)
        return found

    with events_path.open() as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{events_path}:{lineno}: malformed JSON") from exc
            kind = event.get("ev")
            if kind == "notification":
                notifications.append(event)
                continue
            if kind == "api_call":
                api_by_uuid[event["uuid"]] = event
            bucket = _BUCKETS.get(kind)
            if bucket is None:
                continue  # queue_op and any future event type: not used by this study
            stream = stream_for((event["session"], event.get("agent")))
            if bucket == "session_event":
                stream.session_event = event
            else:
                getattr(stream, bucket).append(event)

    for stream in streams.values():
        stream.sort()

    manifest_path = export_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    return Corpus(
        streams=streams,
        manifest=manifest,
        api_by_uuid=api_by_uuid,
        notifications=notifications,
        source=export_dir,
    )
