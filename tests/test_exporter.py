import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tracon.cli import main
from tracon.trace.exporter import Exporter

BASE_MS = 1_750_000_000_000
MARKER = "SECRET"  # every payload in the fixture carries it; none may survive export
MARKER_CMD = f"{MARKER}_CMD"


def iso(offset_ms: int) -> str:
    dt = datetime.fromtimestamp((BASE_MS + offset_ms) / 1000, tz=UTC)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def jl(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def user_line(offset_ms: int, content, **extra) -> dict:
    return {
        "type": "user",
        "timestamp": iso(offset_ms),
        "uuid": f"u-{offset_ms}",
        "parentUuid": None,
        "sessionId": "s1",
        "cwd": f"/Users/test/{MARKER}_dir",
        "gitBranch": f"{MARKER}-branch",
        "entrypoint": "cli",
        "version": "2.1.220",
        "isSidechain": False,
        "message": {"role": "user", "content": content},
        **extra,
    }


def assistant_line(offset_ms: int, msg_id: str, block: dict, **extra) -> dict:
    return {
        "type": "assistant",
        "timestamp": iso(offset_ms),
        "uuid": f"a-{offset_ms}",
        "parentUuid": "u-0",
        "requestId": f"req-{msg_id}",
        "effort": "high",
        "sessionId": "s1",
        "cwd": f"/Users/test/{MARKER}_dir",
        "gitBranch": f"{MARKER}-branch",
        "entrypoint": "cli",
        "version": "2.1.220",
        "isSidechain": False,
        "message": {
            "id": msg_id,
            "role": "assistant",
            "model": "claude-sonnet-5",
            "stop_reason": "tool_use",
            "usage": {
                "input_tokens": 7,
                "output_tokens": 42,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 200,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 50,
                    "ephemeral_1h_input_tokens": 150,
                },
                "service_tier": "standard",
                "speed": "standard",
            },
            "content": [block],
        },
        **extra,
    }


def tool_result_line(offset_ms: int, tool_use_id: str, content: str) -> dict:
    return user_line(
        offset_ms,
        [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}],
    )


@pytest.fixture
def fixture_root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("TRACON_SALT_FILE", str(tmp_path / "salt"))
    root = tmp_path / "projects"
    proj = root / f"-Users-test-{MARKER}proj"

    notif = (
        "<task-notification>\n<task-id>agent-def456</task-id>\n"
        "<tool-use-id>tu_bg</tool-use-id>\n<status>completed</status>\n"
        f"{MARKER}_NOTIF_BODY</task-notification>"
    )
    jl(
        proj / "s1.jsonl",
        [
            user_line(0, f"{MARKER}_PROMPT do the thing"),
            assistant_line(1000, "m1", {"type": "thinking", "thinking": f"{MARKER}_THINKING deep"}),
            assistant_line(1500, "m1", {"type": "text", "text": f"{MARKER}_TEXT"}),
            assistant_line(
                2000,
                "m1",
                {
                    "type": "tool_use",
                    "id": "tu_bash",
                    "name": "Bash",
                    "input": {"command": f"echo {MARKER_CMD}", "description": f"{MARKER}_DSC"},
                },
            ),
            tool_result_line(5000, "tu_bash", f"{MARKER}_RESULT output"),
            assistant_line(
                6000,
                "m2",
                {
                    "type": "tool_use",
                    "id": "tu_sync",
                    "name": "Agent",
                    "input": {"prompt": f"{MARKER}_AGENT_PROMPT"},
                },
            ),
            tool_result_line(20000, "tu_sync", "agent done"),
            assistant_line(
                21000,
                "m3",
                {
                    "type": "tool_use",
                    "id": "tu_bg",
                    "name": "Agent",
                    "input": {"prompt": f"{MARKER}_BG_PROMPT", "run_in_background": True},
                },
            ),
            tool_result_line(21500, "tu_bg", "launched"),
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "timestamp": iso(30000),
                "sessionId": "s1",
                "content": f"{MARKER}_QUEUED",
            },
            user_line(60000, notif, isMeta=True),
            {
                "type": "system",
                "subtype": "turn_duration",
                "timestamp": iso(61000),
                "durationMs": 61000,
                "messageCount": 9,
                "pendingBackgroundAgentCount": 0,
                "sessionId": "s1",
                "version": "2.1.220",
            },
            assistant_line(
                62000,
                "m4",
                {"type": "tool_use", "id": "tu_unmatched", "name": "Read", "input": {}},
            ),
            {"type": "mode", "mode": f"{MARKER}_MODE"},
            {"type": "ai-title", "title": f"{MARKER}_TITLE"},
        ],
    )

    sub = proj / "s1" / "subagents"
    jl(
        sub / "agent-abc123.jsonl",
        [
            user_line(6100, f"{MARKER}_SUBPROMPT", isSidechain=True),
            assistant_line(7000, "am1", {"type": "text", "text": f"{MARKER}_SUBTEXT"}),
        ],
    )
    (sub / "agent-abc123.meta.json").write_text(
        json.dumps(
            {
                "agentType": "sonnet-med",
                "toolUseId": "tu_sync",
                "spawnDepth": 1,
                "description": f"{MARKER}_DESCRIPTION",
            }
        )
    )
    jl(
        sub / "agent-def456.jsonl",
        [
            user_line(22000, f"{MARKER}_BGPROMPT", isSidechain=True),
            assistant_line(23000, "am2", {"type": "text", "text": "ok"}),
        ],
    )
    (sub / "agent-def456.meta.json").write_text(
        json.dumps({"agentType": "claude", "toolUseId": "tu_bg", "spawnDepth": 1})
    )

    wf = sub / "workflows" / "wf_test-1"
    jl(wf / "journal.jsonl", [{"type": "started", "at": iso(0)}])
    jl(
        wf / "agent-999fff.jsonl",
        [assistant_line(40000, "wm1", {"type": "text", "text": "wf work"})],
    )
    (wf / "agent-999fff.meta.json").write_text(json.dumps({"agentType": "claude"}))

    return root


