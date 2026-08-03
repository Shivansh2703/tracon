# agentfail

Empirical failure-mode analysis of real production agent sessions.

**[docs/FINDINGS.md](docs/FINDINGS.md)** is the study. **[site/index.html](site/index.html)** is the
same study as a self-contained page.

## What this is

85,104 tool calls across 1,854 real agent runs (228 main Claude Code sessions + 1,626 subagent
runs), 30.2 days, privacy-stripped at capture. The corpus is one developer's own sessions on his
own projects — a real limitation, stated in the first paragraph of the study rather than a
footnote — but it is real production agentic work rather than a benchmark.

It asks the failure questions: does the agent loop, how does it handle a failed tool call, what is
actually in the long tail of slow calls, do failures cluster near context limits, and does a run
that goes wrong recover. Two of the six questions come back negative, one comes back unanswerable,
and all three are reported that way.

## Reproduce every number

Nothing in the writeup is transcribed by hand. Both documents are generated from one command:

```sh
python -m agentfail report --trace <tracon-export-dir> --json results/study.json
```

Runs in about 3 seconds over the full corpus. Zero dependencies beyond the standard library.

Verify the published figures have not drifted:

```sh
python -m agentfail report --trace <tracon-export-dir> --check results/study.json
```

Exits non-zero if any figure changed.

## Input format

A [tracon](https://github.com/Shivansh2703/tracon) trace export directory containing
`events.jsonl` (one normalized event per line, `ev` discriminator) and `manifest.json`. The
exporter strips all content at capture time: shapes, sizes, ids and timings survive; prompt text,
tool arguments and outputs do not. That constraint shapes the whole study and kills at least one
of its questions outright.

## Layout

```
src/agentfail/
  loader.py            corpus -> per-stream event sequences
  stats.py             Wilson intervals, two-proportion test, Cochran-Armitage trend
  cli.py               `agentfail report`
  analyses/
    summary.py         Q0  corpus description and its biases
    looping.py         Q1  repeat runs, bounded above and below
    errors.py          Q2  error rates and post-error behaviour
    longtail.py        Q3  what the slow calls actually are
    context.py         Q4  context pressure and compaction
    termination.py     Q5/Q6  how runs end, recovery, and what is unanswerable
tests/                 pytest suite; `-m slow` runs against the real corpus
docs/FINDINGS.md       the study
site/index.html        self-contained page, no external requests
results/study.json     generated; the source of every published figure
```

## Tests

```sh
python -m pytest -q          # synthetic fixtures with known answers
python -m pytest -q -m slow  # invariant checks against the real corpus (skips if absent)
```

## Method notes worth knowing before quoting a number

- **Repeat detection is bracketed, not point-estimated.** Arguments survive export only as a
  depth-1 shape (`command:s78`), so two different 78-character commands collide. Every looping
  figure is reported as a lower and an upper bound; the spread is the honest uncertainty.
- **Every rate carries a Wilson 95% interval.** No bare point estimates.
- **`completed` means a run finished, never that its work was correct.** There is no ground truth
  for task correctness anywhere in this corpus, and no figure here should be read as accuracy.
- **Underpowered comparisons are labelled underpowered rather than reported as null** — the
  compaction question has 38 events behind it and says so in-band.
