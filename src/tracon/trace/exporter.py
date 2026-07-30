"""Offline trace exporter: raw Claude Code transcripts → normalized, payload-stripped
trace events.

Reads ``~/.claude/projects/**/*.jsonl`` (main sessions + subagent transcripts + their
meta files), emits one ``events.jsonl`` plus a ``manifest.json`` run report. Never
modifies its input; never emits payload content (see ``privacy``). Unknown line shapes
are schema anomalies: counted, reported, and fatal to the exit code unless explicitly
allowed (see ``schema``).
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tracon.trace import schema
from tracon.trace.privacy import Tokenizer, args_shape, content_chars

_TASK_NOTIF_RE = re.compile(r"<task-notification>([\s\S]*?)</task-notification>")
_TASK_ID_RE = re.compile(r"<task-id>([\s\S]*?)</task-id>")
_TOOL_USE_ID_RE = re.compile(r"<tool-use-id>([\s\S]*?)</tool-use-id>")
_STATUS_RE = re.compile(r"<status>([\s\S]*?)</status>")

_MAX_ANOMALY_SAMPLES = 8


def _parse_ts(value: object) -> int | None:
    """ISO-8601 transcript timestamp → epoch milliseconds."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value).timestamp() * 1000)
    except ValueError:
        return None


class Anomalies:
    """Everything the exporter saw but does not understand. Non-empty anomalies
    fail the run by default: silent drops would corrupt the characterization."""

    def __init__(self) -> None:
        self.unknown_line_types: Counter[str] = Counter()
        self.unknown_system_subtypes: Counter[str] = Counter()
        self.missing_timestamps: Counter[str] = Counter()
        self.parse_errors = 0
        self.samples: list[str] = []

    def sample(self, note: str) -> None:
        if len(self.samples) < _MAX_ANOMALY_SAMPLES:
            self.samples.append(note)

    def any(self) -> bool:
        return bool(
            self.unknown_line_types
            or self.unknown_system_subtypes
            or self.missing_timestamps
            or self.parse_errors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "unknown_line_types": dict(self.unknown_line_types),
            "unknown_system_subtypes": dict(self.unknown_system_subtypes),
            "missing_timestamps": dict(self.missing_timestamps),
            "parse_errors": self.parse_errors,
            "samples": self.samples,
        }


@dataclass
class _AgentMeta:
    hex_id: str
    agent_type: str | None = None
    tool_use_id: str | None = None
    spawn_depth: int | None = None
    model: str | None = None
    effort: str | None = None
    workflow: str | None = None


@dataclass
class _PendingTool:
    tool_use_id: str
    name: str
    ts: int | None
    api_uuid: str | None
    shape: str
    background: bool
    sidechain: bool


@dataclass
class _OpenMessage:
    msg_id: str | None
    ts_first: int | None = None
    ts_last: int | None = None
    uuid: str | None = None
    parent_uuid: str | None = None
    request_id: str | None = None
    model: str | None = None
    effort: str | None = None
    stop_reason: str | None = None
    usage: dict[str, Any] | None = None
    sidechain: bool = False
    blocks: Counter[str] = field(default_factory=Counter)
    chars: Counter[str] = field(default_factory=Counter)


@dataclass
class _ParsedFile:
    session_stub: dict[str, Any]
    events: list[dict[str, Any]]
    matched_result_ids: set[str]
    notif_status_by_hex: dict[str, str]
    notif_status_by_tooluse: dict[str, str]
    spawn_background: dict[str, bool]


