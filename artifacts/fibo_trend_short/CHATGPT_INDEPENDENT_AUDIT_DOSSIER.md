# HỒ SƠ KIỂM ĐỊNH ĐỘC LẬP (INDEPENDENT QUANTITATIVE RED-TEAM AUDIT DOSSIER)
**Tên Hệ Thống:** PeakPulse AI (Đảo Vàng) — Nhánh Chiến Lược `Fibo Trend Short (H4/D1 → H1)`  
**Phiên Bản Hồ Sơ:** `v4.0.0` (Đóng gói tự thân — Self-Contained Specification & Empirical Audit Pack)  
**Dữ Liệu Kiểm Thử:** `01/01/2020 – 31/12/2025` (6 Năm In-Sample, `12,339` lệnh gốc) + `01/01/2026 – 29/09/2026` (9 Tháng Out-of-Sample, `1,503` lệnh gốc)  
**Rổ Tài Sản (14 Cặp USDT Perpetual):** `BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, LTCUSDT, BCHUSDT, 1000PEPEUSDT, 1000BONKUSDT, 1000SHIBUSDT, AAVEUSDT, ADAUSDT, 1INCHUSDT, ACEUSDT, AKTUSDT`

---

## 🎯 PHẦN 0: PROMPT MẪU DÀNH CHO AI KIỂM ĐỊNH (COPY ĐOẠN NÀY KÈM TOÀN BỘ FILE GỬI CHO CHATGPT)

> **Vai trò của bạn:** Bạn là Giám đốc Quản trị Rủi ro Định lượng & Kiểm toán viên Độc lập (Independent Red-Team Quantitative Auditor) tại một quỹ giao dịch định lượng đa chiến lược.  
> **Nhiệm vụ:** Hãy thẩm định độc lập, phản biện khắt khe và kiểm tra tính bền vững toán học/thống kê của hệ thống giao dịch **"Xác Nhận Đảo Chiều & Short Theo Xu Hướng Mới (Fibonacci H4/D1 → H1)"** dựa trên toàn bộ đặc tả kỹ thuật, công thức toán học, quy tắc khớp lệnh và số liệu kiểm nghiệm 7 năm (`2020–2026`) dưới đây.  
> **Yêu cầu phản biện cụ thể:**
> 1. **Kiểm định Phương pháp luận & Sai lệch (Bias Audit):** Đánh giá xem quy trình căn chỉnh thời gian `Point-in-Time` (`htf_close_time <= h1_close_time`), quy tắc xử lý xung đột trong nến `1H` (`SL ưu tiên trước TP`), cơ chế chống nhồi lệnh (`Wave Deduplication`) và cách phân chia 3 vùng dữ liệu (`Calibration 2024–2025` / `Out-of-Time Historical Back-cast 2020–2023` / `Forward OOS 2026`) có còn khe hở nào dẫn đến *Look-ahead Bias*, *Data Snooping / Overfitting* hay *Survivorship Bias* không?
> 2. **Kiểm định Độ nhạy Chi phí & Thực thi (Execution & Fee Stress-Test Audit):** Với bảng kiểm thử chi phí từ `0 bps` đến `40 bps` (0.40%/vòng lệnh) và ngưỡng phí hòa vốn (`Break-Even Fee bps`), lợi thế thống kê (Edge) của các cấu hình `Mốc 4A`, `Mốc 6B`, `Mốc 6A`, `Mốc 6S` có đủ dày để sống sót qua trượt giá thực tế trên sàn Binance Futures không?
> 3. **Kiểm định Phân phối Rủi ro Đuôi & Chồng lấp Danh mục (Tail-Risk & Concurrency Audit):** Đánh giá tỷ lệ chạm `TP1 / TP2 / TP3 / SL / Time-Exit`, tỷ số `Payoff Ratio`, chuỗi thua liên tiếp dài nhất (`Max Losing Streak`) và rủi ro khi mở tối đa `2–8` lệnh đồng thời (`Max Concurrent Positions`) trong các đợt biến động chung toàn thị trường.
> 4. **Kiểm định Tính Bền vững Xuyên Chu kỳ & Đa Tài sản (Cross-Regime & Cross-Sectional Audit):** Phân tích sự khác biệt giữa **Nhánh Mở Rộng (`Mốc 3B/4B/5B/6B`)** và **Nhánh Tinh Hoa (`Mốc 4A/5A/6S` — bắt buộc `pysystemtrade`)** trong đại sóng Parabolic Bull Run `2020–2021` so với giai đoạn `2022–2026`, cũng như mức độ phân bổ lợi nhuận trên 14 đồng coin và giữa 2 khung `H4` vs `D1`.
> 5. **Đề xuất Cải tiến hoặc Chốt Chặn Rủi ro (Actionable Red-Team Recommendations):** Chỉ ra tối đa 3 rủi ro tiềm ẩn lớn nhất khi vận hành tiền thật (Live Trading) và cách khắc phục.

---

## ⚙️ PHẦN 1: ĐẶC TẢ TOÁN HỌC & CƠ CHẾ KHỚP LỆNH TỪNG BƯỚC (EXACT MATHEMATICAL & EXECUTION SPECIFICATION)

### 1.1. Quy Tắc Căn Chỉnh Thời Gian Đa Khung (Zero Look-Ahead Point-in-Time Alignment)
- Dữ liệu gốc là chuỗi nến `1H` chuẩn UTC (`open_time`, `close_time = open_time + 1h`).
- Khung thời gian lớn (`HTF` $\in \{\text{4H}, \text{1D}\}$) được tổng hợp từ nến `1H` với điều kiện chỉ giữ các thanh nến `HTF` **đủ 100% số nến thành phần** (`4` nến `1H` cho `4H`, `24` nến `1H` cho `1D`).
- Tại mỗi bước quyết định khi đóng thanh nến `1H` thứ $t$ (thời điểm `current_decision_ts = h1_close_times[t]`):
  $$\text{visible\_htf}(t) = \{ B_k \in \text{HTF} \mid B_k.\text{close\_time} \le \text{current\_decision\_ts} \}$$
  Tuyệt đối **không bao giờ đọc thanh nến `4H` hoặc `1D` đang mở dở dang**.

### 1.2. Định Nghĩa Cấu Trúc Sóng & 4 Nhân Tố Trực Giao (Factor #1 → Factor #4)
Trên cửa sổ `visible_htf` (tối đa `swing_lookback_bars = 48` nến HTF gần nhất):
1. **Đỉnh `Swing High` ($P_{\text{high}}$ tại $t_{\text{high}}$) & Đáy Chân Sóng `Prior Low` ($P_{\text{low}}$ tại $t_{\text{low}} < t_{\text{high}}$):**
   - `Swing High` là cực đại cục bộ đã được xác nhận bởi ít nhất 2 nến HTF đóng thấp hơn về phía bên phải.
   - `Prior Low` là mức giá thấp nhất trong cửa sổ trước `Swing High`.
   - **Factor #1A (Biên độ sóng bơm FOMO):**
     $$\text{prior\_pump\_pct} = \frac{P_{\text{high}} - P_{\text{low}}}{P_{\text{low}}} \times 100\% \ge 50.0\%$$
