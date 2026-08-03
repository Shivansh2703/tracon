"""Tests for agentfail.analyses.longtail: classify() precedence, tier
thresholds at the boundary, and the never_returned proxy."""

from __future__ import annotations

from agentfail import loader
from agentfail.analyses import longtail
from conftest import build_export


def _call(name="Bash", is_error=False, duration_ms=1000, background=False, **kw):
    return {
        "name": name,
        "is_error": is_error,
        "duration_ms": duration_ms,
        "background": background,
        **kw,
    }


class TestClassifyPrecedence:
    def test_errored_ask_user_question_is_errored_not_waiting_on_human(self):
        call = {"name": "AskUserQuestion", "is_error": True, "background": False}
        assert longtail.classify(call) == "errored"

    def test_errored_agent_wait_tool_is_errored_not_waiting_on_agent(self):
        call = {"name": "Monitor", "is_error": True, "background": False}
        assert longtail.classify(call) == "errored"

    def test_plain_ask_user_question_is_waiting_on_human(self):
        call = {"name": "AskUserQuestion", "is_error": False, "background": False}
        assert longtail.classify(call) == "waiting_on_human"

    def test_exit_plan_mode_is_waiting_on_human(self):
        call = {"name": "ExitPlanMode", "is_error": False, "background": False}
        assert longtail.classify(call) == "waiting_on_human"

    def test_agent_tool_is_waiting_on_agent(self):
        call = {"name": "Agent", "is_error": False, "background": False}
        assert longtail.classify(call) == "waiting_on_agent"

    def test_background_flag_is_waiting_on_agent_regardless_of_tool(self):
        call = {"name": "Bash", "is_error": False, "background": True}
        assert longtail.classify(call) == "waiting_on_agent"

    def test_ordinary_successful_call_is_heavy_work(self):
        call = {"name": "Bash", "is_error": False, "background": False}
        assert longtail.classify(call) == "heavy_work"


class TestTierThresholdBoundary:
    def test_exactly_at_threshold_is_included(self, tmp_path):
        calls = [_call(duration_ms=60_000)]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = longtail.analyze(corpus)
        assert result["tiers"]["ge_60s"]["calls"] == 1

    def test_just_below_threshold_is_excluded(self, tmp_path):
        calls = [_call(duration_ms=59_999)]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = longtail.analyze(corpus)
        assert "ge_60s" not in result["tiers"]  # no calls reach the tier -> omitted

    def test_mixed_around_the_boundary(self, tmp_path):
        calls = [
            _call(duration_ms=59_999),
            _call(duration_ms=60_000),
            _call(duration_ms=61_000),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = longtail.analyze(corpus)
        assert result["tiers"]["ge_60s"]["calls"] == 2
        assert result["timed_calls"] == 3


class TestNeverReturned:
    def test_counts_only_unmatched_status(self, tmp_path):
        calls = [
            _call(name="A", status="matched"),
            _call(name="B", status="unmatched"),
            _call(name="C", status="orphan_result", ts=None),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = longtail.analyze(corpus)
        assert result["never_returned"]["count"] == 1
        assert result["never_returned"]["rate"]["n"] == 1
        assert result["never_returned"]["rate"]["of"] == 3
        assert result["never_returned"]["by_tool"] == [("B", 1)]

    def test_zero_unmatched_gives_zero_count(self, tmp_path):
        calls = [_call(name="A", status="matched"), _call(name="B", status="matched")]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = longtail.analyze(corpus)
        assert result["never_returned"]["count"] == 0
        assert result["never_returned"]["rate"]["n"] == 0
