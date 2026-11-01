# Mô hình production và mức độ bằng chứng

`configs/live.yaml` là cấu hình production không chứa bí mật và được quản lý
phiên bản trong Git. Đây là nguồn duy nhất chọn bundle mà scanner live sử dụng;
bí mật vận hành chỉ nằm trong `.env.docker`. `metadata.json` trong bundle là
nguồn sự thật cho cutoff, threshold, feature schema và checksum.


> **Kiến trúc Production Chính thức (Phân tầng 2 Động cơ):**
> - **Tầng 2 — Engine Tín hiệu Hành động Chính thức (`dao_vang.fibo_short` · `v4.0.21`):** Đảm nhiệm toàn bộ cảnh báo **Telegram chính thức** và kế hoạch giao dịch (`Entry`, `SL Fibo 0.886`, `TP1/TP2/TP3`, định cỡ `0.5% NAV`) với 2 chính sách đã qua kiểm toán 6 năm (`2020–2025`): `elite_sniper_risk` và `sniper_rr1_horizon24`.
> - **Tầng 1 — Frozen ML Bundle (`frozen_20260906_105716_bc3c369b`, mô tả bên dưới):** Đảm nhiệm vai trò **Radar Cảnh báo Sớm trên Web UI (`RADAR` / `WATCHLIST`)** ở chế độ `operating_mode: shadow` và `shadow_telegram_enabled: false` (không bắn Telegram trực tiếp).
> - Xem toàn bộ bảng đối chứng định lượng và hướng dẫn vận hành tại [`docs/PRODUCTION_DEPLOYMENT_GUIDE.md`](PRODUCTION_DEPLOYMENT_GUIDE.md).
## Phiên bản đang phục vụ

| Trường | Giá trị |
|---|---|
| Model ID | frozen_20260906_105716_bc3c369b |
| Freeze time | 2026-09-06T10:57:16.293277+07:00 |
| Train cutoff | 2026-07-28T19:05:39.999000+07:00 |
| Frozen threshold | 0.4100000000000001 |
| Calibration | isotonic_v1 |
| Model SHA-256 | 27961bc6c9a24e52136d00f208258343e8d5b75980fe156dbfba699264f51a12 |
| Calibrator SHA-256 | 0e425413f24a3a96ece91d1e201f0be4dd3709526733d19a19d649871b3c72db |
| Metadata canonical JSON SHA-256 | ef0299576ba6eb8410c3ac2b62b8da9d201183f845f22129417c9de6d1e7849a |

CI chạy tests/qa/test_live_release_contract.py để bảo đảm config live trỏ
đúng bundle, model/calibrator tồn tại, checksum khớp và estimator có thể nạp.
Serving path cũng kiểm tra checksum và fail closed trước khi phát xác suất.

## Migration mục tiêu 20%/24h

Mục tiêu phát triển hiện tại là `distribution_short_v2`: positive khi giá
chạm drawdown 20% trong 24 giờ trước khi vi phạm MAE +4%. Contract v1 không bị
sửa ngược để bảo toàn khả năng tái tạo lịch sử. Model đang phục vụ ở trên vẫn
là v1/8%; vì chưa có bundle v2 được calibration và kiểm định, production chưa
được phép trình bày xác suất v1 như xác suất đạt mục tiêu 20%.

Promotion v2 yêu cầu: tạo bundle mới với metadata v2, sinh protocol mới khóa
checksum, đạt sample/event gates và sau đó mới đổi `scanner.frozen_model_id`.

## Protocol forward-test độc lập

Hợp đồng đánh giá live được khóa tại
`configs/forward_test_live_v1.json`:

| Trường | Giá trị |
|---|---|
| Protocol schema | forward_evidence_v1 |
| Protocol fingerprint | c0db434c787b2b02811138e42a11fe291c25cfcf28487e543b7a00935680ef06 |
| Evaluation start | 2026-09-06T10:57:16.293277+07:00 (freeze time) |
| Universe | Tất cả dòng có nhãn trưởng thành do policy scanner đã khóa tạo ra; không lọc symbol hậu nghiệm |
| Label contract | distribution_short_v1, 24 giờ |
| Event gap | 240 phút theo từng symbol |
| Sample gates | 1.000 dòng dùng được, 50 event dương tính, 30 event dự báo, 7 ngày |
| External API cost | 0 USD; suy luận dùng bundle cục bộ |
| Compute cost | Chưa đo; không được diễn giải thành 0 USD |

CLI, API React và giao diện Streamlit cũ đều dùng cùng evaluator. Model khác
`model_id` trong protocol bị trả `protocol_required` và không được rơi về cách
tính legacy. Evaluator khóa canonical JSON checksum của metadata (cutoff,
threshold, feature schema), ổn định giữa LF/CRLF, và đối chiếu checksum
model/calibrator với cả protocol lẫn metadata;
loại dữ liệu trước freeze time, chờ nhãn đủ 24 giờ, từ chối dòng trùng, ghi
fingerprint dataset/universe, đo latency và chỉ trả metric khi mọi gate đạt.

`all_scored_rows` là một quy tắc bao hàm đã khóa, không phải danh sách symbol
cố định. Báo cáo luôn ghi lại toàn bộ symbol quan sát và fingerprint policy để
phát hiện thay đổi hậu nghiệm.

## Số liệu hiện có và giới hạn diễn giải

Metadata của bundle lưu các training_stats sau:

| Metric | Giá trị |
|---|---:|
| Precision | 0.3895582329 |
| Brier score | 0.1859139683 |
| ECE | 0.0261074685 |

Đây là số liệu đi kèm quá trình tạo bundle, không phải bằng chứng forward-test
độc lập và không chứng minh lợi nhuận giao dịch. Protocol đã tồn tại nhưng
chưa có báo cáo được commit cho thấy toàn bộ sample gate đã đạt. Cho đến lúc
đó, `metrics` phải là `null` và trạng thái đúng là
`insufficient_evidence`. Vì vậy:

- Không dùng các con số ROI, win rate, lead time hoặc event recall trong tài
  liệu nghiên cứu lịch sử để mô tả hiệu năng live hiện tại.
- Không tự động thăng hạng challenger. Mọi thay đổi champion phải qua review và
  đổi scanner.frozen_model_id bằng commit rõ ràng.
- Scanner chỉ phát cảnh báo human-in-the-loop; không được xem xác suất hoặc
  anomaly score là lệnh giao dịch.

## Điều kiện để công bố hiệu năng production

Protocol v1 chỉ cho phép hiển thị event precision/recall, row
precision/recall và Brier khi:

1. `feature_time` sau cả train cutoff và freeze time; nhãn đã trưởng thành đủ
   horizon.
2. Model ID, model/calibrator checksum, label contract và universe policy đều
   khớp protocol.
3. Không có dòng trùng; tối thiểu 1.000 dòng dùng được, 50 event dương tính,
   30 event dự báo và 7 ngày quan sát.
4. Báo cáo ghi dataset/universe fingerprint, số dòng bị loại, event grouping,
   latency, external API cost và trạng thái đo compute cost.

Các metric này vẫn không chứng minh ROI/win rate và không tự động cho phép đổi
champion. Confidence interval, ECE theo phiên bản, phân rã regime và so sánh
baseline/challenger trên cùng event là các gate tiếp theo trước khi dùng báo
cáo cho quyết định thăng hạng model.
