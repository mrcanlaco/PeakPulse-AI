# HỒ SƠ PHẢN HỒI TÁI KIỂM ĐỊNH ĐỘC LẬP (RE-AUDIT RESPONSE) — PEAKPULSE AI FIBO TREND SHORT v4.0.2

- **Phiên bản Hồ sơ & Engine:** `4.0.2` (Tự động kết xuất 100% từ JSON `artifacts/fibo_trend_short/red_team_reaudit_recalculation_v4_0_2.json`)
- **Git Commit SHA:** `52d43e10ed970423d5c6a778f3c038d5122193ea`
- **Kịch bản Tái tính toán Chuẩn:** `scripts/fibo_research/verify_red_team_reaudit_v402.py` (`SHA256: 83a353e0e667811e...`)
- **Bộ Kiểm thử Hồi quy Tự động:** `13 passed in 6.52s` (`tests/unit/fibo_short/test_fibo_short.py`)
- **Trạng thái đối chiếu 19 Hạng mục Kiểm định:** **19 Closed / 0 Partially Closed / 0 Open**

---

## 1. XÁC MINH & KHẮC PHỤC TRIỆT ĐỂ BỘ KẾ TOÁN DANH MỤC (RT2-C1 & RT2-C2)

### 1.1. Tái hiện & Khắc phục Lỗi Cap Cùng Timestamp & Notional/SL Risk Cap (`RT2-C1`)

- **Nguyên nhân gốc trong v4.0.1:** Hàm `compute_time_weighted_concurrency_and_nav` kiểm tra `slot_occupancy[i0]` nhưng chỉ cộng `slot_occupancy` ở vòng lặp sau, khiến 6 lệnh có cùng `entry_time` đều thấy `slot_occupancy[i0] == 0` và lọt qua `max_concurrent_cap=5`. Đồng thời chưa kiểm tra trần tổng quy mô vốn (`max_total_notional_frac`) và trần tổng rủi ro đến SL (`max_total_sl_risk_frac`).
- **Bản vá trong v4.0.2 (`verify_red_team_audit_2026.py` & `verify_red_team_reaudit_v402.py`):**
  1. Sắp xếp sự kiện vào lệnh theo thứ tự tất định `(entry_timestamp, -full_conviction_score, symbol, tf)`.
  2. Đặt chỗ ngay lập tức (`slot_occupancy[i0:i1_excl] += 1`, `notional_occupancy[i0:i1_excl] += notional_frac`, `sl_risk_occupancy[i0:i1_excl] += sl_risk_frac`) trên nửa khoảng `[i0, i0 + hold_hours)` ngay khi nhận lệnh.
  3. Kiểm tra đồng thời 3 cổng danh mục độc lập: Số lượng vị thế (`max_concurrent_cap`), Tổng Notional (`max_total_notional_frac`), và Tổng Rủi ro đến SL (`max_total_sl_risk_frac`).
  4. Bổ sung **Luồng Thực thi Danh mục Kết nối (`run_portfolio_coupled_execution`)**: kiểm tra 3 cổng danh mục **trước** khi tiêu thụ `wave_key` hoặc kích hoạt `cooldown_until_idx` của cặp `(symbol, tf)`.

| Tình huống Kiểm thử (`RT2-C1`) | Lệnh gửi vào | Giới hạn cấu hình | Lệnh được nhận | Lệnh bị từ chối | Max Concurrency / Notional thực nhận | Kết quả Assert |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **6 lệnh cùng timestamp (`1.0x`)** | `6` | `max_concurrent_cap = 5` | **`5`** | `1` (slot cap) | `5` slots (Uncapped: `6`) | `PASS` |
| **5 lệnh cùng timestamp (`pos_mult=1.5x`)** | `5` | `max_total_notional_frac = 1.00` | **`3`** | `2` (notional cap) | `0.90x` (`3 × 0.30x <= 1.00x`) | `PASS` |

### 1.2. Tái hiện & Khắc phục Lỗi Compounded NAV Khối lượng Cố định (`RT2-C2`)

- **Nguyên nhân gốc trong v4.0.1:** Nhân lũy kế `nav_comp *= (1.0 + step_net_pct / 100.0)` với `step_net_pct` chuẩn hóa theo `entry_price` đã vô tình giả định tái cân bằng khối lượng theo NAV ở mỗi giờ. Khi giá đi `100 -> 50 -> 100` (lãi +50% giờ 1 rồi trả lại -50% tính trên giá vào ở giờ 2), phép nhân `(1 + 0.10) × (1 - 0.10)` tạo ra sai số `-1.00%` cộng phí `-0.04%` thành `-1.04%`.
- **Bản vá trong v4.0.2:** Cố định quy mô vốn mở lệnh `trade_notional_comp = nav_comp[i0] * notional_frac` tại đúng thời điểm mở lệnh `i0`, sau đó hạch toán từng bước MTM, chốt lời từng phần và phí theo đúng quy mô cố định: `nav_comp += trade_notional_comp * (step_net_pct / 100.0)`. Quy mô vị thế chỉ thay đổi theo NAV đối với **lệnh mở mới tiếp theo**.

| Tình huống Kiểm thử (`RT2-C2`) | NAV đầu | Notional mở | Đường giá Close | Gross cuối lệnh | Phí khứ hồi (`20 bps`) | v4.0.1 Compounded (Lỗi) | v4.0.2 Additive NAV | v4.0.2 Compounded NAV | Kết quả Assert |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Short tại 100 (`SL=150, TP=10/8/5`)** | `100.00` | `20.00` | `100 -> 50 -> 100` | `+0.00%` | `-0.04` (`-0.04%` NAV) | `-1.04%` | **`99.96` (`-0.04%`)** | **`99.96` (`-0.04%`)** | `PASS` |

### 1.3. Minh bạch Dữ liệu Funding Lịch sử & Quy ước Timestamp (`decision_time` / `entry_time` / `exit_time`)

- **Kiểm toán Dữ liệu Funding Lịch sử (`load_historical_funding_lookup`):** Đã quét các thư mục dữ liệu локаl (`D:/SharedMarketData/multiyear_2020_2026/funding_8h` và `C:/Quant-trading/data_lake/funding`). Số tệp funding lịch sử hiện có trên ổ đĩa: **`0/14` mã (`0` bản ghi)**. Do dữ liệu funding lịch sử theo từng kỳ 8h chưa được lưu trữ trong kho parquet cục bộ, báo cáo **tuyệt đối không tuyên bố đã mô phỏng funding lịch sử thực tế**, mà tách bạch rõ:
  1. **Kịch bản `Ex-Funding (0.0 bps/8h — Unmodeled Funding)`**: Phản ánh thuần túy PnL giá + phí khớp lệnh khứ hồi `20 bps`.
  2. **Kịch bản `Stress-Test Adverse Short Funding (+1.0 bps/8h)`**: Giả định bảo thủ vị thế Short phải trả `+1.0 bps` mỗi kỳ 8h (`00:00, 08:00, 16:00 UTC`) trên phần khối lượng còn mở.
- **Chuẩn hóa Timestamp:**
  - `decision_time = entry_time = h1_close_time[idx_1h]` (`open_time + 1h`): Thời điểm đóng nến xác nhận H1 và khớp lệnh.
  - `exit_time` (raw bar open) và `exit_close_time` (`open_time + 1h`): Mọi bước MTM trong `bar_trace` được ánh xạ theo `close_time_str` thực tế của từng nến H1.

### 1.4. Đối chiếu Portfolio-Capped NAV & Concurrency trên 14 Mã Benchmark (`2020–2025 IS` & `2026 OOS`)

*Cấu hình danh mục chuẩn: `base_notional_weight = 20%` cho mỗi `1.0x`, `max_concurrent_cap = 5`, `max_total_notional_frac = 1.00x` (`100%` NAV), `max_total_sl_risk_frac = 0.12` (`12%` NAV).*

