"""Tests for agentfail.analyses.looping — the most load-bearing module.

Every corpus here is built so the "right answer" (run counts, run lengths,
stream boundaries, bound ordering) is known before the code runs.
"""

from __future__ import annotations

from agentfail import loader
from agentfail.analyses import looping
from conftest import build_export, make_session, make_tool_call


def _call(name="Bash", args_shape="command:s10", result_chars=100, is_error=False, **kw):
    return {
        "name": name,
        "args_shape": args_shape,
        "result_chars": result_chars,
        "is_error": is_error,
        **kw,
    }


class TestConsecutiveRuns:
    def test_no_repeats_gives_no_runs(self, tmp_path):
        calls = [_call(name=f"Tool{i}") for i in range(4)]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        stream = corpus.streams[("s1", None)]
        assert looping.consecutive_runs(stream) == []

    def test_one_run_of_three(self, tmp_path):
        calls = [
            _call(name="A"),
            _call(name="Bash", args_shape="command:s5"),
            _call(name="Bash", args_shape="command:s5"),
            _call(name="Bash", args_shape="command:s5"),
            _call(name="Z"),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        stream = corpus.streams[("s1", None)]
        runs = looping.consecutive_runs(stream)
        assert len(runs) == 1
        assert runs[0]["length"] == 3
        assert runs[0]["tool"] == "Bash"
        assert runs[0]["args_shape"] == "command:s5"

    def test_two_separate_runs(self, tmp_path):
        calls = [
            _call(name="Bash", args_shape="command:s5"),
            _call(name="Bash", args_shape="command:s5"),
            _call(name="Solo"),
            _call(name="Read", args_shape="file_path:s9"),
            _call(name="Read", args_shape="file_path:s9"),
            _call(name="Read", args_shape="file_path:s9"),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        stream = corpus.streams[("s1", None)]
        runs = looping.consecutive_runs(stream)
        assert len(runs) == 2
        lengths = sorted(r["length"] for r in runs)
        assert lengths == [2, 3]

    def test_runs_do_not_span_streams(self, tmp_path):
        # Two separate streams whose calls would merge into one run of 4 if the
        # code wrongly concatenated across streams. Built as one main session
        # and one subagent under it so both streams share the same corpus.
        repeat_call = _call(name="Bash", args_shape="command:s5")
        export = build_export(
            tmp_path,
            [
                {"session": "s1", "agent": None, "calls": [repeat_call, repeat_call]},
                {
                    "session": "s1",
                    "agent": "sub-a",
                    "end_status": "completed",
                    "calls": [repeat_call, repeat_call],
                },
            ],
        )
        corpus = loader.load(export)
        main_stream = corpus.streams[("s1", None)]
        sub_stream = corpus.streams[("s1", "sub-a")]

        main_runs = looping.consecutive_runs(main_stream)
        sub_runs = looping.consecutive_runs(sub_stream)
        assert len(main_runs) == 1 and main_runs[0]["length"] == 2
        assert len(sub_runs) == 1 and sub_runs[0]["length"] == 2
        # And the analyze() aggregate must not report one merged run of 4.
        result = looping.analyze(corpus)
        assert result["upper_bound"]["runs"] == 2
        assert 4 not in result["upper_bound"]["run_length_distribution"]

    def test_stuck_run_threshold_boundary(self, tmp_path):
        run_of_5 = [_call(name="Bash", args_shape="command:s5") for _ in range(5)]
        run_of_4 = [_call(name="Read", args_shape="file_path:s3") for _ in range(4)]
        export = build_export(
            tmp_path,
            [
                {"session": "stuck", "calls": run_of_5},
                {"session": "not-stuck", "calls": run_of_4},
            ],
        )
        corpus = loader.load(export)
        stuck_stream = corpus.streams[("stuck", None)]
        not_stuck_stream = corpus.streams[("not-stuck", None)]

        stuck_runs = looping.consecutive_runs(stuck_stream)
        not_stuck_runs = looping.consecutive_runs(not_stuck_stream)
        assert stuck_runs[0]["length"] == 5
        assert not_stuck_runs[0]["length"] == 4

        result = looping.analyze(corpus)
        stuck_share = result["upper_bound"]["share_of_streams_with_a_stuck_run"]
        # Exactly one of the two streams (the length-5 run) crosses the threshold.
        assert stuck_share["n"] == 1
        assert stuck_share["of"] == 2

    def test_strict_mode_requires_matching_result_chars(self, tmp_path):
        calls = [
            _call(name="Bash", args_shape="command:s5", result_chars=10),
            _call(name="Bash", args_shape="command:s5", result_chars=20),
            _call(name="Bash", args_shape="command:s5", result_chars=20),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        stream = corpus.streams[("s1", None)]

        loose_runs = looping.consecutive_runs(stream, strict=False)
        strict_runs = looping.consecutive_runs(stream, strict=True)
        # loose: all 3 share (name, shape) -> one run of 3
        assert len(loose_runs) == 1 and loose_runs[0]["length"] == 3
        # strict: result_chars differs at position 0 vs 1 -> only calls 2,3 match
        assert len(strict_runs) == 1 and strict_runs[0]["length"] == 2

    def test_errors_in_run_counted(self, tmp_path):
        calls = [
            _call(name="Bash", args_shape="command:s5", is_error=True),
            _call(name="Bash", args_shape="command:s5", is_error=False),
            _call(name="Bash", args_shape="command:s5", is_error=True),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        stream = corpus.streams[("s1", None)]
        runs = looping.consecutive_runs(stream)
        assert runs[0]["errors_in_run"] == 2


class TestLowerBoundLteUpperBound:
    def test_lower_bound_le_upper_bound_when_result_chars_differ(self, tmp_path):
        # Same (name, shape) run of 4, but result_chars differs partway through,
        # so the strict/lower-bound run splits into shorter runs while the
        # loose/upper-bound run stays whole.
        calls = [
            _call(name="Bash", args_shape="command:s5", result_chars=10),
            _call(name="Bash", args_shape="command:s5", result_chars=10),
            _call(name="Bash", args_shape="command:s5", result_chars=99),
            _call(name="Bash", args_shape="command:s5", result_chars=99),
        ]
        export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
        corpus = loader.load(export)
        result = looping.analyze(corpus)

        upper_calls_in_runs = result["upper_bound"]["share_of_calls_inside_a_repeat_run"]["n"]
        lower_calls_in_runs = result["lower_bound"]["share_of_calls_inside_a_repeat_run"]["n"]
        assert lower_calls_in_runs <= upper_calls_in_runs
        assert upper_calls_in_runs == 4  # one run of 4 by (name, shape)
        assert lower_calls_in_runs == 4  # two runs of 2 by (name, shape, result_chars)
        assert result["upper_bound"]["runs"] == 1
        assert result["lower_bound"]["runs"] == 2


def test_analyze_totals_and_run_length_distribution(tmp_path):
    calls = [
        _call(name="Bash", args_shape="command:s5"),
        _call(name="Bash", args_shape="command:s5"),
        _call(name="Solo"),
    ]
    export = build_export(tmp_path, [{"session": "s1", "calls": calls}])
    corpus = loader.load(export)
    result = looping.analyze(corpus)

    assert result["total_tool_calls"] == 3
    assert result["streams_with_tool_calls"] == 1
    assert result["stuck_run_threshold"] == looping.STUCK_RUN_THRESHOLD
    assert result["upper_bound"]["run_length_distribution"] == {2: 1}


def test_stuck_run_vs_bad_ending_scoped_to_subagents(tmp_path):
    run_of_5 = [_call(name="Bash", args_shape="command:s5") for _ in range(5)]
    export = build_export(
        tmp_path,
        [
            {"session": "s1", "agent": None, "calls": run_of_5},  # main session: excluded
            {
                "session": "s1",
                "agent": "sub-a",
                "end_status": "failed",
                "calls": run_of_5,
            },
            {
                "session": "s1",
                "agent": "sub-b",
                "end_status": "completed",
                "calls": [_call(name="Solo")],
            },
        ],
    )
    corpus = loader.load(export)
    result = looping.analyze(corpus)
    scored = result["stuck_run_vs_bad_ending"]
    # Only the two subagent streams are scored, not the main session.
    assert scored["subagent_streams_scored"] == 2
    assert scored["with_stuck_run"]["of"] == 1
    assert scored["with_stuck_run"]["n"] == 1  # sub-a is stuck and failed
    assert scored["without_stuck_run"]["of"] == 1
    assert scored["without_stuck_run"]["n"] == 0  # sub-b has no stuck run and completed
