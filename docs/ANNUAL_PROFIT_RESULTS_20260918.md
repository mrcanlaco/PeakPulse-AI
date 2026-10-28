# Luna Max annual profit results — PROVISIONAL

This artifact is a research-only OHLC/MMR proxy. It is not verified profit, a causal claim, live execution evidence, or a promotion signal.

## Frozen scope and provenance

- Protocol SHA256: `0e65dd6b9ead3a7d437a2e66c391701eb4b79e59d1d5600729e72da873d99443`.
- Input snapshot: `3f2865593e62a24224d9db3231e4ef69d5487d41198225c72b952c00e41bcdd5`.
- Window: `2025-09-01T00:00:00+00:00` through `2026-09-01T00:00:00+00:00` exclusive; warmup `2025-08-01T00:00:00+00:00`.
- Universe: 328 local USDT price files; survivorship/selection bias and local delistings are not resolved.
- Venue label: Binance USD-M; local USDT contract identity is not attested.
- Features are streamed from closed 5m candles only; no future labels, MFE, MAE, or max-return input is used.
- All outcomes are provisional OHLC/MMR 1% proxies; there are no live orders.

## Registered 40 trials

Every row below was registered before account simulation: ten fixed strategies × 20/60 bps round-trip cost × withdraw/retain profits.

| Trial | Profit | Ending wealth | Rankable | Executed | Candidate gap locks | Candidate censored |
|---|---:|---:|:---:|---:|---:|---:|
| M48_1__c20__withdraw | 85.30640706124905 | 10085.306407061249 | yes | 176 | 0 | 21 |
| M48_1__c20__retain | -108.90940345177114 | 9891.090596548229 | yes | 176 | 0 | 21 |
| M48_1__c60__withdraw | -236.93896831358325 | 9763.061031686417 | yes | 176 | 0 | 21 |
| M48_1__c60__retain | -564.0934632247263 | 9435.906536775274 | yes | 176 | 0 | 21 |
| M48_2__c20__withdraw | 14093.491222499411 | 24093.49122249941 | yes | 177 | 0 | 21 |
| M48_2__c20__retain | 14100.275860556507 | 24100.275860556507 | yes | 177 | 0 | 21 |
| M48_2__c60__withdraw | 13238.696050979175 | 23238.696050979175 | yes | 177 | 0 | 21 |
| M48_2__c60__retain | 2403.9172113142668 | 12403.917211314267 | yes | 177 | 0 | 21 |
| M168_2__c20__withdraw | 1145.9046579419373 | 11145.904657941937 | yes | 53 | 0 | 126 |
| M168_2__c20__retain | -3771.1138787351347 | 6228.886121264865 | yes | 53 | 0 | 126 |
| M168_2__c60__withdraw | 762.237482272445 | 10762.237482272445 | yes | 53 | 0 | 126 |
| M168_2__c60__retain | -3788.1423329798927 | 6211.857667020107 | yes | 53 | 0 | 126 |
| NEG48_1__c20__withdraw | 514.6018219980524 | 10514.601821998052 | yes | 159 | 0 | 5 |
| NEG48_1__c20__retain | 95.21960215973195 | 10095.219602159732 | yes | 159 | 0 | 5 |
| NEG48_1__c60__withdraw | 290.09365894419716 | 10290.093658944197 | yes | 159 | 0 | 5 |
| NEG48_1__c60__retain | -421.0081366011782 | 9578.991863398822 | yes | 159 | 0 | 5 |
| E48_1__c20__withdraw | -219.09998577778242 | 9780.900014222218 | yes | 163 | 0 | 5 |
| E48_1__c20__retain | -4678.939596127776 | 5321.060403872224 | yes | 163 | 0 | 5 |
| E48_1__c60__withdraw | -415.8968989922887 | 9584.103101007711 | yes | 163 | 0 | 5 |
| E48_1__c60__retain | -4689.322493815713 | 5310.677506184287 | yes | 163 | 0 | 5 |
| E48_2__c20__withdraw | 1240.2030657654705 | 11240.20306576547 | yes | 81 | 0 | 5 |
| E48_2__c20__retain | -10000.0 | 0.0 | yes | 81 | 0 | 5 |
| E48_2__c60__withdraw | 887.0510661503049 | 10887.051066150305 | yes | 81 | 0 | 5 |
| E48_2__c60__retain | -10000.0 | 0.0 | yes | 81 | 0 | 5 |
| POS48_2__c20__withdraw | -510.3680394692583 | 9489.631960530742 | yes | 62 | 0 | 4 |
| POS48_2__c20__retain | -10000.0 | 0.0 | yes | 62 | 0 | 4 |
| POS48_2__c60__withdraw | -712.5421556775891 | 9287.45784432241 | yes | 62 | 0 | 4 |
| POS48_2__c60__retain | -10000.0 | 0.0 | yes | 62 | 0 | 4 |
| SWITCH48_1__c20__withdraw | -999.4029945154107 | 9000.59700548459 | yes | 165 | 0 | 8 |
| SWITCH48_1__c20__retain | -999.4029945154107 | 9000.59700548459 | yes | 165 | 0 | 8 |
| SWITCH48_1__c60__withdraw | -999.698563842001 | 9000.301436157999 | yes | 165 | 0 | 8 |
| SWITCH48_1__c60__retain | -999.698563842001 | 9000.301436157999 | yes | 165 | 0 | 8 |
| HEDGE48_2__c20__withdraw | 1135.5347068112278 | 11135.534706811228 | yes | 161 | 0 | 6 |
| HEDGE48_2__c20__retain | -999.9999211192608 | 9000.00007888074 | yes | 161 | 0 | 6 |
| HEDGE48_2__c60__withdraw | 928.8253069479215 | 10928.825306947921 | yes | 161 | 0 | 6 |
| HEDGE48_2__c60__retain | -999.999977589745 | 9000.000022410255 | yes | 161 | 0 | 6 |
| PHASE48_1__c20__withdraw | -864.7626900295127 | 9135.237309970487 | yes | 1387 | 0 | 4 |
| PHASE48_1__c20__retain | -999.9997728460767 | 9000.000227153923 | yes | 1387 | 0 | 4 |
| PHASE48_1__c60__withdraw | -999.9999991914628 | 9000.000000808537 | yes | 1387 | 0 | 4 |
| PHASE48_1__c60__retain | -999.9999991914628 | 9000.000000808537 | yes | 1387 | 0 | 4 |

