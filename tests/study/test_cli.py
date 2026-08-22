"""Tests for agentfail.cli: run() subsetting, unknown analysis, main()'s
--json write, and --check drift detection. All against a synthetic corpus —
never the real one."""

from __future__ import annotations

import json

import pytest

from agentfail import cli
from conftest import build_export


def _make_export(tmp_path):
    calls = [
        {"name": "Bash", "args_shape": "command:s10", "is_error": False, "duration_ms": 1000, "result_chars": 20},
        {"name": "Bash", "args_shape": "command:s10", "is_error": True, "duration_ms": 2000, "result_chars": 5},
    ]
    return build_export(
        tmp_path,
        [
            {"session": "s1", "agent": None, "calls": calls},
            {"session": "s1", "agent": "sub-a", "end_status": "completed", "calls": calls},
        ],
    )


class TestRun:
    def test_run_all_analyses_by_default(self, tmp_path):
        export = _make_export(tmp_path)
        result = cli.run(export)
        assert set(result) == set(cli.ANALYSES)

    def test_run_with_only_subset(self, tmp_path):
        export = _make_export(tmp_path)
        result = cli.run(export, only=["corpus", "looping"])
        assert set(result) == {"corpus", "looping"}

    def test_run_unknown_analysis_raises_systemexit(self, tmp_path):
        export = _make_export(tmp_path)
        with pytest.raises(SystemExit) as excinfo:
            cli.run(export, only=["not_a_real_analysis"])
        assert "not_a_real_analysis" in str(excinfo.value)

    def test_run_partial_unknown_mixed_with_known_still_raises(self, tmp_path):
        export = _make_export(tmp_path)
        with pytest.raises(SystemExit):
            cli.run(export, only=["corpus", "bogus"])


class TestMain:
    def test_main_writes_json_file_and_returns_zero(self, tmp_path):
        export = _make_export(tmp_path)
        out_json = tmp_path / "out" / "result.json"
        rc = cli.main(["report", "--trace", str(export), "--json", str(out_json)])
        assert rc == 0
        assert out_json.exists()
        data = json.loads(out_json.read_text())
        assert set(data) == set(cli.ANALYSES)

    def test_main_check_matches_stored_result_returns_zero(self, tmp_path, capsys):
        export = _make_export(tmp_path)
        stored = tmp_path / "stored.json"
        result = cli.run(export)
        stored.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

        rc = cli.main(["report", "--trace", str(export), "--check", str(stored)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "matches" in out

    def test_main_check_detects_drift_returns_one(self, tmp_path, capsys):
        export = _make_export(tmp_path)
        stored = tmp_path / "stored.json"
        stored.write_text(json.dumps({"drifted": True}))

        rc = cli.main(["report", "--trace", str(export), "--check", str(stored)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "DRIFT" in err

    def test_main_only_flag_restricts_output(self, tmp_path):
        export = _make_export(tmp_path)
        out_json = tmp_path / "out2" / "result.json"
        rc = cli.main(
            ["report", "--trace", str(export), "--only", "corpus", "--json", str(out_json)]
        )
        assert rc == 0
        data = json.loads(out_json.read_text())
        assert set(data) == {"corpus"}