class _FileParser:
    """Single transcript file (main session or subagent) → normalized events."""

    def __init__(
        self,
        path: Path,
        session_id: str,
        agent_hex: str | None,
        project_token: str | None,
        tokenizer: Tokenizer,
        anomalies: Anomalies,
        tooluse_to_agent: dict[str, str],
    ) -> None:
        self._path = path
        self._session = session_id
        self._agent = agent_hex
        self._project = project_token
        self._tok = tokenizer
        self._anomalies = anomalies
        self._tooluse_to_agent = tooluse_to_agent

        self._events: list[dict[str, Any]] = []
        self._pending_tools: dict[str, _PendingTool] = {}
        self._open_msg: _OpenMessage | None = None
        self._line_types: Counter[str] = Counter()
        self._versions: set[str] = set()
        self._ts_min: int | None = None
        self._ts_max: int | None = None
        self._cwd: str | None = None
        self._git_branch: str | None = None
        self._entrypoint: str | None = None
        self._matched_result_ids: set[str] = set()
        self._notif_by_hex: dict[str, str] = {}
        self._notif_by_tooluse: dict[str, str] = {}
        self._spawn_background: dict[str, bool] = {}
        self._seen_uuids: set[str] = set()
        self._seen_queue_ops: set[tuple[str, int]] = set()
        self._n_duplicates = 0
        self._n_orphan_results = 0

    def _ref(self) -> str:
        return f"{self._project or '?'}/{self._path.name}"

    def _base(self, ev: str, ts: int | None) -> dict[str, Any]:
        return {"ev": ev, "session": self._session, "agent": self._agent, "ts": ts}

    def _emit(self, event: dict[str, Any]) -> None:
        self._events.append(event)

    def _track_line_meta(self, line: dict[str, Any], ts: int | None) -> None:
        if ts is not None:
            self._ts_min = ts if self._ts_min is None else min(self._ts_min, ts)
            self._ts_max = ts if self._ts_max is None else max(self._ts_max, ts)
        version = line.get("version")
        if isinstance(version, str):
            self._versions.add(version)
        if self._cwd is None and isinstance(line.get("cwd"), str):
            self._cwd = line["cwd"]
        if self._git_branch is None and isinstance(line.get("gitBranch"), str):
            self._git_branch = line["gitBranch"]
        if self._entrypoint is None and isinstance(line.get("entrypoint"), str):
            self._entrypoint = line["entrypoint"]

    def parse(self) -> _ParsedFile:
        n_lines = 0
        with self._path.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw_s = raw.strip()
                if not raw_s:
                    continue
                n_lines += 1
                try:
                    line = json.loads(raw_s)
                except json.JSONDecodeError:
                    self._anomalies.parse_errors += 1
                    self._anomalies.sample(f"parse_error {self._ref()}:{n_lines}")
                    continue
                if not isinstance(line, dict):
                    self._anomalies.parse_errors += 1
                    continue
                # Claude Code re-appends chunks of history into the same file on
                # resume/reconnect; the copies carry the original line uuid.
                # Processing them again would double-count api_calls and turn
                # every re-logged tool_result into a false orphan.
                uuid = line.get("uuid")
                if isinstance(uuid, str):
                    if uuid in self._seen_uuids:
                        self._n_duplicates += 1
                        continue
                    self._seen_uuids.add(uuid)
                self._dispatch(line)
        self._flush_message()
        self._flush_unmatched_tools()
        return _ParsedFile(
            session_stub=self._session_stub(n_lines),
            events=self._events,
            matched_result_ids=self._matched_result_ids,
            notif_status_by_hex=self._notif_by_hex,
            notif_status_by_tooluse=self._notif_by_tooluse,
            spawn_background=self._spawn_background,
        )

    def _dispatch(self, line: dict[str, Any]) -> None:
        line_type = line.get("type")
        if not isinstance(line_type, str):
            self._anomalies.unknown_line_types["<no type>"] += 1
            self._anomalies.sample(f"no-type line {self._ref()}")
            return
        self._line_types[line_type] += 1
        ts = _parse_ts(line.get("timestamp"))
        self._track_line_meta(line, ts)

        if line_type == "assistant":
            self._on_assistant(line, ts)
        elif line_type == "user":
            self._flush_message()
            self._on_user(line, ts)
        elif line_type == "system":
            self._flush_message()
            self._on_system(line, ts)
        elif line_type == "queue-operation":
            self._on_queue_op(line, ts)
        elif line_type not in schema.IGNORED_LINE_TYPES:
            self._anomalies.unknown_line_types[line_type] += 1
            self._anomalies.sample(f"line type {line_type!r} {self._ref()}")

    # -- assistant messages (one content block per line, merged by message.id) --

    def _on_assistant(self, line: dict[str, Any], ts: int | None) -> None:
        message = line.get("message")
        if not isinstance(message, dict):
            self._anomalies.unknown_line_types["assistant:<no message>"] += 1
            return
        msg_id = message.get("id") if isinstance(message.get("id"), str) else None
        open_msg = self._open_msg
        if open_msg is None or open_msg.msg_id != msg_id or msg_id is None:
            self._flush_message()
            open_msg = self._open_msg = _OpenMessage(msg_id=msg_id)
            open_msg.ts_first = ts
            open_msg.uuid = line.get("uuid")
            open_msg.parent_uuid = line.get("parentUuid")
            open_msg.sidechain = line.get("isSidechain") is True
        open_msg.ts_last = ts if ts is not None else open_msg.ts_last
        if isinstance(line.get("requestId"), str):
            open_msg.request_id = line["requestId"]
        if isinstance(line.get("effort"), str):
            open_msg.effort = line["effort"]
        if isinstance(message.get("model"), str):
            open_msg.model = message["model"]
        if isinstance(message.get("stop_reason"), str):
            open_msg.stop_reason = message["stop_reason"]
        if isinstance(message.get("usage"), dict):
            open_msg.usage = message["usage"]
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    self._on_block(block, ts, line)

    def _on_block(self, block: dict[str, Any], ts: int | None, line: dict[str, Any]) -> None:
        assert self._open_msg is not None  # noqa: S101 — invariant, caller creates it
        block_type = block.get("type")
        if block_type == "text":
            self._open_msg.blocks["text"] += 1
            self._open_msg.chars["text"] += len(block.get("text") or "")
        elif block_type == "thinking":
            self._open_msg.blocks["thinking"] += 1
            self._open_msg.chars["thinking"] += len(block.get("thinking") or "")
        elif block_type == "tool_use":
            self._open_msg.blocks["tool_use"] += 1
            self._register_tool_use(block, ts, line)
        else:
            self._open_msg.blocks["other"] += 1

    def _register_tool_use(
        self, block: dict[str, Any], ts: int | None, line: dict[str, Any]
    ) -> None:
        tool_use_id = block.get("id")
        if not isinstance(tool_use_id, str):
            return
        tool_input = block.get("input")
        background = isinstance(tool_input, dict) and tool_input.get("run_in_background") is True
        self._spawn_background[tool_use_id] = background
        self._pending_tools[tool_use_id] = _PendingTool(
            tool_use_id=tool_use_id,
            name=str(block.get("name") or "?"),
            ts=ts,
            api_uuid=line.get("uuid") if isinstance(line.get("uuid"), str) else None,
            shape=args_shape(tool_input),
            background=background,
            sidechain=line.get("isSidechain") is True,
        )

    def _flush_message(self) -> None:
        msg = self._open_msg
        if msg is None:
            return
        self._open_msg = None
        if msg.ts_first is None:
            self._anomalies.missing_timestamps["api_call"] += 1
            return
        usage = msg.usage or {}
        cache_creation = usage.get("cache_creation") or {}
        event = self._base("api_call", msg.ts_first)
        event.update(
            {
                "ts_last": msg.ts_last,
                "uuid": msg.uuid,
                "parent_uuid": msg.parent_uuid,
                "request_id": msg.request_id,
                "model": msg.model,
                "effort": msg.effort,
                "stop_reason": msg.stop_reason,
                "blocks": {
                    "text": msg.blocks["text"],
                    "text_chars": msg.chars["text"],
                    "thinking": msg.blocks["thinking"],
                    "thinking_chars": msg.chars["thinking"],
                    "tool_use": msg.blocks["tool_use"],
                    "other": msg.blocks["other"],
                },
                "usage": {
                    "in": usage.get("input_tokens"),
                    "out": usage.get("output_tokens"),
                    "cache_read": usage.get("cache_read_input_tokens"),
                    "cache_create": usage.get("cache_creation_input_tokens"),
                    "cache_create_5m": cache_creation.get("ephemeral_5m_input_tokens"),
                    "cache_create_1h": cache_creation.get("ephemeral_1h_input_tokens"),
                    "service_tier": usage.get("service_tier"),
                    "speed": usage.get("speed"),
                },
                "sidechain": msg.sidechain,
            }
        )
        self._emit(event)

    # -- user lines: tool results, task notifications, or genuine prompts --

    def _on_user(self, line: dict[str, Any], ts: int | None) -> None:
        raw_message = line.get("message")
        message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
        content = message.get("content")
        had_result = False
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    had_result = True
                    self._on_tool_result(block, ts)
        text = self._collect_text(content)
        notifs = list(_TASK_NOTIF_RE.finditer(text)) if text else []
        for match in notifs:
            self._on_notification(match.group(1), ts)
        if had_result or notifs or line.get("isMeta") is True:
            return
        if ts is None:
            self._anomalies.missing_timestamps["prompt"] += 1
            return
        event = self._base("prompt", ts)
        event.update(
            {
                "uuid": line.get("uuid"),
                "parent_uuid": line.get("parentUuid"),
                "text_chars": content_chars(content),
                "origin": line.get("origin") if isinstance(line.get("origin"), str) else None,
                "sidechain": line.get("isSidechain") is True,
            }
        )
        self._emit(event)

    @staticmethod
    def _collect_text(content: object) -> str:
        # scan-only: this text is pattern-matched for notification tags, never emitted
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
            return "\n".join(parts)
        return ""

    def _on_tool_result(self, block: dict[str, Any], ts: int | None) -> None:
        tool_use_id = block.get("tool_use_id")
        if not isinstance(tool_use_id, str):
            return
        pending = self._pending_tools.pop(tool_use_id, None)
        if pending is None:
            # The raw transcript dropped the assistant line that issued this call
            # (observed: stream abort/retry gaps, ~0.01% of calls). Understood
            # source lossiness, not schema drift — recorded, not fatal.
            self._n_orphan_results += 1
            event = self._base("tool_call", None)
            event.update(
                {
                    "ts_result": ts,
                    "duration_ms": None,
                    "id": tool_use_id,
                    "name": None,
                    "args_shape": None,
                    "api_uuid": None,
                    "is_error": block.get("is_error") is True,
                    "result_chars": content_chars(block.get("content")),
                    "background": False,
                    "spawned_agent": self._tooluse_to_agent.get(tool_use_id),
                    "status": "orphan_result",
                    "sidechain": False,
                }
            )
            self._emit(event)
            return
        self._matched_result_ids.add(tool_use_id)
        duration = None
        if ts is not None and pending.ts is not None:
            duration = ts - pending.ts
        event = self._base("tool_call", pending.ts)
        event.update(
            {
                "ts_result": ts,
                "duration_ms": duration,
                "id": tool_use_id,
                "name": pending.name,
                "args_shape": pending.shape,
                "api_uuid": pending.api_uuid,
                "is_error": block.get("is_error") is True,
                "result_chars": content_chars(block.get("content")),
                "background": pending.background,
                "spawned_agent": self._tooluse_to_agent.get(tool_use_id),
                "status": "matched",
                "sidechain": pending.sidechain,
            }
        )
        self._emit(event)

    def _on_notification(self, body: str, ts: int | None) -> None:
        status_m = _STATUS_RE.search(body)
        status = status_m.group(1).strip() if status_m else None
        task_m = _TASK_ID_RE.search(body)
        task_id = task_m.group(1).strip().removeprefix("agent-") if task_m else None
        tooluse_m = _TOOL_USE_ID_RE.search(body)
        tool_use_id = tooluse_m.group(1).strip() if tooluse_m else None
        if status in schema.TERMINAL_NOTIF_STATUSES:
            if task_id:
                self._notif_by_hex[task_id] = status
            if tool_use_id:
                self._notif_by_tooluse[tool_use_id] = status
        agent_ref = task_id
        if agent_ref is None and tool_use_id is not None:
            agent_ref = self._tooluse_to_agent.get(tool_use_id)
        event = self._base("notification", ts)
        event.update({"agent_ref": agent_ref, "tool_use_id": tool_use_id, "status": status})
        self._emit(event)

    # -- system lines --

    def _on_system(self, line: dict[str, Any], ts: int | None) -> None:
        subtype = line.get("subtype")
        if subtype == "turn_duration":
            event = self._base("turn", ts)
            event.update(
                {
                    "duration_ms": line.get("durationMs"),
                    "message_count": line.get("messageCount"),
                    "pending_background_agents": line.get("pendingBackgroundAgentCount"),
                }
            )
            self._emit(event)
        elif subtype == "compact_boundary":
            meta = line.get("compactMetadata")
            meta = meta if isinstance(meta, dict) else {}
            event = self._base("compact", ts)
            trigger = meta.get("trigger")
            event.update(
                {
                    "trigger": trigger if isinstance(trigger, str) else None,
                    "pre_tokens": meta.get("preTokens"),
                }
            )
            self._emit(event)
        elif subtype not in schema.IGNORED_SYSTEM_SUBTYPES:
            key = subtype if isinstance(subtype, str) else "<no subtype>"
            self._anomalies.unknown_system_subtypes[key] += 1
            self._anomalies.sample(f"system subtype {key!r} {self._ref()}")

    def _on_queue_op(self, line: dict[str, Any], ts: int | None) -> None:
        if ts is None:
            self._anomalies.missing_timestamps["queue_op"] += 1
            return
        # queue-operation lines carry no uuid, so the re-appended-history dedupe
        # can't catch their copies; (op, timestamp) is identity enough within a file
        op = line.get("operation") if isinstance(line.get("operation"), str) else None
        key = (op or "?", ts)
        if key in self._seen_queue_ops:
            self._n_duplicates += 1
            return
        self._seen_queue_ops.add(key)
        event = self._base("queue_op", ts)
        event.update(
            {
                "op": op,
                "content_chars": content_chars(line.get("content")),
            }
        )
        self._emit(event)

    # -- finalization --

    def _flush_unmatched_tools(self) -> None:
        for pending in self._pending_tools.values():
            event = self._base("tool_call", pending.ts)
            event.update(
                {
                    "ts_result": None,
                    "duration_ms": None,
                    "id": pending.tool_use_id,
                    "name": pending.name,
                    "args_shape": pending.shape,
                    "api_uuid": pending.api_uuid,
                    "is_error": False,
                    "result_chars": 0,
                    "background": pending.background,
                    "spawned_agent": self._tooluse_to_agent.get(pending.tool_use_id),
                    "status": "unmatched",
                    "sidechain": pending.sidechain,
                }
            )
            self._emit(event)
        self._pending_tools.clear()

    def _session_stub(self, n_lines: int) -> dict[str, Any]:
        event = self._base("session", self._ts_min)
        event.update(
            {
                "t_start": self._ts_min,
                "t_end": self._ts_max,
                "project": self._project,
                "cwd": self._tok.token(self._cwd),
                "git_branch": self._tok.token(self._git_branch),
                "entrypoint": self._entrypoint,
                "versions": sorted(self._versions),
                "n_lines": n_lines,
                "n_duplicate_lines": self._n_duplicates,
                "n_orphan_results": self._n_orphan_results,
                "line_types": dict(self._line_types),
            }
        )
        return event


