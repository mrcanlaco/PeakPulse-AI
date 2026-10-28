# Ứng viên chiến lược không stop-loss — kết quả THĂM DÒ 06/10/2026

> **Nhãn: thăm dò, chưa nghiệm thu theo giao thức.** Các vòng sau được thiết kế sau khi xem kết quả validation của vòng trước (R2 sau R1, R5 sau R3–R4, R6 sau R5), nên validation 2024–2025 đã bị dùng thích nghi và **không phải dữ liệu độc lập**. Niêm phong SHA-256 chỉ chứng minh spec không bị sửa sau khi đóng băng, không ngăn rò rỉ thích nghi. Test 2026 được mở một lần sau khi khóa nhưng danh sách khóa được chọn bằng validation đã nhiễm. Một vòng tuân thủ cần chốt toàn bộ tìm kiếm và chọn lọc trên train trước khi mở validation, và dùng dữ liệu chưa từng thấy (forward từ shadow) làm kiểm định độc lập.

Giao thức: `docs/NOSTOP_RESEARCH_PROTOCOL_20261006.md`. Mã: `src/dao_vang/nostop/`. Dữ liệu và niêm phong: `artifacts/nostop/` (`rounds/*/frozen.json+sha256`, `candidate_lock.json+sha256`, `access_log.jsonl`).

## Kết luận

- Khóa **31 ứng viên** (đóng băng trước mỗi lần chạy validation, khóa trước test; xem nhãn thăm dò ở trên). Test 2026 (01/01–31/08, BTC giữ nguyên −10,6%): **28/31 có CAGR/MaxDD > 1**, **28/31 đạt > 1 ở cả ba giai đoạn**, 29/31 có lợi nhuận dương.
- Trễ khớp lệnh thêm 1 nến 4h: 28/31 còn > 1; thêm 3 nến (12h): 24/31. Chi phí gấp đôi: 24/31 còn > 1 trên test.
- Không ứng viên nào bị thanh lý ở bất kỳ giai đoạn nào. Không dùng stop-loss, trailing hay giảm vị thế theo PnL.
- Tương quan lợi suất ngày giữa các ứng viên trên test: trung vị 0.60. Thực chất là **một họ chiến lược** (long/short cân bằng tiền, dollar-neutral tại kỳ tái cân bằng và KHÔNG trung hòa beta; xếp hạng bằng taker-flow + funding + động lượng), không phải 31 alpha độc lập.

## Kiểm tra sau khi khóa: 01/09 → hiện tại (dữ liệu chưa có khi khóa)

Mô phỏng lại đúng 31 spec đã khóa bằng cùng mã nghiên cứu trên nến Binance sau 31/08 (36 ngày đến 2026-10-06 16:00Z, BTC +9.1%). Vị thế bắt đầu từ trống ngày 01/09, chi phí và funding như backtest.

- **Chỉ 4/31 có lợi nhuận dương**, trung vị **-6.4%**, MaxDD trung vị 12.4%, xấu nhất -18.1%, tốt nhất +4.1%.
- Đây là mẫu rất ngắn (5 tuần, một giai đoạn thị trường) nên không đủ để bác bỏ hay xác nhận, nhưng nó cho thấy Calmar test > 1 chưa phải bằng chứng lợi thế bền vững. Shadow đang chạy tiếp từ thời điểm này.

## Các vòng cải tiến (chỉ số: trung bình Calmar validation của top 20 đã đóng băng trong vòng)

| Vòng | Cấu hình train đã thử | Đóng băng | Val>1 | Val tốt nhất | Top20 trung bình | So với vòng tốt nhất trước |
|---|---:|---:|---:|---:|---:|---:|
| R1 | 2763 | 22 | 0 | 0.94 | 0.39 |  |
| R2 | 1152 | 65 | 17 | 4.78 | 1.59 | +313% |
| R3 | 3360 | 97 | 40 | 4.20 | 2.65 | +67% |
| R4 | 3456 | 48 | 35 | 3.93 | 2.40 | -9% |
| R5 | 972 | 58 | 31 | 4.16 | 2.94 | +11% |
| R6 | 576 | 64 | 38 | 3.26 | 2.15 | -27% |