def run_export(root: Path, tmp_path: Path):
    out = tmp_path / "out"
    manifest = Exporter(root=root, out_dir=out).run()
    events = [json.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]
    return manifest, events, out


def by_ev(events, kind):
    return [e for e in events if e["ev"] == kind]


def test_export_structure(fixture_root, tmp_path):
    manifest, events, _ = run_export(fixture_root, tmp_path)

    assert manifest["sessions"] == 1
    assert manifest["agents"] == 3
    assert manifest["journals_skipped"] == 1
    assert manifest["versions_seen"] == ["2.1.220"]
    assert manifest["anomalies"]["unknown_line_types"] == {}
    assert manifest["anomalies"]["parse_errors"] == 0

    sessions = by_ev(events, "session")
    assert len(sessions) == 4
    main_session = next(s for s in sessions if s["agent"] is None)
    assert main_session["t_start"] == BASE_MS
    assert main_session["t_end"] == BASE_MS + 62000
    assert main_session["line_types"]["assistant"] == 6
    assert main_session["entrypoint"] == "cli"


def test_api_call_merging(fixture_root, tmp_path):
    _, events, _ = run_export(fixture_root, tmp_path)
    calls = [e for e in by_ev(events, "api_call") if e["agent"] is None]
    m1 = next(c for c in calls if c["request_id"] == "req-m1")
    assert m1["ts"] == BASE_MS + 1000
    assert m1["ts_last"] == BASE_MS + 2000
    assert m1["blocks"]["thinking"] == 1
    assert m1["blocks"]["text"] == 1
    assert m1["blocks"]["tool_use"] == 1
    assert m1["blocks"]["thinking_chars"] == len(f"{MARKER}_THINKING deep")
    assert m1["usage"]["cache_read"] == 1000
    assert m1["usage"]["cache_create_1h"] == 150
    assert m1["model"] == "claude-sonnet-5"
    assert m1["effort"] == "high"


def test_tool_calls(fixture_root, tmp_path):
    _, events, _ = run_export(fixture_root, tmp_path)
    calls = {c["id"]: c for c in by_ev(events, "tool_call") if c["agent"] is None}

    bash = calls["tu_bash"]
    assert bash["name"] == "Bash"
    assert bash["duration_ms"] == 3000
    assert bash["args_shape"] == "command:s15,description:s10"
    assert bash["result_chars"] == len(f"{MARKER}_RESULT output")
    assert bash["status"] == "matched"
    assert bash["background"] is False

    sync = calls["tu_sync"]
    assert sync["spawned_agent"] == "abc123"
    assert sync["duration_ms"] == 14000

    bg = calls["tu_bg"]
    assert bg["background"] is True
    assert bg["spawned_agent"] == "def456"

    assert calls["tu_unmatched"]["status"] == "unmatched"
    assert calls["tu_unmatched"]["ts_result"] is None


def test_prompt_and_arrival_events(fixture_root, tmp_path):
    _, events, _ = run_export(fixture_root, tmp_path)
    prompts = [p for p in by_ev(events, "prompt") if p["agent"] is None]
    assert len(prompts) == 1
    assert prompts[0]["text_chars"] == len(f"{MARKER}_PROMPT do the thing")

    queue = by_ev(events, "queue_op")
    assert len(queue) == 1
    assert queue[0]["op"] == "enqueue"
    assert queue[0]["content_chars"] == len(f"{MARKER}_QUEUED")

    turns = by_ev(events, "turn")
    assert len(turns) == 1
    assert turns[0]["duration_ms"] == 61000
    assert turns[0]["pending_background_agents"] == 0

    notifs = by_ev(events, "notification")
    assert len(notifs) == 1
    assert notifs[0]["agent_ref"] == "def456"
    assert notifs[0]["status"] == "completed"


