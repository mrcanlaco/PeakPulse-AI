# V3 six-month OOS event reference export — 2026-09-15

This is a bounded provenance export for the backend six-month study. It is a
recycled retrospective reference, not a new untouched holdout, and it does not
replay prices or compact weighted-average outcomes.

## Source and coverage

- Output: `artifacts/v3_six_month_20260915/oos_reference_events.json`
- Exporter: `scripts/export_v3_oos_reference.py`
- Fixed UTC window: `[2026-02-01 00:00, 2026-08-01 00:00)`.
- Score source: `artifacts/forward48_timing_20260913/forward48_timing_historical_oos.csv`.
- Score coverage: 9,023 unique `(symbol, feature_time)` rows from 2026-03-01
  through 2026-07-29. February has no persisted OOS rows; it is reported as
  missing rather than filled or shifted.
- Scores are persisted fold-specific calibrated probabilities for the legacy
  Entry-1 label. The source did not persist per-fold model hashes, so the
  export records that limitation instead of attesting a model identity.
- PIT enrichment is an exact UTC `(symbol, feature_time)` left join to
  `artifacts/universe_policy_v2_48h.duckdb` (9,023/9,023 matched). No nearest,
  as-of, or forward-filled feature join is used.
- `feature_time_utc` remains the exact join key. The separate
  `signal_time_utc` is `feature_time_utc + 1 millisecond` (the next boundary
  after the source `:04:59.999` timestamp).

## Two named timing lanes

`locked_parent_oos` reuses `forward48_timing_backtest.py:select_signals` and
reconciles exactly to the locked 139 events: fold counts are 24/43/42/30 and
the row thresholds are 0.25/0.24/0.21/0.21. It keeps fold-scoped source
episode IDs, takes the first qualifying row per episode, then applies the
global 24-hour symbol cooldown. The exported selected-event counts by month
are March 20, April 38, May 13, June 47, and July 21.

`current_timing_runtime_reference` runs the existing
`dao_vang.experiments.distribution_v3.Timing` class continuously across all
fold rows before any Champion filtering. It uses the runtime `.39` score
threshold, `.29` post-confirmation floor, two confirmations within 90 minutes,
30% armed peak, four-hour episode age, six-hour episode gap, and global
24-hour cooldown. Its source fold thresholds are retained only as provenance;
they are not this lane's selection threshold. The lane is cold-started at the
first available March row because no February/carry-in rows are available. It
selects 14 rows (March 1, May 1, June 12). This lane is not the locked 139-event
policy.

The current `champion_gate` plus funding persistence is applied only after the
timing selector consumes all rows. The locked lane has 21 Champion-gate rows
(March 1, April 11, June 4, July 5); the runtime lane has 4 (March 1, June 3).
Gate failures retain explicit reasons such as `pump_below_25pct`,
`reversal_not_confirmed`, and `funding_gate_failed`. Funding feature presence
does not certify a funding path or financing result.

Each event includes a stable `event_id`, source event key/hash, UTC feature
time plus distinct signal time, score/raw score, fold and row threshold, source
episode ID, timing lane and reason, legacy label, exact PIT-match flag, funding persistence value, and
the full Champion-gate criteria/reason. `champion_subset` is also exposed per
lane for backend consumers that need only accepted gate rows.

The backend must perform the separate compact 0/+3/+6 price-path and post-stop
replay. Do not interpret `label_value` or this export's counts as compact
execution wins, current live OOS performance, or a causal improvement claim.
The optional independent row-wise `probability >= .39` diagnostic lane is not
emitted here so it cannot be mistaken for a stateful policy.
