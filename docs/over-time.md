# tracon over-time — is the fleet getting worse

**Your fleet's health, over time.** Reads two or more tracon trace exports captured at different
moments and reports what *moved* — with a gate that exits non-zero when a number genuinely got
worse.

## Where it sits

Three questions, one export directory answering all of them. This is the third.

| | question |
|---|---|
| `tracon study` | what do 85,104 real tool calls say about how agent runs fail? |
| `tracon doctor` | what happened in **this one** corpus, against published base rates? |
| **`tracon over-time`** | **is my fleet getting worse, and which seat is responsible?** |

One reading of a moving number is not a state. `doctor` gives you today's numbers; this tells you
whether today is worse than last month, and which part of the fleet moved.

## Use

```sh
# what moved across your exports
tracon over-time track traces/export-2026-07-30 traces/export-2026-08-14 --json fleet.json

# the gate: exit 1 if something regressed against a baseline
tracon over-time check --baseline fleet.json traces/export-2026-08-22
```

Or without installing, from a checkout: `PYTHONPATH=src python -m tracon over-time track …`

`check` exits **0** clean, **1** on regression, **2** on a bad input — so it drops into CI or a
pre-merge hook without a wrapper. Either command takes an export directory or a previously
written `--json` snapshot, so you can keep kilobytes of history instead of 80 MB of events.

## How the gate decides

What makes a gate survive contact with its owner is not firing when nothing happened.

**Rates get a significance test, not a threshold.** Unaccounted rate, never-returned rate and
tool error rate have a real numerator and denominator, so a move counts as a regression only if a
two-proportion test says so at p < 0.05 *in the worsening direction*. Corpora differ in size, and
a gate that fires because 2/20 became 3/20 gets switched off within a week.

**Improvements are never flagged.** In the reference corpora the single largest move in the
unaccounted rate is an improvement, and it is statistically significant. A gate that reports that
as a regression is worse than no gate.

**Metrics with no n fall back to thresholds** — p95, p99 and long-tail share gate on relative
change past an absolute floor, and the output says which rule fired for each finding.

**Metrics with no obviously-bad direction are reported and never gated** — tool share of busy
time and cache-read share move for reasons that are not faults.

## Runs whose outcome was never capturable

Some runs cannot be resolved from a trace export at all — not because they failed, but because
the export carries no outcome for them. They are counted in the raw rate, excluded from the
corrected one, and the report says so in band.

This is not hypothetical, and it is why the distinction exists. On the reference corpora, roughly
**half** the runs that look unaccounted in the August exports are of this kind, and about a third
in July:

| corpus | unaccounted (raw) | corrected |
|---|---|---|
| 2026-07-30 | 20.36% | **15.25%** |
| 2026-08-14 | 16.55% | **8.74%** |
| 2026-08-14b | 16.36% | **8.63%** |

The gate uses the corrected figure. The raw one is still printed, unchanged, so it agrees to the
digit with what `tracon doctor` reports for the same corpus — two commands of one tool must never
print different values for the same named quantity.

*(Measured 2026-08-22 on one operator's own corpora. A point of comparison, not a norm.)*

## Per-seat breakdown

The corpus-level rate tells you something is wrong. The per-seat table tells you where — runs,
unresolvable runs, unaccounted rate and tool minutes per agent type, so a seat that has quietly
stopped finishing its work is visible rather than averaged away.

Agent type names are user-chosen strings from your own fleet config. **They stay on your
machine.** There is no share command, no aggregate, and no network code in it at all.

## What it deliberately does not do

- **No network calls, ever.** Not optional, not behind a flag. Nothing to configure, nothing to
  trust.
- **No content.** It reads tracon's normalized export, which is content-free by construction — no
  prompts, paths, branches, repo names or tool arguments enter it, and none can leave.
- **No live watching.** That is agent-radar's lane. This is measurement after the fact.
- **No sharing.** Whether fleet statistics may be pooled across operators is an open question
  that affects other people, so nothing here emits anything designed to travel.

## Limits, stated once and plainly

The reference figures above come from **one operator, one machine**, on an agent-heavy workflow.
Two of the underlying measurements have replicated against an independent corpus sharing no
transcripts; the unaccounted-run figure has never been validated anywhere else, because no public
corpus is both multi-agent and untruncated. Read it as a description of that machine.

The tool carries none of that limitation — it computes your numbers from your traces.
