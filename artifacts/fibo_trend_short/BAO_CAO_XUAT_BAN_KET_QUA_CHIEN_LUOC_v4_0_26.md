# BÁO CÁO XUẤT BẢN KẾT QUẢ CHIẾN LƯỢC PEAKPULSE AI — FIBO TREND SHORT (v4.0.26 & PAPER OOS v1)

- **Ngày xuất bản:** `2026-10-20 22:55:00+07:00` (`2026-10-20T15:55:00Z`)
- **Phạm vi dữ liệu lịch sử (Backtest Ceiling):** `2020-01-01T00:00:00Z` $\to$ `2025-12-31T23:59:59Z` (tuyệt đối không dùng dữ liệu 2026 để tối ưu tham số).
- **Trạng thái kiểm định giao dịch tiền thật (Live Sign-off):** `NOT_GRANTED` (`orders_allowed = false`, cổng chọn tự động lịch sử: `CASH`).
- **Trạng thái Paper OOS thời gian thực (`paper_oos_v1`):** `OBSERVING` (`PID 28988`, `revision = 781`, `critical_incidents = 0`, 12 tài khoản `NAV = 100.0`).

---

## 1. Tóm tắt Điều hành (Executive Summary)

Qua 26 vòng kiểm toán độc lập và chuẩn hóa kỹ thuật (`v4.0.0` $\to$ `v4.0.26`), chiến lược **Fibo Trend Short** đã được chuyển đổi từ một bản mẫu backtest lý tưởng sang hệ thống hạch toán danh mục cấp độ thực chiến (Institutional-grade Accounting):

1. **Khẳng định về khả năng sinh lời:**
   - Chiến lược **không mất đi lợi nhuận** khi áp dụng điều kiện thực thi chuẩn (**`standard_vip6`**: phí Taker `2.5 bps` + trượt giá `10.0 bps` = **`12.5 bps` mỗi lần khớp**).
   - Trên vũ trụ **338 mã** đã khử hoàn toàn thiên lệch sống sót (Point-in-Time Universe & Contract Lifecycle, `v4.0.21`), **4/6 ứng viên có lợi nhuận ròng dương toàn kỳ 6 năm (`2020–2025`)** và **cả 6/6 ứng viên đều có lợi nhuận ròng dương trong giai đoạn 2 năm gần nhất (`2024–2025`)**.
   - Ứng viên dẫn đầu toàn kỳ 2020–2025 là **`Elite + Sniper` (`elite_sniper_risk`)** với lợi nhuận ròng **`+26.19%`** (chạy liên tục xuyên năm đạt **`+26.05%`**), mức sụt giảm vốn tối đa (**MaxDD**) chỉ **`15.33%`** qua `790` lệnh giao dịch.
   - Trong giai đoạn `2024–2025`, ứng viên **`Sniper RR ≥ 1, tối đa 24 giờ` (`sniper_rr1_horizon24`)** đạt **`+21.46%`** (khoảng tin cậy Bootstrap 95% trung bình tuần hoàn toàn dương: **`[+0.0727%; +0.2992%]`**) và vẫn giữ được lãi ròng **`+1.70%`** ngay cả dưới bài kiểm tra tra tấn chi phí **`stress_regular` (`55.0 bps` mỗi lần khớp)**.

2. **Vì sao chưa cấp quyền giao dịch tiền thật tự động (`live_signoff = NOT_GRANTED`)?**
   - Ở kịch bản tra tấn **`stress_regular`** (phí Taker `5.0 bps` + trượt giá `50.0 bps` = mất `0.55%` mỗi lần khớp, tương đương mất `>1.10%` cho một vòng vào–ra nhiều bậc TP), toàn bộ 6 ứng viên đều âm khi tính gộp cả giai đoạn 6 năm `2020–2025` (dẫn đầu là `Elite + Sniper` ở mức `-14.48%`).
   - Do năm `2023` là năm thị trường phục hồi bất lợi cho vị thế Short và điều kiện cổng Walk-Forward tự động yêu cầu *“mọi năm trước đều dương ở bản chuẩn VÀ tổng lợi nhuận bản Stress không âm, MaxDD từng năm $\le 15\%$”*, bộ chọn tự động giữ trạng thái phòng thủ **`CASH`**.
   - Để có bằng chứng Out-of-Sample (OOS) khách quan tuyệt đối mà không phụ thuộc vào dữ liệu quá khứ 2020–2025 đã qua nhiều vòng nghiên cứu, hệ thống **Paper OOS thời gian thực (`paper_oos_v1`)** đã được khóa giao thức (`SHA256: 3b394d2dc14e...`) và vận hành từ ngày `18/10/2026`.