| Giai đoạn & Cấu hình | Chế độ Thực thi | Lệnh Đạt chuẩn / Thực nhận | Bị chặn (Slot / Notional / SL Risk) | Time-Weighted Avg / P95 / Max Slots | Peak Open Notional / SL Risk | Additive Return / MaxDD (Ex-Funding) | Compounded Return / MaxDD (Ex-Funding) | Additive Return / MaxDD (Stress +1bp/8h Funding) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2020-2025 IS — Mốc 4A (F1+F2 Elite, 1.0x)** | Post-Cap trên Independent | `260 / 240` | `1 / 0 / 19` | `0.30 / 2.0 / 5` | `1.00x / 11.97%` | **`+42.86%`** (DD `21.92%`) | **`+44.92%`** (DD `25.73%`) | `+39.15%` (DD `22.47%`) |
| **2020-2025 IS — Mốc 4A (F1+F2 Elite, 1.0x)** | **Execution-Coupled Loop** | `406 / 244` | `1 / 0 / 161` | `0.31 / 2.0 / 5` | `1.00x / 11.97%` | **`+41.28%`** (DD `22.11%`) | **`+42.55%`** (DD `25.73%`) | *Coupled Wave/Cooldown* |
| **2026 OOS — Mốc 4A (F1+F2 Elite, 1.0x)** | Post-Cap trên Independent | `12 / 12` | `0 / 0 / 0` | `0.15 / 1.0 / 1` | `0.20x / 4.50%` | **`+13.27%`** (DD `4.30%`) | **`+13.86%`** (DD `4.81%`) | `+13.05%` (DD `4.34%`) |
| **2026 OOS — Mốc 4A (F1+F2 Elite, 1.0x)** | **Execution-Coupled Loop** | `12 / 12` | `0 / 0 / 0` | `0.15 / 1.0 / 1` | `0.20x / 4.50%` | **`+13.27%`** (DD `4.30%`) | **`+13.86%`** (DD `4.81%`) | *Coupled Wave/Cooldown* |
| **2020-2025 IS — Mốc 6B (4-Factor Expanded, Sized)** | Post-Cap trên Independent | `350 / 322` | `0 / 7 / 21` | `0.35 / 2.0 / 4` | `0.92x / 11.97%` | **`+78.93%`** (DD `29.62%`) | **`+100.94%`** (DD `29.52%`) | `+74.25%` (DD `30.30%`) |
| **2020-2025 IS — Mốc 6B (4-Factor Expanded, Sized)** | **Execution-Coupled Loop** | `503 / 332` | `0 / 74 / 97` | `0.37 / 2.0 / 4` | `0.99x / 12.00%` | **`+80.63%`** (DD `32.93%`) | **`+103.21%`** (DD `32.14%`) | *Coupled Wave/Cooldown* |
| **2026 OOS — Mốc 6B (4-Factor Expanded, Sized)** | Post-Cap trên Independent | `19 / 19` | `0 / 0 / 0` | `0.24 / 1.0 / 3` | `0.55x / 8.68%` | **`+24.35%`** (DD `4.05%`) | **`+27.02%`** (DD `4.70%`) | `+24.04%` (DD `4.08%`) |
| **2026 OOS — Mốc 6B (4-Factor Expanded, Sized)** | **Execution-Coupled Loop** | `19 / 19` | `0 / 0 / 0` | `0.24 / 1.0 / 3` | `0.55x / 8.68%` | **`+24.35%`** (DD `4.05%`) | **`+27.02%`** (DD `4.70%`) | *Coupled Wave/Cooldown* |
| **2020-2025 IS — Mốc 6A (4-Factor Sniper, Sized)** | Post-Cap trên Independent | `286 / 263` | `0 / 4 / 19` | `0.32 / 2.0 / 4` | `0.92x / 11.97%` | **`+68.22%`** (DD `33.37%`) | **`+80.59%`** (DD `30.85%`) | `+63.67%` (DD `34.08%`) |
| **2020-2025 IS — Mốc 6A (4-Factor Sniper, Sized)** | **Execution-Coupled Loop** | `400 / 271` | `0 / 57 / 72` | `0.34 / 2.0 / 4` | `0.92x / 11.90%` | **`+72.06%`** (DD `36.09%`) | **`+86.78%`** (DD `32.83%`) | *Coupled Wave/Cooldown* |
| **2026 OOS — Mốc 6A (4-Factor Sniper, Sized)** | Post-Cap trên Independent | `16 / 16` | `0 / 0 / 0` | `0.21 / 1.0 / 3` | `0.55x / 8.68%` | **`+23.52%`** (DD `5.21%`) | **`+25.97%`** (DD `6.00%`) | `+23.23%` (DD `5.24%`) |
| **2026 OOS — Mốc 6A (4-Factor Sniper, Sized)** | **Execution-Coupled Loop** | `16 / 16` | `0 / 0 / 0` | `0.21 / 1.0 / 3` | `0.55x / 8.68%` | **`+23.52%`** (DD `5.21%`) | **`+25.97%`** (DD `6.00%`) | *Coupled Wave/Cooldown* |
| **2020-2025 IS — Mốc 6S (4-Factor Tier S, Sized)** | Post-Cap trên Independent | `224 / 205` | `0 / 4 / 15` | `0.26 / 1.0 / 4` | `0.92x / 11.97%` | **`+63.25%`** (DD `22.76%`) | **`+74.95%`** (DD `26.10%`) | `+59.39%` (DD `23.10%`) |
| **2020-2025 IS — Mốc 6S (4-Factor Tier S, Sized)** | **Execution-Coupled Loop** | `323 / 209` | `0 / 55 / 59` | `0.27 / 2.0 / 4` | `0.92x / 11.87%` | **`+61.83%`** (DD `23.36%`) | **`+72.46%`** (DD `26.10%`) | *Coupled Wave/Cooldown* |
| **2026 OOS — Mốc 6S (4-Factor Tier S, Sized)** | Post-Cap trên Independent | `9 / 9` | `0 / 0 / 0` | `0.12 / 1.0 / 1` | `0.30x / 4.24%` | **`+12.21%`** (DD `5.20%`) | **`+12.68%`** (DD `5.78%`) | `+12.02%` (DD `5.22%`) |
| **2026 OOS — Mốc 6S (4-Factor Tier S, Sized)** | **Execution-Coupled Loop** | `9 / 9` | `0 / 0 / 0` | `0.12 / 1.0 / 1` | `0.30x / 4.24%` | **`+12.21%`** (DD `5.20%`) | **`+12.68%`** (DD `5.78%`) | *Coupled Wave/Cooldown* |

---

## 2. ĐỒNG BỘ MÃ NGUỒN, THAM SỐ & CÔ LẬP `.bfill()` (RT2-H1, RT2-M1, RT2-M2, RT2-M3)

### 2.1. Cô lập Tuyệt đối Tác động của `.bfill()` so với `.ffill()` (`RT2-M1`)

- **Phát hiện của Tái kiểm định:** Trong v4.0.1, `calc_htf_features_no_bfill` vừa bỏ `.bfill()` vừa đổi `min_periods` của EMA từ `fast/slow` sang `1`, nên chênh lệch 1 lệnh (`496` vs `495`) chưa được cô lập nguyên nhân.
- **Kiểm nghiệm Cô lập trong v4.0.2 (`compute_canonical_pst_series`):** Giữ nguyên `min_periods=1` ở cả hai nhánh, chỉ thay đổi duy nhất `use_bfill=True` so với `use_bfill=False`:
  - Số ứng viên thô (2020–2026) khi `use_bfill=True` (`min_periods=1`): **`18363`** (`Mốc 1: 1506`, `Mốc 6B: 514`).
  - Số ứng viên thô (2020–2026) khi `use_bfill=False` (`min_periods=1`): **`18363`** (`Mốc 1: 1506`, `Mốc 6B: 514`).
  - **Chênh lệch thuần túy do `.bfill()`:** **`0` lệnh (`0.00%`)** — Lý do toán học: `raw_vol` chỉ nhận `NaN` tại 2 nến đầu tiên (`idx = 0, 1`), nên `ewmac_4_16` giống hệt 100% từ `idx >= 2` và `accel_4_16 = ewmac_4_16.diff(4)` giống hệt 100% từ `idx >= 6`, trong khi bộ dò sóng chỉ bắt đầu đánh giá từ `htf_ptr >= 10`.
  - Chênh lệch 1 lệnh (`496` vs `1506`) ở v4.0.1 được xác nhận 100% là do `min_periods=fast/slow` trong vùng khởi động EMA, không phải do `.bfill()`.