def test_agent_linkage_and_status(fixture_root, tmp_path):
    _, events, _ = run_export(fixture_root, tmp_path)
    agents = {s["agent"]: s for s in by_ev(events, "session") if s["agent"]}

    sync = agents["abc123"]
    assert sync["agent_type"] == "sonnet-med"
    assert sync["spawned_by_tool_use"] == "tu_sync"
    assert sync["spawn_depth"] == 1
    assert sync["background"] is False
    assert sync["end_status"] == "completed"

    bg = agents["def456"]
    assert bg["background"] is True
    assert bg["end_status"] == "completed"  # via task-notification

    wf = agents["999fff"]
    assert wf["workflow"] == "wf_test-1"
    assert wf["end_status"] == "unknown"

    sub_prompts = [p for p in by_ev(events, "prompt") if p["agent"] == "abc123"]
    assert len(sub_prompts) == 1
    assert sub_prompts[0]["sidechain"] is True


def test_privacy_invariant(fixture_root, tmp_path):
    """Nothing a human typed or a tool returned survives into the export."""
    _, _, out = run_export(fixture_root, tmp_path)
    for name in ("events.jsonl", "manifest.json"):
        data = (out / name).read_text()
        assert MARKER not in data, f"payload content leaked into {name}"


def test_unknown_line_type_is_loud(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACON_SALT_FILE", str(tmp_path / "salt"))
    root = tmp_path / "projects"
    jl(
        root / "-Users-test-x" / "weird.jsonl",
        [
            user_line(0, "hello"),
            {"type": "brand-new-shape", "timestamp": iso(1), "sessionId": "weird"},
        ],
    )
    out = tmp_path / "out"
    exporter = Exporter(root=root, out_dir=out)
    manifest = exporter.run()
    assert manifest["anomalies"]["unknown_line_types"] == {"brand-new-shape": 1}
    assert exporter.anomalies.any()

    # CLI: loud by default, overridable
    assert main(["export", "--root", str(root), "--out", str(tmp_path / "o2")]) == 2
    assert (
        main(["export", "--root", str(root), "--out", str(tmp_path / "o3"), "--allow-unknown"]) == 0
    )


def test_vanished_file_is_tolerated(tmp_path, monkeypatch):
    """The corpus is live: a transcript found at discovery can vanish before open.
    A broken symlink reproduces that race deterministically."""
    monkeypatch.setenv("TRACON_SALT_FILE", str(tmp_path / "salt"))
    root = tmp_path / "projects"
    proj = root / "-Users-test-z"
    jl(proj / "s1.jsonl", [user_line(0, "hello")])
    sub = proj / "s1" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-gone000.jsonl").symlink_to(sub / "never-existed.jsonl")

    exporter = Exporter(root=root, out_dir=tmp_path / "out")
    manifest = exporter.run()
    assert manifest["files_vanished"] == 1
    assert manifest["sessions"] == 1
    assert manifest["agents"] == 0
    assert not exporter.anomalies.any()


def test_duplicate_lines_deduped_by_uuid(tmp_path, monkeypatch):
    """Claude Code re-appends history chunks (same line uuid) on resume/reconnect;
    the copies must not double-count events or turn results into false orphans."""
    monkeypatch.setenv("TRACON_SALT_FILE", str(tmp_path / "salt"))
    root = tmp_path / "projects"
    use = assistant_line(
        1000, "m1", {"type": "tool_use", "id": "tu_1", "name": "Read", "input": {}}
    )
    result = tool_result_line(2000, "tu_1", "fine")
    # queue-operation lines carry no uuid — deduped by (op, timestamp) instead
    queue = {
        "type": "queue-operation",
        "operation": "enqueue",
        "timestamp": iso(500),
        "content": "q",
    }
    jl(
        root / "-Users-test-d" / "s1.jsonl",
        [user_line(0, "hi"), queue, use, result, use, result, queue],
    )

    exporter = Exporter(root=root, out_dir=tmp_path / "out")
    manifest = exporter.run()
    assert manifest["duplicate_lines"] == 3
    assert manifest["events_by_type"]["tool_call"] == 1
    assert manifest["events_by_type"]["api_call"] == 1
    assert manifest["events_by_type"]["queue_op"] == 1
    assert manifest["orphan_tool_results"] == 0
    assert not exporter.anomalies.any()


def test_orphan_tool_result_recorded_not_fatal(tmp_path, monkeypatch):
    """A result whose issuing assistant line the transcript dropped is understood
    source lossiness: recorded as a tool_call with status orphan_result, counted
    in the manifest, and not a schema anomaly."""
    monkeypatch.setenv("TRACON_SALT_FILE", str(tmp_path / "salt"))
    root = tmp_path / "projects"
    jl(
        root / "-Users-test-y" / "s9.jsonl",
        [tool_result_line(0, "tu_never_issued", "orphan")],
    )
    out = tmp_path / "out"
    exporter = Exporter(root=root, out_dir=out)
    manifest = exporter.run()
    assert manifest["orphan_tool_results"] == 1
    assert not exporter.anomalies.any()
    events = [json.loads(line) for line in (out / "events.jsonl").read_text().splitlines()]
    orphan = next(e for e in by_ev(events, "tool_call"))
    assert orphan["status"] == "orphan_result"
    assert orphan["name"] is None
    assert orphan["ts_result"] == BASE_MS
