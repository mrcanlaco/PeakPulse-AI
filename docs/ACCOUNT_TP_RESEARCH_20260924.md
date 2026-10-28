# Nghiên cứu TP — 24/09/2026

Đã chạy 11 chính sách TP (ATR 1/1,5/2/3; ATR 2 với trần 1 hoặc 2 USDT; mục tiêu ròng cố định 0,5/1/2/3/5 USDT). Mỗi chính sách thử giới hạn 5 hoặc không giới hạn vị thế, giữ/bỏ AKE, hai mức chi phí và hai giả định khớp. Tổng 176 lượt toàn kỳ cùng 264 lượt kiểm tra ba cửa sổ độc lập, bằng 440 lượt. Vốn 500 USDT, Cross x5, khoảng 25 USDT danh nghĩa, không DCA/SL/time exit, khóa mở mới khi giảm 20% được giữ nguyên.

Mục tiêu tiền khóa tại lúc vào; funding/chi phí chỉ điều chỉnh giá TP. Các chỉ số gồm tài sản có lãi/lỗ chưa chốt, drawdown, số lệnh, số vị thế mắc kẹt, thời gian giữ trung vị và lớn nhất, phí và funding. Mọi phương án được giữ trong bảng kết quả; không tự chọn tham số để giao dịch thật.

## Phát hiện về giả định khớp

Mô phỏng gốc chỉ khớp TP khi giá đóng nến 5 phút đi qua mục tiêu. Lệnh AKE ngày 15/07 có giá thấp của nến đầu 0,0003557, giá đóng 0,0003905, trong khi mức TP ròng 0,5 USDT khoảng 0,000362 sau làm tròn. Vì vậy cách dùng giá đóng nến có thể bỏ qua lần chạm TP nhỏ.

Phép thử bổ sung dùng giá thấp nhất trong nến, TP đã nằm trước cập nhật funding cuối nến. Không dùng funding tương lai để đổi TP ngược về đầu nến. Tuy nhiên vẫn tính funding đến cuối nến, chưa biết thời điểm khớp, độ trễ đặt TP sau khi vào, hàng chờ/khớp từng phần và thứ tự thanh lý. Đây chỉ là độ nhạy với giả định khớp, không phải kết quả đã xác minh, cũng không phải cận trên lợi nhuận. Giả định khớp sớm hơn có thể giải phóng chỗ và làm các giao dịch sau khác đi, nên không luôn tăng PnL.

## Kết quả chính

Nếu loại AKE và tối đa 5 vị thế, tài sản cuối với cách đóng nến / cách chạm giá:

| TP | Đóng nến | Chạm giá |
|---|---:|---:|
| Gốc ATR2, trần 5 USDT | 549,74 | 531,84 |
| Cố định 0,5 USDT | 452,09 | 425,63 |
| Cố định 2 USDT | 533,19 | 535,74 |

TP 2 USDT có kết quả ít thay đổi giữa hai giả định trong nhóm này nhưng drawdown vẫn khoảng 24,8%. Trong cửa sổ 24/07–24/08 bắt đầu lại từ 500 USDT, nó vẫn lỗ khoảng 27,8 USDT. Khi không giới hạn vị thế và bỏ AKE, TP 2 USDT kết thúc 535,20 / 537,73 USDT; vẫn drawdown 24,46% và còn 3 / 2 vị thế mở. Đây là ứng viên so sánh tiếp, không phải thông số tối ưu đã chứng minh.

Nếu giữ AKE, TP 0,5 USDT với giả định chạm giá mở 93 lệnh, 89 TP, còn 4 lệnh; tài sản 428,16 USDT, drawdown 21,85%, funding ròng -65,28 USDT. Cách dùng giá đóng nến vẫn chạm MMR giả định. Giả định khớp là yếu tố quyết định trong việc thoát AKE sớm; kể cả giả định thoát được, tài khoản chưa có lãi.

Nhiều phương án dừng khi funding tích lũy khiến mục tiêu TP tiền không còn biểu diễn bằng giá dương. Không được coi đường tài sản ngắn của chúng là an toàn hoặc có kết quả cuối kỳ. Các lượt vi phạm MMR cũng không có tài sản cuối xác minh được.

## Giới hạn và kiểm tra

Chỉ có tập tín hiệu dựng đến hết 07/09, phần sau quản lý lệnh cũ. Model huấn luyện trùng một phần kỳ, bộ dựng tín hiệu chưa tái hiện đầy đủ scanner; bỏ AKE là hậu nghiệm. Bộ lọc và danh sách coin chưa theo từng thời điểm; MMR giả định 1%. Các cửa sổ bắt đầu lại từ 500 USDT, không cộng kết quả và không gọi là kiểm định ngoài mẫu.

44 kiểm thử đạt; 8 cấu hình gốc được tái lập chính xác; các sổ tài khoản có kết quả cuối được đối soát với lãi đóng và tồn kho mở. Kiểm tra không mở trùng coin/không vượt số vị thế. Checksum xác nhận `configs/live.yaml` không thay đổi. Phần điều chỉnh TP chỉ nằm trong mô phỏng nghiên cứu, không sửa bộ thực thi live.

Đầu ra: `artifacts/account_tp_research_20260924` và thư mục `_touch` tương ứng. Dashboard trong thư mục đầu có bộ lọc coin, số vị thế, giả định khớp và chi phí, kèm CSV gộp. Chạy `scripts/research_account_tp.py --fill close`, `--fill bar_low`, rồi `scripts/report_account_tp.py` để tái lập.
