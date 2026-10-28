# V3 evidence audit — 2026-09-15

## Verdict

The existing V3 variable-search and funding-scout reports are useful exploratory
work, but they are **not promotion-grade evidence**. They must not replace or
modify the current production champion. The V3 configuration already states
`live_eligible: false`, `production_config_unchanged: true`, and requires at
least 100 future resolved events across three chronological windows before
promotion (`configs/distribution_v3_research_standard.yaml`).

## Bounded offline run

The backend research CLI was run against the available local artifact and wrote
the default local outputs:

```text
artifacts/v3_pattern_research_report.json
artifacts/v3_pattern_model.json
```

The run used one common chronological split with a 48-hour purge, 48-hour
symbol cooldown, train-only template fitting, policy-only pattern rates, five
independent pattern thresholds, and the strict evidence gates (at least 100
resolved held-out episodes, three chronological windows, target rate at least
50%, Wilson lower bound above 45%, positive conservative/actual/paired EV, and
ECE at most 0.05). The source has no explicit reference-score column, so the
exact five-condition ablation is marked unavailable rather than substituting a
generic score/probability field. Funding persistence remains visible as a
separate fixed Scout/Champion gate.

The generated report is explicitly tagged
`evidence_status=unsupported_compact_outcome` and
`promotion_eligible=false`: its 4,874 labeled rows are the legacy Entry-1
diagnostic contract, not compact weighted-average outcomes. The report's
Champion diagnostic has 16 resolved, 48-hour-deduplicated episodes (8 positive,
50.0% precision, +1.8% conservative EV); this is exploratory context only and
does not establish a V3 improvement. Compact dual replay over attested market
paths is a separate evidence lane.

## Material limitations

1. **No untouched holdout remains after pattern selection.**
   `scripts/v3_variable_search.py` evaluates 31 alternatives on test folds and
   ranks them by test conservative EV (lines 271–343 and the final ranking).
   `scripts/v3_deep_dive_scout.py` then reuses the same historical period to
   sweep pump thresholds, reversal depth, funding ablations, and
   microstructure filters (lines 191–250). The selected 25% pump, -2% reversal,
   and funding gate is therefore a test-selected hypothesis. All feature and
   rule selection must occur inside training/policy data before one frozen
   evaluation on an untouched held-out cohort.

2. **The reported champion has only one evaluable search fold.**
   `artifacts/v3_variable_search_report.json` records `folds: 1`; its only fold
   is fold 4, with 88 test rows, 18 signals, and 9 target labels. Earlier folds
   are silently skipped by the minimum-size/class check at
   `scripts/v3_variable_search.py:242`. The report's `1/4` display must not be
   interpreted as four-window validation or stability evidence.

3. **The deep-dive document is internally inconsistent.**
   `artifacts/v3_scout_deep_dive.json` records 23 signals and 12 positives
   (52.2%, +2.58%), split across only folds 3 and 4. In contrast,
   `docs/V3_SCOUT_DEEP_DIVE.md` hard-codes 18 signals, 50.0%, and +1.80% in its
   introduction and labels a 23-row table as an 18-signal audit. Generated
   reports must derive headings and summaries from the same result object.

4. **The label and EV are not the actual V3 execution outcome.**
   Both report scripts read `label_value` from
   `universe_policy_candidates_v2`. That label represents an entry-price
   target-before-stop path. They then estimate EV as
   `precision * 20% - (1 - precision) * 16% - 0.2%`
   (`scripts/v3_variable_search.py:175` and
   `scripts/v3_deep_dive_scout.py:179`). This does not simulate the compact V3
   policy's 20/30/50 fills, weighted-average rebasing, intrabar order, realized
   funding, timeout mark-to-market, or incomplete-path exclusions implemented
   by `src/dao_vang/labels/engine_v3.py`.

5. **The probability has a narrower meaning than the reports imply.**
   The calibrated score estimates the probability of the legacy binary
   `label_value`, not the probability of profit or success under the compact V3
   execution path. Separately, the research config explicitly describes the
   0.39 timing score as `reference_only_not_v3_calibrated_probability`. Neither
   value should be presented as a production V3 probability without an exact
   outcome-contract and calibration tag.

6. **Counts are not independent event counts.**
   A 24-hour per-symbol cooldown permits overlapping 48-hour outcome windows;
   cooldown state resets at each fold. The deep-dive policy-threshold search
   does not apply cooldown, although test selection does
   (`scripts/v3_deep_dive_scout.py:134-155`). Reported "signals" are therefore
   selected entries, not necessarily independent episodes. Evidence should
   report rows, selected entries, symbols, deduplicated episodes, resolved
   outcomes, and exclusions separately, using the same frozen event policy in
   training-policy selection and held-out evaluation.

7. **Aggregation and cohorts are not comparable across variants.**
   `scripts/v3_variable_search.py:317-336` reports total signals and true
   positives but uses an unweighted mean of fold precision and EV. Those values
   need not equal pooled `total_tp / total_signals`. In addition, each variant
   computes its fold calendar only after applying its own filter (lines
   213–232), so variants can be ranked on different dates and cohorts. Freeze a
   common split and identical event rows first; report both pooled-event and
   equal-window metrics with explicit names.

8. **Probability quality fails the configured gate.**
   The selected search result has ECE 0.253 versus the configured maximum 0.05,
   and Brier 0.2784 versus a fold null Brier of 0.2282. Its threshold was chosen
   from a policy slice with as few as five signals (two in the deep dive).
   These figures do not support a calibrated-probability or promotion claim.

## Required validation design

- Preserve the existing `pump_filter_v1` candidate champion and frozen serving
  model. Run V3 only as a tagged research/scout lane.
- Freeze a common chronological cohort, episode key, splits, embargo, and
  exclusion policy before fitting. Select every feature, gate, threshold, and
  model using training/policy data only.
- Evaluate once on untouched held-out data and publish two separately named
  outcomes on the same original-horizon cohort: (a) compact-policy TP-before-stop
  from the filled weighted average; and (b) price-only target tracking after
  Stop, freezing the then-active average and target, with no later fills and
  the original 48-hour deadline. The second outcome is not a profitable trade.
  Entry1-only remains a separate legacy diagnostic. Financial returns require
  funding, costs, timeout values and explicit coverage/exclusions.
- Attach lane, hypothesis status, outcome contract/checksum, model/calibrator,
  threshold policy, cohort, fold, event/episode key, and sample-count tags to
  every evidence row and alert update.
- Promotion remains unavailable until the configured future-sample, window,
  calibration, confidence-bound, and EV gates all pass and separate live
  approval is granted.
