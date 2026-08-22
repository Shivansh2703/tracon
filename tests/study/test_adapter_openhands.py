"""The OpenHands adapter.

Fixtures here are cut down from real records in
``OpenHands/openhands-evaluation-outputs``
(``claude-3-5-sonnet-20241022_maxiter_100_N_v2.1-no-hint/output.jsonl``), with
the long strings truncated and nothing else changed — field names, nesting and
value types are the real ones, because an adapter test written against an
imagined schema tests nothing.

The assertions concentrate on the four judgement calls documented in the
adapter's module docstring, since those are the places where a quiet mistake
would move a headline number rather than raise.
"""

from __future__ import annotations

import json

import pytest

from agentfail import loader
from agentfail.adapters import openhands
from agentfail.adapters._emit import ExportWriter, ShapeMode

# --------------------------------------------------------------------------
# Fixtures shaped exactly like the real corpus
# --------------------------------------------------------------------------


def _model_response(
    response_id="chatcmpl-1",
    call_id="toolu_1",
    fn="execute_bash",
    arguments='{"command": "ls -la"}',
    prompt=2333,
    cache_read=1274,
    cache_create=1056,
):
    return {
        "id": response_id,
        "choices": [
            {
                "finish_reason": "tool_calls",
                "index": 0,
                "message": {
                    "content": "I'll look around first.",
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 1,
                            "function": {"arguments": arguments, "name": fn},
                            "id": call_id,
                            "type": "function",
                        }
                    ],
                    "function_call": None,
                },
            }
        ],
        "created": 1730139142,
        "model": "claude-3-5-sonnet-20241022",
        "object": "chat.completion",
        "usage": {
            "completion_tokens": 113,
            "prompt_tokens": prompt,
            "total_tokens": prompt + 113,
            "cache_creation_input_tokens": cache_create,
            "cache_read_input_tokens": cache_read,
        },
    }


def bash_action(event_id, ts, command="ls -la", response_id="chatcmpl-1", call_id="toolu_1", **usage):
    return {
        "id": event_id,
        "timestamp": ts,
        "source": "agent",
        "message": f"Running command: {command}",
        "action": "run",
        "tool_call_metadata": {
            "function_name": "execute_bash",
            "tool_call_id": call_id,
            "model_response": _model_response(
                response_id, call_id, "execute_bash", json.dumps({"command": command}), **usage
            ),
            "total_calls_in_response": 1,
        },
        "args": {
            "command": command,
            "thought": "a long private reasoning string that is not an argument",
            "blocking": False,
            "keep_prompt": True,
            "hidden": False,
            "confirmation_state": "confirmed",
        },
    }


def bash_observation(event_id, ts, cause, exit_code=0, content="total 0\n"):
    return {
        "id": event_id,
        "timestamp": ts,
        "source": "agent",
        "message": f"Command executed with exit code {exit_code}.",
        "cause": cause,
        "observation": "run",
        "content": content,
        "extras": {"command_id": -1, "command": "ls -la", "exit_code": exit_code, "hidden": False},
    }


def editor_action(event_id, ts, code="print(file_editor(...))", call_id="toolu_2"):
    return {
        "id": event_id,
        "timestamp": ts,
        "source": "agent",
        "action": "run_ipython",
        "tool_call_metadata": {
            "function_name": "str_replace_editor",
            "tool_call_id": call_id,
            "model_response": _model_response("chatcmpl-2", call_id, "str_replace_editor", json.dumps({"code": code})),
            "total_calls_in_response": 1,
        },
        "args": {"code": code, "thought": "...", "include_extra": False},
    }


def editor_observation(event_id, ts, cause, content="File created successfully at: /workspace/x.py"):
    return {
        "id": event_id,
        "timestamp": ts,
        "source": "agent",
        "cause": cause,
        "observation": "run_ipython",
        "content": content,
        "extras": {"code": "..."},
    }


def finish_action(event_id, ts):
    return {
        "id": event_id,
        "timestamp": ts,
        "source": "agent",
        "message": "I believe I have solved the task.",
        "action": "finish",
        "tool_call_metadata": {
            "function_name": "finish",
            "tool_call_id": "toolu_fin",
            "model_response": _model_response("chatcmpl-fin", "toolu_fin", "finish", "{}"),
            "total_calls_in_response": 1,
        },
        "args": {"outputs": {}, "thought": "summary"},
    }


def record(history, instance_id="astropy__astropy-14182", resolved=True, error=None):
    return {
        "instance_id": instance_id,
        "history": history,
        "error": error,
        "report": {"resolved": resolved, "empty_generation": False, "failed_apply_patch": False},
        "metrics": {"accumulated_cost": 0.1, "costs": []},
    }


