# V3 training-label compatibility — 2026-09-15

## Verdict

`artifacts/distribution_v3_training.duckdb` is **not** a compact-policy,
weighted-average 48-hour outcome dataset. It is an entry1 price-path dataset
with compact-policy version names attached. It must not be used to claim V3
policy probability, execution EV, or promotion eligibility.

## Direct evidence

- The table contains 4,890 rows, of which 4,874 have labels and 16 are null.
  Across all rows, `label_value` is identical (including nulls) to
  `entry1_label_value`.
- The table contains no fills, weighted-average revisions, execution status,
  funding payments, net return, or compact-policy exclusion fields.
- When the cache exists, `materialize_v3_dataset` copies
  `universe_policy_candidates_v2.label_value` into both label columns
  (`src/dao_vang/experiments/train_distribution_v3.py:120-143`).
- The uncached SQL path finds the first low below `entry_price * 0.80` and first
  high above `entry_price * 1.16`, then duplicates the same first-touch CASE
  into both label columns (lines 171–217). It never invokes
  `src/dao_vang/labels/engine_v3.py`.
- The SQL excludes equal target/stop timestamps as null. The frozen V3 contract
  instead uses stop-first ambiguity and counts it as a stop.
- Stored feature times end in `:04:59.999`; all 4,890 fail the compact engine's
  exact five-minute epoch-alignment check unless the close-boundary convention
  is normalized consistently.

## Required replacement

Build a new, versioned compact-outcome table from strict contiguous post-signal
bars plus attested funding coverage. Preserve `entry1_label_value` only as a
separate legacy diagnostic. For the requested evaluation, publish two distinct
weighted-average compact outcomes on the same frozen cohort and original
48-hour horizon:

1. Target before stop under the compact fill, weighted-average rebasing, and
   frozen intrabar contract.
2. On the first stop touch, freeze the then-active weighted average and target,
   prohibit later fills, and continue a price-only target observation until the
   original signal time plus 48 hours.

The existing compact engine supplies the first outcome but terminates at the
stop, so the second is a separate counterfactual evaluator. Both must retain
event, cohort, contract/checksum, fill, stop, target, timeout, and exclusion
provenance.
