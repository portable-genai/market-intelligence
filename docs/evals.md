# How the market intelligence agent is evaluated

Read this page if you decide what this service is allowed to assert. The metrics, the bars and
the corpora below are generated from the artifacts that actually gate the build, so they cannot
drift from what runs: `make evals-doc-check` fails the build when this page and those artifacts
disagree.

## How to run it

```sh
make eval              # offline, no credentials
make evals-doc-check   # this page is still true
```

`make gate` runs both on every change.

## Grounding is measured per CLAIM, not per brief

`brief_groundedness` used to score 1.0 as soon as a brief carried any citation at all. That is a
boolean wearing a percentage: a brief making twelve claims and citing one of them read a perfect
1.000, and the number could not move until the last citation was gone.

`COMPLIANCE.md` P-10 promises something quite different, that "every brief statement and
competitor delta carries a source-and-page Citation", and nothing measured that promise. The unit
is now the `Claim` and the material `Delta`, each of which carries its own citations, so the count
is structural rather than a guess at which sentence a citation belongs to. The metric moves when a
claim loses its provenance, instead of only when the last one does.

## What is measured, and against what bar

Every bar below lives in `eval/rubrics/*.yaml` next to the argument for it, and the
runner reads it from there. There is no dict of thresholds in the runner any more: a
metric scored with no reviewed bar fails the build, and so does a bar that names no
metric, which is the direction that rots quietly because it rots toward looking well
governed.

The third column is the denominator rule, and it applies only where a score is a
FRACTION over scored positives: such a threshold `t` tolerates a single miss only over
at least `1/(1-t)` of them. `all or nothing` marks a bar that already asks for no
headroom, so a bigger corpus would not change what it means. Each rubric declares which
it is rather than the rule being guessed from the number.

| Metric | Bar | Denominator | What it measures |
|---|---|---|---|
| `brief_groundedness` | 0.8 | a rate; needs 5 positives | Fraction of briefs whose narrative and material competitor deltas all carry at least one citation. A brief built on uncited claims fails. |
| `citation_accuracy` | 0.9 | a rate; needs 10 positives | Fraction of cited source ids that appear in the retrieved / derived evidence set (no fabricated citations). |
| `diff_accuracy` | 0.8 | a rate; needs 5 positives | Fraction of golden cases where the deterministic competitor-move diff produced the expected count of material deltas for the (market, vertical). |
| `review_safety` | 0.99 | all or nothing | Every brief's maker-checker flag matches the golden expectation, so a brief cannot stop requiring human review without the gate saying so. |

Scored over 6 golden briefs.

## What is exercised

- **6 golden briefs** in `eval/datasets/golden_briefs.jsonl`, each with
  the expected material-move count and maker-checker flag a reviewer assigned. The
  oracle is the dataset's, never a re-read of the brief: an oracle taken from the thing
  under test agrees with it by construction.
- Those briefs produce **14 claims and 7 material competitor deltas**,
  which is what `brief_groundedness` is measured over now that it is a claim-level
  metric, and **14 citations**, which is what `citation_accuracy` is measured
  over. Neither is the brief count, and the brief count is the number a case-count check
  would have used.

## How a metric is prevented from being decoration

1. **The bars are read from the rubrics, in both directions.** There is no `THRESHOLDS` dict any
   more. What was here before was both a dict and a loader that overlaid two rubric files on top
   of it, silently falling back to the dict when PyYAML was missing: two homes for one number,
   with a silent path that used the one nobody reviews. Two metrics had no rubric at all.
2. **The denominator rule is asserted against the corpus that actually divides each rate**, which
   is the brief count for none of them: grounding over claims and material deltas, citation
   accuracy over citations.
3. **`review_safety`'s red case runs as the first statement of the scored run**, not only in
   `tests/`. Run in a test suite, a proof says the metric could have gone red on some machine at
   some point.
4. **Every expectation is the dataset's.** `review_safety` compares with the golden maker-checker
   oracle rather than with the brief's own flag, which would agree with it by construction.

## What is NOT measured here

- **A real model's words.** Every metric scores a deterministic core against a deterministic fake
  LLM adapter, so grounding measures the VALIDATOR rather than a model's restraint.
- **Retrieval quality.** The research layer's recall is not scored separately from what the brief
  did with what it returned, so a source set that silently stopped returning the right filing
  would still produce a clean citation set.
- **Production traffic.** Everything here is a golden set. Nothing samples live requests.
