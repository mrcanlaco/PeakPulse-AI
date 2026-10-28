# HỒ SƠ PHẢN HỒI KIỂM ĐỊNH ĐỘC LẬP & PROMPT TÁI KIỂM ĐỊNH (v4.0.0 $\rightarrow$ v4.0.1 POST-AUDIT FIX)
**Chiến lược:** PeakPulse AI — Fibo Trend Short  
**Phiên bản đối chiếu:** `v4.0.0 (Legacy Pre-Audit)` $\rightarrow$ `v4.0.1 (Post-Audit Fix & Standalone Recalculation)`  
**Ngày xuất bản:** `2026-10-16`  
**Tệp dữ liệu kiểm chứng đi kèm:**
- `artifacts/fibo_trend_short/red_team_audit_recalculation_2026.json` (Toàn bộ số liệu tái lập sau khi sửa lỗi)
- `scripts/fibo_research/verify_red_team_audit_2026.py` (Script kiểm chứng độc lập toàn bộ 19 điểm phản biện)
- `tests/unit/fibo_short/test_fibo_short.py` (`10/10 passed` — bao gồm regression tests mới cho các lỗi kiểm toán)

---

## PHẦN A — PROMPT GỬI LẠI BÊN KIỂM ĐỊNH (COPY-PASTE TRỰC TIẾP)

> **Hướng dẫn sử dụng:** Bạn có thể copy toàn bộ khối văn bản trong khung dưới đây để gửi trực tiếp cho AI Kiểm định (ChatGPT o1/o3/GPT-4o hoặc Claude), kèm theo tệp `RED_TEAM_AUDIT_RESPONSE_AND_REAUDIT_PROMPT_2026-10-16.md` và `red_team_audit_recalculation_2026.json` nếu cần đối chiếu chi tiết.

```markdown
Bạn là Kiểm toán viên Định lượng Độc lập (Independent Quantitative Red-Team Auditor).
Trước đó, bạn đã thực hiện kiểm định hồ sơ **PeakPulse AI — Fibo Trend Short v4.0.0** và nêu ra 3 nhóm phản biện lớn (gồm 19 phát hiện chi tiết về cơ chế khớp lệnh, sai khác đặc tả - mã nguồn, và phương pháp tính số liệu/độ bền).

Nhóm phát triển đã thực hiện rà soát độc lập từng điểm, **không tối ưu lại bất kỳ tham số nào trên tập 2026 Holdout**, tiến hành sửa lỗi trực tiếp trong mã nguồn (`v4.0.1 Post-Audit Fix`), bổ sung kiểm thử hồi quy (`pytest`), và tính toán lại toàn bộ bảng biểu.

Nhiệm vụ của bạn trong vòng tái kiểm định (Re-Audit) này:
1. Đánh giá xem từng lỗi kỹ thuật bạn nêu ra ở vòng 1 đã được xử lý đúng bản chất toán học và cơ chế khớp lệnh thực tế hay chưa (Closed / Partially Closed / Open).
2. Xác minh tính hợp lệ của các bảng số liệu tính lại sau khi:
   - Bật kiểm tra `Same-Bar Ratcheted SL` (`pessimistic_high`) ngay trong cùng nến chạm TP1/TP2;
   - Tách mô phỏng `Standalone Independent Execution` (mỗi cấu hình tự quản lý `consumed_waves` và `cooldown_until_idx` riêng thay vì lọc tập con từ Mốc 1);
   - Sửa hoàn toàn kế thừa `exit_price / exit_time / hold_hours` của Mốc 6 (`SL 0.886`);
   - Chuẩn hóa `round_trip_fee_bps`, ép điều kiện nghiêm ngặt `t_low < t_high` (`KER = 0.0` nếu `< 2` nến), và loại bỏ `.bfill()` trong khởi tạo biến động;
   - Bổ sung đường vốn `Hourly Mark-to-Market Account NAV` (với vốn mở lệnh từng phần, phí, funding và trần vị thế đồng thời `max_concurrent = 5`) cùng `Time-Weighted Concurrency`;
   - Tách bạch `2020–2023 Out-of-Calibration Stress-Test` với `2024–2025 In-Sample Calibration`, và thay nhãn `PIT_ZERO_BIAS_MCAP_FLOAT` (dùng cache 2026) bằng chuẩn `PIT_A1E6CA7D_TOP50_VOL` (100% Point-in-Time từ dữ liệu OHLCV 2024–2025).
3. Đưa ra **Phán quyết Kiểm định Cuối cùng (Final Audit Sign-off)** về:
   - Độ trung thực của mã nguồn và báo cáo `v4.0.1`;
   - Các tuyên bố (Claims) nào đã đủ bằng chứng bảo vệ;
   - Đánh giá mức độ sẵn sàng để chuyển sang giai đoạn **Forward Paper Trading / Shadow Live**.

Dưới đây là toàn bộ Báo cáo Phản hồi Kiểm định, Bằng chứng Mã nguồn và Bảng số liệu tính lại để bạn đối chiếu.
```

---

## PHẦN B — BÁO CÁO PHẢN HỒI KIỂM ĐỊNH & ĐỐI CHIẾU SỐ LIỆU CHI TIẾT

### 1. Bảng tổng hợp phân loại 19 phát hiện của Kiểm toán viên

