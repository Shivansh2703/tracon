from __future__ import annotations

import json
from pathlib import Path

from agent_obs.cli import main
from agent_obs.corpus import read_snapshot


def _write_export(tmp_path: Path, name: str, lines: list[dict], generated_at: str) -> Path:
    export_dir = tmp_path / name
    export_dir.mkdir()
    manifest = {"schema_version": 1, "generated_at": generated_at}
    (export_dir / "manifest.json").write_text(json.dumps(manifest))
    with (export_dir / "events.jsonl").open("w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return export_dir


def _lines(unaccounted: int, ok: int) -> list[dict]:
    unaccounted_lines = [
        {"ev": "session", "agent": "a", "end_status": "unknown"} for _ in range(unaccounted)
    ]
    ok_lines = [{"ev": "session", "agent": "a", "end_status": "completed"} for _ in range(ok)]
    return unaccounted_lines + ok_lines


def test_check_clean_exit_zero(tmp_path: Path) -> None:
    baseline_dir = _write_export(
        tmp_path, "baseline", _lines(2, 18), "2026-07-30T00:00:00-04:00"
    )
    current_dir = _write_export(
        tmp_path, "current", _lines(1, 19), "2026-08-14T00:00:00-04:00"
    )
    code = main(["check", "--baseline", str(baseline_dir), str(current_dir)])
    assert code == 0


def test_check_regression_exit_one(tmp_path: Path) -> None:
    baseline_dir = _write_export(
        tmp_path, "baseline", _lines(200, 1800), "2026-07-30T00:00:00-04:00"
    )
    current_dir = _write_export(
        tmp_path, "current", _lines(300, 1700), "2026-08-14T00:00:00-04:00"
    )
    code = main(["check", "--baseline", str(baseline_dir), str(current_dir)])
    assert code == 1


def test_check_bad_path_exit_two(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    code = main(["check", "--baseline", str(missing), str(missing)])
    assert code == 2


def _write_invalid_snapshot(tmp_path: Path, name: str) -> Path:
    export_dir = _write_export(tmp_path, "valid-src", _lines(1, 19), "2026-08-14T00:00:00-04:00")
    d = read_snapshot(export_dir).to_dict()
    d["unaccounted_resolvable"] = -1  # negative count -> from_dict must reject
    path = tmp_path / name
    path.write_text(json.dumps(d))
    return path


def test_check_invalid_baseline_snapshot_exit_two(tmp_path: Path, capsys) -> None:
    bad_baseline = _write_invalid_snapshot(tmp_path, "bad_baseline.json")
    current_dir = _write_export(tmp_path, "current", _lines(1, 19), "2026-08-14T00:00:00-04:00")
    code = main(["check", "--baseline", str(bad_baseline), str(current_dir)])
    assert code == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "unaccounted_resolvable" in captured.err


def test_check_invalid_positional_snapshot_exit_two(tmp_path: Path, capsys) -> None:
    baseline_dir = _write_export(tmp_path, "baseline", _lines(1, 19), "2026-07-30T00:00:00-04:00")
    bad_current = _write_invalid_snapshot(tmp_path, "bad_current.json")
    code = main(["check", "--baseline", str(baseline_dir), str(bad_current)])
    assert code == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "unaccounted_resolvable" in captured.err


def test_track_json_and_baseline_from_track_file(tmp_path: Path) -> None:
    export_dir = _write_export(tmp_path, "solo", _lines(1, 19), "2026-08-14T00:00:00-04:00")
    out_json = tmp_path / "timeline.json"
    code = main(["track", str(export_dir), "--json", str(out_json)])
    assert code == 0
    data = json.loads(out_json.read_text())
    assert "snapshots" in data
    assert "timeline" in data

    # a track --json file used as a baseline uses its last snapshot
    current_dir = _write_export(
        tmp_path, "current", _lines(1, 19), "2026-08-14T00:00:00-04:00"
    )
    code = main(["check", "--baseline", str(out_json), str(current_dir)])
    assert code == 0
