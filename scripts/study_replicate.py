"""Print the three headline findings side by side, original corpus vs public one.

Every figure here is read out of a stored ``report`` result object — the same
``python -m agentfail report`` output, produced by the same analyses, over
whichever export it was pointed at. Nothing is recomputed with a second
implementation, because the entire value of the exercise is that the code did
not change when the data did.

    python scripts/replicate.py --study results/study.json \\
        --public <dir>/results-openhands-shape.json \\
        --exact  <dir>/results-openhands-exact.json \\
        --bash-only <dir>/results-openhands-bashonly.json \\
        --by-model <dir>/by-model-*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentfail.stats import two_proportion_test  # noqa: E402


def load(path: str | Path | None) -> dict | None:
    return json.loads(Path(path).read_text()) if path else None


def rate(node: dict) -> str:
    return f"{node['pct']:.2f}% [{node['ci95_pct'][0]:.2f}-{node['ci95_pct'][1]:.2f}] (n={node['n']}/{node['of']})"


def _tier(result: dict, key: str) -> dict | None:
    return (result.get("longtail") or {}).get("tiers", {}).get(key)


def finding_1(study: dict, public: dict) -> list[str]:
    """Elapsed time predicts tool failure."""
    out = ["", "=" * 78, "FINDING 1 - elapsed time predicts tool failure", "=" * 78]
    for label, result in (("original", study), ("public", public)):
        cmp = result["errors"]["error_rate_long_vs_short"]
        tier = _tier(result, "ge_60s")
        out.append(f"  {label:9} >=60s {rate(cmp['ge_60s'])}")
        out.append(f"  {label:9}  <60s {rate(cmp['lt_60s'])}")
        ratio = cmp["ge_60s"]["pct"] / cmp["lt_60s"]["pct"] if cmp["lt_60s"]["pct"] else float("nan")
        out.append(
            f"  {label:9}       enrichment {ratio:.2f}x  z={cmp['test']['z']:.2f}  p={cmp['test']['p']:.3g}"
        )
        if tier:
            out.append(
                f"  {label:9}       the tail is {tier['share_of_calls']['pct']:.2f}% of calls "
                f"holding {tier['share_of_tool_time_pct']:.1f}% of tool time"
            )
        q = result["longtail"]["duration_quantiles_ms"]
        out.append(
            f"  {label:9}       duration p50={q.get('p50', 0):,.0f}ms p99={q.get('p99', 0):,.0f}ms "
            f"max={q.get('max', 0) / 60000:.1f}min"
        )
    return out


def finding_2(study: dict, public: dict) -> list[str]:
    """No context-pressure effect."""
    out = ["", "=" * 78, "FINDING 2 - failures do not rise with context pressure", "=" * 78]
    for label, result in (("original", study), ("public", public)):
        ctx = result["context"]
        t = ctx["trend_test"]
        out.append(
            f"  {label:9} unstratified trend z={t.get('z', 0):+.2f} p={t.get('p', 1):.3g} "
            f"over {ctx['bins_used_in_trend_test']} bins, {ctx['calls_joined_to_context_size']:,} joined calls"
        )
        for tool, node in ctx["trend_test_stratified_by_tool"].items():
            tt = node["trend_test"]
            note = f" ({tt['note']})" if tt.get("note") else ""
            out.append(
                f"  {label:9}   within {tool:<20} n={node['calls']:>6,}  "
                f"z={tt.get('z', 0):+.2f} p={tt.get('p', 1):.3g}{note}"
            )
        bins = ctx["error_rate_by_context_bin"]
        shown = [f"{k}:{v['pct']:.1f}%" for k, v in list(bins.items())[:7]]
        out.append(f"  {label:9}   error rate by bin  {'  '.join(shown)}")
    return out


def finding_3(study: dict, public: dict, exact: dict | None) -> list[str]:
    """Looping barely exists; error handling is adaptive."""
    out = ["", "=" * 78, "FINDING 3 - looping is rare and error handling is adaptive", "=" * 78]
    for label, result in (("original", study), ("public", public)):
        loop = result["looping"]
        lo, hi = loop["lower_bound"], loop["upper_bound"]
        out.append(
            f"  {label:9} calls inside a repeat run   "
            f"{lo['share_of_calls_inside_a_repeat_run']['pct']:.2f}% - "
            f"{hi['share_of_calls_inside_a_repeat_run']['pct']:.2f}%"
        )
        out.append(
            f"  {label:9} runs with a stuck (>=5) run "
            f"{lo['share_of_streams_with_a_stuck_run']['pct']:.2f}% - "
            f"{hi['share_of_streams_with_a_stuck_run']['pct']:.2f}%   "
            f"(of {loop['streams_with_tool_calls']:,} runs with calls)"
        )
        nxt = result["errors"]["after_error_next_tool_call"]
        adaptive = sum(
            nxt.get(k, {}).get("n", 0) for k in ("same_tool_different_arguments", "switched_tool")
        )
        total = result["errors"]["overall_error_rate"]["n"]
        out.append(
            f"  {label:9} blind identical retry       {rate(nxt['retry_identical_shape'])}"
        )
        out.append(f"  {label:9} adaptive next action        {100 * adaptive / total:.2f}% ({adaptive}/{total})")
        stuck = loop["stuck_run_vs_bad_ending"]
        out.append(
            f"  {label:9} bad ending | stuck run      {rate(stuck['with_stuck_run'])}"
            f"   vs no stuck run {rate(stuck['without_stuck_run'])}"
        )
    retry = two_proportion_test(
        public["errors"]["after_error_next_tool_call"]["retry_identical_shape"]["n"],
        public["errors"]["overall_error_rate"]["n"],
        study["errors"]["after_error_next_tool_call"]["retry_identical_shape"]["n"],
        study["errors"]["overall_error_rate"]["n"],
    )
    out.append(f"  difference in blind-retry rate: z={retry['z']:.2f} p={retry['p']:.3g}")

    if exact:
        out += [
            "",
            "  -- how wide is the study's shape-collision bracket, really? --",
            "  The study can only bracket repeats because its arguments are stripped to a",
            "  shape. This corpus has the real arguments, so the same analysis can be run",
            "  over an exact-argument fingerprint and the bracket checked against truth.",
        ]
        for name, result in (("shape lower", public), ("EXACT", exact), ("shape upper", public)):
            bound = "lower_bound" if "lower" in name else "upper_bound" if "upper" in name else "upper_bound"
            v = result["looping"][bound]["share_of_calls_inside_a_repeat_run"]["pct"]
            out.append(f"    {name:<12} {v:.2f}%")
        truth = exact["looping"]["upper_bound"]["share_of_calls_inside_a_repeat_run"]["pct"]
        lo = public["looping"]["lower_bound"]["share_of_calls_inside_a_repeat_run"]["pct"]
        hi = public["looping"]["upper_bound"]["share_of_calls_inside_a_repeat_run"]["pct"]
        out.append(
            f"    -> truth sits at {100 * (truth - lo) / (hi - lo):.0f}% of the way from the study's "
            f"lower bound to its upper; the lower bound is off by {truth - lo:+.2f}pp, "
            f"the upper by {hi - truth:+.2f}pp"
        )
    return out


def sensitivity(public: dict, bash_only: dict | None) -> list[str]:
    if not bash_only:
        return []
    out = [
        "",
        "=" * 78,
        "SENSITIVITY - drop every error that was detected by matching output text",
        "=" * 78,
        "  The editor tools have no status field, so their failures are read off the",
        "  observation body. Restricting to shell calls leaves only real exit codes.",
    ]
    for label, result in (("all tools", public), ("shell only", bash_only)):
        cmp = result["errors"]["error_rate_long_vs_short"]
        t = result["context"]["trend_test"]
        nxt = result["errors"]["after_error_next_tool_call"]
        loop = result["looping"]
        out.append(
            f"  {label:<11} error rate {rate(result['errors']['overall_error_rate'])}"
        )
        ratio = cmp["ge_60s"]["pct"] / cmp["lt_60s"]["pct"] if cmp["lt_60s"]["pct"] else float("nan")
        out.append(
            f"  {label:<11}   F1 >=60s {cmp['ge_60s']['pct']:.2f}% vs {cmp['lt_60s']['pct']:.2f}% "
            f"({ratio:.2f}x, p={cmp['test']['p']:.3g})"
        )
        out.append(f"  {label:<11}   F2 trend z={t.get('z', 0):+.2f} p={t.get('p', 1):.3g}")
        out.append(
            f"  {label:<11}   F3 blind retry {nxt['retry_identical_shape']['pct']:.2f}%, "
            f"stuck runs {loop['lower_bound']['share_of_streams_with_a_stuck_run']['pct']:.2f}-"
            f"{loop['upper_bound']['share_of_streams_with_a_stuck_run']['pct']:.2f}%"
        )
    return out


def by_model(paths: list[str]) -> list[str]:
    """Is the study measuring agents, or measuring one operator's setup?

    If the public numbers moved because benchmark harnesses differ, every model
    should look alike. If they moved because capability differs, the strongest
    models should sit closest to the original corpus.
    """
    if not paths:
        return []
    rows = []
    for path in sorted(paths):
        result = load(path)
        name = Path(path).stem.replace("by-model-", "")
        loop = result["looping"]
        nxt = result["errors"]["after_error_next_tool_call"]
        term = result["termination"]["end_status_counts"]
        rows.append(
            (
                name,
                result["corpus"]["tool_calls"],
                result["errors"]["overall_error_rate"]["pct"],
                nxt.get("retry_identical_shape", {}).get("pct", 0.0),
                loop["lower_bound"]["share_of_streams_with_a_stuck_run"]["pct"],
                loop["upper_bound"]["share_of_streams_with_a_stuck_run"]["pct"],
                100 * term.get("completed", 0) / max(1, sum(term.values())),
            )
        )
    rows.sort(key=lambda r: r[3])
    out = [
        "",
        "=" * 78,
        "PER MODEL - does capability, not harness, explain the divergence?",
        "=" * 78,
        f"  {'model run':<22}{'calls':>8}{'err%':>8}{'retry%':>8}{'stuck% lo-hi':>16}{'finished%':>11}",
    ]
    for name, calls, err, retry, slo, shi, done in rows:
        out.append(
            f"  {name:<22}{calls:>8,}{err:>8.1f}{retry:>8.1f}{slo:>8.1f}-{shi:<7.1f}{done:>11.1f}"
        )
    return out


def ground_truth(export: str | None) -> list[str]:
    """The question the original corpus cannot ask at all.

    Everything in the study measures whether a run *finished*, never whether it
    was *right* — stated there as a limitation on every finding. SWE-bench
    scores each run against the repository's own tests, so on this corpus the
    same structural signals can be tested against a real outcome.
    """
    if not export:
        return []
    from agentfail import loader
    from agentfail.analyses.looping import STUCK_RUN_THRESHOLD, consecutive_runs
    from agentfail.stats import two_proportion_test, wilson

    corpus = loader.load(export)
    scored = [s for s in corpus.subagent_streams if s.session_event.get("resolved") is not None]

    out = [
        "",
        "=" * 78,
        "EXTENSION - does any of this predict a WRONG answer, not just an unfinished one?",
        "=" * 78,
        f"  {len(scored):,} of {len(corpus.subagent_streams):,} runs carry a SWE-bench verdict; "
        f"{wilson(sum(1 for s in scored if s.session_event['resolved']), len(scored))} resolved overall.",
    ]
    checks = [
        (
            "contains a stuck repeat run",
            lambda s: any(r["length"] >= STUCK_RUN_THRESHOLD for r in consecutive_runs(s)),
        ),
        ("contains >=1 tool error", lambda s: any(c["is_error"] for c in s.tool_calls)),
        (
            "harness flagged it looping",
            lambda s: "stuck in a loop" in str(s.session_event.get("harness_error") or ""),
        ),
    ]
    for label, predicate in checks:
        yes = [s for s in scored if predicate(s)]
        no = [s for s in scored if not predicate(s)]
        y = wilson(sum(1 for s in yes if s.session_event["resolved"]), len(yes))
        n = wilson(sum(1 for s in no if s.session_event["resolved"]), len(no))
        t = two_proportion_test(y.numerator, y.denominator, n.numerator, n.denominator)
        out.append(f"  resolved | {label:<28} {y}")
        out.append(f"  resolved | not {label:<24} {n}    z={t['z']:+.2f} p={t['p']:.3g}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="results/study.json")
    parser.add_argument("--public", required=True)
    parser.add_argument("--exact")
    parser.add_argument("--bash-only")
    parser.add_argument("--by-model", nargs="*", default=[])
    parser.add_argument("--export", help="public export dir, for the ground-truth extension")
    args = parser.parse_args(argv)

    study, public = load(args.study), load(args.public)
    lines = ["", "CORPORA", "-" * 78]
    for label, result in (("original", study), ("public", public)):
        corpus = result["corpus"]
        lines.append(
            f"  {label:9} {corpus['tool_calls']:>7,} calls / {corpus['streams']:>6,} streams "
            f"/ {corpus['distinct_tools']} tools / {corpus['span_days']} days"
        )
    lines += finding_1(study, public)
    lines += finding_2(study, public)
    lines += finding_3(study, public, load(args.exact))
    lines += sensitivity(public, load(args.bash_only))
    lines += ground_truth(args.export)
    lines += by_model(args.by_model)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