| Mã mục | Nội dung phản biện của Kiểm toán viên | Phân loại | Bằng chứng xác minh & Trạng thái xử lý (`v4.0.1`) |
| :--- | :--- | :---: | :--- |
| **1.1** | Bộ mô phỏng kiểm tra SL trước TP nhưng không kiểm tra lại SL vừa dời (`ratcheted SL`) sau TP1/TP2 trong cùng nến (ví dụ chuẩn: lãi gộp ghi `17%` thay vì `5%`). | **Xác nhận đúng** | Tái hiện chính xác: bản cũ ghi `+17.0%` (`TP3_HIT`, `hold=2h`). Đã sửa trong `backtest.py` và `study_factor2_3_4_complete_2025.py` với `ratchet_mode="pessimistic_high"`: kiểm tra ngay `b_high >= active_sl` sau khi chạm TP1/TP2 trong cùng nến $\rightarrow$ trả về đúng **`+5.0%` lãi gộp** (`+4.8%` ròng @ 20 bps, `hold=1h`). |
| **1.2** | Khi mô phỏng lại Mốc 6 với `SL 0.886`, `exit_time`, `hold_hours`, `exit_price` vẫn kế thừa từ lệnh `SL 1.000`. | **Xác nhận đúng** | `simulate_custom_trade()` cũ chỉ trả về `(net_pct, gross_pct, reason)`. Đã nâng cấp thêm `return_exit_meta=True` để trả về chính xác `(net_pct, gross_pct, reason, exit_price, exit_time, hold_hours)` của `SL 0.886` và cập nhật lại toàn bộ lệnh, concurrency, NAV. |
| **1.3** | Các mốc nâng cao (`4A, 6B, 6A, 6S`) được lọc tập con từ danh sách lệnh Mốc 1 đã áp dụng cooldown/consumed waves, làm chặn tín hiệu hợp lệ xuất hiện sau lệnh bị từ chối. | **Xác nhận đúng** | Đã tách biệt rõ **Phân tích tập con (Subset Analysis)** và **Vận hành độc lập từng cấu hình (Standalone Independent Execution)**. Khi chạy độc lập, Mốc 6B tăng từ `452` lên **`504` lệnh** (`+632.09%`, `PF = 1.36` giai đoạn 2020–2025) và **`25` lệnh** (`+125.83%`, `PF = 4.73` năm 2026). |
| **1.4** | Nhãn `TP1_HIT` / `TP2_HIT` biểu thị mốc TP cao nhất đã chạm thay vì nguyên nhân kết thúc lệnh cuối cùng (SL hòa vốn, SL tại TP1 hay hết giờ). | **Xác nhận đúng** | Đã bổ sung bảng phân rã 7 trạng thái kết thúc thực sự (`Terminal Exit Decomposition`): `TP3_FULL`, `TP2_THEN_SL_AT_TP1`, `TP2_THEN_TIME_EXIT`, `TP1_THEN_SL_AT_BE`, `TP1_THEN_TIME_EXIT`, `INITIAL_STOP_LOSS`, `NO_TP_TIME_EXIT`. |
| **1.5** | Không nhất quán đơn vị `fee_bps`: giá trị `10` trừ `0.10%` ở hàm gốc (`backtest.py`) nhưng trừ `0.20%` ở hàm nghiên cứu (`2 * fee_bps`). | **Xác nhận đúng** | Đã chuẩn hóa tham số `round_trip_fee_bps: float | None = None` ở cả `backtest.py` và `study_factor2_3_4_complete_2025.py` để đảm bảo `round_trip_fee_bps=20.0` luôn trừ đúng `0.20%` tổng chi phí hai chiều. |
| **2.1** | Swing High được chấp nhận với 1 nến bên phải (`p_idx + 1`), trong khi văn bản đặc tả ghi 2 nến. | **Xác nhận đúng** | Mã nguồn kiểm tra 1 nến trái + 1 nến phải kết hợp điều kiện bắt buộc **sóng sập hậu đỉnh $\ge 6\%$** (`impulse_drop_pct >= 0.06`, đóng vai trò xác nhận cấu trúc mạnh hơn nến đơn). Đã cập nhật văn bản khớp mã nguồn và thêm tham số cấu hình `swing_pivot_left_bars`, `swing_pivot_right_bars` trong `detector.py`. |
| **2.2** | `Prior Low` có thể nằm ngay trên nến `Swing High` (`l_idx == p_idx`), trái điều kiện `t_low < t_high` và được gán `KER = 1.0`. | **Xác nhận đúng** | Trong 1.467 lệnh Mốc 1 (2020–2025), có đúng **4 lệnh** (`0.27%`) rơi vào `l_idx == p_idx` và **0 lệnh** trong năm 2026. Đã sửa trong `detector.py`: cắt `prior_slice = klines_htf[prior_start_idx:abs_high_idx]` (loại trừ `abs_high_idx`) và trả về `KER = 0.0` khi `< 2` nến. |
| **2.3** | Công thức biến động chuẩn hóa khác nhau giữa văn bản (`EWMA(abs(Δclose))`), nghiên cứu (`ewm.std` + sàn `2%`) và detector (`stdev` của hiệu giá). | **Xác nhận đúng** | Đã xác định chính xác: toàn bộ bảng nghiên cứu Mốc 1–7 do `compute_f1_features()` trong `study_factor1_multi_repo_benchmark_2025.py` tạo ra. Đã cập nhật tài liệu đặc tả khớp 100% công thức mã nguồn nghiên cứu. |
| **2.4** | `.bfill()` trong `robust_vol` của script nghiên cứu có thể đưa thông tin tương lai vào vùng khởi động. | **Đúng một phần** *(Lỗi mã có thật, tác động = 0% đến cổng lọc)* | `.bfill()` chỉ chạm **10 nến H4 đầu tiên** (`idx 0..9` cho `ewmac_16_64`) và **14 nến H4 đầu tiên** (`idx 0..13` cho `accel_4_16`) lúc bắt đầu lịch sử. Kiểm thử nhân quả trên `1.467` lệnh: **`0 / 1.467` lệnh** thay đổi kết quả cổng lọc F1; chỉ **`1 / 1.467` lệnh** (`fibo_4963e109d33e_273`) đổi nhẹ điểm Conviction (`69.0 -> 75.0`). Đã xóa `.bfill()`, thay bằng `.ffill().fillna((close * 0.02).abs())`. |
| **2.5** | Hồ sơ ghi lookback `48` và đệm SL `0.25 ATR`, nhưng script chạy mặc định dùng `30` và `0.20 ATR`. | **Xác nhận đúng** | Toàn bộ kết quả 2020–2025 và 2026 được chạy với `htf_lookback_bars = 30` (120 giờ H4) và `sl_atr_buffer = 0.20`. Đã đồng bộ hóa bảng thông số trong hồ sơ về đúng `30` và `0.20 ATR`. |
| **2.6** | Công thức Conviction Score, ngưỡng điểm và hệ số đi vốn giữa script nghiên cứu và `detector.py` / `scanner.py` khác nhau. | **Xác nhận đúng** | Tách rõ 2 chế độ: (1) **Research Milestone Mode (`study_factor2_3_4_complete_2025.py`)** dùng trọng số `30/25/25/20`, sizing cố định `1.0x`, ngưỡng `S >= 80, A >= 65, B >= 50` (tạo ra toàn bộ bảng Mốc 4–7); (2) **Live Scanner Heuristic Mode (`detector.py`)** dùng sizing bậc thang `0.5x / 1.0x / 1.5x`. |
| **3.1** | “Chronological MaxDD” cộng kết quả cuối cùng của lệnh theo `entry_time`, chưa phải Drawdown NAV tài khoản theo thời gian thực. | **Xác nhận đúng** | Đã xây dựng bộ mô phỏng **Hourly Mark-to-Market Account NAV** (tính PnL mở theo từng giờ H1, chốt lời từng phần 50%/30%/20%, trừ phí & funding, giới hạn `max_concurrent = 5` với `20%` notional/lệnh). Báo cáo song song cả **Tổng điểm % lợi nhuận lệnh (1x Sum)** và **Hiệu suất/MaxDD Tài khoản thực tế**. |
| **3.2** | Avg/P95 concurrency chỉ lấy mẫu tại thời điểm mở lệnh (`entry-sampled`) và chưa tách mức quan sát với trần thực thi. | **Xác nhận đúng** | Đã bổ sung **Time-Weighted Concurrency** trên toàn bộ trục thời gian H1 (`52.608` giờ giai đoạn 2020–2025 và `6.528` giờ năm 2026), đồng thời áp trần thực thi `max_concurrent_cap = 5` trong mô phỏng NAV. |
| **3.3** | Phạm vi dữ liệu 2026 không đồng nhất: 6 mã H1 đến `29/09/2026`, nhưng 8 mã tổng hợp từ M5 chỉ đến `31/08/2026`. | **Xác nhận đúng** | Đã xác minh: 6 mã (`ADA, DOGE,ETH, LINK, SOL, XRP`) có H1 đến `2026-09-29 23:00 UTC`; 8 mã (`ARB, ATOM, AVAX, BNB, BTC, DOT, LTC, OP`) tổng hợp từ M5 kết thúc tại `2026-08-31 23:00 UTC`. Đã ghi chú rõ cửa sổ giao cắt chung và cửa sổ riêng từng nhóm mã. |
| **3.4** | Sai lệch số học trong văn bản: hạng S cộng các năm là `146.8%` nhưng tổng ghi `106.2%`; baseline có `3/14` mã dương nhưng ghi `2/14`; Calibration Mốc 1 ghi `480` lệnh nhưng JSON 6 năm ghi `496`. | **Xác nhận đúng** | Giải trình rõ nguồn gốc: (a) `106.2%` là con số của cấu hình `SL 1.000` bị ghi nhầm vào cột tổng của bảng năm `SL 0.886` (`146.8%`); (b) Baseline có **3/14 mã dương** (`ATOM +81.89%, DOT +89.49%, LTC +29.53%`); (c) `480` lệnh là giai đoạn **2 năm Calibration 2024–2025**, còn `496` lệnh là **6 năm 2020–2025** của Mốc 2. Đã sửa toàn bộ trong báo cáo mới. |
| **3.5** | Cần tách stress-test `2020–2023` khỏi Calibration `2024–2025`, xác minh Break-Even bps và tuyên bố “bất bại 7/7 năm” ở mức phí `40 bps`. | **Xác nhận đúng** | Đã tách riêng bảng `2020–2023` (Out-of-Calibration) và `2024–2025` (Calibration). Tại `40 bps` trên bản sửa lỗi độc lập (`Standalone Fixed`), các cấu hình `4A, 6B, 6S` có lợi nhuận dương toàn khối `2020–2023` (`BE bps = 73.0 / 74.0 / 66.4 bps`) và thắng **6/7 năm** (`2021–2026` dương liên tiếp; năm `2020` âm do siêu sóng tăng DeFi/Altcoin). Đã điều chỉnh tuyên bố từ “7/7 năm” thành **“6/7 năm (dương liên tiếp 6 năm 2021–2026)”**. |
| **3.6** | Trên vũ trụ 338 mã không lọc, OOS 2026 có `PF < 1.0` (`4A=0.85, 6B=0.78, 6S=0.87`). Cần giải thích điều kiện vũ trụ coin hỗ trợ lợi thế. | **Xác nhận đúng** | Vũ trụ 338 mã thô chứa **222 mã rác/thanh khoản mỏng** (`PF = 0.67`, tổng lỗ `-2.950%` do nhiễu râu nến quét SL). Chiến lược **không có lợi thế trên micro-cap thanh khoản thấp**, mà chỉ có lợi thế trên nhóm **Mid/Large-Cap thanh khoản cao** (Top 50 Volume hoặc Core 14). |
| **3.7** | Nhãn `PIT_ZERO_BIAS_MCAP_FLOAT` thực chất dùng tệp `coingecko_marketcap_cache.json` cập nhật ngày `2026-10-16`, chưa phải snapshot lịch sử. | **Xác nhận đúng** | Đã gỡ bỏ nhãn `PIT_ZERO_BIAS_MCAP_FLOAT` khỏi nhóm bằng chứng Point-in-Time. Thay thế bằng chuẩn **`PIT_A1E6CA7D_TOP50_VOL`** (chỉ dùng dữ liệu OHLCV lịch sử tính đến `31/12/2025`: tuổi niêm yết $\ge 63$ ngày + Top 50 Median Daily USD Volume giai đoạn `2024–2025`, loại trừ `BTC/ETH/BNB/PAXG`). Cấu hình này hoàn toàn không dùng dữ liệu 2026 hay PnL quá khứ và đạt **`PF = 1.39` (4A), `1.37` (6B), `1.58` (6A), `1.46` (6S)** trong năm 2026. |
| **3.8** | Phân biệt `Historical Holdout` với `Forward Testing` thực sự; minh bạch số lượng biến thể đã thử nghiệm (Multiple Testing). | **Xác nhận đúng** | Đã phân loại lại giai đoạn 2026 là **Historical Out-of-Sample Holdout** (không phải Live Forward Test) và công bố đầy đủ ma trận toàn bộ các nhánh thử nghiệm (`7 mốc cấu hình x 4 mức SL x 11 bộ lọc vũ trụ coin`) để kiểm soát Selection Bias. |

