# Kế Hoạch Đánh Giá & Hoàn Thiện Cơ Chế Lợi Nhuận & Tự Động Hóa PeakPulse AI (Đào Vàng)

## Mục Tiêu
1. Khảo sát toàn diện dữ liệu thực tế, mô hình ML, chiến lược sinh lời (profit generation) và kết quả backtest / forward test / live data.
2. Đánh giá chi tiết cơ chế tạo lợi nhuận hiện tại: tỷ lệ thắng (win rate), kỳ vọng PnL, RR, phí giao dịch, trượt giá, cơ chế chốt lời / cắt lỗ, định cỡ vị thế (position sizing).
3. Đánh giá tính khả thi và trạng thái sẵn sàng của việc chạy tự động (automated execution / paper / live): kiến trúc bot, reconciliation, safety gates, kill switch, supervisor daemon.
4. Đề xuất & thực hiện cải tiến nâng cao profit (tối ưu hóa entry, take-profit, trailing, lọc tín hiệu nhiễu, quản lý vốn).
5. Hoàn thiện và kích hoạt cơ chế chạy tự động an toàn (simulation / paper / testnet / live ready with strict safeguards).
6. Kiểm thử toàn diện (Unit tests, Integration tests, Simulation run, Dev check) và lập tài liệu vận hành tự động.

## Các Giai Đoạn (Phases)
- [x] **Giai đoạn 1:** Khảo sát toàn cảnh hệ thống: Dữ liệu hiện có (`data_live`, `data`), Artifacts, Models, Signal logs, và các nghiên cứu gần nhất (`scripts/`).
- [x] **Giai đoạn 2:** Phân tích hiệu năng sinh lời (Profit Analysis) của các mô hình & chiến lược (v1, v2, v3, Cross-short ATR, Scale-in policies).
- [/] **Giai đoạn 3:** Rà soát kiến trúc & tính sẵn sàng của cơ chế chạy tự động (Execution Engine, PaperBroker, BinanceExecutionClient, Worker locks, Daemon loops).
- [/] **Giai đoạn 4:** Nâng cấp & hoàn thiện cơ chế tạo lợi nhuận (Profit Mechanism Enhancement): Tinh chỉnh lọc tín hiệu, ATR TP/SL, Dynamic Position Sizing, Quản trị rủi ro & Chi phí.
- [ ] **Giai đoạn 5:** Hoàn thiện cơ chế tự động hóa (Automated Execution Pipeline): Thiết lập luồng tự động khép kín từ Scanner -> Signal Filtering -> Execution Engine -> Reconciliation -> Alerts/Dashboard.
- [ ] **Giai đoạn 6:** Kiểm thử toàn diện, chạy mô phỏng nghiệm thu (Verification & Simulation) và báo cáo kết quả hoàn thiện cho User.
