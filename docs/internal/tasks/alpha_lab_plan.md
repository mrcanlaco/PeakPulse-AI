# Kế hoạch Thực thi (Execution Plan): Alpha Quality Lab

**Mục tiêu:** Xây dựng module `Signal Intelligence & Alpha Quality Lab` (`src/dao_vang/alpha_lab`) để lọc tín hiệu, ngăn chặn Alpha Decay và đảm bảo Kỳ vọng lợi nhuận (EV) dương.

**Agent được chỉ định:** Kế hoạch này được thiết kế để một lập trình viên/Agent khác có thể thực thi theo từng giai đoạn độc lập (Phase-by-Phase), đảm bảo rủi ro kỹ thuật thấp nhất và mang lại giá trị ngay lập tức.

---

## Cấu trúc Thư mục Yêu cầu

Tạo thư mục và các file rỗng ban đầu:
```text
src/dao_vang/
└── alpha_lab/
    ├── __init__.py
    ├── triple_barrier.py
    ├── meta_labeling.py
    ├── regime_classifier.py
    ├── drift_guardian.py
    ├── signal_attribution.py
    └── alpha_backtester.py
```

---

## Phase 1: Nền tảng Đánh giá & Hậu kiểm (Foundation)

**Mục tiêu Phase 1:** Có khả năng đánh giá chính xác một tín hiệu (Long/Short) là đúng hay sai dựa trên rủi ro thực tế (Stop Loss/Take Profit) thay vì thời gian tĩnh.

### Task 1.1: Triển khai `triple_barrier.py`
- **Yêu cầu kỹ thuật:**
  - Viết hàm `apply_triple_barrier(prices: pd.DataFrame, events: pd.DataFrame, pt_sl: list, min_ret: float) -> pd.DataFrame` theo chuẩn của Marcos López de Prado.
  - Sử dụng biến động (Volatility) động, ví dụ tính ATR (Average True Range) nến 1H/4H tại thời điểm ra tín hiệu để xác định khoảng cách cho Take Profit (Barrier Trên) và Stop Loss (Barrier Dưới).
  - Barrier Dọc (Time Horizon): Mặc định 12h - 24h.
- **Input:** DataFrame lịch sử giá (ưu tiên nến 1m/5m để tránh Look-ahead bias) và danh sách thời điểm phát tín hiệu (events).
- **Output:** Nhãn `-1` (chạm SL), `0` (hết giờ), `1` (chạm TP) cho mỗi tín hiệu.

### Task 1.2: Triển khai `signal_attribution.py`
- **Yêu cầu kỹ thuật:**
  - Viết logic tính toán MFE (Maximum Favorable Excursion) và MAE (Maximum Adverse Excursion) cho mỗi tín hiệu.
  - Xây dựng hàm tính Toán Kỳ vọng (EV - Expected Value) của tập tín hiệu.
- **Input:** Output từ Task 1.1.
- **Output:** Báo cáo PnL, Winrate, R:R và EV tổng thể.

---

## Phase 2: Phân loại Trạng thái Thị trường (Contextual Awareness)

**Mục tiêu Phase 2:** Ngăn chặn việc đánh ngược xu hướng mạnh hoặc bị dính bẫy thanh khoản (Whipsaw) khi thị trường biến động 2 chiều.

### Task 2.1: Triển khai `regime_classifier.py`
- **Yêu cầu kỹ thuật:**
  - Kết hợp Rule-based và Unsupervised Learning nhẹ.
  - Sử dụng ADX (đo sức mạnh xu hướng) và Bollinger Bands Width (đo biến động) trên khung D1/H4 của BTC.
  - Phân loại thị trường thành 3 trạng thái:
    1. `TRENDING` (Up/Down mạnh).
    2. `HIGH_VOLATILITY_CHOP` (Biến động lớn, giật 2 chiều).
    3. `SIDEWAY_DISTRIBUTION` (Đi ngang biên độ hẹp).
- **Input:** OHLCV của BTCUSDT khung H4 và D1.
- **Output:** Nhãn trạng thái thị trường tại một thời điểm `t`.

---

## Phase 3: Lọc Tín Hiệu (Meta-Labeling)

**Mục tiêu Phase 3:** Cắt bỏ 60% tín hiệu rác từ mô hình cơ sở (Primary Model) bằng cách trả lời câu hỏi "Có nên khớp lệnh này không?".

### Task 3.1: Triển khai `meta_labeling.py`
- **Yêu cầu kỹ thuật:**
  - Thuật toán: XGBoost Classifier (dùng `xgboost` thư viện Python).
  - **Features bắt buộc:**
    - Trạng thái thị trường (từ Phase 2).
    - Biến động hiện tại (ATR).
    - Các chỉ số vi cấu trúc tại thời điểm `t` (như CVD, Orderbook Imbalance nếu có, Taker Buy/Sell Ratio).
  - **Nhãn mục tiêu (Target):** Lấy từ Phase 1 (1 nếu Tín hiệu đúng, 0 nếu sai).
  - Nếu xác suất của Meta-Model trả về `< 0.65` (hoặc một ngưỡng tối ưu), hàm `filter_signal()` sẽ trả về `False` (Drop tín hiệu).
- **Input:** Vector đặc trưng (Features) tại thời điểm tín hiệu được sinh ra.
- **Output:** Quyết định `True` (Thực thi lệnh) hoặc `False` (Bỏ qua).

---

## Phase 4: Giám sát Hiệu suất Hệ thống (Drift & Calibration)

**Mục tiêu Phase 4:** Cảnh báo sớm khi thuật toán lỗi thời hoặc thị trường thay đổi cơ cấu (Alpha Decay).

### Task 4.1: Triển khai `drift_guardian.py`
- **Yêu cầu kỹ thuật:**
  - Tính toán PSI (Population Stability Index) giữa phân phối feature huấn luyện (Train) và thực tế (Inference).
  - Tính Rolling Brier Score và ECE (Expected Calibration Error) trong cửa sổ 7 ngày gần nhất.
  - Viết cơ chế Trigger Alert: Cảnh báo ra file log hoặc stdout nếu PSI `> 0.2` hoặc Brier Score tăng đột biến.
- **Input:** Xác suất dự đoán lịch sử, nhãn thực tế, tập features In-sample và Out-of-sample.
- **Output:** Các chỉ số Drift Metrics và tín hiệu Alert (Mức độ Warning/Critical).

---

## Quy trình Kiểm định (Validation & Testing)

1. **Unit Testing:** Mỗi file `.py` cần có ít nhất 1 file test tương ứng trong thư mục `tests/alpha_lab/` (sử dụng `pytest`).
2. **Integration:** Dùng `alpha_backtester.py` để chạy một kịch bản giả lập:
   - Truyền 100 tín hiệu (giả lập) vào.
   - Chạy qua Triple-Barrier để gán nhãn.
   - Train Meta-Model trên 70 tín hiệu đầu.
   - Inference Meta-Model trên 30 tín hiệu sau.
   - So sánh PnL của việc Đánh cả 30 lệnh vs Đánh các lệnh được Meta-Model duyệt. EV của tập được duyệt phải cao hơn đáng kể.
