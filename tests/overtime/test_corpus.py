from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracon.overtime.corpus import Snapshot, read_snapshot


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


def test_unresolvable_workflow_run_stays_in_raw_unaccounted_but_not_resolvable(
    tmp_path: Path,
) -> None:
    lines = [
        {"ev": "session", "agent": "a1", "agent_type": "workflow-subagent", "workflow": "wf_x1"},
        {"ev": "session", "agent": "a2", "agent_type": "workflow-subagent", "end_status": "failed"},
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    assert snap.agents == 2
    assert snap.unaccounted == 1  # unchanged definition — a1 has no end_status
    assert snap.unresolvable == 1
    assert snap.resolvable_agents == 1
    assert snap.unaccounted_resolvable == 0
    assert snap.unaccounted_resolvable_rate == pytest.approx(0.0)

    stats = snap.by_agent_type["workflow-subagent"]
    assert stats.runs == 2
    assert stats.unaccounted == 1
    assert stats.unresolvable == 1
    assert stats.resolvable_runs == 1
    assert stats.unaccounted_resolvable == 0


def test_completed_run_with_workflow_id_is_never_negative(tmp_path: Path) -> None:
    # The reviewer's bounce repro: a run with a non-null workflow id (unresolvable) that ALSO
    # has end_status "completed" (accounted). unaccounted_resolvable must be counted directly
    # (never derived as unaccounted - unresolvable), so it can never go negative here.
    lines = [
        {
            "ev": "session",
            "agent": "a1",
            "agent_type": "workflow-subagent",
            "workflow": "wf_x1",
            "end_status": "completed",
        },
        {
            "ev": "session",
            "agent": "a2",
            "agent_type": "workflow-subagent",
            "end_status": "completed",
        },
        {"ev": "session", "agent": "a3", "agent_type": "workflow-subagent", "end_status": "failed"},
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    assert snap.agents == 3
    assert snap.unaccounted == 0
    assert snap.unresolvable == 1
    assert snap.resolvable_agents == 2
    assert snap.unaccounted_resolvable == 0
    assert snap.unaccounted_resolvable_rate == pytest.approx(0.0)

    stats = snap.by_agent_type["workflow-subagent"]
    assert stats.resolvable_runs == 2
    assert stats.unaccounted_resolvable == 0


def test_workflow_id_never_appears_in_to_dict(tmp_path: Path) -> None:
    sentinel = "wf_super_secret_sentinel_12345"
    lines = [
        {"ev": "session", "agent": "a1", "agent_type": "workflow-subagent", "workflow": sentinel},
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    dumped = json.dumps(snap.to_dict())
    assert sentinel not in dumped


def _valid_snapshot_dict() -> dict:
    return {
        "label": "old",
        "corpus_id": None,
        "schema_version": 1,
        "generated_at": None,
        "sessions": 1,
        "agents": 3,
        "unaccounted": 1,
        "unresolvable": 1,
        "resolvable_agents": 2,
        "unaccounted_resolvable": 0,
        "never_returned": 0,
        "tool_calls": 0,
        "tool_errors": 0,
        "tool_ms_total": 0.0,
        "model_ms_total": 0.0,
        "duration_p50_ms": 0.0,
        "duration_p95_ms": 0.0,
        "duration_p99_ms": 0.0,
        "slowest_call_ms": 0.0,
        "longtail_share_60s": 0.0,
        "tokens": {"in": 0, "out": 0, "cache_read": 0, "cache_create": 0},
        "cache_read_share_p50": 0.0,
        "by_agent_type": {
            "wf": {
                "runs": 3,
                "unaccounted": 1,
                "unresolvable": 1,
                "resolvable_runs": 2,
                "unaccounted_resolvable": 0,
                "tool_ms": 0.0,
                "runtime_ms": 0.0,
            }
        },
    }


def test_from_dict_missing_newer_key_raises() -> None:
    # This package has never released a JSON format predating resolvable_agents/
    # unaccounted_resolvable — to_dict() always emits them, so a dict missing one is malformed,
    # not "older". from_dict must raise, not silently clamp-derive a fabricated value.
    d = _valid_snapshot_dict()
    del d["resolvable_agents"]
    with pytest.raises(KeyError):
        Snapshot.from_dict(d)


def test_from_dict_negative_count_raises_naming_field() -> None:
    d = _valid_snapshot_dict()
    d["unaccounted_resolvable"] = -1
    with pytest.raises(ValueError, match="unaccounted_resolvable"):
        Snapshot.from_dict(d)


def test_from_dict_bool_count_raises() -> None:
    d = _valid_snapshot_dict()
    d["unresolvable"] = True
    with pytest.raises(ValueError, match="unresolvable"):
        Snapshot.from_dict(d)


def test_from_dict_sub_count_exceeding_total_raises() -> None:
    d = _valid_snapshot_dict()
    d["resolvable_agents"] = 5  # > agents(3)
    with pytest.raises(ValueError, match="resolvable_agents"):
        Snapshot.from_dict(d)


def test_from_dict_agent_type_sub_count_exceeding_total_raises() -> None:
    d = _valid_snapshot_dict()
    d["by_agent_type"]["wf"]["unaccounted_resolvable"] = 9  # > resolvable_runs(2)
    with pytest.raises(ValueError, match="unaccounted_resolvable"):
        Snapshot.from_dict(d)


def test_unaccounted_resolvable_nonzero_from_accumulator(tmp_path: Path) -> None:
    # Every other corpus-level fixture in this file lands on unaccounted_resolvable == 0
    # (either no unresolvable-and-unaccounted overlap, or none at all) — this one exercises a
    # resolvable (no workflow id) run that is also unaccounted, directly from the streamed
    # accumulator rather than only via an end-to-end CLI test.
    lines = [
        {"ev": "session", "agent": "a1", "agent_type": "wf"},  # no workflow id, no end_status
        {"ev": "session", "agent": "a2", "agent_type": "wf", "end_status": "completed"},
    ]
    snap = read_snapshot(_write_export(tmp_path, lines))
    assert snap.unaccounted_resolvable == 1
    assert snap.unaccounted_resolvable_rate == pytest.approx(0.5)
    stats = snap.by_agent_type["wf"]
    assert stats.unaccounted_resolvable == 1


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
