# V3 sáu tháng — replay đường giá OOS đã xuất (2026-09-15)

Đây là replay hồi cứu trên cohort OOS đã lưu, không phải holdout mới và không
phải phép so sánh chính sách nhân quả. Worker chỉ đọc Parquet local, dùng
`MarketFiles`, `_replay_event` và `_metrics` của
`scripts/research_v3_six_months.py`; không chọn lại cohort, không áp dụng thêm
cooldown, không train model và không tải dữ liệu.

## Phạm vi và nguồn

- Nguồn event: `artifacts/v3_six_month_20260915/oos_reference_events.json`.
- Kết quả: `artifacts/v3_six_month_20260915/oos_price_replay.json`.
- Cửa sổ cố định `[2026-02-01, 2026-08-01)` UTC; tháng 2 không có OOS score
  nên không có event replay.
- 153 event được replay (139 locked parent, 14 runtime Timing), 40 mã đọc một
  lần. Mỗi event kiểm tra `normalise_boundary(feature_time)` đúng bằng
  `signal_time_utc` nguồn.
- Funding được đọc để ghi coverage nhưng không có provider attestation:
  `funding_verified=0` và compact eligibility bị giữ lại ở mọi event. Số dòng
  đạt cadence heuristic không phải bằng chứng funding.

Phân biệt provenance: 153 lane-event rows (139 locked parent, 14 runtime
Timing) tương ứng 149 source_event_id duy nhất; 4 source event xuất hiện ở cả
hai lane. Đây là hai góc nhìn chồng lấn, không phải hai mẫu độc lập và không
được cộng lại hoặc so sánh theo nghĩa nhân quả.

Compact weighted-average execution path và post-stop diagnostic đã được
replay; tuy vậy compact_financial_outcome_eligible=false cho toàn bộ event vì
thiếu provider funding attestation. Các tỷ lệ dưới đây chỉ là chẩn đoán đường
giá hồi cứu, không phải nhãn tài chính đủ điều kiện.

## Đường giá và sau Stop

| Lane | Mẫu số event | Đường giá đủ | Giá chạm TP trước Stop | Tỷ lệ TP / mẫu số | Stop | Sau Stop đạt TP / Stop |
|---|---:|---:|---:|---:|---:|---:|
| Locked parent | 139 | 139 | 58 | 41.73% | 59 | 18/59 = 30.51% |
| Locked Champion subset | 21 | 21 | 11 | 52.38% | 7 | 2/7 = 28.57% |
| Runtime Timing | 14 | 14 | 6 | 42.86% | 7 | 3/7 = 42.86% |
| Runtime Champion subset | 4 | 4 | 1 | 25.00% | 2 | 1/2 = 50.00% |

Các tỷ lệ trên là mô tả đường giá close-fill. `target_after_stop` là kết quả
theo dõi độc lập, không biến lệnh đã Stop thành lệnh thắng. Replay status theo
từng event, actual status và post-stop status đều nằm trong JSON.

## Phân rã theo tháng

Tỷ lệ trong bảng là `price_targets / price_path_resolved`:

| Lane | Tháng 3 | Tháng 4 | Tháng 5 | Tháng 6 | Tháng 7 |
|---|---:|---:|---:|---:|---:|
| Locked parent | 11/20 (55.0%) | 13/38 (34.2%) | 2/13 (15.4%) | 20/47 (42.6%) | 12/21 (57.1%) |
| Locked Champion subset | 1/1 (100%) | 5/11 (45.5%) | — | 1/4 (25.0%) | 4/5 (80.0%) |
| Runtime Timing | 0/1 (0%) | — | 0/1 (0%) | 6/12 (50.0%) | — |
| Runtime Champion subset | 0/1 (0%) | — | — | 1/3 (33.3%) | — |

Mẫu nhỏ chỉ là mô tả; không dùng để tuyên bố cải thiện. Không có compact win,
precision hay net return đủ điều kiện funding trong artifact này. Không suy ra
ưu thế giữa hai lane vì chúng là hai quy tắc chọn event khác nhau trên cùng
nguồn lịch sử tái sử dụng.
