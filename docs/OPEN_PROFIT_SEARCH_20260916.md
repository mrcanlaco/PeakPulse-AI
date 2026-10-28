# Open-profit search batch 01 — kết quả provisional (2026-09-16)

Đây là tìm kiếm hữu hạn trên recycled history, không phải holdout và không phải bằng chứng lợi nhuận đã xác minh. Mọi trial đều mang nhãn PROVISIONAL.

## Contract và provenance

- Registry SHA256: e9d6dc013f6a813fdb2f4255478c6c2e157b40bbbe30e39a2c6a5e9877e615fd.
- Source SHA256: 4776fd9b6582708a1b05d08152673594e20a57d8686c93fee326fd6ba55244b8.
- Grid: 120 strategy trials + 1 cash comparator; source rows sau gate: 18810.
- Entry là open của nến 5m kế tiếp; OHLC adverse chỉ được dùng sau entry. Exit là time/cutoff, không TP/SL chủ động.
- Trade OHLC là mark proxy, maintenance ratio giả định 1%, funding observed cộng đúng dấu khi có, funding thiếu giả định 0 ở base và gắn cờ. Không phải liquidation/execution/PIT evidence của sàn.
- Future price gap sau entry giữ vốn tới cutoff và đánh dấu unresolved/non-rankable; không đổi thành loss 0 và không tái dùng vốn.

## Candidate counts

| Family | Raw | Sau cooldown 24h |
|---|---:|---:|
| momentum_long | 11528 | 1867 |
| exhaustion_short | 2612 | 533 |
| funding_fade_short | 194 | 80 |
| regime_switch | 7044 | 762 |
| hedged_fade | 2612 | 533 |

## Trial ranking (khám phá, không IID)

| Trial | Profit account | Ending wealth | Rankable |
|---|---:|---:|:---:|
| momentum_long__h168__l2__c20 | 22116.8199 | 32116.819879008526 | yes |
| momentum_long__h168__l2__c60 | 21396.8834 | 31396.88343525519 | yes |
| regime_switch__h168__l5__c60 | 13342.1369 | 23342.136879334063 | yes |
| momentum_long__h48__l5__c20 | 11078.5994 | 21078.599375363672 | yes |
| momentum_long__h48__l5__c60 | 10493.7983 | 20493.798309495476 | yes |
| momentum_long__h168__l5__c20 | 6752.7384 | 16752.738443425995 | yes |
| momentum_long__h48__l2__c20 | 3604.6119 | 13604.611857578251 | yes |
| momentum_long__h48__l1__c20 | 3405.4242 | 13405.424243638301 | yes |
| momentum_long__h48__l1__c60 | 3094.9058 | 13094.905763771454 | yes |
| funding_fade_short__h48__l10__c20 | 2900.3589 | 12900.35892297841 | yes |
| momentum_long__h48__l2__c60 | 2857.0307 | 12857.030661074632 | yes |
| funding_fade_short__h48__l10__c60 | 2686.3736 | 12686.373626121225 | yes |

Cash comparator: profit 0.0000; đây là mốc 0, không phải một trade path.
Top provisional trial (không phải winner xác minh): momentum_long__h168__l2__c20.

### Sensitivity đã đăng ký cho top provisional trial

| Comparison | Profit | Rankable |
|---|---:|:---:|
| top base (momentum_long__h168__l2__c20) | 22116.819879008526 | yes |
| same family/horizon, 1x same cost (momentum_long__h168__l1__c20) | 992.3992426689547 | yes |
| same family/horizon, 60bps (momentum_long__h168__l2__c60) | 21396.88343525519 | yes |
| same family/12h (momentum_long__h12__l2__c20) | -1474.3000995059083 | yes |
| same family/48h (momentum_long__h48__l2__c20) | 3604.611857578251 | yes |