def _read_agent_meta(meta_path: Path, hex_id: str) -> _AgentMeta:
    meta = _AgentMeta(hex_id=hex_id)
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return meta
    if not isinstance(raw, dict):
        return meta
    if isinstance(raw.get("agentType"), str):
        meta.agent_type = raw["agentType"]
    if isinstance(raw.get("toolUseId"), str) and raw["toolUseId"]:
        meta.tool_use_id = raw["toolUseId"]
    if isinstance(raw.get("spawnDepth"), int):
        meta.spawn_depth = raw["spawnDepth"]
    if isinstance(raw.get("model"), str):
        meta.model = raw["model"]
    if isinstance(raw.get("effort"), str):
        meta.effort = raw["effort"]
    parent_dir = meta_path.parent.name
    if parent_dir.startswith("wf_"):
        meta.workflow = parent_dir
    return meta


@dataclass
class _SessionUnit:
    project_dir: Path
    session_id: str
    main_path: Path | None
    agent_paths: list[Path]
    metas: dict[str, _AgentMeta]
    n_journals: int


def _discover(root: Path) -> tuple[list[_SessionUnit], int]:
    units: list[_SessionUnit] = []
    n_journals_total = 0
    for project_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        mains = {p.stem: p for p in project_dir.glob("*.jsonl")}
        session_dirs = {
            d.name: d for d in project_dir.iterdir() if d.is_dir() and (d / "subagents").is_dir()
        }
        for session_id in sorted(mains.keys() | session_dirs.keys()):
            agent_paths: list[Path] = []
            metas: dict[str, _AgentMeta] = {}
            n_journals = 0
            session_dir = session_dirs.get(session_id)
            if session_dir is not None:
                sub = session_dir / "subagents"
                agent_paths = sorted(sub.rglob("agent-*.jsonl"))
                for meta_path in sub.rglob("agent-*.meta.json"):
                    hex_id = meta_path.name.removesuffix(".meta.json").removeprefix("agent-")
                    metas[hex_id] = _read_agent_meta(meta_path, hex_id)
                n_journals = sum(1 for _ in sub.rglob("journal.jsonl"))
                n_journals_total += n_journals
            units.append(
                _SessionUnit(
                    project_dir=project_dir,
                    session_id=session_id,
                    main_path=mains.get(session_id),
                    agent_paths=agent_paths,
                    metas=metas,
                    n_journals=n_journals,
                )
            )
    return units, n_journals_total