T0 = "2024-10-28T18:12:22.190317"
T1 = "2024-10-28T18:12:22.346569"  # +156ms
T2 = "2024-10-28T18:12:29.986337"
T3 = "2024-10-28T18:13:41.334098"


def convert_one(tmp_path, rec, shape_mode=ShapeMode.SHAPE):
    writer = ExportWriter(out_dir=tmp_path / "export", adapter="openhands", shape_mode=shape_mode)
    openhands.convert_record(rec, writer, session="run-under-test")
    return writer, loader.load(writer.write())


# --------------------------------------------------------------------------


class TestFieldMapping:
    def test_a_bash_call_maps_every_field_the_findings_need(self, tmp_path):
        _, corpus = convert_one(
            tmp_path,
            record([bash_action(3, T0), bash_observation(4, T1, cause=3), finish_action(29, T3)]),
        )
        stream = corpus.streams[("run-under-test", "astropy__astropy-14182")]
        (call,) = stream.tool_calls

        assert call["name"] == "run", "identity is the runtime action, stable across versions"
        assert call["function_name"] == "execute_bash"
        assert call["duration_ms"] == 156, "duration is observation.ts - action.ts"
        assert call["is_error"] is False
        assert call["result_chars"] == len("total 0\n")
        assert call["args_shape"] == "command:s6"
        # prompt_tokens already includes the cached parts; the split must sum
        # back to it exactly, because the loader adds all three together.
        assert corpus.context_tokens(call) == 2333

    def test_stream_is_a_subagent_so_termination_analyses_apply(self, tmp_path):
        _, corpus = convert_one(tmp_path, record([bash_action(3, T0), bash_observation(4, T1, 3), finish_action(29, T3)]))
        (stream,) = corpus.subagent_streams
        assert stream.is_subagent
        assert stream.end_status == "completed"
        assert stream.agent_type == "claude-3-5-sonnet-20241022"

    def test_ground_truth_rides_along_on_the_session_event(self, tmp_path):
        """The study's own corpus has no notion of a correct answer; this one does."""
        _, corpus = convert_one(tmp_path, record([finish_action(1, T0)], resolved=False))
        (stream,) = corpus.subagent_streams
        assert stream.session_event["resolved"] is False


class TestErrorSignal:
    def test_nonzero_exit_code_is_an_error(self, tmp_path):
        _, corpus = convert_one(
            tmp_path, record([bash_action(3, T0), bash_observation(4, T1, 3, exit_code=1)])
        )
        assert corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls[0]["is_error"]

    def test_absent_exit_code_is_not_an_error(self, tmp_path):
        """21 of 3,587 real bash observations carry exit_code: null. Unknown is
        not failure, and guessing otherwise would inflate the error rate."""
        obs = bash_observation(4, T1, 3)
        obs["extras"]["exit_code"] = None
        _, corpus = convert_one(tmp_path, record([bash_action(3, T0), obs]))
        assert corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls[0]["is_error"] is False

    def test_editor_error_is_detected_by_content_prefix_and_counted(self, tmp_path):
        writer, corpus = convert_one(
            tmp_path,
            record(
                [
                    editor_action(5, T0),
                    editor_observation(6, T1, 5, content="ERROR:\nNo replacement was performed."),
                ]
            ),
        )
        call = corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls[0]
        assert call["is_error"] is True
        assert call["name"] == "run_ipython"
        # audited in the manifest, because it is a heuristic not a flag
        assert writer.counters["error_signal_editor_ERROR_prefix"] == 1

    def test_successful_editor_output_is_not_an_error(self, tmp_path):
        writer, corpus = convert_one(
            tmp_path, record([editor_action(5, T0), editor_observation(6, T1, 5)])
        )
        assert corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls[0]["is_error"] is False
        assert not [k for k in writer.counters if k.startswith("error_signal_")]

    def test_an_error_mentioned_mid_output_does_not_count(self, tmp_path):
        """The prefix is the signal; a test suite printing 'ERROR' in its body
        is a successful tool call reporting a failing test."""
        _, corpus = convert_one(
            tmp_path,
            record([editor_action(5, T0), editor_observation(6, T1, 5, content="ran tests\nERROR: 3 failed")]),
        )
        assert corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls[0]["is_error"] is False


