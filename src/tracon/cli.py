"""tracon command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from tracon import doctor
from tracon.sim.runner import SimConfig, Simulation, simulate
from tracon.sim.workload import build_workload, replicate_workload
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


def _write_aggregate(traces: Path, findings, out_path: Path) -> None:
    """Write the shareable aggregate and show the user exactly what it holds.

    The bytes are printed before anything else, because consent to share a file you have
    not read is not consent.
    """
    manifest_path = Path(traces) / "manifest.json"
    manifest = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    payload = doctor.aggregate(findings, manifest)
    body = json.dumps(payload, indent=2) + "\n"
    out_path.write_text(body, encoding="utf-8")

    print("\n" + "=" * 72)
    print(doctor.SHARE_NOTICE)
    print(body, end="")
    print("=" * 72)
    print(f"written to {out_path} — nothing has been sent.")


def _cmd_doctor(args: argparse.Namespace) -> int:
    traces = args.traces
    tmp: tempfile.TemporaryDirectory | None = None

    if traces is None:
        # Zero-config path: someone typed `tracon doctor` and expects an answer, not a
        # tutorial about exporting first. Export into a temp dir, read it, throw it away.
        tmp = tempfile.TemporaryDirectory(prefix="tracon-doctor-")
        traces = Path(tmp.name)
        print(f"reading transcripts from {args.root} …", file=sys.stderr)
        exporter = Exporter(root=args.root, out_dir=traces)
        exporter.run()
        if exporter.anomalies.any():
            # Not fatal here. doctor's job is to report on the runs it could read, and a
            # new Claude Code line type should not stop someone seeing their hung agents.
            print(
                "note: this Claude Code version has line shapes tracon does not know yet; "
                "they were skipped. Run `tracon export` to see them.",
                file=sys.stderr,
            )

    try:
        findings = doctor.diagnose(traces)
        print(doctor.render(findings))
        if args.json_out is not None:
            args.json_out.write_text(
                json.dumps(doctor.to_json(findings), indent=2) + "\n", encoding="utf-8"
            )
            print(f"\nfindings written to {args.json_out}")
        if args.share_out is not None:
            _write_aggregate(traces, findings, args.share_out)
    finally:
        if tmp is not None:
            tmp.cleanup()
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


def _cmd_simulate(args: argparse.Namespace) -> int:
    executors = None if args.executors == "inf" else int(args.executors)
    config = SimConfig(
        executors=executors,
        max_batch=args.max_batch,
        max_wait_ms=args.max_wait,
        time_compress=args.compress,
        policy=args.policy,
        replicate=args.replicate,
        cold_penalty_ms=args.cold_penalty,
        resident_streams=args.resident,
    )
    results = simulate(args.traces, config)
    out = args.out
    if out is None:
        tag = "inf" if executors is None else str(executors)
        out = args.traces / (
            f"sim-{args.policy}-x{tag}-b{args.max_batch}-c{args.compress}-r{args.replicate}.json"
        )
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    latency = results["turn_latency_ms"]
    print(
        f"{results['turns_completed']} turns "
        f"(+{results['agent_runs']} agent runs, {results['turns_incomplete']} incomplete) "
        f"→ {out}"
    )
    print(
        f"turn latency p50 {latency['p50'] / 1000:.1f}s p95 {latency['p95'] / 1000:.1f}s "
        f"p99 {latency['p99'] / 1000:.1f}s; "
        f"queue wait p95 {results['queue_wait_ms']['p95'] / 1000:.2f}s; "
        f"utilization {results['utilization']}; "
        f"mean batch {results['batches']['mean_size']}"
    )
    if results["fidelity"]:
        err = results["fidelity"]["abs_rel_error"]
        print(
            f"fidelity vs traced ({results['fidelity']['turns_compared']} turns): "
            f"median abs rel error {err['p50']:.1%}, p90 {err['p90']:.1%}"
        )
    return EXIT_OK


def _cmd_sweep(args: argparse.Namespace) -> int:
    """Policy x load-multiplier comparison matrix — the milestone-4 result table."""
    policies = args.policies.split(",")
    replicates = [int(r) for r in args.replicates.split(",")]
    base = build_workload(args.traces / "events.jsonl")
    rows = []
    for factor in replicates:
        workload = replicate_workload(base, factor)
        for policy in policies:
            config = SimConfig(
                executors=int(args.executors),
                max_batch=args.max_batch,
                max_wait_ms=args.max_wait,
                policy=policy,
                replicate=factor,
                cold_penalty_ms=args.cold_penalty,
                resident_streams=args.resident,
            )
            rows.append(Simulation(workload, config).run())

    args.out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(f"| load | policy | p50 | p95 | p99 | queue p95 | util | warm |  ({args.out})")
    print("|---|---|---|---|---|---|---|---|")
    for row in rows:
        latency, config = row["turn_latency_ms"], row["config"]
        context = row["context"]
        serves = context["warm_serves"] + context["cold_serves"]
        warm = f"{context['warm_serves'] / serves:.0%}" if serves else "—"
        print(
            f"| {config['replicate']}x | {config['policy']} "
            f"| {latency['p50'] / 1000:.1f}s | {latency['p95'] / 1000:.1f}s "
            f"| {latency['p99'] / 1000:.1f}s "
            f"| {row['queue_wait_ms']['p95'] / 1000:.2f}s | {row['utilization']} | {warm} |"
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

    doctor = sub.add_parser(
        "doctor",
        help="what went wrong in your agent runs, and what it cost (runs locally, uploads nothing)",
    )
    doctor.add_argument(
        "traces",
        type=Path,
        nargs="?",
        default=None,
        help="an existing export directory; omit to export from --root into a temp dir first",
    )
    doctor.add_argument(
        "--root",
        type=Path,
        default=Path("~/.claude/projects"),
        help="transcript root to walk when no export is given (default: ~/.claude/projects)",
    )
    doctor.add_argument(
        "--json",
        type=Path,
        default=None,
        dest="json_out",
        help="also write findings as JSON to this path",
    )
    doctor.add_argument(
        "--share",
        type=Path,
        default=None,
        nargs="?",
        const=Path("tracon-aggregate.json"),
        dest="share_out",
        help=(
            "write a shareable aggregate (scalars + built-in tool names only) to this path "
            "and print it. Sends nothing — tracon makes no network calls"
        ),
    )
    doctor.set_defaults(func=_cmd_doctor)

    sim = sub.add_parser(
        "simulate",
        help="replay an export through the simulated backend (DES) and measure latency",
    )
    sim.add_argument("traces", type=Path, help="export directory containing events.jsonl")
    sim.add_argument(
        "--executors",
        default="1",
        help="parallel batch executors, or 'inf' for validation mode (default: 1)",
    )
    sim.add_argument("--max-batch", type=int, default=8, help="dynamic batch size (default: 8)")
    sim.add_argument(
        "--max-wait", type=float, default=10.0, help="batching wait in ms (default: 10)"
    )
    sim.add_argument(
        "--compress", type=float, default=1.0, help="time-compression load factor (default: 1)"
    )
    sim.add_argument("--policy", default="fifo", help="scheduling policy (default: fifo)")
    sim.add_argument(
        "--replicate",
        type=int,
        default=1,
        help="phase-offset workload copies — the load knob (default: 1)",
    )
    sim.add_argument(
        "--cold-penalty",
        type=float,
        default=0.0,
        help="added service ms when a stream's context is cold (default: 0)",
    )
    sim.add_argument(
        "--resident",
        type=int,
        default=4,
        help="per-executor context LRU capacity in streams (default: 4)",
    )
    sim.add_argument("--out", type=Path, default=None, help="results JSON path")
    sim.set_defaults(func=_cmd_simulate)

    sweep = sub.add_parser(
        "sweep",
        help="policy x load-multiplier comparison matrix over an export",
    )
    sweep.add_argument("traces", type=Path, help="export directory containing events.jsonl")
    sweep.add_argument(
        "--policies",
        default="fifo,core-sjf,core-unblock",
        help="comma-separated policy list (default: fifo,core-sjf,core-unblock)",
    )
    sweep.add_argument(
        "--replicates",
        default="1,4,8",
        help="comma-separated load multipliers (default: 1,4,8)",
    )
    sweep.add_argument("--executors", default="1", help="parallel batch executors (default: 1)")
    sweep.add_argument("--max-batch", type=int, default=8, help="dynamic batch size (default: 8)")
    sweep.add_argument(
        "--max-wait", type=float, default=10.0, help="batching wait in ms (default: 10)"
    )
    sweep.add_argument(
        "--cold-penalty",
        type=float,
        default=0.0,
        help="added service ms when a stream's context is cold (default: 0)",
    )
    sweep.add_argument(
        "--resident",
        type=int,
        default=4,
        help="per-executor context LRU capacity in streams (default: 4)",
    )
    sweep.add_argument("--out", type=Path, required=True, help="results JSON path")
    sweep.set_defaults(func=_cmd_sweep)

    args = parser.parse_args(argv)
    return args.func(args)