---

## 2. Lộ trình Kiểm toán & Tiến hóa Kỹ thuật (`v4.0.0` $\to$ `v4.0.26`)

| Phiên bản | Hồ sơ đối chiếu | Các bước khắc phục & Chuẩn hóa cốt lõi |
| :--- | :--- | :--- |
| **`v4.0.0` – `v4.0.4`** | [RED_TEAM_REAUDIT_RESPONSE_v4_0_4_2026-10-17.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/RED_TEAM_REAUDIT_RESPONSE_v4_0_4_2026-10-17.md) | Sửa lỗi kiểm tra lại SL hòa vốn trong cùng nến sau TP1/TP2; tách biệt chạy độc lập từng cấu hình (không lọc tập con từ M1); hạch toán danh mục đồng thời (Coupled Portfolio NAV); cố định quy tắc chọn vũ trụ coin theo thời điểm quá khứ (Point-in-Time). |
| **`v4.0.5`** | [RED_TEAM_REAUDIT_RESPONSE_v4_0_5_2026-10-17.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/RED_TEAM_REAUDIT_RESPONSE_v4_0_5_2026-10-17.md) | Khắc phục dứt điểm 4 phát hiện `FS404-01..04`: tính `cooldown` theo đúng giờ thoát thực tế (`exit_close_time`) thay vì số nến khi dữ liệu khuyết; xuất đầy đủ danh tính `executed_trade_ids` cho cả 112 nút danh mục; đồng bộ fingerprint `funding_8h`; giữ nguyên `terminal_outcome` từ simulator (**27/27 tests passed**). |
| **`v4.0.6`** | [PHUONG_PHAP_FIBO_SHORT_v4_0_6.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/PHUONG_PHAP_FIBO_SHORT_v4_0_6.md) | Tách bạch chế độ khối lượng `fixed_1x` và `m6_scaled`; sửa hệ số điểm `<55` về `0.80x`; cố định nến cuối IS đóng lúc `2026-01-01T00:00Z`; áp dụng phí `0/20/40/60 bps` trực tiếp vào simulator; xử lý nhảy giá mở cửa (open gap) qua SL/TP (**55/55 tests passed**). |
| **`v4.0.7` – `v4.0.21`** | [research_v4_0_9/REPORT.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/research_v4_0_9/REPORT.md), [research_v4_0_19/REPORT.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/research_v4_0_19/REPORT.md), [research_v4_0_21/REPORT.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/research_v4_0_21/REPORT.md) | Khóa chuẩn chi phí theo từng lần khớp ([BACKTEST_COST_STANDARD.json](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/BACKTEST_COST_STANDARD.json)); đối soát `360,781` sự kiện funding lịch sử thực tế trên `191` giai đoạn hợp đồng; kiểm định danh mục liên tục không reset năm (`v4.0.19`) và tái kiểm toàn bộ 6 cấu hình trên vũ trụ đã sửa vòng đời hợp đồng (`v4.0.21`). |
| **`v4.0.22` – `v4.0.26` & `paper_oos_v1`** | [research_v4_0_26/REPORT.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/research_v4_0_26/REPORT.md), [PROTOCOL.json](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/paper_oos_v1/PROTOCOL.json) | Xây dựng và kiểm thử toàn bộ đường ống tín hiệu thời gian thực (`signal_snapshot_v423`, `stream_execution_v424`, `decision_feed_v425`), khóa giao thức `paper_oos_v1` và triển khai quan sát 12 tài khoản Paper OOS từ `18/10/2026`. |

---

## 3. Bảng Kết quả Hiệu suất 6 Cấu hình Ứng viên (Đã Chuẩn hóa ở `v4.0.21`)