class TestArgumentFingerprint:
    def test_uses_the_models_arguments_not_the_harness_dict(self, tmp_path):
        """`thought` is prose, near-unique per call; fingerprinting it would
        drive the measured repeat rate to zero whatever the agent did."""
        _, corpus = convert_one(
            tmp_path, record([bash_action(3, T0, command="ls"), bash_observation(4, T1, 3)])
        )
        assert corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls[0]["args_shape"] == "command:s2"

    def test_two_identical_commands_share_a_shape_and_an_exact_signature(self, tmp_path):
        history = [
            bash_action(3, T0, command="pytest", call_id="a", response_id="r1"),
            bash_observation(4, T1, 3),
            bash_action(5, T2, command="pytest", call_id="b", response_id="r2"),
            bash_observation(6, T3, 5),
        ]
        for mode in (ShapeMode.SHAPE, ShapeMode.EXACT):
            _, corpus = convert_one(tmp_path / mode.value, record(history), shape_mode=mode)
            shapes = [c["args_shape"] for c in corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls]
            assert shapes[0] == shapes[1], mode

    def test_different_commands_of_equal_length_collide_under_shape_only(self, tmp_path):
        history = [
            bash_action(3, T0, command="ls -l", call_id="a", response_id="r1"),
            bash_observation(4, T1, 3),
            bash_action(5, T2, command="rm -r", call_id="b", response_id="r2"),
            bash_observation(6, T3, 5),
        ]
        _, shape_corpus = convert_one(tmp_path / "s", record(history), shape_mode=ShapeMode.SHAPE)
        _, exact_corpus = convert_one(tmp_path / "x", record(history), shape_mode=ShapeMode.EXACT)
        key = ("run-under-test", "astropy__astropy-14182")
        shape_sigs = [c["args_shape"] for c in shape_corpus.streams[key].tool_calls]
        exact_sigs = [c["args_shape"] for c in exact_corpus.streams[key].tool_calls]
        assert shape_sigs[0] == shape_sigs[1], "the study's encoding cannot tell these apart"
        assert exact_sigs[0] != exact_sigs[1], "the exact encoding can"

    def test_falls_back_to_semantic_args_when_no_function_call_is_recorded(self, tmp_path):
        """The `non-fncall` configs parse a text-formatted call; there is no
        tool_calls block to read the literal arguments from."""
        action = bash_action(3, T0, command="ls -la")
        action["tool_call_metadata"]["model_response"]["choices"][0]["message"]["tool_calls"] = []
        _, corpus = convert_one(tmp_path, record([action, bash_observation(4, T1, 3)]))
        # 'command' survives; 'thought' and the harness flags do not
        assert corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls[0]["args_shape"] == "command:s6"

    def test_arguments_are_matched_by_tool_call_id_not_by_position(self, tmp_path):
        action = bash_action(3, T0, command="ls -la", call_id="wanted")
        message = action["tool_call_metadata"]["model_response"]["choices"][0]["message"]
        message["tool_calls"].insert(
            0,
            {
                "index": 0,
                "function": {"arguments": json.dumps({"command": "x" * 999}), "name": "execute_bash"},
                "id": "other",
                "type": "function",
            },
        )
        _, corpus = convert_one(tmp_path, record([action, bash_observation(4, T1, 3)]))
        assert corpus.streams[("run-under-test", "astropy__astropy-14182")].tool_calls[0]["args_shape"] == "command:s6"


class TestFinishIsNotAToolCall:
    def test_finish_produces_no_tool_call(self, tmp_path):
        """Otherwise every run contributes a phantom never-returned call and the
        study's 0.029% extreme-tail figure becomes meaningless."""
        _, corpus = convert_one(tmp_path, record([finish_action(29, T3)]))
        stream = corpus.streams[("run-under-test", "astropy__astropy-14182")]
        assert stream.tool_calls == []

    def test_finish_is_a_model_turn_that_issued_no_tool(self, tmp_path):
        """So that an error followed by `finish` is scored as 'stopped working',
        not as 'kept acting'."""
        writer, corpus = convert_one(
            tmp_path,
            record([bash_action(3, T0), bash_observation(4, T1, 3, exit_code=1), finish_action(29, T3)]),
        )
        from agentfail.analyses import errors

        result = errors.analyze(corpus)
        assert result["after_error_model_response"]["text_only_response"]["n"] == 1
        assert "kept_acting" not in result["after_error_model_response"]

    def test_the_task_prompt_is_not_counted_as_a_model_turn(self, tmp_path):
        prompt = {"id": 0, "timestamp": T0, "source": "user", "action": "message", "args": {"content": "fix it"}}
        writer, _ = convert_one(tmp_path, record([prompt, finish_action(29, T3)]))
        assert writer.counters.get("model_turn_message") is None


