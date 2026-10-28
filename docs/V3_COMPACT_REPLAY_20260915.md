# V3 compact Champion replay audit — 2026-09-15

> Bounded retrospective diagnostic on the recycled 23-event Champion cohort. This is not an untouched holdout and does not support an improvement claim.

## Contract and provenance

- Source: `champion.signals_detail` from `C:\Rapid Coding\dao_vang\artifacts\v3_scout_deep_dive.json` (SHA-256 `c7070974f6625b43e33be65d8d608bc012192079a9745e403414942a1fb887ff`).
- Signal boundary: source `HH:04:59.999` rounded to the next exact five-minute UTC close; the source `entry_price` is retained.
- Compact policy: `distribution_short_v3_policy_48h` / checksum `c3fb230c415dce4e60aa0992eacbd0a15ecfb7292a3b6809dff5c1ec17dd5b08`; target `20%`, stop `16%`, offsets `[0.0, 0.03, 0.06]`, weights `[0.2, 0.3, 0.5]`, horizon `48h`.
- Post-stop diagnostic: `post_stop_frozen_average_v1`. A target after a real stop is descriptive and never changes `actual_win`.
- Funding eligibility is false unless an explicit attestation covers `[signal_time, signal_time + 48h]`; local rows alone are not treated as an attestation.
- The artifact hashes the source cohort JSON. Parquet inputs are recorded by root path and are not content-hashed in this bounded audit.

## Coverage summary

- Events: **23**; complete 48h price paths: **6**; evaluated rows: **6**.
- Partial paths: **0**; explicitly excluded for missing first forward kline: **17**.
- Funding-eligible rows: **0**; actual-eligible rows: **0**; paired-evidence eligible: **0**.
- The six complete rows are price-only statuses (**6**): labels remain null and no net return is reported because no explicit funding attestation was supplied.
- Actual statuses: `{"excluded_missing_klines": 17, "target": 4, "timeout": 2}`.
- Post-stop statuses: `{"not_applicable": 6, "not_evaluated": 17}`.

The primary `data/normalized/klines` snapshot contains no June/July windows for this cohort. The configured run also includes the readable local `data_live/normalized/klines` snapshot as a secondary parquet source; event-level path counts aggregate all configured parquet roots and do not attribute rows to one root. Archive CSV files are not used by this replay. Missing windows are not counted as failures or wins.

## Event-level audit

| # | Symbol | Source feature time | Normalized signal | Entry | Price coverage | Bars/prefix | Funding | Actual | Post-stop | Eligible |
|---:|---|---|---|---:|---|---:|---|---|---|---:|
| 1 | APRUSDT | 2026-06-02T20:04:59.999000+00:00 | 2026-06-02T20:05:00+00:00 | 0.2314 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 2 | CLOUSDT | 2026-06-03T11:04:59.999000+00:00 | 2026-06-03T11:05:00+00:00 | 0.19367 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 3 | BEATUSDT | 2026-06-08T12:04:59.999000+00:00 | 2026-06-08T12:05:00+00:00 | 4.4247 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 4 | CLOUSDT | 2026-06-12T04:04:59.999000+00:00 | 2026-06-12T04:05:00+00:00 | 0.18994 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 5 | JELLYJELLYUSDT | 2026-06-14T13:04:59.999000+00:00 | 2026-06-14T13:05:00+00:00 | 0.07401 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 6 | BASUSDT | 2026-06-24T12:04:59.999000+00:00 | 2026-06-24T12:05:00+00:00 | 0.041488 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 7 | MAGMAUSDT | 2026-06-26T16:04:59.999000+00:00 | 2026-06-26T16:05:00+00:00 | 0.73058 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 8 | RAVEUSDT | 2026-06-29T09:04:59.999000+00:00 | 2026-06-29T09:05:00+00:00 | 0.4823 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 9 | TACUSDT | 2026-06-29T20:04:59.999000+00:00 | 2026-06-29T20:05:00+00:00 | 0.058805 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 10 | BLESSUSDT | 2026-07-03T11:04:59.999000+00:00 | 2026-07-03T11:05:00+00:00 | 0.009241 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 11 | 4USDT | 2026-07-06T01:04:59.999000+00:00 | 2026-07-06T01:05:00+00:00 | 0.01251 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 12 | EDGEUSDT | 2026-07-07T17:04:59.999000+00:00 | 2026-07-07T17:05:00+00:00 | 0.3918 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 13 | BUSDT | 2026-07-11T04:04:59.999000+00:00 | 2026-07-11T04:05:00+00:00 | 0.2408 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 14 | AKEUSDT | 2026-07-15T08:04:59.999000+00:00 | 2026-07-15T08:05:00+00:00 | 0.0006601 | complete_48h_price_path | 576/576 | rows_present_no_attestation (12) | target | not_applicable | no |
| 15 | TAGUSDT | 2026-07-19T12:04:59.999000+00:00 | 2026-07-19T12:05:00+00:00 | 0.001228 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 16 | BUSDT | 2026-07-19T13:04:59.999000+00:00 | 2026-07-19T13:05:00+00:00 | 0.2072 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 17 | HEMIUSDT | 2026-07-21T00:04:59.999000+00:00 | 2026-07-21T00:05:00+00:00 | 0.007082 | complete_48h_price_path | 576/576 | rows_present_no_attestation (12) | target | not_applicable | no |
| 18 | LABUSDT | 2026-07-22T04:04:59.999000+00:00 | 2026-07-22T04:05:00+00:00 | 0.1788 | complete_48h_price_path | 576/576 | rows_present_no_attestation (12) | target | not_applicable | no |
| 19 | APRUSDT | 2026-07-24T16:04:59.999000+00:00 | 2026-07-24T16:05:00+00:00 | 0.2165 | complete_48h_price_path | 576/576 | rows_present_no_attestation (12) | timeout | not_applicable | no |
| 20 | PIEVERSEUSDT | 2026-07-26T08:04:59.999000+00:00 | 2026-07-26T08:05:00+00:00 | 0.9435 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 21 | KAITOUSDT | 2026-07-26T14:04:59.999000+00:00 | 2026-07-26T14:05:00+00:00 | 1.2014 | complete_48h_price_path | 576/576 | rows_present_no_attestation (12) | timeout | not_applicable | no |
| 22 | TAGUSDT | 2026-07-27T12:04:59.999000+00:00 | 2026-07-27T12:05:00+00:00 | 0.001355 | missing_first_forward_bar | 0/576 | no_rows (0) | excluded_missing_klines | not_evaluated | no |
| 23 | UAIUSDT | 2026-07-29T17:04:59.999000+00:00 | 2026-07-29T17:05:00+00:00 | 0.4305 | complete_48h_price_path | 576/576 | rows_present_no_attestation (12) | target | not_applicable | no |

## Interpretation limits

- `legacy_entry1_label` is retained only for row identity and compatibility auditing; it is not a compact weighted-average outcome.
- `actual_status` and `post_stop_status` are separate. A post-stop target cannot turn a stopped trade into a win.
- A partial early target/stop, if present, is shown but remains ineligible because the full price path is not covered. An event with no first forward bar is explicitly excluded as missing data.
- This report is diagnostic evidence about local coverage and engine behavior. It must not be read as a claim that V3 improved precision, EV, or promotion eligibility.

Replay artifact: `C:\Rapid Coding\dao_vang\artifacts\v3_compact_replay_champion_audit_20260915.json`.