### 3.1. Hai kịch bản chi phí cố định ([BACKTEST_COST_STANDARD.json](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/BACKTEST_COST_STANDARD.json))
- **Bản Chuẩn (`standard_vip6`):** Phí Taker **`2.5 bps`** (`0.025%`) + Trượt giá bất lợi **`10.0 bps`** (`0.10%`) = **`12.5 bps` mỗi lần khớp** (tính cho cả lệnh vào và từng phần thoát `TP1`, `TP2`, `TP3`/SL/Time-exit; không giảm phí BNB).
- **Bản Stress (`stress_regular`):** Phí Taker **`5.0 bps`** (`0.05%`) + Trượt giá bất lợi **`50.0 bps`** (`0.50%`) = **`55.0 bps` mỗi lần khớp**.
- **Funding:** Hạch toán theo đúng timestamp và tỷ lệ `fundingRate` có dấu lịch sử thực tế trên khối lượng vị thế còn mở.

### 3.2. Hiệu suất NAV Toàn kỳ 6 Năm (`2020–2025`, Vũ trụ đã sửa `v4.0.21`)

| Mã Cấu hình | Tên Cấu hình | Lợi nhuận Ròng Chuẩn (`VIP6 + 10 bps`) | MaxDD (Chuẩn) | Số lệnh (Chuẩn) | Lợi nhuận Ròng Stress (`Regular + 50 bps`) | MaxDD (Stress) | Số lệnh (Stress) |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **`elite_sniper_risk`** | **Elite + Sniper (Khối lượng theo Stop 0.5% NAV)** | **`+26.19%`** | **`15.33%`** | 790 | `-14.48%` | `26.16%` | 813 |
| **`sniper_risk`** | **Sniper (Khối lượng theo Stop 0.5% NAV)** | **`+14.54%`** | **`18.05%`** | 940 | `-23.05%` | `31.54%` | 969 |
| **`sniper_rr1_horizon24`** | **Sniper RR ≥ 1, Giữ tối đa 24 giờ** | **`+7.91%`** | **`17.34%`** | 1,025 | `-30.13%` | `34.68%` | 1,043 |
| **`sniper_horizon24`** | **Sniper, Giữ tối đa 24 giờ** | **`+7.14%`** | **`18.45%`** | 1,263 | `-35.57%` | `37.92%` | 1,277 |
| `m6_risk` | M6 Mở rộng (Khối lượng theo Stop 0.5% NAV) | `-1.61%` | `28.72%` | 1,124 | `-40.22%` | `48.28%` | 1,149 |
| `reference_m6_fixed` | M6 Tham chiếu (Khối lượng cố định) | `-16.89%` | `66.84%` | 1,255 | `-91.35%` | `94.42%` | 1,225 |

*(Ghi chú: Đối với cấu hình dẫn đầu `Elite + Sniper`, khi chạy danh mục liên tục xuyên suốt 2020–2025 không đặt lại trạng thái đầu năm và bỏ embargo giữa các năm tại [research_v4_0_19/REPORT.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/research_v4_0_19/REPORT.md), lợi nhuận ròng Chuẩn đạt **`+26.05%`**, MaxDD giữ nguyên **`15.33%`**).*

### 3.3. Hiệu suất Giai đoạn 2 Năm Gần nhất (`2024–2025` Hồi cứu)

| Mã Cấu hình | Tên Cấu hình | Lợi nhuận Chuẩn (`2024–2025`) | CI 95% Trung bình Tuần (Chuẩn) | Lợi nhuận Stress (`2024–2025`) | CI 95% Trung bình Tuần (Stress) |
| :--- | :--- | ---: | :---: | ---: | :---: |
| **`reference_m6_fixed`** | M6 Khối lượng cố định | **`+66.06%`** | `[-0.1989%; +1.3555%]` | `-24.93%` | `[-1.0191%; +0.6569%]` |
| **`sniper_rr1_horizon24`** | **Sniper RR ≥ 1, Tối đa 24h** | **`+21.46%`** | **`[+0.0727%; +0.2992%]`** | **`+1.70%`** | `[-0.0908%; +0.1205%]` |
| **`m6_risk`** | M6 Khối lượng theo Stop | **`+19.73%`** | `[-0.0383%; +0.3863%]` | `-3.04%` | `[-0.2411%; +0.1742%]` |
| **`sniper_risk`** | **Sniper** | **`+18.80%`** | **`[+0.0032%; +0.3335%]`** | **`+4.76%`** | `[-0.1200%; +0.2075%]` |
| **`elite_sniper_risk`** | **Elite + Sniper** | **`+15.32%`** | `[-0.0017%; +0.2788%]` | **`+3.91%`** | `[-0.1094%; +0.1791%]` |
| **`sniper_horizon24`** | **Sniper, Tối đa 24h** | **`+13.89%`** | **`[+0.0048%; +0.2416%]`** | `-4.81%` | `[-0.1712%; +0.0688%]` |