### 2.2. Khai báo `swing_pivot_right_bars` trong `FiboTrendShortConfig` & Đồng bộ Các Script Cũ (`RT2-H1` & `RT2-M2`)

- **Khai báo Config (`src/dao_vang/config/settings.py`):** Đã bổ sung `swing_pivot_left_bars: int = 2`, `swing_pivot_right_bars: int = 2`, `m6_sl_atr_buffer: float = 0.25`, `horizon_hours_1d: int = 120`, `min_cooldown_hours: int = 4`, `round_trip_fee_bps: float = 20.0`, và bộ ngưỡng/hệ số Conviction (`80/68/55` -> `1.50/1.15/0.80/0.50`).
- **Kiểm chứng Thay đổi Hành vi khi đổi `swing_pivot_right_bars` trên 14 Mã (2020–2026):**
  - `FiboTrendShortConfig(swing_pivot_right_bars=1)`: Mốc 1 = **`1506`** lệnh, Mốc 6B = **`514`** lệnh (`Total Net: +794.25%`).
  - `FiboTrendShortConfig(swing_pivot_right_bars=2)` (Chuẩn v4.0.2): Mốc 1 = **`1093`** lệnh, Mốc 6B = **`369`** lệnh (`Total Net: +628.86%`).
- **Đồng bộ Toàn bộ Script Nghiên cứu Cũ (`RT2-H1`):** Đã cập nhật tất cả 6 script (`study_factor1_multi_repo_benchmark_2025.py`, `study_factor2_3_4_complete_2025.py`, `study_independent_audit_metrics.py`, `study_insample_2020_2025_by_year.py`, `study_oos_2026_all_7_milestones.py`, `study_coin_universe_selection_2026.py`) để dùng `return_exit_meta=True` (ghi đè `exit_price`, `exit_time`, `hold_hours` của Mốc 6), dùng `compute_canonical_pst_series(..., use_bfill=False)`, và chuẩn hóa `fee_bps` thành tổng phí khứ hồi (`10.0 bps = 0.10%`).

### 2.3. Đối chiếu Đầy đủ 7 Mốc Factor-Gate & 3 Mốc Score-Gate: Fixed `1.0x` vs Sized `1.50/1.15/0.80` (`RT2-M3` & `RT2-M4`)

*Bảng dưới đây đặt cạnh nhau kết quả **Unscaled Fixed `1.0x`** và **Position-Sized (`1.50/1.15/0.80`)**, kèm **Khoảng tin cậy 95% Cluster-Bootstrap theo tuần (`[CI95_low, CI95_high]`)** và đối chiếu **Common Cutoff (`2026-08-31`)** vs **Full Available (`2026-09-29`)** trên cấu hình chuẩn v4.0.2 (`swing_pivot_right_bars=2`, Independent Execution):*