---

### 2. Chi tiết các sửa đổi mã nguồn (`v4.0.1`) & Kết quả kiểm thử hồi quy (`pytest`)

#### 2.1. Các tệp mã nguồn đã được sửa đổi
1. **`src/dao_vang/fibo_short/backtest.py` (`_simulate_trade_outcome`)**:
   - Bổ sung tham số `ratchet_mode: str = "pessimistic_high"` (mặc định) và `round_trip_fee_bps: float | None = None`.
   - Ngay trong nhánh chạm `TP1` (`active_sl = entry_price`) và `TP2` (`active_sl = tp1`), nếu không chạm tiếp TP sâu hơn trong cùng nến, engine kiểm tra ngay `b_high >= active_sl` (với `pessimistic_high`) hoặc `b_close >= active_sl` (với `close_rebound`). Nếu vi phạm, phần vị thế còn lại (`50%` sau TP1 hoặc `20%` sau TP2) bị đóng ngay lập tức tại `active_sl` trong chính cây nến đó.
2. **`src/dao_vang/fibo_short/detector.py` (`_compute_ker_from_closes`, `detect_htf_reversal_wave`)**:
   - Sửa `_compute_ker_from_closes`: trả về `0.0` (thay vì `1.0`) khi `len(closes) < 2` hoặc `path_change <= 1e-12`.
   - Sửa `detect_htf_reversal_wave`: cắt `prior_slice = klines_htf[prior_start_idx:abs_high_idx]` (loại trừ `abs_high_idx`) để đảm bảo nghiêm ngặt `t_low < t_high`.
   - Thêm tham số cấu hình `swing_pivot_left_bars` và `swing_pivot_right_bars`.
