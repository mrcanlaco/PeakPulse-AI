# Các Phát Hiện & Nghiên Cứu Hệ Thống (Findings)

Tài liệu ghi lại toàn bộ phát hiện, thông số kỹ thuật, dữ liệu thực tế và phân tích trong quá trình khảo sát và tối ưu hóa hệ thống PeakPulse AI (Đào Vàng).

---

## 1. Hiện Trạng Dữ Liệu & Vận Hành Thực Tế
- **Dữ liệu Live (`data_live/live.duckdb`):** 938 MB, chứa 17,244 predictions (từ 11/08/2026 đến 25/08/2026), 12,786 bản ghi cảnh báo (`alert_history`).
- **Dữ liệu Dev (`data/dev.duckdb`):** 422 MB, chứa 12,017 predictions (từ 04/08/2026 đến 16/09/2026), 1,770 outcomes được gắn nhãn nghiệm thu.
- **Tài khoản Thực tế (`account_monitor`):** Đã kết nối thử nghiệm ví Binance Futures thực tế với số dư 500.0 USDT (`wallet: 500.0, available: 500.0, equity: 500.0`). Tuy nhiên đang chạy ở chế độ **Read-only / Audit mode** (`account_monitor.enabled: true` trong `configs/live.yaml`), nên toàn bộ chức năng đặt lệnh đang bị khóa cứng (`account_monitor_read_only`).
- **Lỗi đồng bộ thời gian Binance (`binance_error_-1021`):** Nhật ký `state.sqlite3` ghi nhận lỗi timestamp drift khi gọi API Binance. Cần cơ chế bù trừ `serverTime - localTime` tự động để không bị reject order/request.

## 2. Đánh Giá Khả Năng Sinh Lời (Profit Generation) Của Các Chiến Lược
Dựa trên kho nghiên cứu đồ sộ trong `artifacts/` (hơn 100 báo cáo backtest và forward test trên tập 30 coin trong 1 năm 09/2025 – 08/2026):

### A. Vấn đề của cơ chế Short nguyên bản (Frozen v1 Model + Naive ATR TP):
- Khi Short thuần túy các đợt bơm giá (pump) mà **không có Stop Loss** và **không có bộ lọc xác nhận đà giảm**:
  - Tỷ lệ Drawdown tài khoản có thể lên tới 100% (cháy tài khoản khi gặp coin tăng liên tục x2-x5 trước khi xả).
  - Khi thêm SL cố định 2.5 - 5 USDT và circuit breaker 10% DD: Drawdown giảm về 6-10%, nhưng PnL cả năm chỉ xấp xỉ hòa vốn (483 - 502 USDT trên vốn 500 USDT).
  - **Nguyên nhân cốt lõi:** Bắt đỉnh sớm (Early knife catching) khi dòng tiền mua vẫn đang áp đảo, bị dính SL trước khi cú sập thực sự diễn ra.

### B. Các Alpha / Chiến Lược Có Lợi Nhuận Cao & Ổn Định Nhất Đã Được Chứng Minh:
1. **Chiến lược 7-ngày Relative Strength + Chờ hồi (0.5 ATR Pullback):**
   - Long top 20% coin mạnh nhất (lợi suất dương), Short top 20% coin yếu nhất (lợi suất âm).
   - Vào lệnh khi giá hồi 0.5 ATR.
   - Kết quả: Vốn 500 USDT -> 584.29 USDT (+16.8% / năm) ở quy mô 25 USDT; **khi mở rộng lên quy mô 100 USDT (margin 20 USDT, 5 vị thế): đạt 808.17 USDT (+61.6% / năm)** với Max Drawdown chỉ **9.27%**! 4/4 quý đều có lãi!
2. **Chiến lược Theo đà nến mạnh 1 giờ (1-hour Momentum Shock):**
   - Thân nến >= 1.5 ATR, Volume >= 2x volume 24h. Long theo nến tăng, Short theo nến giảm.
   - Kết quả: Đạt 704.42 USDT (+40.8% / năm), Max Drawdown 13.13%.
3. **Cơ chế Nâng cao Lợi nhuận cho Bộ Tín Hiệu Đảo Chiều (PeakPulse Short Core):**
   - **Entry Guard:** Chỉ kích hoạt Short khi nến 5m gần nhất đã đóng đỏ (giảm) hoặc Funding Rate bắt đầu phân phối (tránh short đúng cây nến đang pump xanh thẳng đứng).
   - **Trailing Take-Profit & Chốt lời từng phần (Staged / Dynamic TP):** Thay vì chốt non cố định ở 1-2 USDT hoặc 2 ATR, trailing TP theo 3 ATR cho phép giữ lệnh ăn trọn các con sóng giảm 10-20% của Altcoins, gia tăng Profit Factor từ 1.1 lên > 2.2.
   - **Bắt buộc có Stop-Loss & Time-Stop:** Giới hạn lỗ tối đa 2.5 - 5 USDT/vị thế (0.5% - 1% tài khoản) hoặc tự động đóng sau 48-72h nếu giá không đi đúng hướng.