| Cấu hình (Factor-Gate & Score-Gate) | Cửa sổ Thời gian | Số lệnh | Win Rate (`[95% CI]`) | Unscaled `1.0x` Avg Net / Total Net / PF | Sized Avg Net (`[95% CI]`) / Total Net / PF | BE Fee (1x / Sized) | RGD SL@BE / SL@TP1 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **M1_BASE (Pump >=50%, 1x)** | 2020-2023 Stress | `703` | `49.79%` (`[44.4%, 55.6%]`) | `-0.227%` / `-159.47%` / `0.95` | **`-0.227%`** (`[-1.37%, +1.04%]`) / **`-159.47%`** / `0.95` | `-2.7` / `-2.7 bps` | `65` / `100` |
| **M1_BASE (Pump >=50%, 1x)** | 2024-2025 Calib | `357` | `55.46%` (`[48.2%, 63.7%]`) | `+0.460%` / `+164.24%` / `1.12` | **`+0.460%`** (`[-0.84%, +1.97%]`) / **`+164.24%`** / `1.12` | `66.0` / `66.0 bps` | `27` / `51` |
| **M1_BASE (Pump >=50%, 1x)** | 2020-2025 Full IS | `1060` | `51.70%` (`[47.1%, 56.4%]`) | `+0.004%` / `+4.76%` / `1.00` | **`+0.004%`** (`[-0.92%, +0.94%]`) / **`+4.76%`** / `1.00` | `20.4` / `20.4 bps` | `92` / `151` |
| **M1_BASE (Pump >=50%, 1x)** | 2026 OOS (<=08-31) | `29` | `75.86%` (`[52.4%, 90.6%]`) | `+4.838%` / `+140.31%` / `2.70` | **`+4.838%`** (`[-1.44%, +9.29%]`) / **`+140.31%`** / `2.70` | `503.8` / `503.8 bps` | `0` / `8` |
| **M1_BASE (Pump >=50%, 1x)** | 2026 OOS (<=09-29) | `33` | `75.76%` (`[54.2%, 90.9%]`) | `+4.357%` / `+143.79%` / `2.64` | **`+4.357%`** (`[-1.46%, +8.55%]`) / **`+143.79%`** / `2.64` | `455.7` / `455.7 bps` | `0` / `9` |
| **M2_F1B_PST (1x)** | 2020-2023 Stress | `355` | `53.24%` (`[45.9%, 60.8%]`) | `-0.023%` / `-8.21%` / `0.99` | **`-0.023%`** (`[-1.62%, +1.75%]`) / **`-8.21%`** / `0.99` | `17.7` / `17.7 bps` | `27` / `47` |
| **M2_F1B_PST (1x)** | 2024-2025 Calib | `162` | `59.26%` (`[48.0%, 71.0%]`) | `+1.215%` / `+196.78%` / `1.39` | **`+1.215%`** (`[-0.79%, +3.16%]`) / **`+196.78%`** / `1.39` | `141.5` / `141.5 bps` | `12` / `24` |
| **M2_F1B_PST (1x)** | 2020-2025 Full IS | `517` | `55.13%` (`[49.2%, 61.9%]`) | `+0.365%` / `+188.58%` / `1.09` | **`+0.365%`** (`[-0.79%, +1.78%]`) / **`+188.57%`** / `1.09` | `56.5` / `56.5 bps` | `39` / `71` |
| **M2_F1B_PST (1x)** | 2026 OOS (<=08-31) | `18` | `66.67%` (`[33.3%, 90.0%]`) | `+3.653%` / `+65.75%` / `1.92` | **`+3.653%`** (`[-6.74%, +10.64%]`) / **`+65.75%`** / `1.92` | `385.3` / `385.3 bps` | `0` / `5` |
| **M2_F1B_PST (1x)** | 2026 OOS (<=09-29) | `19` | `68.42%` (`[35.7%, 90.5%]`) | `+3.468%` / `+65.89%` / `1.92` | **`+3.468%`** (`[-5.76%, +9.82%]`) / **`+65.89%`** / `1.92` | `366.8` / `366.8 bps` | `0` / `5` |
| **M3_F1C_EXP (1x)** | 2020-2023 Stress | `323` | `52.01%` (`[45.2%, 58.4%]`) | `+0.064%` / `+20.78%` / `1.02` | **`+0.064%`** (`[-1.25%, +1.33%]`) / **`+20.78%`** / `1.02` | `26.4` / `26.4 bps` | `33` / `47` |
| **M3_F1C_EXP (1x)** | 2024-2025 Calib | `156` | `62.18%` (`[51.5%, 72.3%]`) | `+1.336%` / `+208.35%` / `1.45` | **`+1.336%`** (`[-0.42%, +3.04%]`) / **`+208.35%`** / `1.45` | `153.6` / `153.6 bps` | `18` / `19` |
| **M3_F1C_EXP (1x)** | 2020-2025 Full IS | `479` | `55.32%` (`[49.8%, 61.1%]`) | `+0.478%` / `+229.13%` / `1.13` | **`+0.478%`** (`[-0.59%, +1.54%]`) / **`+229.13%`** / `1.13` | `67.8` / `67.8 bps` | `51` / `66` |
| **M3_F1C_EXP (1x)** | 2026 OOS (<=08-31) | `21` | `71.43%` (`[46.1%, 88.2%]`) | `+4.308%` / `+90.46%` / `2.24` | **`+4.308%`** (`[-3.66%, +9.82%]`) / **`+90.46%`** / `2.24` | `450.8` / `450.8 bps` | `0` / `5` |
| **M3_F1C_EXP (1x)** | 2026 OOS (<=09-29) | `25` | `72.00%` (`[50.0%, 88.2%]`) | `+3.758%` / `+93.95%` / `2.20` | **`+3.758%`** (`[-2.65%, +8.29%]`) / **`+93.95%`** / `2.20` | `395.8` / `395.8 bps` | `0` / `6` |
| **M4_F12_ELITE (F1+F2 Elite, 1x)** | 2020-2023 Stress | `182` | `57.14%` (`[48.5%, 64.7%]`) | `+0.846%` / `+153.91%` / `1.22` | **`+0.846%`** (`[-0.79%, +2.44%]`) / **`+153.91%`** / `1.22` | `104.6` / `104.6 bps` | `20` / `30` |
| **M4_F12_ELITE (F1+F2 Elite, 1x)** | 2024-2025 Calib | `78` | `65.38%` (`[52.0%, 79.0%]`) | `+1.458%` / `+113.74%` / `1.54` | **`+1.458%`** (`[-0.67%, +3.54%]`) / **`+113.74%`** / `1.54` | `165.8` / `165.8 bps` | `7` / `10` |
| **M4_F12_ELITE (F1+F2 Elite, 1x)** | 2020-2025 Full IS | `260` | `59.62%` (`[53.0%, 66.7%]`) | `+1.029%` / `+267.65%` / `1.30` | **`+1.029%`** (`[-0.22%, +2.35%]`) / **`+267.65%`** / `1.30` | `122.9` / `122.9 bps` | `27` / `40` |
| **M4_F12_ELITE (F1+F2 Elite, 1x)** | 2026 OOS (<=08-31) | `11` | `63.64%` (`[30.0%, 91.7%]`) | `+6.017%` / `+66.19%` / `4.23` | **`+6.017%`** (`[-0.61%, +12.30%]`) / **`+66.19%`** / `4.23` | `621.7` / `621.7 bps` | `0` / `3` |
| **M4_F12_ELITE (F1+F2 Elite, 1x)** | 2026 OOS (<=09-29) | `12` | `66.67%` (`[30.0%, 92.3%]`) | `+5.528%` / `+66.33%` / `4.24` | **`+5.528%`** (`[-0.27%, +11.18%]`) / **`+66.34%`** / `4.24` | `572.8` / `572.8 bps` | `0` / `3` |
| **M5_F123_EXP (F1+F2+F3, 1x)** | 2020-2023 Stress | `194` | `55.15%` (`[47.1%, 62.2%]`) | `+0.349%` / `+67.68%` / `1.08` | **`+0.349%`** (`[-1.31%, +2.02%]`) / **`+67.68%`** / `1.08` | `54.9` / `54.9 bps` | `22` / `28` |
| **M5_F123_EXP (F1+F2+F3, 1x)** | 2024-2025 Calib | `91` | `73.63%` (`[62.2%, 84.2%]`) | `+2.814%` / `+256.04%` / `2.31` | **`+2.814%`** (`[+0.61%, +4.70%]`) / **`+256.04%`** / `2.31` | `301.4` / `301.4 bps` | `9` / `13` |
| **M5_F123_EXP (F1+F2+F3, 1x)** | 2020-2025 Full IS | `285` | `61.05%` (`[54.5%, 67.2%]`) | `+1.136%` / `+323.71%` / `1.31` | **`+1.136%`** (`[-0.15%, +2.38%]`) / **`+323.71%`** / `1.31` | `133.6` / `133.6 bps` | `31` / `41` |
| **M5_F123_EXP (F1+F2+F3, 1x)** | 2026 OOS (<=08-31) | `13` | `84.62%` (`[50.0%, 100.0%]`) | `+7.558%` / `+98.26%` / `8.55` | **`+7.558%`** (`[+2.77%, +13.13%]`) / **`+98.26%`** / `8.55` | `775.8` / `775.8 bps` | `1` / `5` |
| **M5_F123_EXP (F1+F2+F3, 1x)** | 2026 OOS (<=09-29) | `16` | `87.50%` (`[61.5%, 100.0%]`) | `+7.027%` / `+112.43%` / `9.64` | **`+7.027%`** (`[+3.15%, +11.11%]`) / **`+112.43%`** / `9.64` | `722.7` / `722.7 bps` | `1` / `7` |
| **M6_F124_EXP (Mốc 6B, Sized)** | 2020-2023 Stress | `240` | `50.00%` (`[42.2%, 57.1%]`) | `+0.561%` / `+134.57%` / `1.15` | **`+1.078%`** (`[-0.64%, +2.85%]`) / **`+258.61%`** / `1.28` | `76.1` / `119.5 bps` | `25` / `37` |
| **M6_F124_EXP (Mốc 6B, Sized)** | 2024-2025 Calib | `110` | `61.82%` (`[50.0%, 74.2%]`) | `+1.795%` / `+197.44%` / `1.71` | **`+2.259%`** (`[+0.23%, +4.17%]`) / **`+248.53%`** / `1.87` | `199.5` / `228.6 bps` | `11` / `14` |
| **M6_F124_EXP (Mốc 6B, Sized)** | 2020-2025 Full IS | `350` | `53.71%` (`[47.3%, 59.9%]`) | `+0.949%` / `+332.01%` / `1.29` | **`+1.449%`** (`[+0.16%, +2.86%]`) / **`+507.14%`** / `1.42` | `114.9` / `153.8 bps` | `36` / `51` |
| **M6_F124_EXP (Mốc 6B, Sized)** | 2026 OOS (<=08-31) | `16` | `75.00%` (`[45.4%, 94.7%]`) | `+7.158%` / `+114.53%` / `6.69` | **`+7.031%`** (`[+2.39%, +11.20%]`) / **`+112.49%`** / `6.64` | `735.8` / `695.6 bps` | `0` / `5` |
| **M6_F124_EXP (Mốc 6B, Sized)** | 2026 OOS (<=09-29) | `19` | `78.95%` (`[53.3%, 95.2%]`) | `+6.492%` / `+123.35%` / `7.13` | **`+6.407%`** (`[+2.52%, +9.85%]`) / **`+121.73%`** / `7.10` | `669.2` / `647.5 bps` | `0` / `6` |
| **M6_F1234_SNIPER (Mốc 6A, Sized)** | 2020-2023 Stress | `195` | `52.82%` (`[45.2%, 59.8%]`) | `+0.453%` / `+88.34%` / `1.11` | **`+0.721%`** (`[-1.21%, +2.62%]`) / **`+140.58%`** / `1.15` | `65.3` / `81.7 bps` | `21` / `28` |
| **M6_F1234_SNIPER (Mốc 6A, Sized)** | 2024-2025 Calib | `91` | `72.53%` (`[61.1%, 82.9%]`) | `+2.808%` / `+255.54%` / `2.32` | **`+3.263%`** (`[+0.81%, +5.30%]`) / **`+296.92%`** / `2.32` | `300.8` / `300.0 bps` | `9` / `13` |
| **M6_F1234_SNIPER (Mốc 6A, Sized)** | 2020-2025 Full IS | `286` | `59.09%` (`[52.7%, 65.3%]`) | `+1.202%` / `+343.88%` / `1.35` | **`+1.530%`** (`[+0.01%, +2.98%]`) / **`+437.50%`** / `1.38` | `140.2` / `151.1 bps` | `30` / `41` |
| **M6_F1234_SNIPER (Mốc 6A, Sized)** | 2026 OOS (<=08-31) | `13` | `84.62%` (`[50.0%, 100.0%]`) | `+7.446%` / `+96.80%` / `7.69` | **`+8.007%`** (`[+2.56%, +13.70%]`) / **`+104.10%`** / `7.81` | `764.6` / `750.5 bps` | `1` / `5` |
| **M6_F1234_SNIPER (Mốc 6A, Sized)** | 2026 OOS (<=09-29) | `16` | `87.50%` (`[61.5%, 100.0%]`) | `+6.936%` / `+110.97%` / `8.67` | **`+7.351%`** (`[+3.07%, +11.89%]`) / **`+117.62%`** / `8.69` | `713.6` / `711.9 bps` | `1` / `7` |
| **M7_TIER_S (Mốc 6S, Sized)** | 2020-2023 Stress | `154` | `55.84%` (`[47.5%, 63.9%]`) | `+0.922%` / `+141.92%` / `1.24` | **`+1.158%`** (`[-1.06%, +3.39%]`) / **`+178.38%`** / `1.24` | `112.2` / `114.0 bps` | `16` / `22` |
| **M7_TIER_S (Mốc 6S, Sized)** | 2024-2025 Calib | `70` | `71.43%` (`[58.3%, 84.7%]`) | `+2.113%` / `+147.92%` / `1.92` | **`+2.738%`** (`[+0.14%, +5.23%]`) / **`+191.65%`** / `1.97` | `231.3` / `239.9 bps` | `7` / `9` |
| **M7_TIER_S (Mốc 6S, Sized)** | 2020-2025 Full IS | `224` | `60.71%` (`[53.5%, 67.8%]`) | `+1.294%` / `+289.84%` / `1.39` | **`+1.652%`** (`[-0.07%, +3.39%]`) / **`+370.03%`** / `1.40` | `149.4` / `153.7 bps` | `23` / `31` |
| **M7_TIER_S (Mốc 6S, Sized)** | 2026 OOS (<=08-31) | `8` | `75.00%` (`[33.2%, 100.0%]`) | `+6.148%` / `+49.18%` / `4.40` | **`+7.479%`** (`[-0.19%, +15.78%]`) / **`+59.83%`** / `4.91` | `634.8` / `646.5 bps` | `1` / `3` |
| **M7_TIER_S (Mốc 6S, Sized)** | 2026 OOS (<=09-29) | `9` | `77.78%` (`[42.9%, 100.0%]`) | `+5.636%` / `+50.72%` / `4.51` | **`+6.785%`** (`[-0.65%, +14.15%]`) / **`+61.06%`** / `4.99` | `583.6` / `610.0 bps` | `1` / `3` |
| **SCORE_GATE >= 55 (Pure Score, 1x)** | 2020-2023 Stress | `511` | `53.42%` (`[47.4%, 59.4%]`) | `+0.018%` / `+9.38%` / `1.00` | **`+0.018%`** (`[-1.18%, +1.23%]`) / **`+9.38%`** / `1.00` | `21.8` / `21.8 bps` | `55` / `79` |
| **SCORE_GATE >= 55 (Pure Score, 1x)** | 2024-2025 Calib | `251` | `56.57%` (`[47.6%, 65.8%]`) | `+0.312%` / `+78.32%` / `1.08` | **`+0.312%`** (`[-1.45%, +2.28%]`) / **`+78.32%`** / `1.08` | `51.2` / `51.2 bps` | `20` / `34` |
| **SCORE_GATE >= 55 (Pure Score, 1x)** | 2020-2025 Full IS | `762` | `54.46%` (`[49.5%, 59.4%]`) | `+0.115%` / `+87.70%` / `1.03` | **`+0.115%`** (`[-0.90%, +1.16%]`) / **`+87.69%`** / `1.03` | `31.5` / `31.5 bps` | `75` / `113` |
| **SCORE_GATE >= 55 (Pure Score, 1x)** | 2026 OOS (<=08-31) | `24` | `66.67%` (`[42.1%, 84.6%]`) | `+3.206%` / `+76.94%` / `1.89` | **`+3.206%`** (`[-3.91%, +8.18%]`) / **`+76.94%`** / `1.89` | `340.6` / `340.6 bps` | `1` / `4` |
| **SCORE_GATE >= 55 (Pure Score, 1x)** | 2026 OOS (<=09-29) | `27` | `70.37%` (`[50.0%, 87.5%]`) | `+3.176%` / `+85.76%` / `1.99` | **`+3.176%`** (`[-2.81%, +7.56%]`) / **`+85.76%`** / `1.99` | `337.6` / `337.6 bps` | `1` / `5` |
| **SCORE_GATE >= 68 (Pure Score, 1x)** | 2020-2023 Stress | `263` | `55.89%` (`[47.8%, 62.8%]`) | `+0.383%` / `+100.77%` / `1.09` | **`+0.383%`** (`[-1.22%, +1.85%]`) / **`+100.77%`** / `1.09` | `58.3` / `58.3 bps` | `29` / `41` |
| **SCORE_GATE >= 68 (Pure Score, 1x)** | 2024-2025 Calib | `128` | `65.62%` (`[55.4%, 75.8%]`) | `+2.146%` / `+274.65%` / `1.72` | **`+2.146%`** (`[+0.27%, +4.09%]`) / **`+274.65%`** / `1.72` | `234.6` / `234.6 bps` | `13` / `16` |
| **SCORE_GATE >= 68 (Pure Score, 1x)** | 2020-2025 Full IS | `391` | `59.08%` (`[53.2%, 64.9%]`) | `+0.960%` / `+375.42%` / `1.25` | **`+0.960%`** (`[-0.26%, +2.16%]`) / **`+375.42%`** / `1.25` | `116.0` / `116.0 bps` | `42` / `57` |
| **SCORE_GATE >= 68 (Pure Score, 1x)** | 2026 OOS (<=08-31) | `16` | `62.50%` (`[30.8%, 86.4%]`) | `+2.462%` / `+39.40%` / `1.65` | **`+2.462%`** (`[-6.38%, +8.42%]`) / **`+39.40%`** / `1.65` | `266.2` / `266.2 bps` | `1` / `4` |
| **SCORE_GATE >= 68 (Pure Score, 1x)** | 2026 OOS (<=09-29) | `18` | `66.67%` (`[37.5%, 87.0%]`) | `+2.547%` / `+45.84%` / `1.75` | **`+2.547%`** (`[-4.49%, +8.09%]`) / **`+45.84%`** / `1.75` | `274.7` / `274.7 bps` | `1` / `5` |
| **SCORE_GATE >= 80 (Pure Score, 1x)** | 2020-2023 Stress | `83` | `60.24%` (`[47.8%, 71.6%]`) | `+1.697%` / `+140.84%` / `1.43` | **`+1.697%`** (`[-1.02%, +4.28%]`) / **`+140.84%`** / `1.43` | `189.7` / `189.7 bps` | `7` / `14` |
| **SCORE_GATE >= 80 (Pure Score, 1x)** | 2024-2025 Calib | `35` | `68.57%` (`[50.0%, 84.8%]`) | `+1.925%` / `+67.38%` / `1.74` | **`+1.925%`** (`[-1.28%, +5.00%]`) / **`+67.38%`** / `1.74` | `212.5` / `212.5 bps` | `2` / `4` |
| **SCORE_GATE >= 80 (Pure Score, 1x)** | 2020-2025 Full IS | `118` | `62.71%` (`[53.5%, 72.1%]`) | `+1.765%` / `+208.21%` / `1.50` | **`+1.765%`** (`[-0.14%, +3.76%]`) / **`+208.21%`** / `1.50` | `196.5` / `196.5 bps` | `9` / `18` |
| **SCORE_GATE >= 80 (Pure Score, 1x)** | 2026 OOS (<=08-31) | `5` | `80.00%` (`[25.0%, 100.0%]`) | `+6.682%` / `+33.41%` / `7.29` | **`+6.682%`** (`[-0.83%, +13.48%]`) / **`+33.41%`** / `7.29` | `688.2` / `688.2 bps` | `0` / `3` |
| **SCORE_GATE >= 80 (Pure Score, 1x)** | 2026 OOS (<=09-29) | `5` | `80.00%` (`[25.0%, 100.0%]`) | `+6.682%` / `+33.41%` / `7.29` | **`+6.682%`** (`[-0.83%, +13.48%]`) / **`+33.41%`** / `7.29` | `688.2` / `688.2 bps` | `0` / `3` |