3. **`scripts/fibo_research/study_factor1_multi_repo_benchmark_2025.py` (`compute_f1_features`)**:
   - Loại bỏ `.bfill()` trong khởi tạo `robust_vol`, thay bằng `.ffill().fillna((close * 0.02).abs().clip(lower=1e-10))` hoàn toàn nhân quả (100% causal).
4. **`scripts/fibo_research/study_factor2_3_4_complete_2025.py` (`simulate_custom_trade`)**:
   - Đồng bộ hóa logic `Same-Bar Ratcheted SL`, `round_trip_fee_bps`, và thêm `return_exit_meta: bool = False` để trả về đầy đủ `(net_pct, gross_pct, reason, exit_price, exit_time, hold_hours)` khi mô phỏng `SL 0.886`.

#### 2.2. Bằng chứng tái hiện ví dụ chuẩn của Kiểm toán viên & Kiểm thử `pytest`
- **Ví dụ chuẩn (Toy Example):** Short tại `100`, `SL = 110`, `TP1 = 90`, `TP2 = 80`, `TP3 = 70`; Nến 1: `O=100, H=105, L=89, C=102`; Nến 2: `O=99, H=99, L=69, C=72`.
  - **Engine cũ (`legacy`):** Nến 1 khớp TP1 (`50% * +10% = +5%`), dời `active_sl = 100` nhưng bỏ qua `H=105 >= 100` và `C=102 >= 100`. Sang Nến 2 khớp tiếp TP2 (`30% * +20% = +6%`) và TP3 (`20% * +30% = +6%`) $\rightarrow$ Lãi gộp **`+17.0%`**, `exit_reason = TP3_HIT`, `hold_hours = 2`.
  - **Engine mới (`pessimistic_high` & `close_rebound`):** Nến 1 khớp TP1 (`+5%`), dời `active_sl = 100`, phát hiện ngay `H=105 >= 100` (và `C=102 >= 100`) nên đóng nốt `50%` còn lại tại `100.0` (`0%`) ngay trong Nến 1 $\rightarrow$ Lãi gộp **`+5.0%`** (lãi ròng **`+4.80%`** tại 20 bps), `hold_hours = 1`, `exit_price = 100.0`.