class TestEndStatus:
    @pytest.mark.parametrize(
        "history,error,expected",
        [
            ([finish_action(1, T0)], None, "completed"),
            ([bash_action(3, T0), bash_observation(4, T1, 3)], None, "killed"),
            ([finish_action(1, T0)], "Agent got stuck in a loop", "failed"),
        ],
    )
    def test_status_inference(self, tmp_path, history, error, expected):
        _, corpus = convert_one(tmp_path, record(history, error=error))
        assert corpus.subagent_streams[0].end_status == expected

    def test_killed_means_hit_the_step_cap_not_operator_intervention(self, tmp_path):
        """Named for the reader: the study's `killed` is a human stopping a run.
        Here it is the harness's maxiter. Same label, different cause."""
        _, corpus = convert_one(tmp_path, record([bash_action(3, T0), bash_observation(4, T1, 3)]))
        assert corpus.subagent_streams[0].end_status == "killed"


class TestUnmatchedAndOrphans:
    def test_an_action_with_no_observation_is_marked_unmatched(self, tmp_path):
        writer, corpus = convert_one(tmp_path, record([bash_action(3, T0)]))
        (call,) = corpus.subagent_streams[0].tool_calls
        assert call["status"] == "unmatched"
        assert call["duration_ms"] is None
        assert writer.counters["unmatched_tool_call"] == 1

    def test_an_orphan_observation_is_ignored_rather_than_invented_into_a_call(self, tmp_path):
        orphan = bash_observation(99, T1, cause=12345)
        _, corpus = convert_one(tmp_path, record([bash_action(3, T0), bash_observation(4, T1, 3), orphan]))
        assert len(corpus.subagent_streams[0].tool_calls) == 1


class TestConvertFile:
    def test_converts_a_jsonl_file_and_records_provenance(self, tmp_path):
        src = tmp_path / "sonnet_v21.jsonl"
        src.write_text(
            "\n".join(
                json.dumps(
                    record(
                        [bash_action(3, T0), bash_observation(4, T1, 3), finish_action(29, T3)],
                        instance_id=f"proj__proj-{i}",
                    )
                )
                for i in range(3)
            )
            + "\n"
        )
        out = openhands.convert([src], tmp_path / "export")
        corpus = loader.load(out)

        assert len(corpus.subagent_streams) == 3
        assert {s.key[0] for s in corpus.streams.values()} == {"sonnet_v21"}
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["adapter"] == "openhands"
        assert manifest["provenance"]["sources"][0]["instances"] == 3
        assert "openhands-evaluation-outputs" in manifest["provenance"]["url"]

    def test_limit_per_file_truncates(self, tmp_path):
        src = tmp_path / "run.jsonl"
        src.write_text("\n".join(json.dumps(record([finish_action(1, T0)], instance_id=f"i{i}")) for i in range(5)))
        corpus = loader.load(openhands.convert([src], tmp_path / "export", limit_per_file=2))
        assert len(corpus.subagent_streams) == 2