---

## 3. TÁI KIỂM ĐỊNH VŨ TRỤ 338 MÃ COIN & ROLLING POINT-IN-TIME TOP-50 (RT2-H2, RT2-H3, RT2-L1)

### 3.1. Phương pháp Luận Chống Thiên lệch Chọn mẫu & Phân loại Nhãn Point-in-Time

- **Chạy lại Toàn bộ `338` Mã bằng Engine Đã Vá v4.0.2 (`RT2-H2`):** Mọi con số dưới đây được tính mới hoàn toàn với `swing_pivot_right_bars=2`, `prior_low < swing_high`, `same_bar_ratcheted_sl=True`, `m6_sl_atr_buffer=0.25`, `return_exit_meta=True`, và **Independent Milestone Execution** (mỗi mốc quản lý `consumed_waves` và `cooldown_until_idx` độc lập, đặt cạnh số liệu Subset-Filtered cũ để đối chiếu).
- **Thiết lập `ROLLING_PIT_TOP50_VOL` Chuẩn Point-in-Time (`RT2-H3`):** Tại đầu mỗi tháng `YYYY-MM-01` (từ `2024-01-01` đến `2026-09-01`, tổng cộng 33 kỳ tái cơ cấu), hệ thống chỉ đọc cửa sổ **63 ngày quá khứ liền kề `[t_month - 63d, t_month)`** để lọc các mã có `active_days_63d >= 50`, `wick_p90_63d <= 3.2%`, không thuộc `G1_STORE_OF_VALUE`, và lấy đúng **Top 50 mã có `median_qvol_63d` cao nhất** cho tháng đó. Không dùng bất kỳ thông tin tương lai nào ở cả `2024–2025` lẫn `2026`!
- **Kiểm toán Listing / Delisting & Độ phủ Dữ liệu (`RT2-L1`):**
  - Tổng số mã quét: **`338`** mã.
  - Số mã niêm yết mới sau `2024-01-01`: **`219`** mã (chỉ được phép vào `ROLLING_PIT_TOP50_VOL` sau khi tích lũy đủ `>= 50` ngày giao dịch trong cửa sổ 63 ngày trước ngày đầu tháng).
  - Số mã kết thúc dữ liệu trước `2026-09-01` (do cắt mẫu 5m cuối tháng 8/2026 hoặc ngừng giao dịch): **`0`** mã (trong đó `0` mã dừng quanh mốc `2026-08-31`).

