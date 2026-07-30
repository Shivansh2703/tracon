import json
from pathlib import Path

from tracon.trace.characterize import Characterizer, characterize, dist

BASE = 1_750_000_000_000


def write_events(path: Path, events: list[dict]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def ev(kind: str, session: str = "s1", agent: str | None = None, **fields) -> dict:
    return {"ev": kind, "session": session, "agent": agent, "ts": fields.pop("ts", BASE), **fields}


def test_dist_nearest_rank():
    d = dist([10.0, 20.0, 30.0, 40.0])
    assert d["n"] == 4
    assert d["p50"] == 20.0
    assert d["p99"] == 40.0
    assert d["max"] == 40.0
    assert d["mean"] == 25.0
    assert dist([]) == {
        "n": 0,
        "mean": 0.0,
        "p50": 0.0,
        "p90": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "max": 0.0,
    }


def _tool(session, agent, ts, dur, name="Bash", **fields):
    return ev(
        "tool_call",
        session,
        agent,
        ts=ts,
        ts_result=ts + dur,
        duration_ms=dur,
        name=name,
        status="matched",
        is_error=False,
        background=False,
        **fields,
    )


def test_tool_latency_shares(tmp_path):
    # three calls: 1s, 9s, 90s → total 100s; ≥10s captures the 90s call only
    events = [
        ev("session", t_start=BASE, t_end=BASE + 200_000),
        _tool("s1", None, BASE, 1_000),
        _tool("s1", None, BASE + 2_000, 9_000),
        _tool("s1", None, BASE + 20_000, 90_000, name="Agent"),
    ]
    write_events(tmp_path, events)
    stats = Characterizer(tmp_path).run()
    tools = stats["tool_latency"]
    assert tools["calls_matched"] == 3
    assert tools["duration_ms"]["p50"] == 9_000
    long_10s = tools["long_calls"]["over_10s"]
    assert long_10s["call_share"] == round(1 / 3, 4)
    assert long_10s["time_share"] == 0.9
    assert tools["by_tool"]["Bash"]["n"] == 2
    assert tools["by_tool"]["Agent"]["time_share"] == 0.9


def test_parallel_overlap_and_fanout(tmp_path):
    # A(0-10s) and B(5-8s) overlap; C(20-21s) is sequential → 1/3 overlap share
    events = [
        ev("session", t_start=BASE, t_end=BASE + 60_000),
        ev("api_call", ts=BASE, ts_last=BASE + 500, blocks={"tool_use": 2}, usage={}),
        ev("api_call", ts=BASE + 19_000, ts_last=BASE + 19_500, blocks={"tool_use": 1}, usage={}),
        ev("api_call", ts=BASE + 30_000, ts_last=BASE + 30_100, blocks={"tool_use": 0}, usage={}),
        _tool("s1", None, BASE, 10_000),
        _tool("s1", None, BASE + 5_000, 3_000),
        _tool("s1", None, BASE + 20_000, 1_000),
    ]
    write_events(tmp_path, events)
    stats = Characterizer(tmp_path).run()
    structure = stats["structure"]
    assert structure["api_calls"] == 3
    assert structure["api_calls_with_tools_share"] == round(2 / 3, 3)
    assert structure["parallel_fanout_share"] == 0.5
    assert structure["fanout_max"] == 2
    assert structure["tool_parallel_overlap_share"] == round(1 / 3, 3)


def test_cache_ratio_and_arrivals(tmp_path):
    events = [
        ev("session", t_start=BASE, t_end=BASE + 100_000),
        ev("prompt", ts=BASE, sidechain=False),
        ev("prompt", ts=BASE + 30_000, sidechain=False),
        ev("queue_op", ts=BASE + 10_000, op="enqueue"),
        ev("queue_op", ts=BASE + 29_000, op="dequeue"),
        ev(
            "api_call",
            ts=BASE + 1_000,
            ts_last=BASE + 2_000,
            blocks={},
            usage={"in": 100, "out": 50, "cache_read": 900, "cache_create": 0},
        ),
    ]
    write_events(tmp_path, events)
    stats = Characterizer(tmp_path).run()
    arrivals = stats["arrivals"]
    assert arrivals["prompts"] == 2
    assert arrivals["inter_arrival_s"]["p50"] == 30.0
    assert arrivals["queue_ops"] == {"enqueue": 1, "dequeue": 1}
    assert arrivals["queue_delivered_share"] == 0.5
    context = stats["context"]
    assert context["cache_read_ratio"]["p50"] == 0.9
    assert context["tokens_total"]["cache_read"] == 900


def test_notification_lag(tmp_path):
    events = [
        ev("session", t_start=BASE, t_end=BASE + 100_000),
        ev(
            "session",
            agent="abc",
            t_start=BASE + 1_000,
            t_end=BASE + 10_000,
            background=True,
            end_status="completed",
            spawn_depth=1,
        ),
        ev("notification", ts=BASE + 25_000, agent_ref="abc", status="completed"),
    ]
    write_events(tmp_path, events)
    stats = Characterizer(tmp_path).run()
    assert stats["structure"]["notification_lag_s"]["p50"] == 15.0
    assert stats["structure"]["agent_end_status"] == {"completed": 1}


def test_characterize_writes_outputs_and_report_renders(tmp_path):
    events = [
        ev("session", t_start=BASE, t_end=BASE + 100_000),
        ev("prompt", ts=BASE, sidechain=False),
        _tool("s1", None, BASE + 1_000, 5_000),
        ev(
            "api_call",
            ts=BASE + 500,
            ts_last=BASE + 900,
            blocks={"tool_use": 1},
            usage={"in": 10, "out": 5, "cache_read": 100, "cache_create": 20},
            model="claude-sonnet-5",
        ),
        ev("turn", ts=BASE + 7_000, duration_ms=7_000, pending_background_agents=0),
    ]
    write_events(tmp_path, events)
    stats = characterize(tmp_path)
    assert (tmp_path / "stats.json").exists()
    report = (tmp_path / "report.md").read_text()
    assert "# Workload characterization" in report
    assert "tool calls" in report
    assert stats["context"]["turns"] == 1