class TestOlderPairedHistory:
    """The v1.9-era runs store history as [action, observation] pairs and use a
    different file editor. Eight of the thirteen runs in the replication corpus
    are in this format; skipping it silently emptied 62% of the corpus once."""

    def paired_record(self, **kw):
        return record(
            [
                [bash_action(3, T0), bash_observation(4, T1, cause=3)],
                [editor_action(5, T2), editor_observation(6, T3, cause=5)],
            ],
            **kw,
        )

    def test_paired_history_is_flattened_not_dropped(self, tmp_path):
        _, corpus = convert_one(tmp_path, self.paired_record())
        calls = corpus.subagent_streams[0].tool_calls
        assert [c["name"] for c in calls] == ["run", "run_ipython"]
        assert calls[0]["duration_ms"] == 156

    def test_mixed_layouts_in_one_record_both_survive(self, tmp_path):
        rec = record([[bash_action(3, T0), bash_observation(4, T1, 3)], editor_action(5, T2), editor_observation(6, T3, 5)])
        _, corpus = convert_one(tmp_path, rec)
        assert len(corpus.subagent_streams[0].tool_calls) == 2

    @pytest.mark.parametrize(
        "content,expected,label",
        [
            ("[File: /workspace/x.py (10 lines total)]", False, None),
            ("[File: /workspace/x.py (10 lines total after edit)]", False, None),
            ("[No exact match found in /workspace/x.py for ...]", True, "editor_no_exact_match"),
            ("[Your proposed edit has introduced new syntax error(s).", True, "editor_syntax_error"),
            ("ERROR: File /workspace/x.py not found.", True, "editor_ERROR_prefix"),
            ("[Code executed successfully with no output]", False, None),
            ("[Found 2 matches for \"models.py\" in /workspace]", False, None),
            ("Cell In[1], line 3\n  bad syntax", True, "cell_traceback"),
        ],
    )
    def test_v19_editor_vocabulary(self, tmp_path, content, expected, label):
        """Templates taken from the real v1.9 runs, in proportion to how often
        they occur; the successes matter as much as the failures, since a loose
        marker would turn ordinary file reads into a doubled error rate."""
        writer, corpus = convert_one(
            tmp_path, record([editor_action(5, T0), editor_observation(6, T1, 5, content=content)])
        )
        assert corpus.subagent_streams[0].tool_calls[0]["is_error"] is expected
        if label:
            assert writer.counters[f"error_signal_{label}"] == 1

    def test_calls_without_token_usage_are_left_unjoined(self, tmp_path):
        """v1.9 records carry no per-call usage, so those calls must drop out of
        the context analysis rather than being binned at zero tokens."""
        action = bash_action(3, T0)
        del action["tool_call_metadata"]["model_response"]["usage"]
        _, corpus = convert_one(tmp_path, record([action, bash_observation(4, T1, 3)]))
        call = corpus.subagent_streams[0].tool_calls[0]
        assert call["api_uuid"] is None
        assert corpus.context_tokens(call) is None

    def test_an_action_with_no_tool_metadata_at_all_still_becomes_a_call(self, tmp_path):
        action = {
            "id": 3, "timestamp": T0, "source": "agent", "action": "run",
            "args": {"command": "ls -la", "thought": "...", "blocking": False},
        }
        _, corpus = convert_one(tmp_path, record([[action, bash_observation(4, T1, 3)]]))
        call = corpus.subagent_streams[0].tool_calls[0]
        assert call["name"] == "run" and call["function_name"] is None
        assert call["args_shape"] == "command:s6"


class TestModelTurnsWithoutTokenAccounting:
    """Eight of the thirteen runs record no per-call usage. The turn must still
    be emitted or 'after an error, did the model keep acting?' silently reads as
    'no further model call' for most of the corpus — which is what a first cut
    of this adapter did, dropping the figure from 98% to 47%."""

    def _untokened(self, event_id, ts, **kw):
        action = bash_action(event_id, ts, **kw)
        del action["tool_call_metadata"]
        return action

    def test_the_turn_is_emitted_and_counts_as_tool_use(self, tmp_path):
        from agentfail.analyses import errors

        rec = record(
            [
                [self._untokened(3, T0), bash_observation(4, T1, 3, exit_code=1)],
                [self._untokened(5, T2), bash_observation(6, T3, 5)],
            ]
        )
        writer, corpus = convert_one(tmp_path, rec)
        result = errors.analyze(corpus)
        assert result["after_error_model_response"]["kept_acting"]["n"] == 1
        assert writer.counters["call_without_token_usage"] == 2

    def test_but_the_call_stays_out_of_the_context_analysis(self, tmp_path):
        from agentfail.analyses import context

        rec = record([[self._untokened(3, T0), bash_observation(4, T1, 3)]])
        _, corpus = convert_one(tmp_path, rec)
        assert context.analyze(corpus)["calls_unjoinable"] == 1


class TestOnlyActionsFilter:
    """The sensitivity lever: a corpus in which every error is a real exit code."""

    def test_filters_to_the_named_actions(self, tmp_path):
        src = tmp_path / "run.jsonl"
        src.write_text(
            json.dumps(
                record([bash_action(3, T0), bash_observation(4, T1, 3), editor_action(5, T2), editor_observation(6, T3, 5)])
            )
        )
        corpus = loader.load(openhands.convert([src], tmp_path / "export", only_actions={"run"}))
        names = [c["name"] for c in corpus.subagent_streams[0].tool_calls]
        assert names == ["run"]
        manifest = json.loads((tmp_path / "export" / "manifest.json").read_text())
        assert manifest["provenance"]["only_actions"] == ["run"]
        assert manifest["events_by_type"]["filtered_out_run_ipython"] == 1

    def test_unfiltered_by_default(self, tmp_path):
        src = tmp_path / "run.jsonl"
        src.write_text(json.dumps(record([bash_action(3, T0), bash_observation(4, T1, 3), editor_action(5, T2), editor_observation(6, T3, 5)])))
        corpus = loader.load(openhands.convert([src], tmp_path / "export"))
        assert len(corpus.subagent_streams[0].tool_calls) == 2