- **Kết quả chạy bộ kiểm thử đơn vị (`pytest`):**
  - Lệnh thực thi: `.\.venv\Scripts\python.exe -m pytest tests/unit/fibo_short/test_fibo_short.py -v`
  - Kết quả: **`10 passed in 1.89s`** (bao gồm 2 kiểm thử hồi quy mới `test_same_bar_ratcheted_sl_recheck_regression` và `test_prior_low_strictly_before_swing_high_and_ker_zero_on_single_bar`).

---

### 3. Các bảng số liệu tính lại toàn diện (`v4.0.1 Post-Audit Recalculation`)

> **Thông số chuẩn của toàn bộ bảng tính lại dưới đây:**
> - **Phiên bản mã:** `v4.0.1` (`ratchet_mode = "pessimistic_high"`, `strict_prior_low = True` (`t_low < t_high`), `causal_vol = True` (không `.bfill()`), `SL 0.886` dùng đúng `exit_price / exit_time / hold_hours` thực tế).
> - **Cơ chế vận hành:** `Standalone Independent Execution` — mỗi cấu hình tự quản lý `consumed_waves` và `cooldown_until_idx` riêng (kèm số liệu `Subset Filtered` để đối chiếu).
> - **Tham số cấu trúc:** `htf_lookback_bars = 30` (120h H4), `sl_atr_buffer = 0.20`, `max_hold_bars = 48` (48h H1), `cooldown_bars = 6` (6h H1).
> - **Mô hình chi phí:** `round_trip_fee_bps = 20.0` (`0.20%` mỗi lệnh cho bảng chuẩn) và `40.0` (`0.40%` mỗi lệnh cho bảng Stress-Test).

#### Bảng 3.1 — So sánh Trước & Sau sửa lỗi trên 14 mã Core (2020–2025 vs 2026 Holdout @ 20 bps)

| Cấu hình | Chế độ mô phỏng | 2020–2025 Số lệnh | 2020–2025 WR (%) | 2020–2025 PF | 2020–2025 Tổng Net (%) | 2026 Holdout Số lệnh | 2026 Holdout WR (%) | 2026 Holdout PF | 2026 Holdout Tổng Net (%) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mốc 1 (Baseline)** | Legacy (`v4.0.0`) | 1.467 | 36,95% | 0,88 | -435,88% | 109 | 38,53% | 0,97 | -7,48% |
| **Mốc 1 (Baseline)** | **Fixed (`v4.0.1`)** | **1.465** | **36,86%** | **0,84** | **-563,99%** | **109** | **38,53%** | **0,92** | **-19,09%** |
| **Mốc 2 (+F1 Gate)** | Legacy (`v4.0.0`) | 496 | 56,45% | 1,28 | +414,49% | 26 | 69,23% | 3,13 | +102,42% |
| **Mốc 2 (+F1 Gate)** | **Standalone Fixed (`v4.0.1`)** | **495** | **56,36%** | **1,22** | **+320,97%** | **26** | **69,23%** | **2,95** | **+93,75%** |
| **Mốc 4A (Score $\ge 65$, SL 1.0)** | Legacy Subset (`v4.0.0`) | 317 | 58,99% | 1,39 | +412,55% | 14 | 71,43% | 4,05 | +71,12% |
| **Mốc 4A (Score $\ge 65$, SL 1.0)** | Fixed Subset (`v4.0.1`) | 317 | 58,99% | 1,31 | +338,10% | 14 | 71,43% | 3,66 | +61,95% |
| **Mốc 4A (Score $\ge 65$, SL 1.0)** | **Standalone Fixed (`v4.0.1`)** | **378** | **59,52%** | **1,30** | **+394,54%** | **16** | **68,75%** | **3,46** | **+69,83%** |
| **Mốc 6B (Score $\ge 50$, SL 0.886)** | Legacy Subset (`v4.0.0`) | 452 | 53,54% | 1,35 | +567,60% | 23 | 73,91% | 4,36 | +118,52% |
| **Mốc 6B (Score $\ge 50$, SL 0.886)** | Fixed Subset (`v4.0.1`) | 452 | 53,54% | 1,28 | +456,16% | 23 | 73,91% | 4,11 | +109,85% |
| **Mốc 6B (Score $\ge 50$, SL 0.886)** | **Standalone Fixed (`v4.0.1`)** | **504** | **54,37%** | **1,36** | **+632,09%** | **25** | **76,00%** | **4,73** | **+125,83%** |
| **Mốc 6A (Score $\ge 65$, SL 0.886)** | Legacy Subset (`v4.0.0`) | 251 | 56,57% | 1,41 | +394,16% | 14 | 71,43% | 3,87 | +69,75% |
| **Mốc 6A (Score $\ge 65$, SL 0.886)** | Fixed Subset (`v4.0.1`) | 251 | 56,57% | 1,33 | +319,71% | 14 | 71,43% | 3,48 | +60,58% |
| **Mốc 6A (Score $\ge 65$, SL 0.886)** | **Standalone Fixed (`v4.0.1`)** | **401** | **58,35%** | **1,31** | **+502,45%** | **21** | **80,95%** | **4,81** | **+119,32%** |
| **Mốc 6S (Score $\ge 80$, SL 0.886)** | Legacy Subset (`v4.0.0`) | 176 | 56,82% | 1,56 | +383,46% | 10 | 70,00% | 3,49 | +49,17% |
| **Mốc 6S (Score $\ge 80$, SL 0.886)** | Fixed Subset (`v4.0.1`) | 176 | 56,82% | 1,46 | +320,29% | 10 | 70,00% | 3,49 | +49,17% |
| **Mốc 6S (Score $\ge 80$, SL 0.886)** | **Standalone Fixed (`v4.0.1`)** | **314** | **59,24%** | **1,33** | **+439,50%** | **13** | **76,92%** | **4,11** | **+71,18%** |

