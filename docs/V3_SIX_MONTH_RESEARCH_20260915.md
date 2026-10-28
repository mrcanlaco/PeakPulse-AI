# V3 sáu tháng — khảo sát cơ chế (research-only)



Đợt cố định: 2026-02-01T00:00:00+00:00 đến 2026-08-01T00:00:00+00:00 UTC.

Hồi cứu trên nguồn PIT đã từng dùng trong pipeline nhãn 24h; không đổi live, không tải dữ liệu mới và không nâng model.

## Kết quả chính

- Common diagnostic sample: 1933 dòng cooldown 24h; 1580 dòng evidence cooldown 48h. Failed rows vẫn tiêu thụ cooldown, nên không phải faithful Champion selector.
- Đường giá kết thúc: 1926; compact đủ funding: 0 (không có provider attestation nên không chứng nhận).
- TP trước Stop: 351/1926 (18.2%; Wilson95=[0.16564025819796258, 0.20011074979003368]).
- Sau Stop: tổng Stop=568; đủ đường giá=567; TP=81 (14.3%; Wilson95=[0.11645440272056028, 0.17406664521332188]); thiếu=1.
- 48h evidence diagnostic: giá đủ=1575; TP=247 (15.7%); Stop=433; sau Stop đủ=432; sau Stop TP=46.
- Pattern/stage: unavailable — No pre-Feb frozen classifier with verified fit and provenance was available for this bounded mechanism run; no new outcome-fit classifier.

## Theo tháng (24h common diagnostic sample)

| Tháng | N | Giá đủ | TP | Tỷ lệ | Stop | Sau Stop đủ | Sau Stop TP |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-02 | 340 | 340 | 51 | 15.0% | 88 | 88 | 9 |
| 2026-03 | 271 | 271 | 47 | 17.3% | 63 | 63 | 5 |
| 2026-04 | 439 | 439 | 68 | 15.5% | 171 | 171 | 21 |
| 2026-05 | 292 | 292 | 41 | 14.0% | 86 | 86 | 13 |
| 2026-06 | 375 | 375 | 92 | 24.5% | 108 | 108 | 25 |
| 2026-07 | 216 | 209 | 52 | 24.9% | 52 | 51 | 8 |

## Theo tháng: population đủ market-four + persistence

Đây là composition summary sau common sampling, không phải một policy selector độc lập và không phải bằng chứng score/Champion.

| Tháng | N | Giá đủ | TP | Tỷ lệ | Sau Stop đủ | Sau Stop TP |
|---|---:|---:|---:|---:|---:|---:|
| 2026-02 | 2 | 2 | 2 | 100.0% | 0 | 0 |
| 2026-04 | 2 | 2 | 1 | 50.0% | 1 | 0 |
| 2026-05 | 1 | 1 | 0 | 0.0% | 0 | 0 |
| 2026-06 | 5 | 5 | 3 | 60.0% | 2 | 1 |
| 2026-07 | 2 | 2 | 1 | 50.0% | 1 | 0 |

## Ablation điều kiện (cùng cohort; giá-only)

Leave-one-out giữ các điều kiện còn lại; N sau common sampling, không phải số episode độc lập. Score/reference condition unavailable.

| Variant | N | Giá đủ | TP | Tỷ lệ | Stop | Sau Stop đủ | Sau Stop TP |
|---|---:|---:|---:|---:|---:|---:|---:|
| market_four_plus_persistence | 12 | 12 | 7 | 58.3% | 4 | 4 | 1 |
| leave_one_out_pump | 33 | 33 | 10 | 30.3% | 11 | 11 | 1 |
| leave_one_out_reversal | 16 | 16 | 7 | 43.8% | 7 | 7 | 2 |
| leave_one_out_funding_percentile | 40 | 40 | 19 | 47.5% | 14 | 14 | 2 |
| leave_one_out_funding_change | 18 | 18 | 11 | 61.1% | 5 | 5 | 2 |
| leave_one_out_persistence_extra | 18 | 18 | 11 | 61.1% | 6 | 6 | 1 |
| only_pump | 237 | 237 | 98 | 41.4% | 108 | 108 | 30 |
| only_reversal | 854 | 851 | 208 | 24.4% | 295 | 295 | 45 |
| only_funding_percentile | 397 | 396 | 68 | 17.2% | 81 | 80 | 8 |
| only_funding_change | 376 | 376 | 83 | 22.1% | 114 | 113 | 18 |
| only_persistence_extra | 867 | 862 | 160 | 18.6% | 260 | 259 | 35 |

## Strata cơ chế (cùng 24h sample)

Funding raw sign tách riêng vì percentile cao vẫn có thể âm. OI giảm không chứng minh liquidation; các hàng là liên hệ đồng thời.

