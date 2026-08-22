"""``tracon study`` — the failure-mode study, as a subcommand.

Every number in ``docs/study-findings.md`` and ``docs/study-findings.html`` comes out of

    tracon study report --trace <export-dir>

and nothing is transcribed by hand from anywhere else. ``--json`` writes the
full result object; ``--check`` re-runs the study and diffs it against a stored
result so a drifted figure fails loudly instead of quietly.

    tracon study adapt --adapter openhands --out <dir> <files...>

converts a public agent-trajectory corpus into the same export format, so that
``report`` runs the *identical* analyses over it. See ``tracon.study.adapters``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tracon.study import loader
from tracon.study.analyses import context, errors, longtail, looping, summary, termination

ANALYSES = {
    "corpus": summary.analyze,
    "looping": looping.analyze,
    "errors": errors.analyze,
    "longtail": longtail.analyze,
    "context": context.analyze,
    "termination": termination.analyze,
}


def run(trace: str | Path, only: list[str] | None = None) -> dict:
    corpus = loader.load(trace)
    names = only or list(ANALYSES)
    unknown = [n for n in names if n not in ANALYSES]
    if unknown:
        raise SystemExit(f"unknown analysis: {', '.join(unknown)} (have: {', '.join(ANALYSES)})")
    return {name: ANALYSES[name](corpus) for name in names}


def adapt(
    adapter: str,
    inputs: list[str],
    out: Path,
    shape_mode: str,
    limit: int | None,
    only_actions: list[str] | None = None,
) -> Path:
    """Convert a foreign corpus into an export directory the loader accepts."""
    from importlib import import_module

    from tracon.study.adapters import REGISTRY, ShapeMode

    if adapter not in REGISTRY:
        raise SystemExit(f"unknown adapter: {adapter} (have: {', '.join(REGISTRY)})")
    module = import_module(REGISTRY[adapter])
    return module.convert(
        [Path(p) for p in inputs],
        out,
        shape_mode=ShapeMode(shape_mode),
        limit_per_file=limit,
        only_actions=set(only_actions) if only_actions else None,
    )


def _headlines(result: dict) -> list[str]:
    """The handful of figures the writeup leads with, printed for eyeballing."""
    lines = []
    corpus = result.get("corpus")
    if corpus:
        lines.append(
            f"corpus: {corpus['tool_calls']:,} tool calls across {corpus['streams']:,} streams "
            f"({corpus['main_sessions']} sessions + {corpus['subagent_runs']} subagent runs), "
            f"{corpus['span_days']} days"
        )
    err = result.get("errors")
    if err:
        rate = err["overall_error_rate"]
        lines.append(
            f"tool error rate: {rate['pct']}% CI{rate['ci95_pct']} (n={rate['n']}/{rate['of']})"
        )
        kept = err["after_error_model_response"].get("kept_acting")
        if kept:
            lines.append(
                f"after an error the model kept acting: {kept['pct']}% (n={kept['n']}/{kept['of']})"
            )
        retry = err["after_error_next_tool_call"].get("retry_identical_shape")
        if retry:
            lines.append(
                f"blind identical retry after an error: {retry['pct']}% "
                f"(n={retry['n']}/{retry['of']})"
            )
        unres = err["declared_complete_with_unresolved_error"]["rate"]
        lines.append(
            f"completed runs carrying an unresolved error: {unres['pct']}% CI{unres['ci95_pct']} "
            f"(n={unres['n']}/{unres['of']})"
        )
    loop = result.get("looping")
    if loop:
        up = loop["upper_bound"]["share_of_calls_inside_a_repeat_run"]
        lo = loop["lower_bound"]["share_of_calls_inside_a_repeat_run"]
        lines.append(f"calls inside a repeat run: {lo['pct']}%–{up['pct']}% (lower/upper bound)")
    tail = result.get("longtail")
    if tail:
        tier = tail["tiers"].get("ge_60s")
        if tier:
            lines.append(
                f"calls >=60s: {tier['calls']:,} ({tier['share_of_calls']['pct']}% of calls) "
                f"holding {tier['share_of_tool_time_pct']}% of tool time"
            )
    ctx = result.get("context")
    if ctx:
        t = ctx["trend_test"]
        lines.append(
            f"context-size vs error-rate trend: z={t.get('z', 0):.2f} p={t.get('p', 1):.3f}"
        )
    return lines


def add_subcommand(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "study",
        help="why agent runs fail — the failure-mode study, re-run over any export",
        description="Failure-mode analysis of real agent traces",
    )
    parser.add_argument("command", choices=["report", "adapt"], help="what to run")
    parser.add_argument("inputs", nargs="*", help="adapt: source files to convert")
    parser.add_argument("--adapter", help="adapt: which public corpus format the inputs are in")
    parser.add_argument("--out", type=Path, help="adapt: export directory to write")
    parser.add_argument(
        "--shape-mode",
        default="shape",
        choices=["shape", "exact"],
        help="adapt: 'shape' reproduces the study's lossy argument fingerprint; "
        "'exact' uses the real arguments, which the study's own corpus cannot",
    )
    parser.add_argument(
        "--limit-per-file", type=int, help="adapt: stop after N records per input file"
    )
    # Deliberately comma-separated rather than nargs="*": a greedy list flag
    # swallows the trailing positional input files, and the adapter then runs
    # on nothing.
    parser.add_argument(
        "--only-actions",
        help="adapt: comma-separated source actions to keep — used for sensitivity "
        "checks, e.g. --only-actions run keeps the calls whose failure is a real exit code",
    )
    parser.add_argument("--trace", type=Path, help="tracon export directory (see `tracon export`)")
    parser.add_argument("--only", nargs="*", help=f"subset of analyses: {', '.join(ANALYSES)}")
    parser.add_argument("--json", type=Path, help="write the full result object here")
    parser.add_argument(
        "--check", type=Path, help="compare against a stored result and fail on drift"
    )
    parser.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    if args.command == "adapt":
        if not args.adapter or not args.out or not args.inputs:
            raise SystemExit("adapt needs --adapter, --out and at least one input file")
        out = adapt(
            args.adapter,
            args.inputs,
            args.out,
            args.shape_mode,
            args.limit_per_file,
            [a for a in (args.only_actions or "").split(",") if a] or None,
        )
        print(f"wrote {out}")
        return 0

    if args.trace is None:
        raise SystemExit("study report needs --trace <export dir> (make one with `tracon export`)")

    result = run(args.trace, args.only)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json}")

    for line in _headlines(result):
        print(line)

    if args.check:
        stored = json.loads(args.check.read_text())
        # Compare through a JSON round-trip. Counter.most_common() yields tuples
        # that deserialize as lists, so a raw == against a stored file always
        # reports drift and the check silently becomes useless.
        if stored != json.loads(json.dumps(result)):
            print(f"DRIFT: result differs from {args.check}", file=sys.stderr)
            return 1
        print(f"check: matches {args.check}")
    return 0
