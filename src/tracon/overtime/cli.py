"""``tracon over-time`` — is the fleet getting worse, and which seat is responsible."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tracon.overtime.corpus import Snapshot, read_snapshot
from tracon.overtime.gate import check, render_check
from tracon.overtime.track import build_timeline, render_timeline


class UsageError(Exception):
    """A user-facing error: bad path, bad file. Reported to stderr, exit 2."""


def _load_snapshot(path_str: str) -> Snapshot:
    path = Path(path_str)
    if path.is_dir():
        try:
            return read_snapshot(path)
        except FileNotFoundError as exc:
            raise UsageError(str(exc)) from exc
    if path.is_file() and path.suffix == ".json":
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise UsageError(f"{path}: could not read JSON — {exc}") from exc
        if "snapshots" in data:
            snapshots = data["snapshots"]
            if not snapshots:
                raise UsageError(f"{path}: track JSON has no snapshots")
            try:
                return Snapshot.from_dict(snapshots[-1])
            except (KeyError, ValueError) as exc:
                raise UsageError(f"{path}: invalid snapshot ({exc})") from exc
        try:
            return Snapshot.from_dict(data)
        except KeyError as exc:
            raise UsageError(f"{path}: not a snapshot or track JSON (missing {exc})") from exc
        except ValueError as exc:
            raise UsageError(f"{path}: invalid snapshot ({exc})") from exc
    raise UsageError(f"{path}: not an export directory (no events.jsonl) or a .json file")


def _cmd_track(args: argparse.Namespace) -> int:
    snapshots = [_load_snapshot(p) for p in args.paths]
    timeline = build_timeline(snapshots)
    print(render_timeline(timeline))
    if args.json:
        out = {"snapshots": [s.to_dict() for s in snapshots], "timeline": timeline}
        Path(args.json).write_text(json.dumps(out, indent=2))
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    baseline = _load_snapshot(args.baseline)
    current = _load_snapshot(args.path)
    regressions = check(baseline, current, tolerance=args.tolerance)
    print(render_check(regressions, baseline, current))
    if args.json:
        out = {
            "baseline": baseline.label,
            "current": current.label,
            "regressions": [
                {
                    "metric": r.metric,
                    "display_name": r.display_name,
                    "baseline_value": r.baseline_value,
                    "current_value": r.current_value,
                    "rule": r.rule,
                    "evidence": r.evidence,
                }
                for r in regressions
            ],
        }
        Path(args.json).write_text(json.dumps(out, indent=2))
    return 1 if regressions else 0


def add_subcommand(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "over-time",
        help="is the fleet getting worse — movement across exports, and a gate",
    )
    inner = parser.add_subparsers(dest="over_time_command", required=True)

    track_p = inner.add_parser("track", help="report fleet movement across N snapshots")
    track_p.add_argument("paths", nargs="+", help="export directories or snapshot/track JSON files")
    track_p.add_argument("--json", help="write {snapshots, timeline} to this path")
    track_p.set_defaults(over_time_func=_cmd_track)

    check_p = inner.add_parser("check", help="gate the current snapshot against a baseline")
    check_p.add_argument("path", help="export directory or snapshot/track JSON file")
    check_p.add_argument("--baseline", required=True, help="baseline snapshot or track JSON file")
    check_p.add_argument("--tolerance", type=float, default=0.10)
    check_p.add_argument("--json", help="write the regression report to this path")
    check_p.set_defaults(over_time_func=_cmd_check)

    parser.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """A bad path or a hand-edited baseline is a user error, not a traceback: exit 2."""
    try:
        return args.over_time_func(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
