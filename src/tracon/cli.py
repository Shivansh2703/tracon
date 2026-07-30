"""tracon command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from tracon.trace.characterize import characterize
from tracon.trace.exporter import Exporter

EXIT_OK = 0
EXIT_ANOMALIES = 2


def _cmd_export(args: argparse.Namespace) -> int:
    out_dir = args.out
    if out_dir is None:
        today = datetime.now().astimezone().date().isoformat()
        out_dir = Path("traces") / f"export-{today}"
    exporter = Exporter(root=args.root, out_dir=out_dir)
    manifest = exporter.run()

    print(
        f"exported {manifest['files']} files "
        f"({manifest['sessions']} sessions, {manifest['agents']} agents) "
        f"in {manifest['duration_s']}s → {out_dir}"
    )
    print("events: " + json.dumps(manifest["events_by_type"]))
    if manifest["journals_skipped"]:
        print(
            f"skipped {manifest['journals_skipped']} workflow journal files "
            "(different schema, not walked)"
        )

    if exporter.anomalies.any():
        print(
            "\nSCHEMA ANOMALIES — the transcript format has shapes this exporter "
            "does not understand:",
            file=sys.stderr,
        )
        print(json.dumps(exporter.anomalies.to_dict(), indent=2), file=sys.stderr)
        if not args.allow_unknown:
            print("\nfailing loudly (pass --allow-unknown to export anyway)", file=sys.stderr)
            return EXIT_ANOMALIES
        print("\ncontinuing despite anomalies (--allow-unknown)", file=sys.stderr)
    return EXIT_OK


def _cmd_characterize(args: argparse.Namespace) -> int:
    out = args.out if args.out is not None else args.traces
    stats = characterize(args.traces, out)
    tools = stats["tool_latency"]
    print(
        f"characterized {stats['corpus']['sessions']} sessions / "
        f"{stats['corpus']['agents']} agents → {out}/stats.json, {out}/report.md"
    )
    print(
        f"tool time: {tools['total_hours']}h "
        f"({tools['tool_share_of_busy_time']:.0%} of busy time); "
        f"p50 {tools['duration_ms']['p50'] / 1000:.2f}s "
        f"p99 {tools['duration_ms']['p99'] / 1000:.1f}s"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tracon",
        description="dependency- and session-aware scheduler for agentic LLM workloads",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser(
        "export",
        help="export normalized, payload-stripped trace events from Claude Code transcripts",
    )
    export.add_argument(
        "--root",
        type=Path,
        default=Path("~/.claude/projects"),
        help="transcript root to walk (default: ~/.claude/projects)",
    )
    export.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: traces/export-<today>)",
    )
    export.add_argument(
        "--allow-unknown",
        action="store_true",
        help="exit 0 even when unknown line shapes were seen (they are still reported)",
    )
    export.set_defaults(func=_cmd_export)

    char = sub.add_parser(
        "characterize",
        help="compute workload statistics (stats.json + report.md) over an export",
    )
    char.add_argument(
        "traces",
        type=Path,
        help="export directory containing events.jsonl (+ manifest.json)",
    )
    char.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: the traces directory itself)",
    )
    char.set_defaults(func=_cmd_characterize)

    args = parser.parse_args(argv)
    return args.func(args)
