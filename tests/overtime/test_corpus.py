from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_obs.corpus import Snapshot, read_snapshot


def _write_export(tmp_path: Path, lines: list[dict], manifest: dict | None = None) -> Path:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "manifest.json").write_text(json.dumps(manifest or {"schema_version": 1}))
    with (export_dir / "events.jsonl").open("w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return export_dir


def _tc(agent: str | None, status: str, duration_ms: float | None) -> dict:
    return {
        "ev": "tool_call",
        "agent": agent,
        "status": status,
        "duration_ms": duration_ms,
        "is_error": False,
    }


def test_missing_events_jsonl_raises(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        read_snapshot(empty_dir)


def test_unaccounted_counts_missing_and_unknown_only_for_subagents(tmp_path: Path) -> None:
    lines = [
        {"ev": "session", "agent": None, "end_status": "failed"},  # main session, never counted
        {"ev": "session", "agent": "a1", "end_status": "completed"},
        {"ev": "session", "agent": "a2", "end_status": "failed"},
        {"ev": "session", "agent": "a3"},  # absent end_status -> unaccounted
        {"ev": "session", "agent": "a4", "end_status": "unknown"},  # unaccounted
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    assert snap.sessions == 1
    assert snap.agents == 4
    assert snap.unaccounted == 2
    assert snap.unaccounted_rate == pytest.approx(0.5)


def test_never_returned_and_null_duration_is_safe(tmp_path: Path) -> None:
    lines = [
        _tc(None, "matched", 100),
        _tc(None, "unmatched", None),
        _tc(None, "orphan_result", None),
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    assert snap.tool_calls == 3
    assert snap.never_returned == 2
    assert snap.never_returned_rate == pytest.approx(2 / 3)
    assert snap.duration_p50_ms == 100  # nulls never entered the quantile stream


def test_agent_type_join_when_session_follows_tool_calls(tmp_path: Path) -> None:
    lines = [
        _tc("a1", "matched", 500),
        _tc("a1", "matched", 300),
        {"ev": "session", "agent": "a1", "agent_type": "sonnet-med", "end_status": "completed"},
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    stats = snap.by_agent_type["sonnet-med"]
    assert stats.runs == 1
    assert stats.tool_ms == 800


def test_untyped_agent_bucket(tmp_path: Path) -> None:
    lines = [
        {"ev": "session", "agent": "a1", "agent_type": None, "end_status": "completed"},
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    assert "(untyped)" in snap.by_agent_type


def test_quantile_definition_pinned(tmp_path: Path) -> None:
    lines = [_tc(None, "matched", d) for d in (1, 2, 3, 4)]
    snap = read_snapshot(_write_export(tmp_path, lines))
    # pinned to tracon doctor's _q: idx = round(p * (n - 1)) -> round(0.5 * 3) == 2 -> value 3
    assert snap.duration_p50_ms == 3
    assert snap.slowest_call_ms == 4


def test_longtail_share_60s_hand_computable(tmp_path: Path) -> None:
    lines = [
        _tc(None, "matched", 60_000),
        _tc(None, "matched", 30_000),
        _tc(None, "matched", 10_000),
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    # total = 100_000, longtail (>=60s) = 60_000
    assert snap.longtail_share_60s == pytest.approx(0.6)


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "manifest.json").write_text("{}")
    with (export_dir / "events.jsonl").open("w") as f:
        f.write("not json at all\n")
        f.write(json.dumps({"ev": "session", "agent": None, "end_status": "completed"}) + "\n")
        f.write("{broken\n")
    snap = read_snapshot(export_dir)
    assert snap.sessions == 1


def test_snapshot_round_trips_through_json(tmp_path: Path) -> None:
    lines = [
        {"ev": "session", "agent": "a1", "agent_type": "haiku-low", "end_status": "completed"},
        _tc("a1", "matched", 50),
        {
            "ev": "api_call",
            "agent": "a1",
            "ts": 100,
            "ts_last": 150,
            "usage": {"in": 10, "out": 5, "cache_read": 2, "cache_create": 1},
        },
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    round_tripped = Snapshot.from_dict(json.loads(json.dumps(snap.to_dict())))
    assert round_tripped == snap