2. **Factor #1B (Bộ lọc Chế độ Xu hướng & Đứt gãy Gia tốc Robert Carver — `pysystemtrade`):**
   - Biến động chuẩn hóa: $\sigma_{\text{robust}} = \text{EWMA}_{35}(|\Delta P_{\text{close}}|)$.
   - Xu hướng dài hạn chuẩn hóa biến động tại đỉnh:
     $$\text{ewmac}_{16,64} = \frac{\text{EWMA}_{16}(P_{\text{close}}) - \text{EWMA}_{64}(P_{\text{close}})}{\sigma_{\text{robust}}}$$
   - Gia tốc động lượng (Đạo hàm bậc 2) tại thanh HTF vừa đóng:
     $$\text{accel}_{4,16}(t) = \text{ewmac}_{4,16}(t) - \text{ewmac}_{4,16}(t - 4)$$
   - **Điều kiện `pst_pass`:**
     $$\text{pst\_pass} \iff \big(\text{ewmac}_{16,64}(t_{\text{high}}) \le 0.0\big) \lor \big(\text{accel}_{4,16}(t_{\text{cur}}) \le -1.0\big)$$
3. **Factor #1C (Độ Rỗng Thanh Khoản Sóng Bơm — Kaufman Efficiency Ratio `ker_wave`):**
   - Tính trên chuỗi giá đóng cửa HTF từ `Prior Low` ($t_{\text{low}}$) đến `Swing High` ($t_{\text{high}}$):
     $$\text{ker\_wave} = \frac{|C_{t_{\text{high}}} - C_{t_{\text{low}}}|}{\sum_{i=t_{\text{low}}+1}^{t_{\text{high}}} |C_i - C_{i-1}|} \in [0, 1]$$
   - **Hai chế độ lọc Factor #1:**
     - **Chế độ Tinh Hoa (`f1_elite` — Bắt buộc có `PST`):** $\text{pst\_pass} \land (\text{ker\_wave} \ge 0.35)$.
     - **Chế độ Mở Rộng (`f1_expanded` — Bổ sung nhánh siêu dựng cột):** $\text{f1\_elite} \lor (\text{ker\_wave} \ge 0.65)$.
4. **Factor #2 (Nhịp Sập Đầu Tiên Phá Cấu Trúc — `Impulse Drop`):**
   - Sau $t_{\text{high}}$, giá giảm xuống tạo đáy nhịp sập đầu tiên `Impulse Low` ($P_{\text{imp}}$ tại $t_{\text{imp}} > t_{\text{high}}$). Khoảng biên độ nhịp sập: $R_{\text{wave}} = P_{\text{high}} - P_{\text{imp}}$.
   - Độ sâu nhịp sập: $\text{imp\_drop\_pct} = \frac{P_{\text{high}} - P_{\text{imp}}}{P_{\text{high}}} \times 100\% \ge 6.0\%$.
   - Độ thẳng Kaufman của nhịp sập (chống bẫy Cờ Tăng / Bull Flag zíc-zắc):
     $$\text{imp\_ker} = \frac{|C_{t_{\text{imp}}} - C_{t_{\text{high}}}|}{\sum_{j=t_{\text{high}}+1}^{t_{\text{imp}}} |C_j - C_{j-1}|} \ge 0.50$$
5. **Factor #3 (Vùng Hồi Fibonacci Breakeven Wall & Kích Hoạt Phá Cấu Trúc H1):**
   - Các mốc Fibonacci tính từ đáy `Impulse Low` ($0.0$) ngược lên `Swing High` ($1.0$):
     $$\text{Fibo}(r) = P_{\text{imp}} + r \times (P_{\text{high}} - P_{\text{imp}})$$
   - Sau $t_{\text{imp}}$, giá hồi lên chạm vào vùng `Fibo(0.500)` đến `Fibo(0.786)` nhưng đỉnh cao nhất của nhịp hồi không vượt quá `Fibo(0.786)` ($\text{max\_fibo\_ratio} \le 0.786$).
   - **Kích hoạt trên khung `1H` (`H1 Trigger`):**
     - `CANDLE_PATTERN_1`: Nến `1H` đóng đỏ dạng Shooting Star / Bearish Engulfing tại vùng Fibo.
     - `BREAK_STRUCTURE_2` (`cond2_break_prev_low`): Nến `1H` đóng cửa phá thủng đáy `Low` của nến `1H` liền trước (`close_1h < prev_low_1h`) hoặc đóng gãy ngược xuống dưới mốc `Fibo(0.500)` sau khi đã chạm vùng `0.500–0.618`.
     - `COMBO_1_2`: Thỏa mãn đồng thời cả mẫu nến đảo chiều và phá vỡ cấu trúc H1.
     - **Điều kiện khóa Factor #3 (`Mốc 5A/5B`, `Mốc 6A/6S`):** Bắt buộc có phá vỡ cấu trúc `cond2_break_prev_low == True` (tức chỉ lấy `BREAK_STRUCTURE_2` hoặc `COMBO_1_2`, loại bỏ `CANDLE_PATTERN_1` đơn độc) và $\text{max\_fibo\_ratio} \le 0.786$.
6. **Factor #4 (Vị Trí Stop Loss `Fibo 0.886`, Thoát Lệnh Phân Tầng & Đi Vốn Theo `Conviction Score 0–100`):**
   - **Giá vào lệnh (`entry_price`):** Giá đóng cửa của thanh nến `1H` kích hoạt tín hiệu.
   - **Vị trí Stop Loss (`stop_loss`):**
     - Ở `Mốc 0 → Mốc 5`: $\text{SL} = \max(P_{\text{high}}, \text{entry\_price} \times 1.005) + 0.25 \times \text{ATR}_{14}(\text{1H})$ (`above_swing_high`).
     - Ở `Mốc 6A / 6B / 6S`: $\text{SL} = \max(\text{Fibo}(0.886), \text{entry\_price} \times 1.005) + 0.25 \times \text{ATR}_{14}(\text{1H})$ (`above_0886`).
   - **3 Mốc Chốt Lời (`TP1`, `TP2`, `TP3`):**
     - $\text{TP}_1 = \text{Fibo}(0.000) = P_{\text{imp}}$ (Đáy nhịp sập đầu tiên).
     - $\text{TP}_2 = P_{\text{high}} - 1.272 \times (P_{\text{high}} - P_{\text{imp}})$ (Fibo Extension `1.272`).
     - $\text{TP}_3 = P_{\text{high}} - 1.618 \times (P_{\text{high}} - P_{\text{imp}})$ (Fibo Extension `1.618`).
   - **Thang Điểm Hội Tụ 4 Tầng (`Conviction Score` $S \in [0, 100]$):**
     - Biên độ `prior_pump_pct`: $\ge 100\% \rightarrow +15\text{đ}$; $70–100\% \rightarrow +11\text{đ}$; $50–70\% \rightarrow +7\text{đ}$.
     - Độ rỗng sóng tăng `ker_wave`: $\ge 0.65 \rightarrow +20\text{đ}$; $0.35–0.65 \rightarrow +14\text{đ}$.
     - Xung lực nhịp sập `imp_ker` (khi `Drop >= 6%`): $\ge 0.65 \rightarrow +15\text{đ}$; $0.50–0.65 \rightarrow +10\text{đ}$.
     - Chế độ vĩ mô & gia tốc `pysystemtrade`: Thỏa mãn cả `ewmac(16,64)<=0` VÀ `accel(4,16)<=-1.0` $\rightarrow +20\text{đ}$; thỏa mãn 1 trong 2 $\rightarrow +14\text{đ}$.
     - Tương quan liên thị trường BTC: `btc_ewmac_4_16 <= 0.5` $\rightarrow +5\text{đ}$; `idiosyncratic_spread >= 60%` $\rightarrow +5\text{đ}$.
     - Cấu trúc kích hoạt H1: `COMBO_1_2` $\rightarrow +12\text{đ}$; `BREAK_STRUCTURE_2` $\rightarrow +9\text{đ}$; `CANDLE_PATTERN_1` $\rightarrow +4\text{đ}$.
     - Cạn kiệt Volume nhịp hồi H1 (`pullback_vol_ratio_1h`): $\le 1.1 \rightarrow +8\text{đ}$; $1.1–1.4 \rightarrow +4\text{đ}$.
   - **Hệ số nhân khối lượng vị thế (`pos_mult`) ở `Mốc 6A/6B/6S`:**
     $$\text{pos\_mult} = \begin{cases} 1.50\times & \text{nếu } S \ge 80 \\ 1.15\times & \text{nếu } 68 \le S < 80 \\ 0.80\times & \text{nếu } S < 68 \end{cases}$$