---

#### Bảng 3.2 — Phân rã nguyên nhân kết thúc lệnh thực tế (`Terminal Exit Decomposition` — Standalone Fixed `v4.0.1`, 2020–2025)

| Cấu hình | Tổng lệnh | `TP3_FULL` (Ăn trọn 3 TP) | `TP2_THEN_SL_AT_TP1` (Chạm TP2 rồi lùi về TP1) | `TP2_THEN_TIME_EXIT` (Chạm TP2 rồi hết 48h) | `TP1_THEN_SL_AT_BE` (Chạm TP1 rồi hòa vốn) | `TP1_THEN_TIME_EXIT` (Chạm TP1 rồi hết 48h) | `INITIAL_STOP_LOSS` (Chạm SL gốc) | `NO_TP_TIME_EXIT` (Hết 48h chưa chạm TP1) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mốc 1 (Baseline)** | 1.465 | 79 (5,4%) | 240 (16,4%) | 22 (1,5%) | 145 (9,9%) | 72 (4,9%) | 578 (39,5%) | 329 (22,5%) |
| **Mốc 2 (+F1 Gate)** | 495 | 31 (6,3%) | 94 (19,0%) | 10 (2,0%) | 61 (12,3%) | 27 (5,5%) | 177 (35,8%) | 95 (19,2%) |
| **Mốc 4A (Score $\ge 65$, SL 1.0)** | 378 | 21 (5,6%) | 73 (19,3%) | 10 (2,6%) | 47 (12,4%) | 26 (6,9%) | 132 (34,9%) | 69 (18,3%) |
| **Mốc 6B (Score $\ge 50$, SL 0.886)** | 504 | 27 (5,4%) | 93 (18,5%) | 10 (2,0%) | 59 (11,7%) | 26 (5,2%) | 199 (39,5%) | 90 (17,9%) |
| **Mốc 6A (Score $\ge 65$, SL 0.886)** | 401 | 19 (4,7%) | 72 (18,0%) | 10 (2,5%) | 51 (12,7%) | 28 (7,0%) | 150 (37,4%) | 71 (17,7%) |
| **Mốc 6S (Score $\ge 80$, SL 0.886)** | 314 | 15 (4,8%) | 59 (18,8%) | 7 (2,2%) | 39 (12,4%) | 21 (6,7%) | 115 (36,6%) | 58 (18,5%) |

---

#### Bảng 3.3 — Đường vốn Tài khoản theo giờ (`Hourly Mark-to-Market Account NAV`) & `Time-Weighted Concurrency` (`v4.0.1`)

*Mô hình tài khoản: Mỗi lệnh phân bổ `20% NAV` (tương ứng trần `max_concurrent_cap = 5` lệnh mở đồng thời, không dùng đòn bẩy vượt 1.0x tổng tài khoản). Cập nhật MTM từng giờ H1 cho phần vị thế đang mở, ghi nhận phần đã chốt lời 50%/30%/20% và trừ phí/funding.*

| Cấu hình & Giai đoạn | Tổng điểm % lệnh (1x Sum, không cap) | Lợi nhuận Tài khoản Cộng dồn (20% Notional, Cap=5) | Lợi nhuận Tài khoản Lãi kép (Compounded NAV) | MaxDD Tài khoản Cộng dồn (MTM) | MaxDD Tài khoản Lãi kép (MTM) | Concurrency Trung bình theo Giờ (Toàn thời gian / Khi có lệnh) | P95 / Max Concurrency Quan sát | Số lệnh bị từ chối do chạm Cap=5 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mốc 4A (2020–2025)** | +394,54% | **+66,72%** | **+67,42%** | **31,59%** | **32,54%** | `0,443` / `1,59` (27,8% giờ) | 2,0 / 10 | 28 / 378 |
| **Mốc 6B (2020–2025)** | +632,09% | **+110,20%** | **+133,37%** | **46,73%** | **43,26%** | `0,505` / `1,70` (29,7% giờ) | 2,0 / 11 | 51 / 504 |
| **Mốc 6A (2020–2025)** | +502,45% | **+93,75%** | **+107,00%** | **43,95%** | **39,07%** | `0,434` / `1,62` (26,7% giờ) | 2,0 / 10 | 32 / 401 |
| **Mốc 6S (2020–2025)** | +439,50% | **+84,92%** | **+89,24%** | **58,87%** | **49,15%** | `0,376` / `1,52` (24,7% giờ) | 2,0 / 9 | 21 / 314 |
| **Mốc 4A (2026 Holdout)** | +69,83% | **+13,97%** | **+14,73%** | **3,25%** | **3,68%** | `0,119` / `1,30` (9,1% giờ) | 1,0 / 2 | 0 / 16 |
| **Mốc 6B (2026 Holdout)** | +125,83% | **+25,17%** | **+28,03%** | **2,88%** | **3,35%** | `0,145` / `1,40` (10,3% giờ) | 1,0 / 4 | 0 / 25 |
| **Mốc 6A (2026 Holdout)** | +119,32% | **+23,86%** | **+26,41%** | **2,98%** | **3,46%** | `0,146` / `1,42` (10,3% giờ) | 1,0 / 4 | 0 / 21 |
| **Mốc 6S (2026 Holdout)** | +71,18% | **+14,24%** | **+14,97%** | **4,16%** | **4,68%** | `0,104` / `1,15` (9,0% giờ) | 1,0 / 3 | 0 / 13 |

