"""Tests for agentfail.analyses.termination: end-status rates, recovery
denominators, and the thin-evidence proxy boundary."""

from __future__ import annotations

from agentfail import loader
from agentfail.analyses import termination
from conftest import build_export


def _call(name="Bash", is_error=False, **kw):
    return {"name": name, "is_error": is_error, **kw}


def test_end_status_counts_and_rates(tmp_path):
    export = build_export(
        tmp_path,
        [
            {"session": "s1", "agent": "a", "end_status": "completed", "calls": [_call()]},
            {"session": "s1", "agent": "b", "end_status": "completed", "calls": [_call()]},
            {"session": "s1", "agent": "c", "end_status": "failed", "calls": [_call(is_error=True)]},
            {"session": "s1", "agent": "d", "end_status": "killed", "calls": [_call()]},
        ],
    )
    corpus = loader.load(export)
    result = termination.analyze(corpus)
    assert result["subagent_runs"] == 4
    assert result["end_status_counts"] == {"completed": 2, "failed": 1, "killed": 1}
    rates = result["end_status_rates"]
    assert rates["completed"]["n"] == 2
    assert rates["completed"]["of"] == 4
    assert rates["failed"]["n"] == 1
    assert rates["killed"]["n"] == 1


def test_recovery_denominator_excludes_streams_with_no_tool_calls(tmp_path):
    export = build_export(
        tmp_path,
        [
            # Has an error, then goes on to complete.
            {
                "session": "s1",
                "agent": "a",
                "end_status": "completed",
                "calls": [_call(is_error=True), _call(is_error=False)],
            },
            # No tool calls at all, but reports completed. Must not count toward
            # either "with_error" or "no_tool_error" recovery denominators.
            {"session": "s1", "agent": "b", "end_status": "completed", "calls": []},
            # Clean run (no error), completed.
            {"session": "s1", "agent": "c", "end_status": "completed", "calls": [_call()]},
        ],
    )
    corpus = loader.load(export)
    result = termination.analyze(corpus)
    recovery = result["recovery"]

    assert recovery["runs_containing_at_least_one_tool_error"] == 1
    assert recovery["error_runs_completed_rate"]["of"] == 1
    assert recovery["error_runs_completed_rate"]["n"] == 1

    assert recovery["runs_with_no_tool_error"] == 1  # only stream c; b is excluded
    assert recovery["clean_runs_completed_rate"]["of"] == 1
    assert recovery["clean_runs_completed_rate"]["n"] == 1


def test_thin_evidence_boundary_two_counts_three_does_not(tmp_path):
    two_calls = [_call(), _call()]
    three_calls = [_call(), _call(), _call()]
    export = build_export(
        tmp_path,
        [
            {"session": "s1", "agent": "a", "end_status": "completed", "calls": two_calls},
            {"session": "s1", "agent": "b", "end_status": "completed", "calls": three_calls},
        ],
    )
    corpus = loader.load(export)
    result = termination.analyze(corpus)
    thin = result["premature_confidence"]["weak_shape_proxy"]
    assert thin["rate"]["of"] == 2  # 2 completed streams total
    assert thin["rate"]["n"] == 1  # only the 2-call stream is "thin"
    assert thin["completed_runs_by_tool_call_count"]["1-2"] == 1
    assert thin["completed_runs_by_tool_call_count"]["3-9"] == 1


def test_thin_evidence_zero_calls_counts_as_thin(tmp_path):
    export = build_export(
        tmp_path,
        [{"session": "s1", "agent": "a", "end_status": "completed", "calls": []}],
    )
    corpus = loader.load(export)
    result = termination.analyze(corpus)
    thin = result["premature_confidence"]["weak_shape_proxy"]
    assert thin["rate"]["n"] == 1
    assert thin["rate"]["of"] == 1
    assert thin["completed_runs_by_tool_call_count"]["0"] == 1


def test_hard_failures_combines_failed_and_killed(tmp_path):
    export = build_export(
        tmp_path,
        [
            {"session": "s1", "agent": "a", "end_status": "completed", "calls": [_call()]},
            {"session": "s1", "agent": "b", "end_status": "failed", "agent_type": "general-purpose", "calls": [_call(is_error=True)]},
            {"session": "s1", "agent": "c", "end_status": "killed", "agent_type": "Explore", "calls": [_call()]},
        ],
    )
    corpus = loader.load(export)
    result = termination.analyze(corpus)
    hard = result["hard_failures"]
    assert hard["failed_or_killed"]["n"] == 2
    assert hard["failed_or_killed"]["of"] == 3
    by_type = dict(hard["by_agent_type"])
    assert by_type == {"general-purpose": 1, "Explore": 1}


def test_unknown_status_default_when_missing(tmp_path):
    export = build_export(
        tmp_path,
        [{"session": "s1", "agent": "a", "end_status": None, "calls": [_call()]}],
    )
    corpus = loader.load(export)
    result = termination.analyze(corpus)
    assert result["end_status_counts"] == {"unknown": 1}
