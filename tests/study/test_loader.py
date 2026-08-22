"""Tests for tracon.study.loader: stream keying, sort order, and error paths."""

from __future__ import annotations

import json

import pytest
from conftest import make_api_call, make_compact, make_session, make_tool_call

from tracon.study import loader


def test_streams_keyed_by_session_and_agent(export_dir):
    main_call = make_tool_call("s1", None, name="Bash")
    sub_call = make_tool_call("s1", "agent-a", name="Read")
    events = [
        make_session("s1", None),
        make_session("s1", "agent-a", end_status="completed"),
        main_call,
        sub_call,
    ]
    corpus = loader.load(export_dir(events))

    assert set(corpus.streams) == {("s1", None), ("s1", "agent-a")}
    main_stream = corpus.streams[("s1", None)]
    sub_stream = corpus.streams[("s1", "agent-a")]

    assert main_stream.is_subagent is False
    assert sub_stream.is_subagent is True
    assert [c["name"] for c in main_stream.tool_calls] == ["Bash"]
    assert [c["name"] for c in sub_stream.tool_calls] == ["Read"]
    assert sub_stream.end_status == "completed"
    assert main_stream.end_status is None  # main sessions carry no completion record


def test_main_vs_subagent_split_on_corpus(export_dir):
    events = [
        make_session("s1", None),
        make_session("s1", "agent-a", end_status="completed"),
        make_session("s2", None),
    ]
    corpus = loader.load(export_dir(events))
    subs = corpus.subagent_streams
    assert len(subs) == 1
    assert subs[0].key == ("s1", "agent-a")


def test_events_sorted_by_ts_even_when_file_order_is_reversed(export_dir):
    c3 = make_tool_call("s1", None, name="Third", ts=3000, ts_result=3500)
    c1 = make_tool_call("s1", None, name="First", ts=1000, ts_result=1500)
    c2 = make_tool_call("s1", None, name="Second", ts=2000, ts_result=2500)
    # Deliberately written out of chronological order.
    events = [make_session("s1", None), c3, c1, c2]
    corpus = loader.load(export_dir(events))

    stream = corpus.streams[("s1", None)]
    assert [c["name"] for c in stream.tool_calls] == ["First", "Second", "Third"]


def test_orphan_result_sorts_by_ts_result_and_does_not_crash(export_dir):
    normal_1 = make_tool_call("s1", None, name="Before", ts=1000, ts_result=1200)
    orphan = make_tool_call(
        "s1", None, name="Orphan", ts=None, ts_result=1500, status="orphan_result"
    )
    normal_2 = make_tool_call("s1", None, name="After", ts=2000, ts_result=2200)
    events = [make_session("s1", None), normal_2, orphan, normal_1]

    corpus = loader.load(export_dir(events))
    stream = corpus.streams[("s1", None)]

    assert [c["name"] for c in stream.tool_calls] == ["Before", "Orphan", "After"]
    orphan_loaded = stream.tool_calls[1]
    assert orphan_loaded["ts"] is None
    assert orphan_loaded["status"] == "orphan_result"


def test_malformed_json_line_raises_valueerror_with_line_number(tmp_path):
    export = tmp_path / "export"
    export.mkdir()
    lines = [
        json.dumps(make_session("s1", None)),
        "{not valid json",
        json.dumps(make_tool_call("s1", None)),
    ]
    (export / "events.jsonl").write_text("\n".join(lines) + "\n")
    (export / "manifest.json").write_text("{}")

    with pytest.raises(ValueError) as excinfo:
        loader.load(export)
    assert "2" in str(excinfo.value)  # the malformed line is line 2


def test_missing_events_file_raises_filenotfounderror(tmp_path):
    empty_dir = tmp_path / "no-export-here"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        loader.load(empty_dir)


def test_blank_lines_are_skipped(export_dir):
    export = export_dir([make_session("s1", None), make_tool_call("s1", None)])
    # Inject a blank line manually.
    path = export / "events.jsonl"
    text = path.read_text()
    path.write_text(text + "\n\n" + text.splitlines()[-1] + "\n")
    corpus = loader.load(export)  # must not raise
    assert len(corpus.streams[("s1", None)].tool_calls) == 2


class TestContextTokens:
    def test_sums_cache_read_in_and_cache_create(self, export_dir):
        api = make_api_call("s1", None, uuid="api-1", in_tokens=100, cache_read=50, cache_create=25)
        call = make_tool_call("s1", None, api_uuid="api-1")
        events = [make_session("s1", None), api, call]
        corpus = loader.load(export_dir(events))
        stream = corpus.streams[("s1", None)]
        loaded_call = stream.tool_calls[0]
        assert corpus.context_tokens(loaded_call) == 175

    def test_missing_usage_fields_treated_as_zero(self, export_dir):
        api_event = {
            "ev": "api_call",
            "session": "s1",
            "agent": None,
            "ts": 1000,
            "uuid": "api-2",
            "usage": {"in": 10},  # cache_read / cache_create absent
        }
        call = make_tool_call("s1", None, api_uuid="api-2")
        events = [make_session("s1", None), api_event, call]
        corpus = loader.load(export_dir(events))
        stream = corpus.streams[("s1", None)]
        assert corpus.context_tokens(stream.tool_calls[0]) == 10

    def test_returns_none_when_unjoinable(self, export_dir):
        call = make_tool_call("s1", None, api_uuid=None)
        events = [make_session("s1", None), call]
        corpus = loader.load(export_dir(events))
        stream = corpus.streams[("s1", None)]
        assert corpus.context_tokens(stream.tool_calls[0]) is None

    def test_returns_none_when_api_uuid_points_nowhere(self, export_dir):
        call = make_tool_call("s1", None, api_uuid="does-not-exist")
        events = [make_session("s1", None), call]
        corpus = loader.load(export_dir(events))
        stream = corpus.streams[("s1", None)]
        assert corpus.context_tokens(stream.tool_calls[0]) is None


def test_manifest_is_loaded(export_dir):
    events = [make_session("s1", None)]
    manifest = {"schema_version": 1, "generated_at": "2026-01-01"}
    corpus = loader.load(export_dir(events, manifest))
    assert corpus.manifest == manifest


def test_manifest_missing_defaults_to_empty_dict(tmp_path):
    export = tmp_path / "export"
    export.mkdir()
    (export / "events.jsonl").write_text(json.dumps(make_session("s1", None)) + "\n")
    corpus = loader.load(export)
    assert corpus.manifest == {}


def test_compacts_and_notifications_and_queue_ops(export_dir):
    events = [
        make_session("s1", None),
        make_compact("s1", None, trigger="auto"),
        {"ev": "notification", "session": "s1", "agent": None, "ts": 1000, "status": "killed"},
        {"ev": "queue_op", "session": "s1", "agent": None, "ts": 1100, "op": "enqueue"},
    ]
    corpus = loader.load(export_dir(events))
    stream = corpus.streams[("s1", None)]
    assert len(stream.compacts) == 1
    assert len(corpus.notifications) == 1
    # queue_op is not bucketed into any stream field, and does not crash the loader.