---

#### Bảng 3.4 — Tách biệt `2020–2023 Stress-Test (Out-of-Calibration)` vs `2024–2025 Calibration` & Hiệu suất từng năm tại `40 bps` (`Standalone Fixed v4.0.1`)

| Cấu hình | 2020–2023 Số lệnh | 2020–2023 Net @ 20bps | 2020–2023 Net @ 40bps | 2020–2023 PF @ 40bps | 2020–2023 Break-Even (bps) | 2024–2025 Số lệnh | 2024–2025 Net @ 20bps | 2024–2025 Net @ 40bps | 2024–2025 Break-Even (bps) | Số năm dương @ 20bps / @ 40bps |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mốc 4A (SL 1.0)** | 238 | +126,24% | **+78,64%** | **1,08** | **73,0 bps** | 140 | +268,30% | **+240,30%** | **211,6 bps** | **6/7** (`2021–2026`) / **6/7** |
| **Mốc 6B (SL 0.886)** | 328 | +177,04% | **+111,44%** | **1,09** | **74,0 bps** | 176 | +455,05% | **+419,85%** | **278,6 bps** | **6/7** (`2021–2026`) / **6/7** |
| **Mốc 6A (SL 0.886)** | 258 | +73,83% | **+22,23%** | **1,02** | **48,6 bps** | 143 | +428,62% | **+400,02%** | **319,7 bps** | **6/7** (`2021–2026`) / **5/7** |
| **Mốc 6S (SL 0.886)** | 207 | +109,28% | **+67,88%** | **1,06** | **66,4 bps** | 107 | +330,21% | **+308,81%** | **328,6 bps** | **6/7** (`2021–2026`) / **6/7** |

**Chi tiết từng năm tại mức phí khắc nghiệt `40 bps` (`0.40%` / lệnh — Standalone Fixed `v4.0.1`):**
- **Mốc 4A (`SL 1.000`):** `2020: -52.53%` | `2021: +35.67%` | `2022: +55.57%` | `2023: +39.93%` | `2024: +119.83%` | `2025: +120.47%` | `2026: +66.63%` $\rightarrow$ **Thắng 6/7 năm (dương liên tiếp 2021–2026)**.
- **Mốc 6B (`SL 0.886`):** `2020: -78.18%` | `2021: +61.49%` | `2022: +64.17%` | `2023: +63.97%` | `2024: +234.60%` | `2025: +185.25%` | `2026: +120.83%` $\rightarrow$ **Thắng 6/7 năm (dương liên tiếp 2021–2026)**.
- **Mốc 6A (`SL 0.886`):** `2020: -75.95%` | `2021: -0.97%` | `2022: +70.26%` | `2023: +28.89%` | `2024: +242.59%` | `2025: +157.43%` | `2026: +115.12%` $\rightarrow$ **Thắng 5/7 năm tại 40 bps (6/7 năm tại 20 bps)**.
- **Mốc 6S (`SL 0.886`):** `2020: -60.29%` | `2021: +5.87%` | `2022: +65.47%` | `2023: +56.83%` | `2024: +177.26%` | `2025: +131.55%` | `2026: +68.58%` $\rightarrow$ **Thắng 6/7 năm (dương liên tiếp 2021–2026)**.

---

#### Bảng 3.5 — Đối chiếu Vũ trụ 338 mã: Loại bỏ `PIT_ZERO_BIAS_MCAP_FLOAT` & Chuẩn hóa `PIT_A1E6CA7D_TOP50_VOL` (100% Point-in-Time OHLCV)

| Bộ lọc Vũ trụ (Universe Tier) | Đặc tính Point-in-Time (PIT) | Số mã | OOS 2026 PF (Mốc 4A) | OOS 2026 PF (Mốc 6B) | OOS 2026 PF (Mốc 6A) | OOS 2026 PF (Mốc 6S) | Kết luận Kiểm định |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **1. `RAW_ALL_338`** | Không lọc (chứa 222 mã thanh khoản mỏng) | 338 | 0,85 | 0,78 | 0,80 | 0,87 | **Bác bỏ giao dịch toàn sàn:** 222 mã thanh khoản thấp bị quét SL bởi râu nến (`PF = 0.67`). |
| **2. `PIT_ZERO_BIAS_MCAP_FLOAT`** | **Không đạt PIT** (dùng cache CoinGecko ngày `2026-10-16`) | 49 | 1,64 | 1,70 | 1,70 | 1,50 | **Thu hồi nhãn `ZERO_BIAS`:** Chỉ giữ làm tham chiếu phụ có điều kiện, không dùng làm bằng chứng PIT. |
| **3. `PIT_A1E6CA7D_TOP50_VOL`** | **Đạt 100% PIT** (chỉ dùng OHLCV `2024–2025`: tuổi $\ge 63$d + Top 50 Median USD Vol, trừ `BTC/ETH/BNB/PAXG`) | **46** | **1,39** (`+261,8%`) | **1,37** (`+354,3%`) | **1,58** (`+376,7%`) | **1,46** (`+212,2%`) | **Chuẩn PIT chính thức:** Hoàn toàn không dùng dữ liệu 2026 hay PnL quá khứ; cả 4 cấu hình đều sinh lời tốt (`PF = 1.37–1.58`). |
| **4. `CORE_14_ORIGINAL`** | 14 mã Mid/Large-Cap cố định từ đầu nghiên cứu | 14 | **3,46** (`+69,8%`) | **4,73** (`+125,8%`) | **4,81** (`+119,3%`) | **4,11** (`+71,2%`) | **Danh mục vận hành cốt lõi:** Tập trung lợi thế cao nhất trên các đồng Altcoin thanh khoản lớn. |