---

## 4. Phân rã Dòng tiền & Hiệu suất Từng năm (Giải phẫu Sự sụt giảm từ "Chỉ số Đẹp" về Thực tế)

Số liệu kiểm toán tại [research_v4_0_9/REPORT.md](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/research_v4_0_9/REPORT.md) làm sáng tỏ cách thức phí giao dịch, độ trượt giá và chu kỳ thị trường tác động lên từng cấu hình:

### 4.1. Phân rã Kế toán Dòng tiền Danh mục (`2020–2025`, đơn vị: `% NAV đầu kỳ`)
$$\text{PnL Ròng} = \text{PnL Giá Tham Chiếu} - \text{Phí Taker} - \text{Trượt Giá} + \text{Funding}$$

| Cấu hình & Kịch bản | PnL Giá Tham chiếu | Phí Taker | Trượt giá (Slippage) | Funding Ròng | Lợi nhuận Ròng |
| :--- | ---: | ---: | ---: | ---: | ---: |
| **M6 Cố định — Chuẩn (`12.5 bps/fill`)** | `+53.63%` | `-12.03%` | `-48.14%` | `+19.74%` | **`+13.21%`** |
| **M6 Cố định — Stress (`55.0 bps/fill`)** | `+2.91%` | `-9.28%` | `-92.76%` | `+11.87%` | **`-87.26%`** |
| **Elite + Sniper — Chuẩn (`12.5 bps/fill`)** | `+20.80%` | `-2.12%` | `-8.47%` | `+3.24%` | **`+13.45%`** *(Vũ trụ v4.0.21: **`+26.19%`**)* |
| **Elite + Sniper — Stress (`55.0 bps/fill`)** | `+16.43%` | `-3.33%` | `-33.28%` | `+2.80%` | **`-17.38%`** *(Vũ trụ v4.0.21: **`-14.48%`**)* |
| **Sniper RR≥1 24h — Chuẩn (`12.5 bps/fill`)** | `+15.98%` | `-2.68%` | `-10.73%` | `+1.90%` | **`+4.47%`** *(Vũ trụ v4.0.21: **`+7.91%`**)* |
| **Sniper RR≥1 24h — Stress (`55.0 bps/fill`)** | `+11.78%` | `-3.98%` | `-39.75%` | `+1.58%` | **`-30.37%`** *(Vũ trụ v4.0.21: **`-30.13%`**)* |

### 4.2. Lợi nhuận theo Từng năm Lịch sử (`2020–2025`, Bản Chuẩn VIP6 tại `v4.0.9`)

| Cấu hình | Năm 2020 | Năm 2021 | Năm 2022 | Năm 2023 | Năm 2024 | Năm 2025 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Elite + Sniper (`elite_sniper_risk`)** | **`+3.43%`** | **`+2.82%`** | **`+6.24%`** | `-8.15%` | **`+3.24%`** | **`+5.89%`** |
| **Sniper (`sniper_risk`)** | **`+1.50%`** | `-1.51%` | **`+5.52%`** | `-13.10%` | **`+6.28%`** | **`+5.07%`** |
| **Sniper RR ≥ 1, Tối đa 24h** | `-1.74%` | **`+2.86%`** | `-3.18%` | `-4.80%` | **`+9.50%`** | **`+2.40%`** |
| **Sniper, Tối đa 24h** | **`+0.20%`** | **`+3.28%`** | `-0.81%` | `-10.25%` | **`+8.88%`** | **`+0.79%`** |
| **M6 Khối lượng theo Stop (`m6_risk`)** | **`+2.14%`** | `-5.76%` | **`+1.68%`** | `-15.65%` | `-0.78%` | **`+8.01%`** |
| **M6 Khối lượng cố định (`reference_m6_fixed`)** | `-0.44%` | `-1.88%` | **`+23.29%`** | `-29.53%` | `-2.32%` | **`+36.55%`** |

