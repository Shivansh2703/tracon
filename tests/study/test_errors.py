"""Tests for tracon.study.analyses.errors: after-error classification and the
declared_complete_with_unresolved_error proxy."""

from __future__ import annotations

from conftest import build_export

from tracon.study import loader
from tracon.study.analyses import errors


def _call(name="Bash", args_shape="command:s10", is_error=False, **kw):
    return {"name": name, "args_shape": args_shape, "is_error": is_error, **kw}


class TestAfterErrorNextToolCall:
    def test_identical_shape_is_retry_identical_shape(self, tmp_path):
        calls = [
            _call(name="Bash", args_shape="command:s10", is_error=True),
            _call(name="Bash", args_shape="command:s10", is_error=False),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        bucket = result["after_error_next_tool_call"]
        assert bucket["retry_identical_shape"]["n"] == 1
        assert "same_tool_different_arguments" not in bucket
        assert "switched_tool" not in bucket

    def test_same_tool_different_shape_bucket(self, tmp_path):
        calls = [
            _call(name="Bash", args_shape="command:s10", is_error=True),
            _call(name="Bash", args_shape="command:s99", is_error=False),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        bucket = result["after_error_next_tool_call"]
        assert bucket["same_tool_different_arguments"]["n"] == 1
        assert "retry_identical_shape" not in bucket

    def test_different_tool_bucket(self, tmp_path):
        calls = [
            _call(name="Bash", args_shape="command:s10", is_error=True),
            _call(name="Read", args_shape="file_path:s10", is_error=False),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        bucket = result["after_error_next_tool_call"]
        assert bucket["switched_tool"]["n"] == 1

    def test_nothing_after_bucket(self, tmp_path):
        calls = [_call(name="Bash", args_shape="command:s10", is_error=True)]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        bucket = result["after_error_next_tool_call"]
        assert bucket["no_further_tool_call"]["n"] == 1

    def test_counts_are_exact_across_all_four_cases_together(self, tmp_path):
        # One stream carrying all four error-then-X shapes, so the totals in
        # after_error_next_tool_call must sum exactly right.
        calls = [
            _call(name="Bash", args_shape="command:s10", is_error=True),
            _call(name="Bash", args_shape="command:s10", is_error=False),  # retry identical
            _call(name="Bash", args_shape="command:s10", is_error=True),
            _call(name="Bash", args_shape="command:s99", is_error=False),  # same tool, diff shape
            _call(name="Bash", args_shape="command:s99", is_error=True),
            _call(name="Read", args_shape="file_path:s10", is_error=False),  # switched
            _call(name="Read", args_shape="file_path:s10", is_error=True),  # nothing after
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        bucket = result["after_error_next_tool_call"]
        assert bucket["retry_identical_shape"]["n"] == 1
        assert bucket["same_tool_different_arguments"]["n"] == 1
        assert bucket["switched_tool"]["n"] == 1
        assert bucket["no_further_tool_call"]["n"] == 1
        assert result["overall_error_rate"]["of"] == 7
        assert result["overall_error_rate"]["n"] == 4


class TestDeclaredCompleteWithUnresolvedError:
    def test_error_followed_by_same_tool_success_does_not_count(self, tmp_path):
        calls = [
            _call(name="Bash", args_shape="command:s10", is_error=True),
            _call(name="Bash", args_shape="command:s99", is_error=False),  # resolves it
        ]
        export = build_export(
            tmp_path,
            [{"session": "s1", "agent": "sub-a", "end_status": "completed", "calls": calls}],
        )
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        rate = result["declared_complete_with_unresolved_error"]["rate"]
        assert rate["n"] == 0
        assert rate["of"] == 1

    def test_error_never_followed_by_success_counts(self, tmp_path):
        calls = [
            _call(name="Bash", args_shape="command:s10", is_error=True),
            _call(name="Read", args_shape="file_path:s10", is_error=False),  # different tool
        ]
        export = build_export(
            tmp_path,
            [{"session": "s1", "agent": "sub-a", "end_status": "completed", "calls": calls}],
        )
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        rate = result["declared_complete_with_unresolved_error"]["rate"]
        assert rate["n"] == 1
        assert rate["of"] == 1

    def test_non_completed_streams_excluded_from_completed_denominator(self, tmp_path):
        completed_ok = [_call(name="Bash", is_error=False)]
        failed_with_error = [_call(name="Bash", is_error=True)]
        export = build_export(
            tmp_path,
            [
                {
                    "session": "s1",
                    "agent": "sub-a",
                    "end_status": "completed",
                    "calls": completed_ok,
                },
                {
                    "session": "s1",
                    "agent": "sub-b",
                    "end_status": "failed",
                    "calls": failed_with_error,
                },
            ],
        )
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        rate = result["declared_complete_with_unresolved_error"]["rate"]
        assert rate["of"] == 1  # only sub-a is "completed"
        assert rate["n"] == 0
        by_status = result["declared_complete_with_unresolved_error"]["by_end_status"]
        assert by_status["failed"]["n"] == 1
        assert by_status["failed"]["of"] == 1

    def test_main_sessions_excluded_declared_complete_proxy(self, tmp_path):
        # Main sessions have no end_status; they must never appear in this proxy.
        calls = [_call(name="Bash", is_error=True)]
        export = build_export(tmp_path, [{"session": "s1", "agent": None, "calls": calls}])
        corpus = loader.load(export)
        result = errors.analyze(corpus)
        rate = result["declared_complete_with_unresolved_error"]["rate"]
        assert rate["of"] == 0
        assert rate["n"] == 0