### 1.3. Cơ Chế Mô Phỏng Khớp Lệnh Bảo Thủ Trên Chuỗi Nến `1H` Tương Lai
Trên các thanh nến `1H` tiếp theo sau thời điểm vào lệnh (tối đa `horizon = 72` giờ cho sóng `4H` và `120` giờ cho sóng `1D`):
1. **Quy tắc ưu tiên `Stop Loss` trước `Take Profit` trong cùng 1 thanh nến `1H` (Conservative Intra-Bar Conflict Rule):**
   - Ở mỗi thanh nến `1H` tương lai, hệ thống **luôn kiểm tra `bar.high >= active_sl` TRƯỚC**. Nếu thỏa mãn, toàn bộ phần vị thế còn mở bị đóng ngay tại `active_sl` và kết thúc lệnh (không được hưởng `TP` dù `bar.low` trong cùng nến đó cũng chạm `TP`).
2. **Quy tắc Chốt lời từng phần & Dời SL bảo vệ (`Staged Exit & Breakeven Ratchet`):**
   - Khi `bar.low <= TP1`: Đóng **50% vị thế** tại `TP1`, đồng thời **dời `active_sl = entry_price` (Hòa vốn)**.
   - Khi `bar.low <= TP2` (sau khi đã chạm `TP1`): Đóng tiếp **30% vị thế** tại `TP2`, đồng thời **dời `active_sl = TP1` (Khóa lãi)**.
   - Khi `bar.low <= TP3`: Đóng nốt **20% vị thế cuối cùng** tại `TP3` và kết thúc lệnh (`TP3_HIT`).
   - Nếu hết `horizon` (`72h` hoặc `120h`) mà phần vị thế còn lại chưa chạm `active_sl` hay `TP3`: Đóng phần vị thế còn lại theo giá `close` của thanh nến `1H` cuối cùng (`TIME_EXIT`).
3. **Quy tắc Chống Nhồi Lệnh Trùng Sóng (`Wave Deduplication & Cooldown`):**
   - Mỗi con sóng được định danh bởi khóa duy nhất `wave_key = f"{tf}:{swing_high_time}:{impulse_low_time}"`. Khi đã vào 1 lệnh trên con sóng đó, `wave_key` được đưa vào tập `consumed_waves` — **cấm mở lệnh thứ 2 trên cùng 1 con sóng**.
   - Ngoài ra, luồng `(symbol, tf)` đó phải nghỉ tối thiểu `cooldown_bars = max(4, hold_hours)` nến `1H` (tức không mở lệnh mới khi lệnh cũ trên cùng `(symbol, tf)` chưa đóng).
4. **Quy tắc Trừ Phí Giao Dịch & Trượt Giá Mặc Định (`Default Fee Deduction`):**
   - Ở `Mốc 0 → Mốc 5`: Mặc định trừ `10 bps = 0.10%` mỗi vòng lệnh (`net_return_pct = gross_return_pct - 0.10%`).
   - Ở `Mốc 6A / 6B / 6S`: Mặc định trừ mức phí khắt khe gấp đôi là **`20 bps = 0.20%` mỗi vòng lệnh trước khi nhân hệ số vị thế** (`net_return_pct = (gross_return_pct - 0.20%) * pos_mult`).

---

## 🛡️ PHẦN 2: PHÂN VÙNG DỮ LIỆU 3 LỚP & KHAI BÁO BẬC TỰ DO (DATA PARTITIONING & DEGREES OF FREEDOM DISCLOSURE)

Để kiểm toán viên đánh giá rủi ro **Data Snooping / Multiple Testing Overfitting**, nghiên cứu được chia thành **3 vùng dữ liệu độc lập về mặt thời gian**:

| Phân Vùng Thời Gian | Khoảng Thời Gian (UTC) | Vai Trò Phương Pháp Luận | Số Lệnh Gốc (`Mốc 0`) | Số Lệnh Sóng `>=50%` (`Mốc 1`) | Có Chỉnh Tham Số Không? |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **1. Calibration In-Sample** | `01/01/2024 – 31/12/2025` (2 năm) | Giai đoạn nghiên cứu, giải phẫu tuần tự Ceteris Paribus F1→F4 và chọn ngưỡng | `4,706` | `480` | **Có** (26 biến thể được thử nghiệm qua 4 giai đoạn) |
| **2. Out-of-Time Historical Back-Cast** | `01/01/2020 – 31/12/2023` (4 năm) | Kiểm chứng lùi qua Đại sóng Bull `2020–2021`, Bear `2022`, Sideways `2023` **sau khi đã khóa cứng công thức từ 2024–2025** | `7,633` | `987` | **Không (Zero Re-tuning)** |
| **3. Forward Out-of-Sample (OOS)** | `01/01/2026 – 29/09/2026` (9 tháng) | Kiểm chứng tiến hoàn toàn mù trên dữ liệu tương lai chưa từng chạm tới | `1,503` | `52` | **Không (Zero Re-tuning)** |

**Khai báo tổng số giả thuyết đã thử (Trial Count / Degrees of Freedom trên tập 2024–2025):**
- **Giai đoạn Factor #1:** Quét 11 mốc biên độ `prior_pump_pct` (`5% → 100%`) + đối chiếu 12 chỉ báo từ 5 kho mã nguồn mở (`pysystemtrade`, `QuantConnect/Lean`, `crypto-factor-research`, `freqtrade`, `microsoft/qlib`). Khóa 3 biến trực giao: `prior_pump_pct >= 50%`, `pst_pass`, `ker_wave >= 0.35 / 0.65`.
- **Giai đoạn Factor #2:** Thử nghiệm 5 biến đo nhịp sập (`imp_drop_pct`, `imp_retrace_of_pump`, `imp_vol_units`, `imp_ker`, `imp_vol_ratio`). Phát hiện 3 biến đầu đa cộng tuyến cao ($r \in [0.74, 0.86]$), khóa biến trực giao `imp_ker >= 0.50` ($r = 0.119$).
- **Giai đoạn Factor #3:** Thử nghiệm 3 phân vùng Fibo (`0.500–0.618`, `0.618–0.786`, `>0.786`), 3 loại nến xác nhận H1 (`CANDLE_PATTERN_1`, `BREAK_STRUCTURE_2`, `COMBO_1_2`), và tỷ số Volume nhịp hồi (`pullback_vol_ratio_1h`).
- **Giai đoạn Factor #4:** Thử nghiệm 4 vị trí đặt SL (`above_swing_high`, `above_0786`, `above_0886`, `atr_tight`) và bộ quy tắc chấm điểm `Conviction Score (0–100)`.

