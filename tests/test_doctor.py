"""Tests for ``tracon doctor``.

The detector's whole value is telling an unfinished run from a finished one, so that
distinction is tested directly rather than through the report text.
"""

import json

import pytest

from tracon.doctor import aggregate, diagnose, render, to_json


def write_events(tmp_path, events):
    out = tmp_path / "export"
    out.mkdir()
    (out / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    return out


def agent(agent_id, end_status, t_start=0, t_end=60_000):
    return {
        "ev": "session",
        "session": "s1",
        "agent": agent_id,
        "ts": t_start,
        "t_start": t_start,
        "t_end": t_end,
        "end_status": end_status,
        "agent_type": "worker",
    }


def tool(status="matched", duration_ms=1000, name="Bash", is_error=False):
    return {
        "ev": "tool_call",
        "session": "s1",
        "agent": None,
        "ts": 0,
        "status": status,
        "duration_ms": duration_ms,
        "name": name,
        "is_error": is_error,
    }


def test_unaccounted_counts_every_non_terminal_status(tmp_path):
    """completed and failed are outcomes. Everything else — including a missing status
    and an explicitly 'unknown' one — is a run nobody can account for."""
    out = write_events(
        tmp_path,
        [
            {"ev": "session", "session": "s1", "agent": None, "ts": 0},
            agent("a1", "completed"),
            agent("a2", "failed"),
            agent("a3", "unknown"),
            agent("a4", None),
            agent("a5", "killed"),
        ],
    )
    f = diagnose(out)

    assert f.sessions == 1
    assert f.agents == 5
    # a3, a4, a5 — 'killed' is terminal for the process but is not an outcome for the work.
    assert f.unaccounted == 3
    assert f.unaccounted_rate == pytest.approx(0.6)


def test_unaccounted_examples_are_ranked_by_runtime(tmp_path):
    out = write_events(
        tmp_path,
        [
            agent("short", None, 0, 60_000),
            agent("longest", None, 0, 600_000),
            agent("middle", None, 0, 300_000),
            agent("fine", "completed", 0, 999_000),
        ],
    )
    f = diagnose(out)

    assert [e["agent"] for e in f.unaccounted_examples] == ["longest", "middle", "short"]
    assert f.unaccounted_examples[0]["runtime_min"] == pytest.approx(10.0)


def test_never_returned_and_error_rate(tmp_path):
    out = write_events(
        tmp_path,
        [
            tool(status="matched"),
            tool(status="unmatched"),
            tool(status="orphan_result"),
            tool(status="matched", is_error=True),
        ],
    )
    f = diagnose(out)

    assert f.tool_calls == 4
    assert f.never_returned == 2
    assert f.tool_errors == 1


def test_tool_share_of_busy_time(tmp_path):
    out = write_events(
        tmp_path,
        [
            tool(duration_ms=3000),
            {"ev": "api_call", "session": "s1", "agent": None, "ts": 0, "ts_last": 1000},
        ],
    )
    f = diagnose(out)

    assert f.tool_ms_total == 3000
    assert f.model_ms_total == 1000
    assert f.tool_share == pytest.approx(0.75)


def test_cache_share_and_token_totals(tmp_path):
    out = write_events(
        tmp_path,
        [
            {
                "ev": "api_call",
                "session": "s1",
                "agent": None,
                "ts": 0,
                "usage": {"in": 10, "out": 5, "cache_read": 90, "cache_create": 0},
            }
        ],
    )
    f = diagnose(out)

    assert f.tokens == {"in": 10, "out": 5, "cache_read": 90, "cache_create": 0}
    assert f.cache_shares == [pytest.approx(0.9)]


def test_doctor_reads_only_the_fields_it_declares(tmp_path):
    """doctor must not blindly re-emit event dicts.

    The export is content-free by construction, but a future field could carry something
    that is not. So: plant a marker in fields doctor has no business reading — ``cwd`` and
    ``git_branch`` — and require it never surfaces in either output. If someone later
    "helpfully" dumps whole events into the report, this fails.
    """
    marker = "PLANTED_MARKER_ba9f"
    out = write_events(
        tmp_path,
        [
            {
                "ev": "session",
                "session": "s1",
                "agent": "a1",
                "ts": 0,
                "t_start": 0,
                "t_end": 1000,
                "end_status": None,
                "agent_type": "worker",
                "cwd": marker,
                "git_branch": marker,
            },
            {**tool(), "args_shape": marker},
        ],
    )
    f = diagnose(out)

    assert marker not in render(f)
    assert marker not in json.dumps(to_json(f))
    # and the run itself was still detected — the test would pass vacuously otherwise
    assert f.unaccounted == 1


def test_aggregate_collapses_everything_not_on_the_allow_list(tmp_path):
    """The leak this guards against: MCP tool names are user-installed software.

    `mcp__claude-in-chrome__computer` discloses a browser extension. A private MCP server
    discloses itself. Neither is Claude Code vocabulary, so neither travels.
    """
    out = write_events(
        tmp_path,
        [
            tool(name="Bash", duration_ms=1000),
            tool(name="mcp__claude-in-chrome__computer", duration_ms=2000),
            tool(name="mcp__acme-internal__deploy", duration_ms=500),
        ],
    )
    agg = aggregate(diagnose(out))

    assert agg["tool_ms_by_builtin"] == {"Bash": 1000, "other": 2500}
    blob = json.dumps(agg)
    assert "mcp__" not in blob
    assert "acme" not in blob


def test_aggregate_allow_list_is_load_bearing(monkeypatch, tmp_path):
    """Negative control. With the allow-list emptied, the MCP name must reach the output —
    otherwise the test above proves nothing about the allow-list."""
    out = write_events(tmp_path, [tool(name="mcp__acme-internal__deploy", duration_ms=500)])

    monkeypatch.setattr("tracon.doctor.SHAREABLE_TOOLS", frozenset({"mcp__acme-internal__deploy"}))
    leaked = json.dumps(aggregate(diagnose(out)))
    assert "acme" in leaked


def test_aggregate_never_carries_agent_types_or_run_detail(tmp_path):
    """Custom subagent types are user-named — `opus-med` and `sonnet-med` are one
    operator's own. The aggregate carries counts, never the per-run list."""
    out = write_events(
        tmp_path,
        [agent("a1", None), agent("a2", None, 0, 600_000)],
    )
    agg = aggregate(diagnose(out))

    assert agg["unaccounted"] == 2
    assert "unaccounted_examples" not in agg
    assert "agent_type" not in json.dumps(agg)
    assert "worker" not in json.dumps(agg)


def test_aggregate_takes_only_three_named_manifest_fields(tmp_path):
    """Never the manifest itself — it holds counts and version lists not reviewed for
    sharing, and a future field would travel by default."""
    out = write_events(tmp_path, [tool()])
    manifest = {
        "corpus_id": "t_abc123",
        "schema_version": 1,
        "tracon_version": "0.1.0",
        "root": "t_deadbeef",
        "versions_seen": ["2.1.232"],
        "future_field_nobody_reviewed": "LEAK",
    }
    agg = aggregate(diagnose(out), manifest)

    assert agg["corpus_id"] == "t_abc123"
    assert "LEAK" not in json.dumps(agg)
    assert "versions_seen" not in agg
    assert "root" not in agg


def test_missing_export_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="tracon export"):
        diagnose(tmp_path)
