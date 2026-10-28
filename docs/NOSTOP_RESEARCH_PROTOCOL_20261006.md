# Giao thức nghiên cứu chiến lược không stop-loss — 06/10/2026

Mục tiêu: tìm ứng viên có **CAGR / MaxDD > 1** (càng cao càng tốt), **không dùng stop-loss**, theo Train 2020–2023 → Validation 2024–2025 → Test 2026. Mã nguồn: `src/dao_vang/nostop/`. Kết quả: `artifacts/nostop/`.

## Định nghĩa "không stop-loss"

Cấm mọi lệnh thoát/giảm vị thế phụ thuộc vào **PnL của chính vị thế, giá vào lệnh, mức sụt giảm của tài khoản hoặc mức ký quỹ**: stop cố định, trailing stop, break-even stop, giới hạn lỗ, circuit breaker theo drawdown, giảm tỷ trọng sau khi lỗ.

Được phép:
- Thoát theo thời gian (giữ N ngày), chốt lời (TP), cân bằng lại theo tín hiệu thị trường (xếp hạng, bộ lọc chế độ BTC) không tham chiếu giá vào lệnh.
- Định cỡ theo biến động **thị trường** (back-cast từ lợi suất quá khứ của chính danh mục giả định, không dùng PnL thực của chiến lược).
- Đòn bẩy tổng ≤ 3×; mỗi chiến lược tự đặt vol target và đòn bẩy tối đa 2×.

Duy nhất một sự kiện cưỡng bức: **thanh lý Cross** (ký quỹ duy trì 2% danh nghĩa, kiểm tra tại cực trị bất lợi của nến: low cho long, high cho short, mọi tài sản đồng thời). Thanh lý = tài khoản về 0, kết thúc mô phỏng (ruined).

## Dữ liệu

- 116 hợp đồng perpetual USDT (data lake dùng chung). 2020–2025: nến 4h; 2026-01 → 2026-08-31: ghép từ nến 5m. Funding 8h thực.
- **Thiên lệch sống sót**: danh sách coin là những coin còn tồn tại cuối 2025, không có coin đã bị hủy niêm yết. Số coin giao dịch được tăng từ ~30 (2020) lên 116 (2024+). Tập vũ trụ theo thời điểm: ≥90 ngày lịch sử + top K thanh khoản 30 ngày.
- Test 2026 chỉ có 8 tháng (CAGR quy năm từ 8 tháng rất nhiễu); báo cả tổng lợi nhuận.

## Thực thi và chi phí

- Quyết định tại **đóng nến t** (chỉ dữ liệu ≤ t); khớp tại **mở nến t+1**; lợi nhuận open→open.
- Chi phí một chiều = phí taker 5 bps + trượt giá theo hạng thanh khoản (3 bps top10, 8 bps top30, 15 bps còn lại). Stress = ×2.
- Funding trừ/cộng tại các mốc 00/08/16 UTC trên vị thế đang giữ (long trả khi funding dương, short nhận).
- Mỗi split bắt đầu lại từ vốn 1.0, không mang vị thế.

## Chỉ số

- CAGR / MaxDD (MaxDD trên đường vốn 4h). Cột phụ `calmar_intra`: MaxDD tính cả cực trị trong nến (bảo thủ, giả định mọi tài sản đồng thời).
- Sharpe, năm dương, tháng thắng, vòng quay, phí, funding.

## Cổng niêm phong (mã `registry.py`)

1. Phát triển và tinh chỉnh **chỉ trên Train**. Lưới tham số, làm mượt "cao nguyên": điểm chọn phải có Calmar trung bình cùng các láng giềng ±1 bước > 0,8.
2. **Freeze**: ghi spec chính xác vào `rounds/<round>/frozen.json` + SHA-256, không ghi đè.
3. **Validation** chỉ chạy được cho spec đã freeze (mã chặn bằng `authorize`). Chọn các ứng viên có Calmar validation > 1, không thanh lý.
4. **Lock**: niêm phong danh sách ứng viên + hash các round vào `candidate_lock.json` trước khi chạm Test.
5. **Test 2026** chỉ chạy cho spec đã lock; mọi lần truy cập val/test ghi vào `access_log.jsonl`.

## Vòng cải tiến và điều kiện dừng

Mỗi vòng: ý tưởng mới → tinh chỉnh trên Train → freeze → validation. Chỉ số cải tiến của vòng = trung bình Calmar validation của top 20 ứng viên **đã freeze trong chính vòng đó** (xếp theo validation). Phiên bản đầu của giao thức ghi "top 20 đã freeze" mà không nói rõ phạm vi; tôi chọn phạm vi theo vòng vì chỉ số cộng dồn chỉ có thể tăng (cực đại của tập ngày càng lớn). **Dừng khi một vòng không nâng chỉ số này thêm quá 5% so với vòng tốt nhất trước và đã cạn ý tưởng**; sau đó lock và mở Test một lần. Lịch sử: R2 1,59 → R3 2,65 → R4 2,41 (−9%) → R5 2,94 (+11% so với R3) → R6 2,15 (−27%): dừng.

Ghi chú kỹ thuật: tham số `rebal < 1` trong họ `xs_*`/`composite` (gặp ở nhóm `taker` rebal 0,5 của R2, không ứng viên nào được khóa) được `int()` về 0 và chạy mỗi nến 4h, không phải 12h. Để kiểm soát theo nến dùng `rebal_bars`.

**Tuyên bố tuân thủ (đã sửa):** quy trình *không* được tuân thủ đầy đủ. Yêu cầu là phát triển và tune trên train, validation chỉ chọn ứng viên đã đóng băng. Thực tế R2 được thiết kế sau khi xem validation R1 (taker-flow và funding giữ được, động lượng giá thì không), R5 sau R3–R4, R6 sau R5 (nhân tố thanh khoản đảo dấu). Vì vậy validation 2024–2025 là dữ liệu bị dùng thích nghi, không còn độc lập; niêm phong SHA-256 chỉ khóa nội dung spec, không ngăn rò rỉ thích nghi. Toàn bộ kết quả của đợt này được xếp loại **thăm dò**. Test 2026 chỉ là một lần mở sau khi khóa, nhưng danh sách khóa được chọn bằng validation đã nhiễm, và kiểm tra 01/09→06/10 sau khi khóa (3/31 có lãi) cho thấy kết quả chưa đứng vững.

**Một vòng tuân thủ** phải: (1) chốt toàn bộ họ chiến lược, lưới tham số, quy tắc chọn và số lượng ứng viên trên train, không nhìn validation; (2) đóng băng; (3) mở validation đúng một lần để chọn; (4) khóa; (5) dùng dữ liệu chưa từng thấy (forward của shadow từ 06/10/2026 trở đi) làm kiểm định độc lập. Không gọi dữ liệu đã dùng là validation độc lập mới.

## Kiểm thử bắt buộc

`tests/unit/nostop/test_nostop.py`: mọi họ tín hiệu không nhìn trước (cắt tương lai khỏi panel, trọng số các dòng trước đó không đổi), khớp tại open kế tiếp theo tính tay, vị thế lỗ không bị engine đóng, squeeze 25× thanh lý tài khoản Cross, dấu funding.