- Top opportunity-path status counts before account overlap (not account realized PnL): {'liquidated_proxy': 98, 'open_at_cutoff': 46, 'time_exit': 1723}.
- Top opportunity-path month summary (not account realized PnL): {'2026-02': {'selected': 324, 'resolved': 324, 'unresolved_or_rejected': 0, 'status_counts': {'liquidated_proxy': 13, 'time_exit': 311}, 'mean_net_return_on_margin': -0.00045579134417460195}, '2026-03': {'selected': 258, 'resolved': 258, 'unresolved_or_rejected': 0, 'status_counts': {'liquidated_proxy': 17, 'time_exit': 241}, 'mean_net_return_on_margin': -0.09087468911415572}, '2026-04': {'selected': 429, 'resolved': 429, 'unresolved_or_rejected': 0, 'status_counts': {'liquidated_proxy': 18, 'time_exit': 411}, 'mean_net_return_on_margin': 0.6751803076174192}, '2026-05': {'selected': 284, 'resolved': 284, 'unresolved_or_rejected': 0, 'status_counts': {'liquidated_proxy': 8, 'time_exit': 276}, 'mean_net_return_on_margin': 0.04774124075041512}, '2026-06': {'selected': 360, 'resolved': 360, 'unresolved_or_rejected': 0, 'status_counts': {'liquidated_proxy': 32, 'time_exit': 328}, 'mean_net_return_on_margin': 0.13456521405441524}, '2026-07': {'selected': 212, 'resolved': 212, 'unresolved_or_rejected': 0, 'status_counts': {'liquidated_proxy': 10, 'open_at_cutoff': 46, 'time_exit': 156}, 'mean_net_return_on_margin': 0.02784232834602247}}.
- Top opportunity-path symbol concentration (not account realized PnL): {'top_symbols_by_path_return': [{'symbol': 'RAVEUSDT', 'net_return_on_margin_sum': 195.10825745807372}, {'symbol': 'VELVETUSDT', 'net_return_on_margin_sum': 41.305453531197074}, {'symbol': 'AKEUSDT', 'net_return_on_margin_sum': 37.391762071492714}, {'symbol': 'BEATUSDT', 'net_return_on_margin_sum': 36.59791483090792}, {'symbol': '币安人生USDT', 'net_return_on_margin_sum': 28.04912429650941}, {'symbol': 'HUSDT', 'net_return_on_margin_sum': 22.25414479316164}, {'symbol': 'LABUSDT', 'net_return_on_margin_sum': 19.34559151561958}, {'symbol': 'SKYAIUSDT', 'net_return_on_margin_sum': 10.698118652815237}, {'symbol': 'UBUSDT', 'net_return_on_margin_sum': 7.982836150864642}, {'symbol': 'ENJUSDT', 'net_return_on_margin_sum': 5.736213551369669}], 'symbol_count_with_resolved_path': 180, 'top_5_abs_share': 0.5690583077154939}.
- Top opportunity-path future-gap unresolved: 0; open-at-cutoff: 46; entry rejected: 0.
Các dòng trên là sensitivity/context đã đăng ký, không phải reselection hoặc causal test.

Các trial khác nhau không phải account paths độc lập; bảng trên chỉ xếp hạng trong batch đã đăng ký và không chọn lại sau stress.

## Coverage và giới hạn

- Symbols đọc một lần: 181; price files thiếu: 0; funding files thiếu: 0.
- Price paths thiếu entry: 0; paths có future gap: 0.
- Funding, maintenance tiers, venue leverage/borrow, continuous mark, fills và liquidation thật chưa được attested. Không gọi 10x là được sàn chấp nhận.
- Universe chỉ gồm coin đã pump >=15% và kế thừa caveat của PIT cohort cũ; Feb–Jul là recycled history.

## Diagnostic cố định của winner

- withdrawal_control: trial momentum_long__h168__l2__c20, profit -3838.330080696209; không dùng để chọn lại winner.
- funding_stress_control: trial momentum_long__h168__l2__c20, profit 18413.98448120848; không dùng để chọn lại winner.

Executed-path audit được lưu trong JSON cho candidate IDs thực sự account engine thực thi (kèm cả hai legs hedge):
- top_base: 27 executed candidate paths.
- withdrawal_control: 27 executed candidate paths.
- funding_stress_control: 27 executed candidate paths.

Kết luận: đây là proxy account-path research. Không có câu verified-profit, causal advantage hoặc promotion nào từ artifact.