---

## 📊 PHẦN 3: BẢNG TIẾN HÓA CHIẾN LƯỢC XUYÊN SUỐT 7 NĂM (`2020–2025 IS` & `2026 OOS`)

### 3.1. Bảng Hiệu Suất Tách Theo Từng Năm (`2020 → 2026`) Của Toàn Bộ 11 Cấp Độ Cấu Hình

| Cấu Hình Chiến Lược | Tổng 6 Năm IS (`2020–2025`) | Năm `2020` (DeFi Bull) | Năm `2021` (Mega Bull) | Năm `2022` (Bear Winter) | Năm `2023` (Sideways) | Năm `2024` (ETF & Meme) | Năm `2025` (Alt Cycle) | **OOS `2026` (Thực Chiến)** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mốc 0: Baseline (`Pump >= 5%`)** | **-3,366.6%**<br/>(`12,339` lệnh, PF `0.89`) | `-775.2%`<br/>(WR `43.4%`, PF `0.75`) | `-1,531.3%`<br/>(WR `44.4%`, PF `0.81`) | `+197.0%`<br/>(WR `51.1%`, PF `1.05`) | `-705.2%`<br/>(WR `47.1%`, PF `0.82`) | `-980.6%`<br/>(WR `46.9%`, PF `0.85`) | `+428.8%`<br/>(WR `50.4%`, PF `1.08`) | **`+566.7%`**<br/>(`1,503` lệnh, PF `1.21`, DD `285.6%`) |
| **Mốc 1: F1A (`Pump >= 50%`)** | **+166.5%**<br/>(`1,467` lệnh, PF `1.03`) | `-147.5%`<br/>(WR `46.3%`, PF `0.78`) | `-121.0%`<br/>(WR `47.4%`, PF `0.96`) | `+182.5%`<br/>(WR `60.4%`, PF `1.58`) | `-17.8%`<br/>(WR `52.7%`, PF `0.96`) | `-35.0%`<br/>(WR `53.7%`, PF `0.97`) | `+305.3%`<br/>(WR `59.2%`, PF `1.54`) | **`+95.0%`**<br/>(`52` lệnh, WR `65.4%`, PF `1.51`) |
| **Mốc 2: +F1B (`pysystemtrade`)** | **+404.9%**<br/>(`642` lệnh, PF `1.16`) | `-137.6%`<br/>(WR `47.9%`, PF `0.65`) | **`+62.6%`**<br/>(WR `52.7%`, PF `1.05`) | `+159.6%`<br/>(WR `60.2%`, PF `1.64`) | `-16.0%`<br/>(WR `51.5%`, PF `0.85`) | `+141.1%`<br/>(WR `64.6%`, PF `1.53`) | `+195.2%`<br/>(WR `60.7%`, PF `1.58`) | **`+57.1%`**<br/>(`24` lệnh, WR `70.8%`, PF `1.59`) |
| **Mốc 3B: +F1C Mở Rộng (`PST OR KER>=0.65`)** | **+326.1%**<br/>(`567` lệnh, PF `1.16`) | `-27.5%`<br/>(WR `52.1%`, PF `0.89`) | `-82.1%`<br/>(WR `49.2%`, PF `0.91`) | `+127.9%`<br/>(WR `60.7%`, PF `1.66`) | `-73.9%`<br/>(WR `47.9%`, PF `0.62`) | `+234.1%`<br/>(WR `66.1%`, PF `1.78`) | `+147.6%`<br/>(WR `62.8%`, PF `1.67`) | **`+72.4%`**<br/>(`32` lệnh, WR `68.8%`, PF `1.64`) |
| **Mốc 3A: +F1C Tinh Hoa (`PST & KER>=0.35`)** | **+447.9%**<br/>(`390` lệnh, PF `1.34`) | **`+27.4%`**<br/>(WR `57.1%`, PF `1.15`) | `-3.1%`<br/>(WR `51.7%`, PF `0.99`) | `+106.5%`<br/>(WR `59.3%`, PF `1.61`) | `-13.7%`<br/>(WR `52.0%`, PF `0.82`) | `+222.5%`<br/>(WR `72.3%`, PF `2.69`) | `+108.2%`<br/>(WR `62.7%`, PF `1.64`) | **`+31.0%`**<br/>(`19` lệnh, WR `68.4%`, PF `1.36`) |
| **Mốc 4B: +F2 Mở Rộng (`imp_ker >= 0.50`)** | **+323.9%**<br/>(`443` lệnh, PF `1.20`) | `+0.9%`<br/>(WR `53.7%`, PF `1.00`) | `-70.1%`<br/>(WR `48.1%`, PF `0.91`) | `+91.9%`<br/>(WR `61.4%`, PF `1.78`) | `-51.2%`<br/>(WR `51.3%`, PF `0.67`) | `+207.8%`<br/>(WR `66.7%`, PF `1.90`) | `+144.5%`<br/>(WR `68.9%`, PF `2.11`) | **`+124.6%`**<br/>(`25` lệnh, WR `76.0%`, PF `4.45`) |
| **★ Mốc 4A: +F2 Tinh Hoa (Bất Bại 7/7 Năm)** | **+456.8%**<br/>(`299` lệnh, PF `1.46`) | **`+44.4%`**<br/>(WR `60.0%`, PF `1.33`) | **`+35.4%`**<br/>(WR `52.6%`, PF `1.07`) | **`+58.9%`**<br/>(WR `57.9%`, PF `1.54`) | **`+5.3%`**<br/>(WR `60.0%`, PF `1.10`) | **`+199.6%`**<br/>(WR `74.1%`, PF `3.03`) | **`+113.2%`**<br/>(WR `70.2%`, PF `2.15`) | **`+77.5%`**<br/>(`15` lệnh, WR `73.3%`, **PF `4.55`**) |
| **Mốc 5B: +F3 Mở Rộng (`H1 BOS`)** | **+266.7%**<br/>(`250` lệnh, PF `1.29`) | `+18.8%`<br/>(WR `57.1%`, PF `1.23`) | `-83.0%`<br/>(WR `47.3%`, PF `0.84`) | `+53.4%`<br/>(WR `65.2%`, PF `1.89`) | `+20.8%`<br/>(WR `68.8%`, PF `1.49`) | `+129.7%`<br/>(WR `74.0%`, PF `2.11`) | `+126.9%`<br/>(WR `77.5%`, PF `2.83`) | **`+82.9%`**<br/>(`15` lệnh, WR `80.0%`, PF `4.45`) |
| **★ Mốc 5A: +F3 Tinh Hoa (Bất Bại 7/7 Năm)** | **+313.6%**<br/>(`169` lệnh, PF `1.58`) | **`+39.9%`**<br/>(WR `63.6%`, PF `1.73`) | **`+23.5%`**<br/>(WR `53.9%`, PF `1.08`) | **`+31.7%`**<br/>(WR `60.0%`, PF `1.53`) | **`+4.4%`**<br/>(WR `71.4%`, PF `1.24`) | **`+126.5%`**<br/>(WR `77.8%`, PF `3.02`) | **`+87.6%`**<br/>(WR `75.0%`, PF `2.53`) | **`+40.4%`**<br/>(`9` lệnh, WR `77.8%`, **PF `3.61`**) |
| **👑 Mốc 6B: +F4 Toàn Diện (`SL 0.886 + Đi Vốn`)** | **+518.0%**<br/>(`443` lệnh, PF `1.32`) | `-29.1%`<br/>(WR `50.0%`, PF `0.86`) | `-21.4%`<br/>(WR `43.7%`, PF `0.97`) | **`+103.0%`**<br/>(WR `61.4%`, PF `1.92`) | `-10.5%`<br/>(WR `48.7%`, PF `0.91`) | **`+280.0%`**<br/>(WR `65.5%`, PF `2.31`) | **`+195.9%`**<br/>(WR `67.2%`, PF `2.70`) | **`+127.0%`**<br/>(`25` lệnh, WR `76.0%`, **PF `4.76`**, DD `12.1%`) |
| **👑 Mốc 6A: +F4 Sniper Mở Rộng (`SL 0.886 + Đi Vốn`)** | **+372.7%**<br/>(`250` lệnh, PF `1.39`) | `-16.5%`<br/>(WR `53.6%`, PF `0.85`) | `-24.9%`<br/>(WR `46.2%`, PF `0.95`) | **`+60.3%`**<br/>(WR `65.2%`, PF `1.97`) | **`+29.9%`**<br/>(WR `68.8%`, PF `1.76`) | **`+159.4%`**<br/>(WR `74.0%`, PF `2.22`) | **`+164.5%`**<br/>(WR `75.0%`, PF `3.42`) | **`+86.0%`**<br/>(`15` lệnh, WR `80.0%`, **PF `4.68`**, DD `8.4%`) |
| **👑 Mốc 6S: +F4 Sniper Tinh Hoa (Bất Bại 7/7 Năm)** | **+378.9%**<br/>(`169` lệnh, PF `1.59`) | **`+2.4%`**<br/>(WR `59.1%`, PF `1.03`) | **`+59.5%`**<br/>(WR `51.9%`, PF `1.18`) | **`+39.3%`**<br/>(WR `60.0%`, PF `1.63`) | **`+6.5%`**<br/>(WR `71.4%`, PF `1.33`) | **`+150.1%`**<br/>(WR `77.8%`, PF `2.73`) | **`+121.3%`**<br/>(WR `71.9%`, PF `2.99`) | **`+45.2%`**<br/>(`9` lệnh, WR `77.8%`, **PF `4.03`**, DD `7.6%`) |