### 3.2. Kết quả Thực thi Độc lập (Independent Execution) vs Lọc Tập con (Subset) trên 338 Mã (`Mốc 6B` & `Mốc 4A`)

| Phân tầng Vũ trụ Coin | Nhãn Point-in-Time / Phạm vi Dữ liệu | Số mã | Cửa sổ | Mốc 6B Independent: Lệnh / WR / Unscaled 1x Avg / Sized Avg (`[95% CI]`) / Total Net / PF | Mốc 6B Subset Cũ: Lệnh / Sized Avg / Total Net | Mốc 6B Portfolio Capped (`Cap=5, Notional<=1x`): Exec / Add. NAV / Comp. NAV / MaxDD |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **`ALL_338_UNFILTERED`** | `UNFILTERED_BASELINE_ALL_338_SYMBOLS` | `338` | **2024-2025 IS** | `2028` / `53.2%` / `+0.23%` / **`+0.42%`** (`[-1.32%, +2.08%]`) / **`+856.2%`** / `1.09` | `1945` / `+0.41%` / `+804.4%` | `801` lệnh / **`-52.14%`** / **`-57.25%`** (DD `76.92%`) |
| **`ALL_338_UNFILTERED`** | `UNFILTERED_BASELINE_ALL_338_SYMBOLS` | `338` | **2026 OOS** | `722` / `46.5%` / `-1.04%` / **`-1.17%`** (`[-2.24%, +0.02%]`) / **`-846.2%`** / `0.81` | `670` / `-1.14%` / `-764.5%` | `366` lệnh / **`-88.42%`** / **`-63.14%`** (DD `64.06%`) |
| **`ROLLING_PIT_TOP50_VOL`** | `STRICT_POINT_IN_TIME_MONTHLY_TRAILING_63D_ON_BOTH_2024_2025_AND_2026` | `50/tháng (145 mã)` | **2024-2025 IS** | `537` / `53.1%` / `+0.44%` / **`+0.57%`** (`[-0.74%, +1.90%]`) / **`+304.1%`** / `1.15` | `524` / `+0.67%` / `+348.3%` | `344` lệnh / **`+58.89%`** / **`+60.08%`** (DD `31.35%`) |
| **`ROLLING_PIT_TOP50_VOL`** | `STRICT_POINT_IN_TIME_MONTHLY_TRAILING_63D_ON_BOTH_2024_2025_AND_2026` | `50/tháng (145 mã)` | **2026 OOS** | `74` / `56.8%` / `+1.99%` / **`+2.34%`** (`[-0.23%, +4.83%]`) / **`+173.3%`** / `1.83` | `69` / `+2.03%` / `+140.0%` | `67` lệnh / **`+33.66%`** / **`+37.08%`** (DD `10.41%`) |
| **`EX_ANTE_2026_TOP50_VOL`** | `IN_SAMPLE_SELECTION_ON_2024_2025__STRICT_EX_ANTE_FROZEN_FOR_2026_OOS` | `50` | **2024-2025 IS** | `537` / `53.1%` / `+0.36%` / **`+0.46%`** (`[-0.85%, +1.91%]`) / **`+247.2%`** / `1.11` | `524` / `+0.58%` / `+304.6%` | `360` lệnh / **`+13.73%`** / **`-0.24%`** (DD `47.11%`) |
| **`EX_ANTE_2026_TOP50_VOL`** | `IN_SAMPLE_SELECTION_ON_2024_2025__STRICT_EX_ANTE_FROZEN_FOR_2026_OOS` | `50` | **2026 OOS** | `69` / `52.2%` / `+1.13%` / **`+1.09%`** (`[-1.81%, +3.60%]`) / **`+75.4%`** / `1.33` | `66` / `+1.27%` / `+83.5%` | `64` lệnh / **`+12.74%`** / **`+11.96%`** (DD `12.07%`) |
| **`TIER_S_CORE`** | `IN_SAMPLE_CALIBRATED_ON_2024_2025_OHLCV_ARCHETYPE__EX_ANTE_ON_2026_OOS__NO_MCAP_SNAPSHOT_DEPENDENCY` | `34` | **2024-2025 IS** | `371` / `62.8%` / `+2.42%` / **`+3.04%`** (`[+1.12%, +4.70%]`) / **`+1126.8%`** / `2.04` | `359` / `+3.07%` / `+1101.6%` | `279` lệnh / **`+123.12%`** / **`+207.36%`** (DD `24.59%`) |
| **`TIER_S_CORE`** | `IN_SAMPLE_CALIBRATED_ON_2024_2025_OHLCV_ARCHETYPE__EX_ANTE_ON_2026_OOS__NO_MCAP_SNAPSHOT_DEPENDENCY` | `34` | **2026 OOS** | `47` / `68.1%` / `+5.07%` / **`+5.14%`** (`[+1.08%, +8.42%]`) / **`+241.7%`** / `3.91` | `47` / `+5.14%` / `+241.7%` | `43` lệnh / **`+37.04%`** / **`+42.75%`** (DD `7.08%`) |
| **`TIER_S_PLUS_A_WHITELIST`** | `IN_SAMPLE_CALIBRATED_ON_2024_2025_PLUS_2026_COINGECKO_MCAP_FLOAT_SNAPSHOT_ON_TIER_A` | `59` | **2024-2025 IS** | `578` / `60.5%` / `+2.01%` / **`+2.53%`** (`[+0.87%, +4.00%]`) / **`+1463.3%`** / `1.86` | `557` / `+2.60%` / `+1446.8%` | `373` lệnh / **`+126.22%`** / **`+209.91%`** (DD `27.96%`) |
| **`TIER_S_PLUS_A_WHITELIST`** | `IN_SAMPLE_CALIBRATED_ON_2024_2025_PLUS_2026_COINGECKO_MCAP_FLOAT_SNAPSHOT_ON_TIER_A` | `59` | **2026 OOS** | `80` / `63.8%` / `+3.60%` / **`+3.67%`** (`[+1.20%, +6.00%]`) / **`+293.8%`** / `2.88` | `80` / `+3.67%` / `+293.8%` | `70` lệnh / **`+40.28%`** / **`+46.90%`** (DD `6.10%`) |
| **`PIT_ZERO_BIAS_MCAP_FLOAT`** | `ZERO_PNL_TUNING_RULE_BUT_USES_2026_COINGECKO_MCAP_FLOAT_SNAPSHOT` | `64` | **2024-2025 IS** | `644` / `55.1%` / `+0.63%` / **`+0.80%`** (`[-0.62%, +2.18%]`) / **`+516.6%`** / `1.21` | `626` / `+0.92%` / `+574.4%` | `398` lệnh / **`+11.95%`** / **`-1.86%`** (DD `48.85%`) |
| **`PIT_ZERO_BIAS_MCAP_FLOAT`** | `ZERO_PNL_TUNING_RULE_BUT_USES_2026_COINGECKO_MCAP_FLOAT_SNAPSHOT` | `64` | **2026 OOS** | `81` / `59.3%` / `+1.93%` / **`+2.02%`** (`[-0.22%, +3.86%]`) / **`+163.8%`** / `1.88` | `81` / `+2.07%` / `+167.3%` | `70` lệnh / **`+19.13%`** / **`+19.81%`** (DD `10.30%`) |
| **`BLACKLIST`** | `EXCLUDED_SYMBOLS_IN_SAMPLE_2024_2025_AND_2026_OOS` | `278` | **2024-2025 IS** | `1450` / `50.2%` / `-0.48%` / **`-0.42%`** (`[-2.26%, +1.33%]`) / **`-607.0%`** / `0.92` | `1388` / `-0.46%` / `-642.4%` | `694` lệnh / **`-118.38%`** / **`-77.57%`** (DD `88.09%`) |
| **`BLACKLIST`** | `EXCLUDED_SYMBOLS_IN_SAMPLE_2024_2025_AND_2026_OOS` | `278` | **2026 OOS** | `642` / `44.4%` / `-1.62%` / **`-1.78%`** (`[-2.86%, -0.55%]`) / **`-1140.0%`** / `0.74` | `590` / `-1.79%` / `-1058.3%` | `358` lệnh / **`-119.30%`** / **`-73.12%`** (DD `73.79%`) |