class Exporter:
    def __init__(
        self,
        root: Path,
        out_dir: Path,
        tokenizer: Tokenizer | None = None,
    ) -> None:
        self._root = root.expanduser()
        self._out_dir = out_dir
        self._tok = tokenizer if tokenizer is not None else Tokenizer()
        self.anomalies = Anomalies()
        self._vanished = 0

    def run(self) -> dict[str, Any]:
        started = time.monotonic()
        if not self._root.is_dir():
            raise FileNotFoundError(f"transcript root not found: {self._root}")
        self._out_dir.mkdir(parents=True, exist_ok=True)
        units, n_journals = _discover(self._root)

        event_counts: Counter[str] = Counter()
        line_type_totals: Counter[str] = Counter()
        versions: set[str] = set()
        n_files = 0
        n_sessions = 0
        n_agents = 0
        n_duplicates = 0
        n_orphans = 0

        events_path = self._out_dir / "events.jsonl"
        with events_path.open("w", encoding="utf-8") as out:

            def write_events(events: list[dict[str, Any]]) -> None:
                for event in events:
                    event_counts[event["ev"]] += 1
                    out.write(json.dumps(event, separators=(",", ":")) + "\n")

            for unit in units:
                parsed = self._parse_unit(unit)
                for stub, events in parsed:
                    line_types = stub.get("line_types", {})
                    line_type_totals.update(line_types)
                    versions.update(stub.get("versions", []))
                    n_duplicates += stub.get("n_duplicate_lines", 0)
                    n_orphans += stub.get("n_orphan_results", 0)
                    n_files += 1
                    if stub.get("agent") is None:
                        n_sessions += 1
                    else:
                        n_agents += 1
                    write_events([stub, *events])

        manifest = {
            "schema_version": schema.SCHEMA_VERSION,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "root": str(self._root),
            "duration_s": round(time.monotonic() - started, 2),
            "files": n_files,
            "sessions": n_sessions,
            "agents": n_agents,
            "journals_skipped": n_journals,
            "files_vanished": self._vanished,
            "duplicate_lines": n_duplicates,
            "orphan_tool_results": n_orphans,
            "lines_by_type": dict(line_type_totals),
            "events_by_type": dict(event_counts),
            "versions_seen": sorted(versions),
            "anomalies": self.anomalies.to_dict(),
        }
        (self._out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return manifest

    def _parse_unit(self, unit: _SessionUnit) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
        project_token = self._tok.token(unit.project_dir.name)
        tooluse_to_agent = {
            meta.tool_use_id: hex_id
            for hex_id, meta in unit.metas.items()
            if meta.tool_use_id is not None
        }

        results: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        matched_ids: set[str] = set()
        notif_by_hex: dict[str, str] = {}
        notif_by_tooluse: dict[str, str] = {}
        spawn_background: dict[str, bool] = {}
        agent_stubs: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []

        def absorb(parsed: _ParsedFile) -> None:
            matched_ids.update(parsed.matched_result_ids)
            notif_by_hex.update(parsed.notif_status_by_hex)
            notif_by_tooluse.update(parsed.notif_status_by_tooluse)
            spawn_background.update(parsed.spawn_background)

        def parse_file(path: Path, agent_hex: str | None) -> _ParsedFile | None:
            # the corpus is live — a file found at discovery can vanish before open
            try:
                return _FileParser(
                    path,
                    unit.session_id,
                    agent_hex,
                    project_token,
                    self._tok,
                    self.anomalies,
                    tooluse_to_agent,
                ).parse()
            except OSError:
                self._vanished += 1
                return None

        if unit.main_path is not None:
            parsed = parse_file(unit.main_path, None)
            if parsed is not None:
                absorb(parsed)
                results.append((parsed.session_stub, parsed.events))

        for agent_path in unit.agent_paths:
            hex_id = agent_path.stem.removeprefix("agent-")
            parsed = parse_file(agent_path, hex_id)
            if parsed is not None:
                absorb(parsed)
                agent_stubs.append((hex_id, parsed.session_stub, parsed.events))

        for hex_id, stub, events in agent_stubs:
            meta = unit.metas.get(hex_id, _AgentMeta(hex_id=hex_id))
            background = (
                spawn_background.get(meta.tool_use_id, False)
                if meta.tool_use_id is not None
                else False
            )
            stub.update(
                {
                    "agent_type": meta.agent_type,
                    "spawn_depth": meta.spawn_depth,
                    "spawned_by_tool_use": meta.tool_use_id,
                    "background": background,
                    "workflow": meta.workflow,
                    "model": meta.model,
                    "effort": meta.effort,
                    "end_status": _resolve_end_status(
                        meta,
                        background=background,
                        matched_ids=matched_ids,
                        notif_by_hex=notif_by_hex,
                        notif_by_tooluse=notif_by_tooluse,
                    ),
                }
            )
            results.append((stub, events))
        return results


def _resolve_end_status(
    meta: _AgentMeta,
    *,
    background: bool,
    matched_ids: set[str],
    notif_by_hex: dict[str, str],
    notif_by_tooluse: dict[str, str],
) -> str:
    """Completion-signal precedence, mirroring agent-radar's collector: an explicit
    task-notification wins; otherwise a sync spawn's tool_result means completed
    (a background spawn's tool_result is only the launch ack, so it proves nothing)."""
    status = notif_by_hex.get(meta.hex_id)
    if status is None and meta.tool_use_id is not None:
        status = notif_by_tooluse.get(meta.tool_use_id)
    if status is not None:
        return status
    if not background and meta.tool_use_id is not None and meta.tool_use_id in matched_ids:
        return "completed"
    return "unknown"