| Stratum | N | Giá đủ | TP | Tỷ lệ | Sau Stop đủ | Sau Stop TP |
|---|---:|---:|---:|---:|---:|---:|
| funding_raw_nonpositive | 1022 | 1019 | 179 | 17.6% | 294 | 45 |
| funding_raw_positive | 911 | 907 | 172 | 19.0% | 273 | 36 |
| funding_raw_unknown | 0 | 0 | 0 | n/a | 0 | 0 |
| funding_percentile_high | 397 | 396 | 68 | 17.2% | 80 | 8 |
| funding_percentile_below_high | 689 | 683 | 141 | 20.6% | 231 | 32 |
| funding_percentile_unknown | 847 | 847 | 142 | 16.8% | 256 | 41 |
| funding_change_positive | 376 | 376 | 83 | 22.1% | 113 | 18 |
| funding_change_nonpositive | 1557 | 1550 | 268 | 17.3% | 454 | 63 |
| funding_change_unknown | 0 | 0 | 0 | n/a | 0 | 0 |
| funding_persistence_positive | 867 | 862 | 160 | 18.6% | 259 | 35 |
| funding_persistence_nonpositive | 1066 | 1064 | 191 | 18.0% | 308 | 46 |
| funding_persistence_unknown | 0 | 0 | 0 | n/a | 0 | 0 |
| oi_decline | 200 | 199 | 50 | 25.1% | 52 | 8 |
| oi_rise_or_flat | 1733 | 1727 | 301 | 17.4% | 515 | 73 |
| oi_unknown | 0 | 0 | 0 | n/a | 0 | 0 |
| pump_15_to_25pct | 1696 | 1689 | 253 | 15.0% | 459 | 51 |
| pump_25_to_35pct | 117 | 117 | 43 | 36.8% | 56 | 11 |
| pump_35pct_or_more | 120 | 120 | 55 | 45.8% | 52 | 19 |
| reversal_above_minus1pct | 617 | 616 | 79 | 12.8% | 157 | 16 |
| reversal_minus2_to_minus1pct | 462 | 459 | 64 | 13.9% | 115 | 20 |
| reversal_at_or_below_minus2pct | 854 | 851 | 208 | 24.4% | 295 | 45 |
| reversal_unknown | 0 | 0 | 0 | n/a | 0 | 0 |
| momentum_1h_negative | 211 | 211 | 55 | 26.1% | 69 | 10 |
| momentum_1h_nonnegative | 1722 | 1715 | 296 | 17.3% | 498 | 71 |
| momentum_1h_unknown | 0 | 0 | 0 | n/a | 0 | 0 |
| momentum_4h_negative | 149 | 148 | 34 | 23.0% | 45 | 8 |
| momentum_4h_nonnegative | 1784 | 1778 | 317 | 17.8% | 522 | 73 |
| momentum_4h_unknown | 0 | 0 | 0 | n/a | 0 | 0 |
| momentum_deceleration_positive | 1472 | 1467 | 255 | 17.4% | 437 | 64 |
| momentum_deceleration_nonpositive | 461 | 459 | 96 | 20.9% | 130 | 17 |
| momentum_deceleration_unknown | 0 | 0 | 0 | n/a | 0 | 0 |

## Điều kiện, độ phủ và giới hạn

Bốn điều kiện: pump >=25%, reversal <=-2%, funding percentile 30d >=80%, funding_change_8h >0. Persistence >0 là gate bổ sung. PIT không có reference score provenance rõ, nên đủ năm điều kiện trong cohort này unavailable; OOS score/Champion lane được báo riêng.
- bt_combined_all: 822711 dòng giờ, 194 mã trong kỳ.
- Feature source kết thúc tại 2026-07-31T00:04:59.999000+00:00; 31/07 partial, không impute/đổi cửa sổ.
- Funding cadence chỉ heuristic; không có provider attestation độc lập nên compact eligibility/net return bị withheld.
- Entry price là close signal-candle hồi cứu, không bảo đảm live fill.
- Wilson chỉ mô tả; cooldown 24h chồng lấn horizon 48h, cooldown 48h vẫn phụ thuộc regime/mã, không phải CI episode độc lập.
- Survivorship bias và kế thừa selection nhãn 24h cũ vẫn còn; OOS Champion lanes được LunaCompact báo riêng tại docs/V3_SIX_MONTH_OOS_REPLAY_20260915.md.

## Tệp

- Protocol: artifacts\v3_six_month_20260915\protocol_manifest.json
- Cohort trước outcome: artifacts\v3_six_month_20260915\cohort_pre_outcome.csv
- Replay từng dòng: artifacts\v3_six_month_20260915\outcomes.jsonl
- Report JSON: artifacts\v3_six_month_20260915\report.json