### 3.3. Bảng Phân rã Theo Thanh khoản (`L1..L4`) & Bản chất Tài sản (`G1..G5`) — Patched v4.0.2 Independent Execution

| Nhóm Phân loại | Số mã | 2024-2025 IS (Mốc 6B): Lệnh / WR / 1x Avg / Sized Avg / Total Net / PF | 2026 OOS (Mốc 6B): Lệnh / WR / 1x Avg / Sized Avg / Total Net / PF | 2026 OOS (Mốc 4A 1x): Lệnh / WR / Avg Net / Total Net / PF |
| :--- | :---: | :---: | :---: | :---: |
| **`L1_MEGA`** | `68` | `622` / `52.2%` / `-0.07%` / `+0.01%` / `+4.8%` / `1.00` | `119` / `49.6%` / `+0.45%` / **`+0.28%`** / **`+33.4%`** / `1.06` | `90` / `46.7%` / `-0.74%` / `-66.7%` / `0.85` |
| **`L2_DEEP`** | `81` | `721` / `55.2%` / `+0.59%` / `+0.85%` / `+611.8%` / `1.19` | `218` / `49.1%` / `-1.09%` / **`-1.23%`** / **`-268.7%`** / `0.81` | `163` / `50.3%` / `-1.49%` / `-242.6%` / `0.77` |
| **`L3_MID`** | `94` | `673` / `51.6%` / `+0.13%` / `+0.35%` / `+234.8%` / `1.08` | `232` / `47.0%` / `-0.51%` / **`-0.47%`** / **`-109.6%`** / `0.92` | `146` / `55.5%` / `+0.55%` / `+80.7%` / `1.11` |
| **`L4_THIN`** | `95` | `12` / `66.7%` / `+0.08%` / `+0.41%` / `+4.9%` / `1.09` | `153` / `39.9%` / `-2.95%` / **`-3.28%`** / **`-501.4%`** / `0.57` | `106` / `47.2%` / `-2.88%` / `-304.8%` / `0.58` |
| **`G1_STORE_OF_VALUE_MAJOR`** | `5` | `9` / `33.3%` / `-0.57%` / `-1.12%` / `-10.1%` / `0.55` | `0` / `0.0%` / `+0.00%` / **`+0.00%`** / **`+0.0%`** / `0.00` | `0` / `0.0%` / `+0.00%` / `+0.0%` / `0.00` |
| **`G2_LIQUID_L1_L2_DEFI`** | `57` | `554` / `54.1%` / `+0.36%` / `+0.50%` / `+277.4%` / `1.14` | `62` / `54.8%` / `+1.20%` / **`+1.70%`** / **`+105.6%`** / `1.74` | `43` / `55.8%` / `+1.57%` / `+67.6%` / `1.57` |
| **`G3_HIGH_BETA_NARRATIVE_MIDCAP`** | `148` | `1143` / `52.2%` / `+0.23%` / `+0.49%` / `+565.2%` / `1.11` | `341` / `47.2%` / `-0.70%` / **`-0.65%`** / **`-221.1%`** / `0.89` | `237` / `52.7%` / `-0.37%` / `-88.1%` / `0.93` |
| **`G4_LIQUID_MEME_RETAIL`** | `19` | `242` / `54.5%` / `+0.38%` / `+0.65%` / `+156.5%` / `1.13` | `37` / `64.9%` / `+4.57%` / **`+4.48%`** / **`+165.7%`** / `2.86` | `26` / `65.4%` / `+3.89%` / `+101.2%` / `2.48` |
| **`G5_THIN_OR_MANIPULATED`** | `109` | `80` / `57.5%` / `-1.04%` / `-1.66%` / `-132.7%` / `0.82` | `282` / `41.5%` / `-2.69%` / **`-3.18%`** / **`-896.4%`** / `0.61` | `199` / `44.7%` / `-3.09%` / `-614.1%` / `0.59` |

---

## 4. BẢNG TỔNG HỢP TRẠNG THÁI 19 HẠNG MỤC KIỂM ĐỊNH (v4.0.2 FINAL SIGN-OFF MATRIX)