R1 (động lượng giá, funding, taker riêng lẻ, trend BTC): 0/22 vượt 1 ở validation. R2 chuyển sang tổ hợp taker-flow + funding + động lượng (sau khi thấy kết quả R1). R3 thêm hysteresis và so sánh beta-neutral/ivol (bằng chứng train: hysteresis 0,1 và K=40 tốt hơn, beta-neutral và ivol kém). R4 tinh chỉnh quanh R3. R5 thử thêm nhân tố (thanh khoản, lottery, volume surge), long-only theo chế độ BTC, và định thời BTC/ETH theo taker-flow. R6 trung hòa theo 3 bậc thanh khoản. Dừng sau R6: R4 (−9%) và R6 (−27%) không vượt vòng tốt nhất trước (R5) quá 5%.

## Bảng xếp hạng (theo Calmar validation giảm dần; cột test là ngoài mẫu thật sự)

| # | ID | Cấu hình | Calmar train | Calmar val | CAGR/MaxDD val | Calmar test | CAGR test (8 th., quy năm) | MaxDD test | Lợi nhuận test | Calmar test ×2 chi phí | Trọng số lớn nhất/vị thế |
|---:|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `composite-2a753a0b` | taker7+fz7 · q0.1 K40 rebal3d buf0 | 3.82 | 4.78 | 81%/17% | 11.75 | 108% | 9.2% | +63% | 5.92 | 13% |
| 2 | `composite-1d172c74` | resid14+taker7+fund7 · q0.15 K40 rebal7d buf0.1 | 3.85 | 4.20 | 79%/19% | -0.30 | -11% | 37.4% | -8% | -0.46 | 10% |
| 3 | `composite-da9831d3` | mom30+taker7+fund7+liq30 · q0.15 K30 rebal2d buf0.1 | 2.57 | 4.16 | 75%/18% | 1.52 | 25% | 16.7% | +16% | 0.78 | 11% |
| 4 | `composite-1115ddbe` | mom14+taker7+fz7 · q0.15 K40 rebal3d buf0.1 | 1.53 | 4.10 | 64%/16% | 2.92 | 45% | 15.4% | +28% | 1.60 | 10% |
| 5 | `composite-e198bc11` | taker7+fund14 · q0.2 K50 rebal2d buf0.3 | 3.18 | 3.93 | 57%/14% | 5.11 | 72% | 14.1% | +43% | 4.08 | 8% |
| 6 | `composite-689d0027` | resid14+taker7+fund7 · q0.15 K40 rebal3d buf0.1 | 3.14 | 3.72 | 60%/16% | 6.40 | 99% | 15.4% | +58% | 4.70 | 10% |
| 7 | `composite-5a1d85e7` | mom30+taker7+fund7+small1 · q0.15 K30 rebal2d buf0.1 smooth2d | 2.99 | 3.72 | 66%/18% | 3.74 | 44% | 11.8% | +27% | 2.68 | 12% |
| 8 | `composite-79e70546` | taker7+fund14+vsurge14 · q0.2 K40 rebal3d buf0.3 smooth2d | 4.09 | 3.72 | 62%/17% | 4.37 | 80% | 18.3% | +48% | 3.21 | 9% |
| 9 | `composite-c6b82573` | taker7+fund14+liq30 · q0.15 K30 rebal2d buf0.1 | 2.17 | 3.61 | 63%/17% | 10.17 | 99% | 9.8% | +58% | 8.12 | 12% |
| 10 | `composite-7bb7e845` | mom14+taker3+fund7 · q0.15 K30 rebal3d buf0.1 smooth2d | 4.56 | 3.44 | 64%/19% | 7.15 | 116% | 16.2% | +67% | 5.30 | 11% |
| 11 | `composite-f576217c` | taker7+fund14+vsurge14 · q0.15 K40 rebal3d buf0.1 smooth2d | 3.96 | 3.41 | 67%/19% | 4.44 | 81% | 18.2% | +48% | 2.78 | 10% |
| 12 | `composite-3db01c74` | taker7+fund7 · q0.15 K40 rebal3d buf0.1 | 2.92 | 3.41 | 59%/17% | 12.45 | 138% | 11.1% | +78% | 8.91 | 10% |
| 13 | `composite-4ffd303e` | mom30+taker7+fz7 · q0.15 K40 rebal2d buf0.1 smooth2d | 2.97 | 3.39 | 55%/16% | 1.43 | 22% | 15.2% | +14% | 0.45 | 10% |
| 14 | `composite-d52034d2` | mom30+taker7+fz7+vsurge14 · q0.15 K45 rebal3d buf0.3 tier-neutral | 2.18 | 3.26 | 56%/17% | 4.96 | 57% | 11.5% | +35% | 2.35 | 8% |
| 15 | `composite-1734ab6b` | mom30+taker7+fund7+lot30 · q0.15 K45 rebal2d buf0.1 tier-neutral | 3.55 | 3.23 | 53%/17% | 5.01 | 91% | 18.2% | +54% | 2.85 | 8% |
| 16 | `composite-cb76e959` | taker7+fund14+small1 · q0.15 K30 rebal3d buf0.1 | 1.80 | 3.19 | 56%/18% | 4.74 | 52% | 11.0% | +32% | 3.54 | 12% |
| 17 | `composite-5ca075cb` | mom30+taker14+fund7 · q0.2 K40 rebal2d buf0.3 | 3.28 | 3.18 | 66%/21% | 3.05 | 46% | 15.2% | +29% | 2.30 | 9% |
| 18 | `composite-18e1d382` | mom30+taker7+fz7 · q0.15 K30 rebal3d buf0.1 | 4.44 | 2.95 | 45%/15% | 4.69 | 86% | 18.4% | +51% | 3.54 | 11% |
| 19 | `composite-15d5e2b1` | mom30+taker7+fund7+lvol30 · q0.15 K45 rebal3d buf0.1 tier-neutral | 2.33 | 2.92 | 59%/20% | 12.26 | 144% | 11.8% | +81% | 9.10 | 8% |
| 20 | `composite-83bcb747` | taker7+fund7+fz7 · q0.15 K40 rebal3d buf0.1 | 3.12 | 2.82 | 56%/20% | 10.86 | 136% | 12.5% | +77% | 7.63 | 11% |
| 21 | `composite-c4e0753f` | mom30+taker7+fund14 · q0.2 K30 rebal2d buf0.2 | 4.49 | 2.75 | 53%/19% | 3.99 | 50% | 12.4% | +31% | 2.92 | 10% |
| 22 | `composite-0033c4a3` | taker3+fund3 · q0.15 K40 rebal7d buf0.1 ivol | 2.13 | 2.75 | 53%/19% | 4.98 | 120% | 24.1% | +69% | 3.81 | 20% |
| 23 | `composite-bc1d5476` | mom30+taker7+fund7+lot30 · q0.2 K30 rebal2d buf0.1 | 3.52 | 2.71 | 50%/19% | 3.97 | 68% | 17.0% | +41% | 2.95 | 10% |
| 24 | `composite-bfca9858` | mom30+taker7+fund7+lvol30 · q0.2 K30 rebal2d buf0.1 smooth2d | 2.96 | 2.70 | 52%/19% | 4.33 | 55% | 12.6% | +34% | 3.34 | 10% |
| 25 | `composite-e0272cb2` | mom30+taker3+taker7+fund7+lvol30 · q0.25 K45 rebal3d buf0.1 tier-neutral | 2.41 | 2.70 | 50%/19% | 1.40 | 29% | 20.9% | +19% | 0.30 | 7% |
| 26 | `composite-f6d5a468` | mom30+taker7+fz7+vsurge14 · q0.25 K45 rebal3d buf0.3 tier-neutral | 2.32 | 2.67 | 42%/16% | 1.34 | 24% | 17.9% | +15% | 0.36 | 7% |
| 27 | `composite-fbe18bc9` | mom30+taker3+taker7+fund7 · q0.15 K40 rebal7d buf0.1 ivol | 4.96 | 2.64 | 51%/19% | 4.96 | 93% | 18.8% | +55% | 4.03 | 20% |
| 28 | `composite-77eeb077` | mom30+taker3+taker7+fund7 · q0.15 K40 rebal3d buf0.1 | 6.03 | 2.55 | 49%/19% | 7.00 | 108% | 15.4% | +63% | 4.73 | 10% |
| 29 | `composite-4906d74d` | mom30+taker7+fund7+vsurge14 · q0.2 K30 rebal3d buf0.3 | 4.44 | 2.53 | 60%/24% | 5.66 | 78% | 13.8% | +47% | 4.45 | 10% |
| 30 | `composite-182117e4` | mom30+taker7+fz7 · q0.2 K40 rebal3d buf0 | 3.06 | 2.52 | 44%/18% | 0.53 | 8% | 15.8% | +6% | -0.47 | 9% |
| 31 | `mkt_flow-b17ea3bc` | mkt_flow L3 z90 thr1.0 BTCETH long | 1.05 | 1.17 | 19%/16% | -0.38 | -8% | 19.7% | -5% | -0.57 | 33% |

