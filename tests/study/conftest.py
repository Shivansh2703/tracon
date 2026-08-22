"""Synthetic corpus builder.

Every analysis test constructs a tiny export whose right answer is known by
construction (a handful of events.jsonl lines + a manifest.json), loads it
with ``agentfail.loader.load``, and asserts on the exact numbers that follow.

Two layers:

* ``make_session`` / ``make_tool_call`` / ``make_api_call`` / ``make_compact``
  build single event dicts with sane defaults, for tests that need full
  control over field values or file ordering (e.g. loader sort-order tests,
  malformed-line tests).
* ``write_export`` writes a list of already-built event dicts to a temp
  ``events.jsonl`` (+ ``manifest.json``) and returns the directory.
* ``build_export`` is the ergonomic, stream-shaped entry point most analysis
  tests should reach for: describe each stream as a dict of session info plus
  a list of tool-call specs, and it wires up ids, timestamps, and the
  api_call <-> tool_call join automatically.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

_counter = itertools.count(1)


def _next_ts() -> int:
    """Monotonically increasing millisecond-ish timestamp, unique per call."""
    return 1_700_000_000_000 + next(_counter) * 1000


def make_session(
    session: str,
    agent: str | None = None,
    *,
    ts: int | None = None,
    t_start: int | None = None,
    t_end: int | None = None,
    project: str = "proj",
    end_status: str | None = None,
    agent_type: str | None = None,
    **extra,
) -> dict:
    ts = ts if ts is not None else _next_ts()
    ev = {
        "ev": "session",
        "session": session,
        "agent": agent,
        "ts": ts,
        "t_start": t_start if t_start is not None else ts,
        "t_end": t_end if t_end is not None else ts + 1000,
        "project": project,
    }
    if end_status is not None:
        ev["end_status"] = end_status
    if agent_type is not None:
        ev["agent_type"] = agent_type
    ev.update(extra)
    return ev


def make_tool_call(
    session: str,
    agent: str | None = None,
    *,
    name: str = "Bash",
    args_shape: str = "command:s10",
    ts: int | None = 0,
    ts_result: int | None = 0,
    duration_ms: int | None = 1000,
    is_error: bool = False,
    result_chars: int = 100,
    api_uuid: str | None = None,
    background: bool = False,
    status: str = "matched",
    id: str | None = None,
    **extra,
) -> dict:
    """``ts=0``/``ts_result=0`` are sentinels meaning "auto"; pass ``None``
    explicitly to build an orphan_result-shaped call with no issuing ts."""
    if ts == 0:
        ts = _next_ts()
    if ts_result == 0:
        ts_result = (ts + duration_ms) if (ts is not None and duration_ms is not None) else None
    ev = {
        "ev": "tool_call",
        "session": session,
        "agent": agent,
        "ts": ts,
        "ts_result": ts_result,
        "duration_ms": duration_ms,
        "id": id or f"toolu_{next(_counter)}",
        "name": name,
        "args_shape": args_shape,
        "api_uuid": api_uuid,
        "is_error": is_error,
        "result_chars": result_chars,
        "background": background,
        "spawned_agent": None,
        "status": status,
        "sidechain": False,
    }
    ev.update(extra)
    return ev


def make_api_call(
    session: str,
    agent: str | None = None,
    *,
    ts: int | None = None,
    uuid: str | None = None,
    in_tokens: int = 0,
    cache_read: int = 0,
    cache_create: int = 0,
    tool_use_blocks: int = 0,
    model: str = "claude",
    **extra,
) -> dict:
    ts = ts if ts is not None else _next_ts()
    ev = {
        "ev": "api_call",
        "session": session,
        "agent": agent,
        "ts": ts,
        "uuid": uuid or f"api_{next(_counter)}",
        "model": model,
        "blocks": {"tool_use": tool_use_blocks},
        "usage": {"in": in_tokens, "cache_read": cache_read, "cache_create": cache_create},
    }
    ev.update(extra)
    return ev


def make_compact(
    session: str,
    agent: str | None = None,
    *,
    ts: int | None = None,
    trigger: str = "manual",
    pre_tokens: int = 100_000,
    **extra,
) -> dict:
    ts = ts if ts is not None else _next_ts()
    ev = {
        "ev": "compact",
        "session": session,
        "agent": agent,
        "ts": ts,
        "trigger": trigger,
        "pre_tokens": pre_tokens,
    }
    ev.update(extra)
    return ev


def write_export(directory: Path, events: list[dict], manifest: dict | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "events.jsonl").open("w") as handle:
        for ev in events:
            handle.write(json.dumps(ev) + "\n")
    (directory / "manifest.json").write_text(json.dumps(manifest or {}))
    return directory


def build_export(tmp_path: Path, streams: list[dict], manifest: dict | None = None, name: str = "export") -> Path:
    """Ergonomic stream-shaped corpus builder.

    ``streams`` is a list of::

        {
            "session": "s1", "agent": None,          # required
            "end_status": "completed", "agent_type": "general-purpose",
            "t_start": ..., "t_end": ...,
            "calls": [
                {"name": "Bash", "args_shape": "command:s10", "is_error": False,
                 "result_chars": 10, "duration_ms": 500,
                 "context_in": 1000, "context_cache_read": 0, "context_cache_create": 0,
                 "api_uuid": "no-join"},   # pass explicit api_uuid, or "no-join" for None
                ...
            ],
            "compacts": [{"trigger": "manual", "pre_tokens": 50000}, ...],
        }

    Each call spec auto-creates a joined api_call unless ``api_uuid`` is given
    (a real string reuses/creates that uuid; the literal ``"no-join"`` leaves
    the tool_call's api_uuid as None so ``context_tokens`` returns None).
    """
    events: list[dict] = []
    for spec in streams:
        session = spec["session"]
        agent = spec.get("agent")
        events.append(
            make_session(
                session,
                agent,
                end_status=spec.get("end_status"),
                agent_type=spec.get("agent_type"),
                t_start=spec.get("t_start"),
                t_end=spec.get("t_end"),
                project=spec.get("project", "proj"),
            )
        )
        for call_spec in spec.get("calls", []):
            call_spec = dict(call_spec)
            context_in = call_spec.pop("context_in", 0)
            context_cache_read = call_spec.pop("context_cache_read", 0)
            context_cache_create = call_spec.pop("context_cache_create", 0)
            explicit_api_uuid = call_spec.pop("api_uuid", "auto")
            tool_ev = make_tool_call(session, agent, **call_spec)
            if explicit_api_uuid == "auto":
                api_ev = make_api_call(
                    session,
                    agent,
                    ts=tool_ev["ts"] if tool_ev["ts"] is not None else tool_ev["ts_result"],
                    uuid=f"api_for_{tool_ev['id']}",
                    in_tokens=context_in,
                    cache_read=context_cache_read,
                    cache_create=context_cache_create,
                )
                tool_ev["api_uuid"] = api_ev["uuid"]
                events.append(api_ev)
            elif explicit_api_uuid == "no-join":
                tool_ev["api_uuid"] = None
            else:
                tool_ev["api_uuid"] = explicit_api_uuid
            events.append(tool_ev)
        for compact_spec in spec.get("compacts", []):
            events.append(make_compact(session, agent, **compact_spec))
    return write_export(tmp_path / name, events, manifest)


@pytest.fixture
def export_dir(tmp_path):
    """Low-level: pass a pre-built list of event dicts, get an export dir."""

    def _build(events: list[dict], manifest: dict | None = None) -> Path:
        return write_export(tmp_path / "export", events, manifest)

    return _build