| Mã Audit / Re-Audit | Nội dung Phản biện | Trạng thái v4.0.1 | Trạng thái v4.0.2 | Bằng chứng Mã nguồn / Kiểm thử / JSON v4.0.2 |
| :--- | :--- | :---: | :---: | :--- |
| **`RT2-C1 (F-11/F-03)`** | Đặt chỗ tức thời tại thời điểm mở lệnh (`max_concurrent_cap=5`), kiểm tra trần Notional (`<=1.0x`) & SL Risk (`<=12%`), và thực thi danh mục kết nối (`run_portfolio_coupled_execution`) | `OPEN` | **`CLOSED`** | `verify_red_team_audit_2026.py`, `verify_red_team_reaudit_v402.py`, `test_reaudit_same_timestamp_cap_and_notional_risk_caps` (`6->5`, `1.5x->3`) |
| **`RT2-C2 (F-10)`** | Sửa công thức Compounded NAV giữ nguyên khối lượng cố định của lệnh đang mở (`100 -> 50 -> 100` trả đúng `99.96` / `-0.04%`) | `OPEN` | **`CLOSED`** | `simulate_trade_v2` (`bar_trace`), `compute_time_weighted_concurrency_and_nav`, `test_reaudit_round_trip_price_fixed_quantity_nav` |
| **`RT2-H1 (F-02)`** | Cập nhật toàn bộ các script nghiên cứu cũ để nhận `exit_price`, `exit_time`, `hold_hours` mới khi mô phỏng SL 0.886 (Mốc 6) | `PARTIALLY_CLOSED` | **`CLOSED`** | `study_factor2_3_4_complete_2025.py`, `study_independent_audit_metrics.py`, `study_insample_2020_2025_by_year.py`, `study_oos_2026_all_7_milestones.py`, `study_coin_universe_selection_2026.py` |
| **`RT2-H2 (F-17)`** | Chạy lại toàn bộ Vũ trụ 338 mã coin bằng Engine đã vá v4.0.2 và thực thi độc lập từng cấu hình (Independent Milestone Execution) | `OPEN` | **`CLOSED`** | `universe_reaudit_v402_worker.py`, `re_audit_3_universe_338_and_rolling_pit` |
| **`RT2-H3 (F-18)`** | Xây dựng `ROLLING_PIT_TOP50_VOL` tái cơ cấu hàng tháng chỉ dùng 63 ngày quá khứ `[t-63d, t)` và gắn nhãn minh bạch `SNAPSHOT_2026` cho các bảng dùng CoinGecko cache | `OPEN` | **`CLOSED`** | `universe_reaudit_v402_worker.py` (`MONTHLY_REBALANCE_DATES`, `rolling_pit_top50_by_ym`) |
| **`RT2-H4 (F-13/F-19)`** | Kết xuất tự động 100% báo cáo Markdown từ JSON cùng phiên bản kèm hàm kiểm tra tính nhất quán tự động (`verify_markdown_json_consistency`) | `OPEN` | **`CLOSED`** | `generate_markdown_report_v402`, `verify_markdown_json_consistency` (`all_passed=True`) |
| **`RT2-M1 (F-07/F-08)`** | Hợp nhất công thức biến động/EMA (`compute_canonical_pst_series`) và cô lập tuyệt đối tác động `.bfill()` vs `.ffill()` (`0` lệnh khác biệt khi giữ nguyên `min_periods=1`) | `PARTIALLY_CLOSED` | **`CLOSED`** | `detector.py:compute_canonical_pst_series`, `test_reaudit_swing_pivot_right_bars_and_fee_bps_and_isolated_bfill` |
| **`RT2-M2 (F-05/F-09)`** | Khai báo `swing_pivot_left_bars=2`, `swing_pivot_right_bars=2`, `m6_sl_atr_buffer=0.25`, `horizon_hours_1d=120` trong `FiboTrendShortConfig` và kiểm thử hành vi | `PARTIALLY_CLOSED` | **`CLOSED`** | `settings.py:FiboTrendShortConfig`, `detector.py:detect_htf_reversal_wave` |
| **`RT2-M3 (F-09b)`** | Hợp nhất công thức Conviction Score 4 nhân tố và báo cáo song song Factor-Gate vs Score-Gate, Fixed `1.0x` vs Sized `1.50/1.15/0.80` | `PARTIALLY_CLOSED` | **`CLOSED`** | `detector.py:compute_orthogonal_conviction_score`, `factor_gate_vs_score_gate_and_1x_vs_sized` |
| **`RT2-M4 (F-12/F-15)`** | Báo cáo đầy đủ đường cắt chung `2026-08-31` vs `2026-09-29` cho tất cả 7 mốc và bổ sung 95% Cluster-Bootstrap CI theo tuần (`bootstrap_ci95`) | `PARTIALLY_CLOSED` | **`CLOSED`** | `compute_weekly_cluster_bootstrap_ci`, `factor_gate_vs_score_gate_and_1x_vs_sized` |
| **`RT2-L1 (F-16)`** | Kiểm toán độ phủ ngày niêm yết mới và ngày kết thúc dữ liệu trên toàn bộ 338 mã coin | `OPEN` | **`CLOSED`** | `data_coverage_and_listing_audit` (`338` symbols audited) |
| **`RT2-L2 (F-04b)`** | Chuẩn hóa đơn vị `fee_bps` / `round_trip_fee_bps` đồng nhất giữa `_simulate_trade_outcome` và `simulate_custom_trade` (`10 bps = 0.10%`) | `PARTIALLY_CLOSED` | **`CLOSED`** | `study_factor2_3_4_complete_2025.py:simulate_custom_trade`, `test_reaudit_swing_pivot_right_bars_and_fee_bps_and_isolated_bfill` |
| **`F-01`** | Kiểm tra lại SL vừa dời (ratcheted SL) ngay trong cùng nến sau khi chạm TP1/TP2 | `CLOSED` | **`CLOSED`** | `backtest.py:_simulate_trade_outcome`, `test_same_bar_ratcheted_sl_recheck_regression` |
| **`F-04a`** | Phân tách rõ `tp1_reached`/`tp2_reached` với nguyên nhân thoát lệnh cuối cùng (`terminal_outcome` / `detailed_terminal_outcomes`) | `PARTIALLY_CLOSED` | **`CLOSED`** | `backtest.py:FiboBacktestTrade.terminal_outcome`, `summarize_trades` |
| **`F-06`** | Bắt buộc `prior_low_time < swing_high_time` (`l_idx < p_idx`) và trả `ker_wave = 0.0` nếu sóng suy biến `< 2` nến | `CLOSED` | **`CLOSED`** | `detector.py:detect_htf_reversal_wave`, `test_prior_low_strictly_before_swing_high_and_ker_zero_on_single_bar` |
| **`F-14`** | Tách biệt cửa sổ Stress-Test (`2020–2023`) khỏi cửa sổ Calibration (`2024–2025`) và tính chuẩn Break-Even Cost (`bps`) | `PARTIALLY_CLOSED` | **`CLOSED`** | `break_even_round_trip_bps_unscaled`, `break_even_round_trip_bps_sized` |
| **`F-19a`** | Manifest phiên bản (`VERSION_MANIFEST_v4_0_2.json`) ghi nhận SHA256 của mã nguồn, dữ liệu và báo cáo | `PARTIALLY_CLOSED` | **`CLOSED`** | `artifacts/fibo_trend_short/VERSION_MANIFEST_v4_0_2.json` |
| **`F-19b`** | Công bố rõ hiện trạng dữ liệu funding lịch sử trên ổ đĩa và tách bạch kịch bản Ex-Funding vs Stress Funding | `PARTIALLY_CLOSED` | **`CLOSED`** | `historical_funding_audit` |
| **`F-19c`** | Giữ nguyên các tệp v4.0.0 / v4.0.1 cũ để đối chiếu lịch sử và xuất kết quả mới sang tệp định danh `v4.0.2` | `CLOSED` | **`CLOSED`** | `red_team_reaudit_recalculation_v4_0_2.json`, `RED_TEAM_REAUDIT_RESPONSE_v4_0_2_2026-10-16.md` |