### Xếp theo Calmar test (chỉ để tham khảo, không dùng để chọn lại)

`composite-3db01c74`, `composite-15d5e2b1`, `composite-2a753a0b`, `composite-83bcb747`, `composite-c6b82573`, `composite-7bb7e845`, `composite-77eeb077`, `composite-689d0027`, `composite-4906d74d`, `composite-e198bc11` là 10 ứng viên có Calmar test cao nhất; 3 ứng viên Calmar test ≤ 1: `composite-1d172c74` (-0.30), `composite-182117e4` (0.53), `mkt_flow-b17ea3bc` (-0.38).

## Giới hạn và rủi ro cần đọc trước khi tin các con số

1. **Chọn lọc nhiều lần**: 354 cấu hình đóng băng, hàng nghìn cấu hình train. Validation đã được dùng để chọn nên Calmar validation bị thổi phồng. Chỉ test 2026 là ngoài mẫu, và nó chỉ dài 8 tháng (một chế độ thị trường: BTC giảm). CAGR quy năm từ 8 tháng cực nhiễu, hãy đọc lợi nhuận tổng.
2. **Dò vết validation giữa các vòng**: ý tưởng vòng sau (R2, R5) được định hướng bởi kết quả validation vòng trước. Nhật ký truy cập: freeze: 6 lần/354 spec, lock: 1 lần/31 spec, test: 1 lần/31 spec, val: 6 lần/354 spec.
3. **Thiên lệch sống sót**: vũ trụ 116 coin còn tồn tại cuối 2025, không có coin đã hủy niêm yết. Ảnh hưởng chưa định lượng.
4. **Nhân tố thanh khoản đảo dấu giữa train và validation** (illiq/big tốt nhất ở train, tệ nhất ở validation; liq/small ngược lại). Ứng viên phụ thuộc nhân tố này mong manh theo chế độ. R6 trung hòa thanh khoản (tier-neutral) nhằm loại rủi ro đó; nhóm này có Calmar validation thấp hơn, và chưa có bằng chứng độc lập rằng nó miễn nhiễm với đảo dấu.
5. **Vòng quay rất lớn** (50–140 lần vốn/năm): kết quả nhạy với chi phí thật, trượt giá và độ sâu sổ lệnh của coin cỡ vừa/nhỏ. Chi phí mô hình 8–20 bps/chiều theo bậc thanh khoản; mô phỏng không có hàng chờ, khớp từng phần hay tác động giá.
6. **Rủi ro đuôi không stop**: vị thế lớn nhất thường 7–13% vốn (20% ở vài ứng viên rebal 7 ngày, 33% ở `mkt_flow`). Một coin tăng 5–10× trong một nến trong khi giữ short sẽ gây lỗ khoảng 35–130% vốn tùy kích thước. Backtest 2020–2026 không thanh lý lần nào, nhưng 116 coin sống sót không bao gồm các trường hợp tệ nhất. Kiểm soát duy nhất là kích thước vị thế, bộ lọc thanh khoản và vol-target.
7. Dữ liệu `taker_buy_volume` ở 2026 ghép từ nến 5m; 2020–2025 lấy từ bảng 4h có sẵn. Chưa đối chiếu sàn từng nến.