## Cash baseline

Cash baseline profit is 0. It is kept separate from the 40 strategy paths.

## Coverage and accounting notes

- Price rows valid/invalid/duplicate-conflict: 30265917 / 0 / 0.
- Hourly decisions expected/valid/missing: 2873280 / 2369214 / 504066.
- Funding files present: 328; missing: 0; funding coverage is not attested.
- A price gap after a known entry locks capital and makes the affected account non-rankable; it is not silently changed into a loss or a reusable exit.
- Funding cashflow is signed by side, uses exact settlement timestamps, excludes settlements at entry/actual exit ties, and is reported separately from feature lag/provenance.
- Monthly, period, coin, and largest-event figures are static entry attribution; they are not isolated coin backtests or causal tests.
- The 02/2026–07/2026 segment is recycled exploratory history; it is not a fresh holdout. No claim is made that the other segments were previously unseen.
- Closed-event drawdown excludes the full intratrade path; censored/unrealized MTM is reported separately.
- The last two table columns count candidate outcomes before account overlap/capital selection, not executed open positions. Each actual account has zero or one open position/pair at cutoff.
- A clean no-resume price rebuild reproduced all 328 executable price hashes; no source-snapshot rebase was used for the successful run. The earlier attempt failed on Windows stdout encoding before accounts were completed; the successful unchanged-parameter run used Python UTF-8 mode and output directory `backtest_utf8`.

## Outcome claims

No verified-profit, causal-advantage, historical-tier, continuous-mark, true-liquidation, or live-execution claim is made.