### 3.2. Bảng Phân Tích Thang Điểm Hội Tụ 4 Tầng (`Conviction Score 0–100`) Tách Theo Từng Năm (`2020 → 2026`)
Chấm điểm trên toàn bộ `1,467` lệnh có `Prior Pump >= 50%` (`2020–2025`) và `52` lệnh `OOS 2026`:

| Hạng Điểm Hội Tụ (`0–100`) | Tổng 6 Năm IS (`2020–2025`) | Năm `2020` | Năm `2021` (Mega Bull) | Năm `2022` (Bear) | Năm `2023` | Năm `2024` | Năm `2025` | **OOS `2026`** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Hạng D/C (`< 55 điểm` — Đứng Ngoài)** | `-134.3%`<br/>(`623` lệnh, WR `47.5%`, PF `0.95`) | `-66.3%`<br/>(`140` lệnh, PF `0.81`) | `-241.0%`<br/>(`216` lệnh, PF `0.85`) | `+152.9%`<br/>(`65` lệnh, PF `1.88`) | `+25.6%`<br/>(`40` lệnh, PF `1.21`) | `-88.1%`<br/>(`91` lệnh, PF `0.76`) | `+82.6%`<br/>(`71` lệnh, PF `1.39`) | `+51.4%`<br/>(`23` lệnh, WR `65.2%`) |
| **Hạng B (`55–69 điểm` — Thận Trọng)** | `-237.5%`<br/>(`526` lệnh, WR `50.2%`, PF `0.90`) | `-113.0%`<br/>(`82` lệnh, PF `0.62`) | `-64.4%`<br/>(`176` lệnh, PF `0.94`) | `-60.1%`<br/>(`44` lệnh, PF `0.73`) | `-56.3%`<br/>(`62` lệnh, PF `0.70`) | `-52.1%`<br/>(`91` lệnh, PF `0.84`) | `+108.4%`<br/>(`71` lệnh, PF `1.47`) | `-20.1%`<br/>(`12` lệnh, PF `0.67`) |
| **★ Hạng A (`70–84 điểm` — Chủ Lực 1.25R)** | **`+432.2%`**<br/>(`284` lệnh, WR `62.7%`, PF `1.42`) | `+32.7%`<br/>(`24` lệnh, WR `62.5%`, PF `1.26`) | **`+140.2%`**<br/>(`110` lệnh, WR `60.0%`, PF `1.28`) | **`+64.0%`**<br/>(`28` lệnh, WR `60.7%`, PF `1.70`) | `-3.4%`<br/>(`32` lệnh, WR `56.3%`, PF `0.95`) | **`+127.6%`**<br/>(`52` lệnh, WR `67.3%`, PF `1.97`) | **`+71.1%`**<br/>(`38` lệnh, WR `71.1%`, PF `1.84`) | **`+54.6%`**<br/>(`16` lệnh, WR `75.0%`, PF `2.46`) |
| **👑 Hạng S (`>= 85 điểm` — Tối Thượng 2.0R)** | **`+106.2%`**<br/>(`34` lệnh, **WR `73.5%`, PF `2.25`**, DD `31.3%`) | `-0.8%`<br/>(`1` lệnh) | **`+44.7%`**<br/>(`13` lệnh, **WR `69.2%`, PF `2.01`**) | **`+25.7%`**<br/>(`1` lệnh, **WR `100%`**) | **`+16.3%`**<br/>(`1` lệnh, **WR `100%`**) | `+17.7%`<br/>(`11` lệnh, WR `63.6%`, PF `1.63`) | **`+43.2%`**<br/>(`7` lệnh, **WR `85.7%`, PF `3.32`**) | **`+9.1%`**<br/>(`1` lệnh, **WR `100%`**) |

---

## 💸 PHẦN 4: KIỂM THỬ ĐỘ NHẠY CHI PHÍ GIAO DỊCH & TRƯỢT GIÁ (`0 → 40 BPS` ROUND-TRIP STRESS TEST)