---

### 4. Ma trận Quản trị Tuyên bố (Updated Claim Governance) & Điều kiện Giao dịch Tiền thật

1. **Những gì đã được chứng minh vững chắc sau khi vá toàn bộ lỗi (`v4.0.1`):**
   - Sau khi áp dụng kiểm tra `Same-Bar Ratcheted SL (pessimistic_high)`, tách mô phỏng `Standalone Independent Execution`, ép `t_low < t_high`, xóa `.bfill()`, và chuẩn hóa phí `round_trip_fee_bps`, các cấu hình cốt lõi (**Mốc 4A, 6B, 6A, 6S**) vẫn duy trì lợi thế thống kê rõ rệt trên cả tập `2020–2023 Out-of-Calibration`, `2024–2025 Calibration`, và `2026 Historical Holdout`.
   - Khi mô phỏng tài khoản thực tế theo giờ (`Hourly Mark-to-Market Account NAV`, `20% Notional/lệnh`, `Cap = 5`), **Mốc 4A** đạt `+67.42%` compounded (`MaxDD 32.54%`) giai đoạn 2020–2025 và `+14.73%` (`MaxDD 3.68%`) năm 2026; **Mốc 6B** đạt `+133.37%` compounded (`MaxDD 43.26%`) giai đoạn 2020–2025 và `+28.03%` (`MaxDD 3.35%`) năm 2026.
   - Trên vũ trụ rộng 338 mã, chuẩn chọn mã **100% Point-in-Time bằng thanh khoản OHLCV (`PIT_A1E6CA7D_TOP50_VOL`)** chứng minh chiến lược hoạt động tốt trên nhóm Top 50 Volume (`PF = 1.37–1.58` năm 2026) mà không cần dùng dữ liệu vốn hóa năm 2026 hay lọc theo PnL quá khứ.

2. **Những tuyên bố đã được điều chỉnh / thu hồi để đảm bảo trung thực tuyệt đối:**
   - **Thu hồi tuyên bố “bất bại 7/7 năm”:** Thay bằng **“Thắng 6/7 năm (dương liên tiếp 6 năm từ 2021 đến 2026 ngay cả ở mức phí khắc nghiệt 40 bps; năm 2020 âm do chu kỳ siêu tăng trưởng Altcoin/DeFi)”**.
   - **Thu hồi nhãn `PIT_ZERO_BIAS_MCAP_FLOAT`:** Chuyển sang sử dụng **`PIT_A1E6CA7D_TOP50_VOL`** làm bằng chứng Point-in-Time duy nhất cho vũ trụ 338 mã.
   - **Định danh đúng giai đoạn 2026:** Ghi rõ là **Historical Out-of-Sample Holdout**, không gọi là Live Forward Test.

3. **5 Điều kiện bắt buộc (Live Readiness Gates) trước khi giao dịch tiền thật:**
   - **Gate 1 (Đồng bộ Config Production):** Khóa cấu hình thực thi (`Mốc 6B` hoặc `Mốc 4A` ở chế độ `Standalone Independent`) giữa `scanner.py`, `detector.py` và `backtest.py` (`htf_lookback_bars=30`, `sl_atr_buffer=0.20`, `max_concurrent_cap=5`).
   - **Gate 2 (Khóa Vũ trụ Giao dịch):** Chỉ giao dịch trên danh sách **Core 14 Mid/Large-Cap** hoặc danh sách **Top 50 Volume (`PIT_A1E6CA7D_TOP50_VOL`)** được tái cân bằng định kỳ đầu mỗi quý bằng dữ liệu OHLCV quá khứ; tuyệt đối cấm chạy trên các mã Small/Micro-Cap thanh khoản mỏng.
   - **Gate 3 (Forward Paper Trading / Shadow Live):** Vận hành Paper Trading thời gian thực tối thiểu **30–60 lệnh** (hoặc 8–12 tuần) với ghi log bất biến (hash commit Git + timestamp mở/đóng lệnh) để đo độ trượt giá thực tế.
   - **Gate 4 (Quản trị Rủi ro Tài khoản MTM):** Giới hạn rủi ro mỗi lệnh `0.5% – 1.0% NAV` (hoặc tối đa `15%–20% Notional` không đòn bẩy), trần vị thế đồng thời `max_concurrent = 5`, và ngắt mạch tự động (`Circuit Breaker`) nếu Drawdown tài khoản MTM vượt `15%`.
   - **Gate 5 (Kiểm soát Đa kiểm định):** Không tinh chỉnh thêm bất kỳ tham số nào trên dữ liệu 2026; mọi đánh giá tiếp theo phải dựa hoàn toàn vào dữ liệu Forward Live sau thời điểm khóa mã `v4.0.1`.