## Ghi chú alpha để thử nghiệm

- **Taker-flow + funding (carry) xếp hạng chéo, long/short cân bằng tiền (không trung hòa beta)**: họ cho kết quả tốt nhất trong tìm kiếm, nhưng nguồn lợi nhuận chưa được kiểm chứng nhân quả. Ổn định qua trễ 4h và 12h. Chưa kiểm tra riêng đóng góp của từng nhân tố sau R5.
- **Động lượng giá thuần** (xs_mom, ts_mom_basket, trend BTC): Calmar train 1,4–4 nhưng validation < 1 (0/22 ở R1): suy giảm 2024–2025. Chỉ có ích khi kết hợp flow.
- **Funding một mình** (short funding cao): train ổn, validation 0,5–0,8. Là một thành phần của tổ hợp chứ không đủ độc lập.
- **Định thời BTC/ETH theo taker-flow tổng hợp** (`mkt_flow`): 1 cấu hình vượt validation (1,17) nhưng test −0,38. Chưa đạt.
- **Không đạt**: đảo chiều ngắn hạn, low-vol, lottery, vol-shock đơn lẻ, BTC-ratio mean reversion, size đơn lẻ, pump-fade short (có TP, không stop), dump-bounce, alt-short/BTC-long. Pump-fade/dump-bounce train Calmar ≤ 0,9 (không đủ cho gate).
- Hướng chưa thử: OI/long-short ratio (dữ liệu chỉ từ 2024 nên không train được), dữ liệu TradFi, tín hiệu sổ lệnh/L2, chọn vũ trụ theo thời điểm gồm coin bị hủy niêm yết.
