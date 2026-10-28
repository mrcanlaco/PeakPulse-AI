# Phạm vi cải tiến: điều kiện kích thước lệnh

Tiếp nối backtest một năm, không ghi đè kết quả cũ và không giao dịch thật.

## Câu hỏi của bước này

Nếu đối chiếu quy mô từng lệnh mô phỏng với bộ lọc kích thước của sàn được lấy ngày 18/09/2026, có bao nhiêu lệnh vượt qua các kiểm tra đó, thất bại hoặc chưa đủ dữ liệu để đánh giá? Những nhánh nào phụ thuộc vào lệnh quá nhỏ hoặc quá lớn?

Đây là kiểm tra độ nhạy theo **quy định hiện tại**, không phải xác nhận quy định lịch sử hoặc khả năng khớp lệnh thực tế.

## Dữ liệu cố định

- Baseline: `artifacts/annual_profit_20260918/backtest_utf8/`, đủ 40 trial, 10.336 record thực hiện và 10.980 chân lệnh. Các record thuộc nhiều cấu hình có thể trùng tín hiệu, không phải 10.336 quan sát độc lập.
- SHA-256 `accounts.json`: `99040bcb8684beac10e4b7054e684023ea01c7a7510bd027be3d4e83a8904e65`.
- Quy định: public Binance USD-M `/fapi/v1/exchangeInfo`, lấy lúc `2026-09-18T02:16:27.6921243Z`, 897 symbols.
- SHA-256 snapshot: `1f15b404bd1dfcf8f95e7cd0b85018e34c187e2ff8c73763bc8d2a8650f343e0`.

## Cách diễn giải

Theo [tài liệu Binance](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/common-definition), giới hạn khối lượng và bước khối lượng phải được kiểm tra theo symbol. Dùng khối lượng dự kiến từ margin thực tế của từng chân và leverage trong trial đã khóa; làm tròn xuống theo bước hợp lệ, không lấy precision thay cho step size. Hedge cần cả hai chân vượt qua các kiểm tra.

Giá entry trong baseline chỉ là proxy để kiểm tra giá trị lệnh tối thiểu; chưa có mark giá lịch sử phù hợp để xác nhận đầy đủ. Missing symbol/filter không được tự coi là pass. Margin dưới 5/20 USD chỉ là thống kê giả định để phát hiện phần vốn nhỏ, không phải quy định chung của sàn.

Mỗi chân được xét như một lệnh market đơn. Vượt maxQty không chứng minh không thể chia nhỏ lệnh; việc chia lệnh, thời gian thực hiện và tác động giá chưa được mô phỏng.

“Vượt qua kiểm tra kích thước” không đồng nghĩa đặt được lệnh: chưa xác nhận trạng thái hợp đồng lịch sử, giới hạn vị thế/tier, sổ lệnh, mark price, số dư khả dụng, ADL hoặc các điều kiện sàn khác. Làm tròn giảm quy mô cũng không cho phép giữ nguyên P&L để gọi là lợi nhuận mới.

## Không làm trong bước này

Không loại record rồi cộng lại P&L, không tự tái sử dụng vốn, không đổi lịch cấp tranche, không nạp thêm, không đổi tín hiệu/threshold, không sửa baseline hoặc V3 đang chạy.

Hai phương án vốn được đưa ra để chốt cho lần replay tiếp theo: dừng và giữ phần dư, hoặc cất phần dư và dùng phần vốn tiếp theo trong 10.000 USD ban đầu. Điều kiện nghỉ tranche phải được định nghĩa riêng với việc một symbol cụ thể đòi hỏi lệnh tối thiểu lớn hơn; một lệnh không đủ điều kiện không chứng minh phần vốn không thể giao dịch bất kỳ mã nào khác.
