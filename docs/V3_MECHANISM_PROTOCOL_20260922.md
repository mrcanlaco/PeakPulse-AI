# V3 mechanism comparison — frozen descriptive protocol

This protocol is written before computing the new comparison. It uses already
examined historical data, so it is exploratory, not a new holdout. It cannot
prove liquidation causality or select a profitable trading policy by itself.

## Cohort and identity

Use the accepted events in
`artifacts/v3_six_month_20260915/oos_reference_events.json`, preserving both
`locked_parent_oos` and `current_timing_runtime_reference` lane identities.
Publish source SHA-256 and event IDs before reading outcomes. Do not merge lane
rows into an independent sample: deduplicate source_event_id for the descriptive
combined view and retain per-lane tables. Within each lane, additionally report
a chronological per-symbol 48-hour non-overlapping episode subset. This is an
explicit descriptive sensitivity view, not a replacement of the frozen selector.

## Price-path groups, fixed before comparison

Use Entry-1 close solely as a common reference for these descriptive groups;
this is NOT the compact weighted-average TP contract. Require the exact entry
and all 576 subsequent five-minute bars through the original 48-hour horizon.

- `down_only`: low reaches -20% and high never reaches +20% from Entry-1.
- `up_only`: high reaches +20% and low never reaches -20% from Entry-1.
- `two_sided`: both barriers reached, including same-bar uncertainty; do not
  silently choose a first barrier or call this a profitable trade.
- `sideways`: neither barrier reached and terminal close return is within
  [-5%, +5%], inclusive. This is a terminal-return convention, not low volatility.
- `intermediate`: neither barrier reached and terminal return is outside that band.
- `incomplete`: missing/invalid entry or future bars; exclude from resolved rates
  and retain explicit reason and denominator.

Publish maximum upward/downward excursion, terminal return and first barrier
timestamps with candle-resolution caveats. Keep compact actual trade outcome and
post-stop observation in separate columns; funding eligibility does not change
the descriptive price group, and a price group does not establish net profit.

## Permitted explanatory inputs

Only exact pre-signal/source-time feature joins: pump 24h, distance from 24h high,
funding percentile 30d, funding change 8h, funding persistence 7d, OI change 4h,
price return 1h/4h and volume percentile 24h where genuinely available. No
forward-filled future values or post-event OI/funding used as predictors. Missing
features stay missing with per-group availability counts. Fold OOS reference
score remains a legacy-label score, not V3 success probability.

## Comparison and limits

Publish group counts by lane and month; median and quartile summaries of each
pre-signal feature; independent/non-overlap episode counts; Wilson intervals for
group proportions with explicit repeated-symbol/dependence limitations. Do not
choose thresholds, name a winner, fit a model, or perform an unreported search.
Unknown template classifications stay unknown. Any template application before
its fit_end must be marked in-sample descriptive and excluded from claims of
out-of-sample pattern discrimination.

If annual cached paths replace older lake data, publish both source identities
and reconcile differences; never overwrite the original replay. Conclude with
observed associations and rival explanations, not statements that funding forces
liquidations. A future frozen challenger evaluation is a separate next step.

## Pre-outcome input check

Root verified on 2026-09-22 that `artifacts/universe_policy_v2_48h.duckdb`
still matches source SHA-256
`2b3712f24803c0a82abe97a495e13dd1118c77fa4fa395325085c344f46924f4`.
Its `universe_policy_candidates_v2` table provides all nine explanatory columns
listed above. All 149 unique source events match exactly by symbol and UTC
feature_time, producing 149 joined rows (no extra join duplicates). This proves
join availability, not non-null coverage or statistical independence.
