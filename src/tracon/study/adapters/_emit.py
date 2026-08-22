"""Shared machinery for every adapter: the argument fingerprint and the writer.

Nothing dataset-specific lives here. An adapter parses its own format, calls
``ExportWriter.session`` / ``.api_call`` / ``.tool_call``, and closes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------
# Argument fingerprint
# --------------------------------------------------------------------------
# Reproduced from tracon/src/tracon/trace/privacy.py so that repeat-run
# detection on a public corpus is defined identically to the study's. Vendored
# rather than imported: agentfail must not depend on tracon being installed,
# and a silent upstream change to the fingerprint would silently move the
# comparison. tests/test_adapters_emit.py pins the format.


def _type_code(value: object) -> str:
    # bool before int: bool is an int subclass.
    if isinstance(value, bool):
        return "b"
    if isinstance(value, str):
        return f"s{len(value)}"
    if isinstance(value, int):
        return "i"
    if isinstance(value, float):
        return "f"
    if value is None:
        return "n"
    if isinstance(value, list):
        return f"a{len(value)}"
    if isinstance(value, dict):
        return f"o{len(value)}"
    return "?"


def shape(args: object) -> str:
    """Depth-1 structural fingerprint: key names, value types, sizes; no values.

    ``{"command": "ls -la", "description": "x"}`` -> ``command:s6,description:s1``.
    """
    if not isinstance(args, dict):
        return _type_code(args)
    items = sorted((str(key), _type_code(value)) for key, value in args.items())
    return ",".join(f"{key}:{code}" for key, code in items)


def exact_signature(args: object) -> str:
    """Content-addressed fingerprint of the *actual* arguments.

    Public corpora ship real tool arguments, which the study's own corpus does
    not. Emitting this in the ``args_shape`` slot makes the unmodified looping
    analysis measure exact repeats rather than shape repeats — the ground truth
    the study could only bracket. Hashed rather than stored verbatim so an
    export stays small and carries no source code.
    """
    blob = json.dumps(args, sort_keys=True, default=str, ensure_ascii=False)
    return "x" + hashlib.blake2b(blob.encode("utf-8"), digest_size=10).hexdigest()


class ShapeMode(str, Enum):
    """Which fingerprint goes into the ``args_shape`` field.

    ``SHAPE`` reproduces the study's own (lossy) encoding, for a like-for-like
    comparison. ``EXACT`` uses the real arguments, which no tracon export can
    do. Running both over one corpus measures how much of the study's
    repeat-run bracket is shape collision.
    """

    SHAPE = "shape"
    EXACT = "exact"


# --------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------


@dataclass
class ExportWriter:
    """Accumulates events and writes a loader-compatible export directory.

    Ordering is not enforced here: ``loader.load`` sorts every stream by
    timestamp on read, exactly as it does for a real tracon export.
    """

    out_dir: Path
    adapter: str
    shape_mode: ShapeMode = ShapeMode.SHAPE
    events: list[dict] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)

    def bump(self, key: str) -> None:
        """Count something worth auditing later; lands in the manifest."""
        self.counters[key] = self.counters.get(key, 0) + 1

    _bump = bump  # internal alias used by this module's own hot paths

    def fingerprint(self, args: object) -> str:
        return shape(args) if self.shape_mode is ShapeMode.SHAPE else exact_signature(args)

    def session(
        self,
        session: str,
        agent: str | None = None,
        *,
        ts: int | None = None,
        t_start: int | None = None,
        t_end: int | None = None,
        project: str = "public",
        end_status: str | None = None,
        agent_type: str | None = None,
        **extra: Any,
    ) -> None:
        ev = {
            "ev": "session",
            "session": session,
            "agent": agent,
            "ts": ts if ts is not None else t_start,
            "t_start": t_start,
            "t_end": t_end,
            "project": project,
            "end_status": end_status,
            "agent_type": agent_type,
        }
        ev.update(extra)
        self.events.append(ev)
        self._bump("session")

    def api_call(
        self,
        session: str,
        agent: str | None,
        *,
        uuid: str,
        ts: int | None,
        in_tokens: int | None = None,
        cache_read: int | None = None,
        cache_create: int | None = None,
        tool_use_blocks: int = 0,
        model: str | None = None,
        **extra: Any,
    ) -> None:
        """An LLM turn. ``usage`` is omitted entirely when the source corpus has
        no token accounting, so ``Corpus.context_tokens`` yields 0 rather than a
        guess — and the caller is expected to *not* join tool calls to it in
        that case (see ``tool_call(api_uuid=None)``)."""
        usage: dict[str, int] = {}
        if in_tokens is not None:
            usage["in"] = in_tokens
        if cache_read is not None:
            usage["cache_read"] = cache_read
        if cache_create is not None:
            usage["cache_create"] = cache_create
        ev = {
            "ev": "api_call",
            "session": session,
            "agent": agent,
            "ts": ts,
            "uuid": uuid,
            "model": model,
            "blocks": {"tool_use": tool_use_blocks},
            "usage": usage,
        }
        ev.update(extra)
        self.events.append(ev)
        self._bump("api_call")

    def tool_call(
        self,
        session: str,
        agent: str | None,
        *,
        id: str,
        name: str | None,
        args: object = None,
        args_shape: str | None = None,
        ts: int | None = None,
        ts_result: int | None = None,
        duration_ms: int | None = None,
        is_error: bool = False,
        result_chars: int = 0,
        api_uuid: str | None = None,
        background: bool = False,
        status: str = "matched",
        **extra: Any,
    ) -> None:
        ev = {
            "ev": "tool_call",
            "session": session,
            "agent": agent,
            "ts": ts,
            "ts_result": ts_result,
            "duration_ms": duration_ms,
            "id": id,
            "name": name,
            "args_shape": args_shape if args_shape is not None else self.fingerprint(args),
            "api_uuid": api_uuid,
            "is_error": is_error,
            "result_chars": result_chars,
            "background": background,
            "spawned_agent": None,
            "status": status,
            "sidechain": False,
        }
        ev.update(extra)
        self.events.append(ev)
        self._bump("tool_call")
        if is_error:
            self._bump("tool_call_error")
        if duration_ms is not None:
            self._bump("tool_call_timed")

    def _check_no_phantom_context(self) -> None:
        """Guard against the one bug that would silently fabricate a finding.

        ``Corpus.context_tokens`` sums the issuing api_call's usage fields with
        ``or 0``, so a tool call joined to a *usage-less* api_call reports a
        context size of zero rather than "unknown". Every such call would land
        in the 0-25k bin and the context-pressure analysis would print a
        confident flat line built from nothing. An adapter for a corpus without
        token accounting must pass ``api_uuid=None``; this makes forgetting an
        error at write time instead of a plausible number in the writeup.
        """
        usage_by_uuid = {
            ev["uuid"]: ev.get("usage") or {} for ev in self.events if ev["ev"] == "api_call"
        }
        for ev in self.events:
            if ev["ev"] != "tool_call":
                continue
            uuid = ev.get("api_uuid")
            if uuid is None:
                continue
            if uuid not in usage_by_uuid:
                raise ValueError(
                    f"tool_call {ev['id']} joins api_uuid {uuid!r}, which was never emitted"
                )
            if not usage_by_uuid[uuid]:
                raise ValueError(
                    f"tool_call {ev['id']} joins api_call {uuid!r} that carries no token usage. "
                    "Pass api_uuid=None instead — an unjoinable call is reported as unjoinable, "
                    "whereas this would be silently binned as a 0-token context."
                )

    def write(self, manifest_extra: dict | None = None) -> Path:
        self._check_no_phantom_context()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        with (self.out_dir / "events.jsonl").open("w") as handle:
            for ev in self.events:
                handle.write(json.dumps(ev, ensure_ascii=False) + "\n")
        manifest = {
            "schema_version": 1,
            "adapter": self.adapter,
            "shape_mode": self.shape_mode.value,
            "events_by_type": dict(self.counters),
            "provenance": self.notes,
        }
        manifest.update(manifest_extra or {})
        (self.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return self.out_dir
