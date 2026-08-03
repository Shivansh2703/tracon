"""Command line entry point.

Every number in ``docs/FINDINGS.md`` and ``site/index.html`` comes out of

    python -m agentfail report --trace <export-dir>

and nothing is transcribed by hand from anywhere else. ``--json`` writes the
full result object; ``--check`` re-runs the study and diffs it against a stored
result so a drifted figure fails loudly instead of quietly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import loader
from .analyses import context, errors, longtail, looping, summary, termination

DEFAULT_TRACE = "~/Personal/infinity/tracon/traces/export-2026-07-30"

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
        lines.append(f"tool error rate: {rate['pct']}% CI{rate['ci95_pct']} (n={rate['n']}/{rate['of']})")
        kept = err["after_error_model_response"].get("kept_acting")
        if kept:
            lines.append(f"after an error the model kept acting: {kept['pct']}% (n={kept['n']}/{kept['of']})")
        retry = err["after_error_next_tool_call"].get("retry_identical_shape")
        if retry:
            lines.append(f"blind identical retry after an error: {retry['pct']}% (n={retry['n']}/{retry['of']})")
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
        lines.append(f"context-size vs error-rate trend: z={t.get('z', 0):.2f} p={t.get('p', 1):.3f}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentfail", description="Failure-mode analysis of real agent traces")
    parser.add_argument("command", choices=["report"], help="what to run")
    parser.add_argument("--trace", default=DEFAULT_TRACE, help="tracon export directory")
    parser.add_argument("--only", nargs="*", help=f"subset of analyses: {', '.join(ANALYSES)}")
    parser.add_argument("--json", type=Path, help="write the full result object here")
    parser.add_argument("--check", type=Path, help="compare against a stored result and fail on drift")
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    raise SystemExit(main())