### 4.3. Bốn bài học cốt lõi rút ra từ quá trình kiểm toán
1. **Độ nhạy rất cao với chi phí trượt giá (Slippage Sensitivity):** Do chiến lược thoát lệnh nhiều nhịp (`TP1`, `TP2`, `TP3`), mỗi điểm cơ bản (bps) trượt giá bị nhân lên qua nhiều lần khớp. Ở mức trượt giá `10 bps/fill`, `Elite + Sniper` giữ được lợi nhuận tốt (`+26.19%`), nhưng nếu để trượt giá lên tới `50 bps/fill` (như khi vào lệnh Market lớn trên các đồng thanh khoản mỏng), trượt giá sẽ lấy đi hơn `33%` NAV và xóa sạch lợi thế.
2. **Kiểm soát rủi ro theo khoảng cách Stop (`0.5% NAV risk`) là bắt buộc:** Cấu hình `Elite + Sniper` thắng 5/6 năm (2020, 2021, 2022, 2024, 2025) và chỉ lỗ nhẹ `-8.15%` vào năm 2023 (trong khi bản `M6 cố định` lỗ `-29.53%` năm 2023 và MaxDD lên tới `66.84%`).
3. **Loại bỏ hoàn toàn thiên lệch nhìn trước tương lai (Zero Look-ahead & Point-in-Time):** Danh sách coin mỗi tháng chỉ được chọn từ các hợp đồng đang giao dịch thực tế tại thời điểm đó với độ sâu lịch sử $\ge 50$ ngày và râu nến H4 `p90 <= 3.2%`.
4. **Tính trung thực khoa học trong thẩm định Alpha:** Không dùng việc tinh chỉnh tham số trên tập 2024–2025 để tự công nhận OOS. Mọi kết luận duyệt giao dịch tiền thật phải dựa trên **Paper OOS thời gian thực (`paper_oos_v1`)**.

---

## 5. Trạng thái Vận hành Thực tế của Hệ thống Paper OOS (`paper_oos_v1`)

Tính đến **`2026-10-20 22:55:29+07:00` (`2026-10-20T15:55:29Z`)** theo [STATUS.json](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/paper_oos_v1/STATUS.json):

- **Trạng thái tiến trình:** `OBSERVING` (`PID = 28988`, `error = null`, `revision = 781`).
- **Mốc dữ liệu mới nhất đã xử lý:**
  - Nến 5m mới nhất (`last_bar_ms`): `1792511700000` (`2026-10-20T15:55:00Z` — khớp 100% thời gian thực hiện tại).
  - Tín hiệu H1 mới nhất (`last_signal_ms`): `1792508400000` (`2026-10-20T15:00:00Z` — nến H1 đóng gần nhất).
- **Độ ổn định vận hành:**
  - Kể từ khi khôi phục tự động sau sự cố khởi động lại máy chủ ngày `19/10/2026 14:31` ([20261019T073310Z_unexpected_reboot_recovered.json](file:///c:/Rapid%20Coding/dao_vang/artifacts/fibo_trend_short/paper_oos_v1/operations/20261019T073310Z_unexpected_reboot_recovered.json)), hệ thống đã chạy liên tục **hơn 32 giờ không phát sinh thêm bất kỳ sự cố trễ nhịp nào** (`opportunity_incidents` giữ nguyên ở mức `176`, `critical_incidents = 0`).
- **Tình hình 12 tài khoản Paper (`6 cấu hình × 2 kịch bản chi phí`):**
  - `open_positions`: `0`
  - `accepted_trades`: `0` trên cả 12 tài khoản
  - `closed_trades`: `0` trên cả 12 tài khoản
  - `NAV`: **`100.00`** trên cả 12 tài khoản.
  - Web Dashboard giám sát nội bộ: `http://127.0.0.1:8766` (`lean-v2` mode).