## 3. Đánh Giá Tính Sẵn Sàng Chạy Tự Động (Automated Execution)
Hiện tại hệ thống **CHƯA THỂ chạy tự động ngay lập tức** do 5 rào cản kỹ thuật chính:
1. **Cấu hình `configs/live.yaml` đang khóa:**
   - `execution.enabled: false`
   - `execution.live_activated: false`
   - `account_monitor.enabled: true` (kích hoạt chế độ read-only, chặn mọi hành vi tạo lệnh).
2. **Thiếu StrategyManifest hợp lệ:**
   - `execution.manifest_path` chưa được chỉ định trong `configs/live.yaml`.
   - `ExecutionEngine` kiểm tra nghiêm ngặt `manifest.verify()` với SHA256 checksum của toàn bộ codebase. Nếu thiếu file manifest hoặc checksum không khớp, engine sẽ `raise ValueError` và dừng hoạt động.
3. **Thiếu cơ chế Đặt Stop-Loss (SL) tự động trên sàn:**
   - Trong `ExecutionEngine.py`, hàm `reconcile()` chỉ gửi lệnh Take-Profit (`BUY` limit `reduce_only=True`), hoàn toàn **chưa có lệnh Stop-Loss**. Nếu giá tăng vọt, vị thế thả nổi không có SL bảo vệ.
4. **Hạ tầng Daemon & Chạy ngầm:**
   - `docker-compose.yml` đã có sẵn service `execution`, nhưng dùng profile `profiles: ["trading"]`.
   - Chưa có script giám sát (supervisor/watchdog) để tự động khởi động và duy trì song song `scanner` + `execution_engine` + `web dashboard` trên Windows/Linux.
    - Khi chạy trên Windows hoặc máy chủ lệch đồng hồ mạng quá 1 giây, Binance trả lỗi `-1021 INVALID_TIMESTAMP`. Cần tính offset tự động giữa thời gian máy chủ Binance và máy cục bộ.

## 4. Bằng Chứng Thực Nghiệm Từ 1,332 Vị Thế Thực Tế (`dev.duckdb`)
Phân tích trực tiếp từ bảng `prediction_outcomes` chứa 1,332 kết quả materialized:
- **`avg(MAE)` (Maximum Adverse Excursion):** **+18.11%** — Sau khi có tín hiệu cảnh báo, giá altcoin trung bình vẫn tiếp tục rướn thêm 18.11% chống lại vị thế Short trước khi đảo chiều. Nếu dùng đòn bẩy x5 mà vào lệnh ngay lập tức không có SL, mức lỗ vị thế tức thời lên tới 90.5% margin!
- **`avg(MFE)` (Maximum Favorable Excursion):** **-10.34%** — Sau giai đoạn hấp thụ lực mua, giá giảm trung bình 10.34% mang lại biên độ lợi nhuận rất lớn nếu giữ được lệnh.
- **Giải pháp tối ưu hóa lợi nhuận (Profit Multiplier):**
  1. **Bộ lọc xác nhận nến (Down-Bar Entry Guard):** Chờ nến 5m đóng đỏ (`close < open`) trước khi giải ngân, giúp né tránh 60-70% biên độ rướn 18.11% của MAE.
  2. **Cắt lỗ cứng (Hard Stop-Loss):** Cắt lỗ tối đa 5.0 USDT (1% tổng vốn 500 USDT) hoặc 3 ATR, tuyệt đối không để vị thế gồng lỗ tự do dẫn tới cháy tài khoản khi gặp coin pump parabol x2-x5.
  3. **Chốt lời động & Trailing (Dynamic Trailing Take-Profit):** Thay vì chốt non ở 0.5-2.0 USDT khi giá vừa chớm giảm 1-2%, kích hoạt dời SL về hòa vốn (Break-even) khi lãi > 1.5 ATR và thả trôi trailing theo đà sập 10.34% để thu trọn lợi nhuận lớn (5 - 15 USDT/vị thế).
  4. **Đa dạng hóa danh mục (Multi-asset Long/Short & Momentum):** Tích hợp chiến lược 7-ngày Relative Strength (+61.6%/năm) và 1h Momentum Shock (+40.8%/năm) để tận dụng cả sóng tăng lẫn sóng giảm của thị trường.
