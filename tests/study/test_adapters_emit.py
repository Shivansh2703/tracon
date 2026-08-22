"""The shared adapter machinery: fingerprints and the export writer.

These tests exist because two things here are load-bearing for the replication
and silently breakable:

* ``shape`` must stay bit-identical to tracon's ``args_shape``, or the public
  corpora are measured with a different ruler than the study's own corpus;
* the writer must refuse to join a tool call to a usage-less api_call, because
  that failure mode does not crash — it produces a fully plausible, entirely
  fabricated context-pressure result.
"""

from __future__ import annotations

import json

import pytest

from agentfail import loader
from agentfail.adapters._emit import (
    ExportWriter,
    ShapeMode,
    exact_signature,
    shape,
)


class TestShape:
    def test_matches_tracon_docstring_example(self):
        assert shape({"command": "ls -la", "description": "x"}) == "command:s6,description:s1"

    def test_matches_a_real_export_line(self):
        # Verbatim from export-2026-07-30/events.jsonl: a Bash call with a
        # 216-char command and a 52-char description.
        args = {"command": "c" * 216, "description": "d" * 52}
        assert shape(args) == "command:s216,description:s52"

    def test_keys_are_sorted_so_dict_order_cannot_move_the_fingerprint(self):
        assert shape({"b": "xx", "a": "y"}) == shape({"a": "y", "b": "xx"}) == "a:s1,b:s2"

    @pytest.mark.parametrize(
        "value,code",
        [
            (True, "b"),  # bool before int: bool is an int subclass
            (False, "b"),
            (3, "i"),
            (3.5, "f"),
            (None, "n"),
            ([1, 2, 3], "a3"),
            ({"k": 1}, "o1"),
            ("abc", "s3"),
        ],
    )
    def test_type_codes(self, value, code):
        assert shape({"k": value}) == f"k:{code}"

    def test_non_dict_input_degrades_to_a_bare_type_code(self):
        assert shape("hello") == "s5"
        assert shape(None) == "n"

    def test_shape_collides_for_same_length_different_content(self):
        """The whole reason the study reports a bracket rather than a number."""
        assert shape({"command": "ls -l"}) == shape({"command": "rm -r"})


class TestExactSignature:
    def test_distinguishes_what_shape_cannot(self):
        a, b = {"command": "ls -l"}, {"command": "rm -r"}
        assert shape(a) == shape(b)
        assert exact_signature(a) != exact_signature(b)

    def test_stable_across_key_order(self):
        assert exact_signature({"a": 1, "b": 2}) == exact_signature({"b": 2, "a": 1})

    def test_survives_unserialisable_values(self):
        assert exact_signature({"k": object()}).startswith("x")


def _writer(tmp_path, **kwargs) -> ExportWriter:
    return ExportWriter(out_dir=tmp_path / "export", adapter="test", **kwargs)


class TestExportWriter:
    def test_round_trips_through_the_real_loader(self, tmp_path):
        w = _writer(tmp_path)
        w.session("s1", "a1", t_start=1000, t_end=5000, end_status="completed")
        w.api_call("s1", "a1", uuid="u1", ts=1000, in_tokens=1234, tool_use_blocks=1)
        w.tool_call(
            "s1", "a1", id="t1", name="Bash", args={"command": "ls"},
            ts=1000, ts_result=2000, duration_ms=1000, api_uuid="u1", result_chars=42,
        )
        corpus = loader.load(w.write())

        stream = corpus.streams[("s1", "a1")]
        assert stream.is_subagent and stream.end_status == "completed"
        call = stream.tool_calls[0]
        assert call["name"] == "Bash"
        assert call["args_shape"] == "command:s2"
        assert corpus.context_tokens(call) == 1234

    def test_shape_mode_exact_changes_only_the_fingerprint(self, tmp_path):
        w = _writer(tmp_path, shape_mode=ShapeMode.EXACT)
        w.session("s1", "a1")
        w.tool_call("s1", "a1", id="t1", name="Bash", args={"command": "ls"})
        corpus = loader.load(w.write())
        assert corpus.streams[("s1", "a1")].tool_calls[0]["args_shape"].startswith("x")

    def test_manifest_records_provenance_and_counts(self, tmp_path):
        w = _writer(tmp_path)
        w.notes["source_url"] = "https://example.invalid/corpus"
        w.session("s1")
        w.tool_call("s1", None, id="t1", name="Bash", is_error=True, duration_ms=5)
        w.tool_call("s1", None, id="t2", name="Bash")
        manifest = json.loads((w.write() / "manifest.json").read_text())

        assert manifest["schema_version"] == 1
        assert manifest["adapter"] == "test"
        assert manifest["shape_mode"] == "shape"
        assert manifest["events_by_type"]["tool_call"] == 2
        assert manifest["events_by_type"]["tool_call_error"] == 1
        assert manifest["events_by_type"]["tool_call_timed"] == 1
        assert manifest["provenance"]["source_url"] == "https://example.invalid/corpus"

    def test_untimed_calls_stay_untimed_rather_than_becoming_zero(self, tmp_path):
        """A corpus with no wall clock must produce *no* long-tail rows."""
        from agentfail.analyses import longtail

        w = _writer(tmp_path)
        w.session("s1")
        for i in range(5):
            w.tool_call("s1", None, id=f"t{i}", name="Bash", duration_ms=None)
        result = longtail.analyze(loader.load(w.write()))
        assert result["timed_calls"] == 0
        assert result["tiers"] == {}
        assert result["total_tool_hours"] == 0.0


class TestPhantomContextGuard:
    def test_rejects_join_to_a_usage_less_api_call(self, tmp_path):
        w = _writer(tmp_path)
        w.session("s1")
        w.api_call("s1", None, uuid="u1", ts=1)  # no token counts available
        w.tool_call("s1", None, id="t1", name="Bash", api_uuid="u1")
        with pytest.raises(ValueError, match="no token usage"):
            w.write()

    def test_rejects_join_to_a_missing_api_call(self, tmp_path):
        w = _writer(tmp_path)
        w.session("s1")
        w.tool_call("s1", None, id="t1", name="Bash", api_uuid="ghost")
        with pytest.raises(ValueError, match="never emitted"):
            w.write()

    def test_unjoined_calls_are_reported_unjoinable_not_binned_at_zero(self, tmp_path):
        from agentfail.analyses import context

        w = _writer(tmp_path)
        w.session("s1")
        w.api_call("s1", None, uuid="u1", ts=1)
        for i in range(5):
            w.tool_call("s1", None, id=f"t{i}", name="Bash", api_uuid=None)
        result = context.analyze(loader.load(w.write()))
        assert result["calls_joined_to_context_size"] == 0
        assert result["calls_unjoinable"] == 5
        assert result["error_rate_by_context_bin"] == {}