Mỗi mức phí dưới đây là **tổng chi phí khứ hồi cho cả 2 đầu Vào + Ra (Round-Trip Fee + Slippage)** tính trên quy mô vị thế:
- `0 bps (0.00%)`: Lợi nhuận Gộp lý thuyết (Gross PnL).
- `10 bps (0.10%)`: 2 đầu Taker Binance Futures có chiết khấu BNB/VIP hoặc 1 Maker + 1 Taker (`0.02% + 0.05% + 0.03% slippage`).
- `20 bps (0.20%)`: 2 đầu Taker tiêu chuẩn (`0.05% x 2 = 0.10%`) + `0.10%` trượt giá (Mức mặc định đang áp dụng cho `Mốc 6A/6B/6S`).
- `30 bps (0.30%)`: Kịch bản trượt giá nặng (`0.10%` phí + `0.20%` trượt giá).
- `40 bps (0.40%)`: Kịch bản thanh khoản cực xấu / quét lệnh Market lúc biến động sốc (`0.10%` phí + `0.30%` trượt giá).
- **Ngưỡng Hòa Vốn (`Break-Even Fee bps`):** Mức chi phí khứ hồi tối đa mà tại đó `Tổng Lãi Ròng = 0%`.

### 4.1. Stress-Test Chi Phí Trên Tập Calibration `2024–2025` (2 Năm) & Tập Mở Rộng `2020–2025` (6 Năm) & `OOS 2026`

| Cấu Hình & Giai Đoạn | Số Lệnh | **0 bps (Gross)**<br/>Tổng Lãi (PF) | **10 bps (0.10%)**<br/>Tổng Lãi (PF) | **20 bps (0.20%)**<br/>Tổng Lãi (PF) | **30 bps (0.30%)**<br/>Tổng Lãi (PF) | **40 bps (0.40%)**<br/>Tổng Lãi (PF) | **Ngưỡng Phí Hòa Vốn**<br/>(`Break-Even Cost`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mốc 1 (`Pump>=50%`) — 6 Năm IS (20–25)** | `1,467` | `+313.2%` (`1.05`) | `+166.5%` (`1.03`) | `+19.8%` (`1.00`) | `-126.9%` (`0.98`) | `-273.6%` (`0.96`) | **`21.4 bps` (`0.21%`)** ⚠️ Mỏng |
| **Mốc 2 (`+F1B PST`) — 6 Năm IS (20–25)** | `642` | `+469.1%` (`1.19`) | `+404.9%` (`1.16`) | `+340.7%` (`1.13`) | `+276.5%` (`1.11`) | `+212.3%` (`1.08`) | **`73.1 bps` (`0.73%`)** |
| **Mốc 3A (`+F1C Tinh Hoa`) — 6 Năm IS (20–25)** | `390` | `+486.9%` (`1.37`) | `+447.9%` (`1.34`) | `+408.9%` (`1.30`) | `+369.9%` (`1.27`) | `+330.9%` (`1.24`) | **`124.8 bps` (`1.25%`)** |
| **★ Mốc 4A (`+F2 Tinh Hoa`) — 6 Năm IS (20–25)** | `299` | `+486.7%` (`1.50`) | `+456.8%` (`1.46`) | `+426.9%` (`1.43`) | `+397.0%` (`1.39`) | `+367.1%` (`1.36`) | **`162.8 bps` (`1.63%`)** ✔ Rất dày |
| **★ Mốc 5A (`+F3 Tinh Hoa`) — 6 Năm IS (20–25)** | `169` | `+330.5%` (`1.61`) | `+313.6%` (`1.58`) | `+296.7%` (`1.54`) | `+279.8%` (`1.50`) | `+262.9%` (`1.47`) | **`195.6 bps` (`1.96%`)** ✔ Rất dày |
| **👑 Mốc 6B (`+F4 Toàn Diện`) — 6 Năm IS (20–25)** | `443` | `+613.5%` (`1.39`) | `+565.7%` (`1.36`) | **`+518.0%` (`1.32`)** | `+470.2%` (`1.28`) | `+422.4%` (`1.25`) | **`128.0 bps` (`1.28%`)** |
| **👑 Mốc 6A (`+F4 Sniper`) — 6 Năm IS (20–25)** | `250` | `+428.8%` (`1.47`) | `+400.7%` (`1.43`) | **`+372.7%` (`1.39`)** | `+344.6%` (`1.35`) | `+316.6%` (`1.32`) | **`149.8 bps` (`1.50%`)** |
| **👑 Mốc 6S (`+F4 Sniper Tinh Hoa`) — 6 Năm IS** | `169` | `+418.4%` (`1.68`) | `+398.7%` (`1.63`) | **`+378.9%` (`1.59`)** | `+359.2%` (`1.55`) | `+339.4%` (`1.51`) | **`202.8 bps` (`2.03%`)** 🏆 Dày nhất |
| **👑 Mốc 6B (`+F4 Toàn Diện`) — 2 Năm IS (24–25)** | `148` | `+508.4%` (`2.59`) | `+492.2%` (`2.51`) | **`+475.9%` (`2.43`)** | `+459.7%` (`2.36`) | `+443.4%` (`2.29`) | **`313.5 bps` (`3.14%`)** |
| **👑 Mốc 6A (`+F4 Sniper`) — 2 Năm IS (24–25)** | `90` | `+345.2%` (`2.81`) | `+334.6%` (`2.73`) | **`+323.9%` (`2.66`)** | `+313.3%` (`2.59`) | `+302.7%` (`2.52`) | **`334.6 bps` (`3.35%`)** |
| **👑 Mốc 6S (`+F4 Sniper Tinh Hoa`) — 2 Năm IS** | `67` | `+286.6%` (`3.01`) | `+278.5%` (`2.92`) | **`+270.4%` (`2.83`)** | `+262.3%` (`2.75`) | `+254.2%` (`2.67`) | **`353.8 bps` (`3.54%`)** |
| **👑 Mốc 6B (`+F4 Toàn Diện`) — OOS `2026`** | `25` | `+132.1%` (`5.06`) | `+129.5%` (`4.91`) | **`+127.0%` (`4.76`)** | `+124.4%` (`4.62`) | `+121.8%` (`4.48`) | **`515.9 bps` (`5.16%`)** |
| **👑 Mốc 6A (`+F4 Sniper`) — OOS `2026`** | `15` | `+89.3%` (`4.93`) | `+87.6%` (`4.80`) | **`+86.0%` (`4.68`)** | `+84.4%` (`4.57`) | `+82.8%` (`4.45`) | **`551.0 bps` (`5.51%`)** |
| **👑 Mốc 6S (`+F4 Sniper Tinh Hoa`) — OOS `2026`** | `9` | `+47.2%` (`4.25`) | `+46.2%` (`4.14`) | **`+45.2%` (`4.03`)** | `+44.2%` (`3.93`) | `+43.2%` (`3.82`) | **`472.3 bps` (`4.72%`)** |

---

## 📉 PHẦN 5: PHÂN PHỐI KẾT QUẢ LỆNH, RỦI RO ĐUÔI & ĐỘ CHỒNG LẤP DANH MỤC (DISTRIBUTION, TAIL RISK & CONCURRENCY)

*Lưu ý quan trọng về cách tính `Max Drawdown`: Mọi con số `MaxDD` trong hệ thống đều là **Chronological Portfolio-Ordered Drawdown** (sắp xếp toàn bộ lệnh của cả 14 đồng coin theo đúng thứ tự thời gian thực `entry_time` rồi tính đường cong vốn cộng dồn).*

| Cấu Hình & Giai Đoạn | Số Lệnh | Tỷ Lệ Kết Thúc Lệnh:<br/>`TP3 / TP2 / TP1_BE / SL / TimeExit` | `Avg Win` vs `Avg Loss` | `Payoff Ratio` (`W/L`) | `Median PnL` / Lệnh | `Best` / `Worst` Trade | Chuỗi Thua Dài Nhất (`Max Losing Streak`) | Giữ Lệnh TB (`Hold Hours`) | Số Lệnh Mở Đồng Thời (`Max / P95 / Avg`) | `Chrono MaxDD` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mốc 1 (`Pump>=50%`) — 6 Năm IS** | `1,467` | `9.8% / 14.7% / 13.5% / 39.4% / 22.7%` | `+8.13%` / `-8.41%` | `0.97` | `+1.12%` | `+38.3%` / `-43.5%` | `22 lệnh` (`-200.8%`) | `58.0h` | `16 / 9.0 / 3.94` | `815.8%` |
| **Mốc 2 (`+F1B PST`) — 6 Năm IS** | `642` | `12.5% / 13.9% / 12.6% / 33.3% / 27.7%` | `+8.13%` / `-8.88%` | `0.92` | `+2.19%` | `+38.3%` / `-36.8%` | `17 lệnh` (`-200.8%`) | `63.7h` | `15 / 10.0 / 3.20` | `339.9%` |
| **Mốc 3A (`+F1C Tinh Hoa`) — 6 Năm IS** | `390` | `10.5% / 14.6% / 15.4% / 30.8% / 28.7%` | `+7.75%` / `-8.34%` | `0.93` | `+2.99%` | `+35.4%` / `-36.8%` | `13 lệnh` (`-104.9%`) | `65.7h` | `12 / 5.0 / 2.07` | `152.9%` |
| **★ Mốc 4A (`+F2 Tinh Hoa`) — 6 Năm IS** | `299` | `9.7% / 16.7% / 16.4% / 29.1% / 28.1%` | `+7.84%` / `-8.57%` | `0.91` | `+3.95%` | `+35.4%` / `-36.8%` | `13 lệnh` (`-107.1%`) | `64.6h` | **`8 / 4.0 / 1.84`** | `147.6%` |
| **★ Mốc 5A (`+F3 Tinh Hoa`) — 6 Năm IS** | `169` | `9.5% / 18.3% / 17.8% / 23.7% / 30.8%` | `+7.74%` / `-9.40%` | `0.82` | `+4.23%` | `+35.4%` / `-36.8%` | **`9 lệnh`** (`-91.4%`) | `69.5h` | **`6 / 4.0 / 1.58`** | `113.9%` |
| **👑 Mốc 6B (`+F4 Toàn Diện`) — 6 Năm IS** | `443` | `8.1% / 18.1% / 14.5% / 39.7% / 19.6%` | `+8.82%` / `-7.87%` | **`1.12`** | `+2.23%` | `+53.0%` / `-38.2%` | `18 lệnh` (`-107.2%`) | `58.0h` | **`8 / 4.9 / 2.10`** | `227.0%` |
| **👑 Mốc 6A (`+F4 Sniper`) — 6 Năm IS** | `250` | `7.6% / 20.0% / 16.8% / 31.6% / 24.0%` | `+8.33%` / `-9.14%` | `0.91` | `+3.36%` | `+41.3%` / `-38.2%` | `11 lệnh` (`-86.0%`) | `64.6h` | **`6 / 4.0 / 1.77`** | `164.6%` |
| **👑 Mốc 6S (`+F4 Sniper Tinh Hoa`) — 6 Năm IS** | `169` | `8.3% / 18.3% / 18.3% / 27.2% / 27.8%` | `+8.43%` / `-9.37%` | `0.90` | `+3.96%` | `+41.3%` / `-38.2%` | **`9 lệnh`** (`-84.8%`) | `69.5h` | **`6 / 4.0 / 1.58`** | `120.8%` |
| **👑 Mốc 6B (`+F4 Toàn Diện`) — OOS `2026`** | `25` | `0.0% / 48.0% / 8.0% / 20.0% / 24.0%` | `+8.46%` / `-5.63%` | **`1.50`** | `+7.14%` | `+22.2%` / `-8.4%` | **`2 lệnh`** (`-12.1%`) | `78.7h` | **`3 / 3.0 / 1.60`** | **`12.1%`** |
| **👑 Mốc 6A (`+F4 Sniper`) — OOS `2026`** | `15` | `0.0% / 60.0% / 6.7% / 20.0% / 13.3%` | `+9.11%` / `-7.78%` | **`1.17`** | `+8.31%` | `+16.5%` / `-8.4%` | **`1 lệnh`** (`-8.4%`) | `81.1h` | **`3 / 3.0 / 1.47`** | **`8.4%`** |
| **👑 Mốc 6S (`+F4 Sniper Tinh Hoa`) — OOS `2026`** | `9` | `0.0% / 55.6% / 11.1% / 22.2% / 11.1%` | `+8.59%` / `-7.46%` | **`1.15`** | `+7.50%` | `+16.5%` / `-7.6%` | **`1 lệnh`** (`-7.6%`) | `76.4h` | **`2 / 1.6 / 1.11`** | **`7.6%`** |

---

## 🪙 PHẦN 6: KIỂM ĐỊNH PHÂN RÃ CHÉO THEO KHUNG THỜI GIAN (`H4` VS `D1`) & THEO 14 ĐỒNG COIN

### 6.1. Đối Chiếu Hiệu Suất Giữa Khung `H4` (Sóng Trung Hạn) & Khung `D1` (Sóng Vĩ Mô)

| Cấu Hình & Giai Đoạn | Khung `H4` — Số Lệnh | Khung `H4` — Win Rate | Khung `H4` — Tổng Lãi (`PF`) | Khung `H4` — `BE Fee` | Khung `D1` — Số Lệnh | Khung `D1` — Win Rate | Khung `D1` — Tổng Lãi (`PF`) | Khung `D1` — `BE Fee` |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mốc 1 (`Pump>=50%`) — 6 Năm IS (20–25)** | `409` | `50.86%` | `-243.2%` (`PF 0.87`) | `-49.5 bps` | `1,058` | `51.80%` | `+409.8%` (`PF 1.10`) | `+48.7 bps` |
| **★ Mốc 4A (`F2 Tinh Hoa`) — 6 Năm IS (20–25)** | `85` | **`62.35%`** | **`+142.7%` (`PF 1.46`)** | **`+177.9 bps`** | `214` | **`61.21%`** | **`+314.1%` (`PF 1.47`)** | **`+156.8 bps`** |
| **👑 Mốc 6B (`F4 Toàn Diện`) — 6 Năm IS (20–25)** | `123` | `52.85%` | `+95.8%` (`PF 1.18`) | `+90.7 bps` | `320` | `54.69%` | **`+422.2%` (`PF 1.39`)** | **`+142.3 bps`** |
| **👑 Mốc 6B (`F4 Toàn Diện`) — 2 Năm IS (24–25)** | `33` | **`63.64%`** | **`+102.9%` (`PF 2.02`)** | **`+286.2 bps`** | `115` | **`66.96%`** | **`+373.1%` (`PF 2.63`)** | **`+321.2 bps`** |
| **👑 Mốc 6A (`F4 Sniper`) — 2 Năm IS (24–25)** | `15` | **`73.33%`** | **`+59.4%` (`PF 2.15`)** | **`+316.1 bps`** | `75` | **`74.67%`** | **`+264.6%` (`PF 2.79`)** | **`+338.3 bps`** |
| **👑 Mốc 6B (`F4 Toàn Diện`) — OOS `2026`** | `6` | **`66.67%`** | **`+12.8%` (`PF 2.91`)** | **`+226.9 bps`** | `19` | **`78.95%`** | **`+114.1%` (`PF 5.22`)** | **`+608.3 bps`** |
| **👑 Mốc 6A (`F4 Sniper`) — OOS `2026`** | `2` | **`100.0%`** | **`+15.3%` (`PF 99.0`)** | **`+596.8 bps`** | `13` | **`76.92%`** | **`+70.7%` (`PF 4.03`)** | **`+542.0 bps`** |

### 6.2. Phân Rã Theo Từng Đồng Coin Trong Rổ 14 Tài Sản (Kiểm Tra Rủi Ro Tập Trung / Concentration Risk)

| Đồng Coin (`Symbol`) | **Mốc 0 Baseline (24–25)**<br/>Số Lệnh \| Tổng Lãi (`PF`) | **★ Mốc 4A Tinh Hoa (6 Năm 20–25)**<br/>Số Lệnh \| WR \| Tổng Lãi (`PF`) | **👑 Mốc 6B Toàn Diện (2 Năm 24–25)**<br/>Số Lệnh \| WR \| Tổng Lãi (`PF`) | **👑 Mốc 6B Toàn Diện (OOS `2026`)**<br/>Số Lệnh \| WR \| Tổng Lãi (`PF`) |
| :--- | :---: | :---: | :---: | :---: |
| `1000BONKUSDT` | `153` \| `-2.7%` (`0.99`) | `16` \| `81.3%` \| **`+99.5%` (`4.16`)** | `19` \| `73.7%` \| **`+124.5%` (`3.75`)** | `2` \| `100.0%` \| **`+16.2%` (`99.0`)** |
| `1000PEPEUSDT` | `180` \| `-29.3%` (`0.95`) | `27` \| `66.7%` \| **`+44.7%` (`1.60`)** | `32` \| `56.3%` \| **`+74.9%` (`1.86`)** | `8` \| `75.0%` \| **`+56.5%` (`9.40`)** |
| `1000SHIBUSDT` | `204` \| `-20.7%` (`0.96`) | `25` \| `72.0%` \| **`+115.0%` (`2.41`)** | `10` \| `90.0%` \| **`+72.4%` (`5.29`)** | `0` \| — \| `0.0%` |
| `ACEUSDT` | `168` \| `+106.0%` (`1.26`) | `14` \| `78.6%` \| **`+63.8%` (`3.94`)** | `14` \| `78.6%` \| **`+67.8%` (`4.79`)** | `2` \| `100.0%` \| **`+26.2%` (`99.0`)** |
| `1INCHUSDT` | `308` \| `+35.1%` (`1.05`) | `30` \| `60.0%` \| **`+64.6%` (`1.70`)** | `13` \| `61.5%` \| **`+44.1%` (`2.75`)** | `0` \| — \| `0.0%` |
| `SOLUSDT` | `508` \| `-240.3%` (`0.84`) | `37` \| `54.1%` \| `-3.5%` (`0.98`) | `12` \| `66.7%` \| **`+31.8%` (`3.26`)** | `2` \| `100.0%` \| **`+3.8%` (`99.0`)** |
| `AKTUSDT` | `172` \| `+81.7%` (`1.18`) | `4` \| `50.0%` \| **`+4.3%` (`1.26`)** | `6` \| `66.7%` \| **`+22.8%` (`2.85`)** | `5` \| `40.0%` \| **`+9.2%` (`1.47`)** |
| `ADAUSDT` | `512` \| `-65.8%` (`0.96`) | `33` \| `63.6%` \| **`+42.3%` (`1.47`)** | `14` \| `50.0%` \| **`+20.0%` (`1.42`)** | `0` \| — \| `0.0%` |
| `LTCUSDT` | `475` \| `-48.9%` (`0.96`) | `16` \| `75.0%` \| **`+47.5%` (`3.10`)** | `3` \| `100.0%` \| **`+13.6%` (`99.0`)** | `0` \| — \| `0.0%` |
| `ETHUSDT` | `477` \| `-171.7%` (`0.87`) | `22` \| `45.5%` \| `-11.0%` (`0.88`) | `6` \| `66.7%` \| **`+11.0%` (`2.68`)** | `0` \| — \| `0.0%` |
| `AAVEUSDT` | `514` \| `-95.4%` (`0.94`) | `30` \| `56.7%` \| `-13.4%` (`0.91`) | `8` \| `87.5%` \| **`+6.3%` (`1.23`)** | `3` \| `66.7%` \| **`+2.5%` (`1.35`)** |
| `BNBUSDT` | `327` \| `-87.9%` (`0.88`) | `23` \| `47.8%` \| **`+25.9%` (`1.34`)** | `4` \| `25.0%` \| **`+2.3%` (`1.70`)** | `0` \| — \| `0.0%` |
| `BCHUSDT` | `462` \| `-56.3%` (`0.95`) | `16` \| `62.5%` \| `-10.9%` (`0.82`) | `7` \| `57.1%` \| `-15.6%` (`0.43`) | `3` \| `100.0%` \| **`+12.6%` (`99.0`)** |
| `BTCUSDT` | `246` \| `-102.7%` (`0.83`) | `6` \| `50.0%` \| `-12.1%` (`0.51`) | `0` (Tự động đứng ngoài) | `0` (Tự động đứng ngoài) |
| **Tỷ Lệ Mã Có Lãi (`Breadth`)** | **2 / 14 mã (`14.3%`)** | **9 / 14 mã (`64.3%`)** | **12 / 13 mã active (`92.3%`)** | **7 / 7 mã active (`100.0%`)** |
| **Tỷ Trọng Mã Lãi Lớn Nhất (`Top-1 Share`)** | — | `22.7%` (`1000SHIBUSDT`) | `25.3%` (`1000BONKUSDT`) | `44.5%` (`1000PEPEUSDT`) |

**Nhận định kiểm toán về độ phủ danh mục (Cross-Sectional Breadth):**
- Ở `Mốc 0 (Baseline)`, chỉ có `2/14` mã có lãi (`14.3%`), còn lại `12/14` mã đều lỗ nặng.
- Sau khi khóa 4 Nhân tố (`Mốc 6B` giai đoạn `2024–2025`), **12/13 đồng coin có tín hiệu đều sinh lời dương (`92.3%`)**, đồng coin đóng góp lớn nhất (`1000BONKUSDT`) chỉ chiếm `25.3%` tổng lợi nhuận dương — chứng minh Alpha mang tính cấu trúc rộng khắp toàn thị trường chứ không bị phụ thuộc vào một mã cá biệt.
- Trong `OOS 2026`, **7/7 đồng coin có tín hiệu (`100.0%`) đều có lãi ròng dương**, trong khi các đồng Major như `BTCUSDT`, `ETHUSDT`, `BNBUSDT` không tạo sóng bơm FOMO rỗng ruột nên bộ lọc tự động đứng ngoài 100%, giúp tránh toàn bộ các nhịp Short ngược xu hướng tổ chức.
