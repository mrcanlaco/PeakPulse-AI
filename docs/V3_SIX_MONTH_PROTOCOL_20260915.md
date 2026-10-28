# Giao thức khảo sát V3 sáu tháng

## Khoá phạm vi trước khi tính kết quả

- Thời gian tín hiệu UTC: [2026-02-01 00:00, 2026-08-01 00:00).
- Đây là sáu tháng lịch gần nhất có trong nguồn đặc trưng lịch sử đã lưu;
  không phải sáu tháng gần nhất tính đến ngày khảo sát 15/09/2026.
- Nguồn đặc trưng: `artifacts/backtest_results_pit.duckdb`, `bt_combined`.
  Kiểm kê trước khảo sát: 6.325.526 dòng, 193 mã, từ 01/12/2025 17:04:59.999 UTC
  đến 31/07/2026 00:04:59.999 UTC. Ngày cuối tháng 7 không đầy đủ.
- Bổ sung kiểm kê trước kết quả: `bt_combined` là view loại mọi dòng thiếu một
  trong 41 đặc trưng. Bảng gốc `bt_combined_all` có 12.994.965 dòng, 194 mã.
  Khảo sát điều kiện thị trường dùng bảng gốc, chỉ yêu cầu những trường cần cho
  phép so sánh và báo nhóm thiếu. View cũ được giữ để đối chiếu/join điểm OOS.
  Cả hai vẫn đã qua bộ lọc nhãn 24h cũ khi tạo dữ liệu; không phải toàn bộ thị
  trường hay mẫu không thiên lệch. Thay đổi nguồn này được khoá trước kết quả,
  không đổi kỳ sáu tháng đã chọn.
- Nguồn giá/phái sinh được cấu hình sẵn: kho `D:/Quant-trading/data_lake`,
  truy cập chỉ đọc. Đầu ra nghiên cứu nằm trong workspace, tách cấu hình live.
- Giữ ngày khoá kể cả khi có tháng thiếu dữ liệu hoặc kết quả xấu; báo riêng
  độ phủ thay vì dịch cửa sổ theo kết quả.

## Câu hỏi cần kiểm tra

1. Các điều kiện pump, đảo chiều, funding và điểm tham chiếu liên quan thế nào
   đến TP -20% theo giá trung bình trong 48h?
2. Mối liên hệ có ổn định theo tháng, mã, cường độ pump, độ sâu đảo chiều,
   động lượng, dấu funding và thay đổi OI không?
3. Sau Stop, bao nhiêu trường hợp còn đạt mục tiêu từ giá trung bình đóng băng
   trước khi hết hạn ban đầu? Mẫu số riêng là các lệnh đã Stop đủ dữ liệu.
4. Kết quả có phụ thuộc vào vài mã hoặc các nhóm rất ít mẫu không?

## Các lớp bằng chứng

- Giữ nguyên logic Champion, xác nhận, persistence và cooldown vận hành 24h.
- Báo thêm thống kê loại chồng lấn cửa sổ 48h; không gọi đó là cùng chính sách
  vận hành. So sánh trên cùng dòng/episode có dữ liệu hợp lệ.
- Với khảo sát điều kiện, lấy mẫu pump >=15% theo khoảng cách 24h/48h trước
  khi chia nhóm điều kiện để giữ cùng mẫu nền. Đây là lấy mẫu chẩn đoán,
  không phải số tín hiệu Champion vận hành: dòng chưa đạt điều kiện vẫn có
  thể chiếm mốc lấy mẫu. Chỉ các lane Timing OOS mô phỏng bộ chọn tín hiệu.
- Giá vào hồi cứu dùng giá đóng nến tín hiệu; không bảo đảm khớp được giá đó
  trong giao dịch thực. Nến tương lai chỉ bắt đầu sau thời điểm tín hiệu.
- Điểm dự báo chỉ dùng như bằng chứng OOS nếu có nguồn model, thời gian fit và
  hiệu chuẩn kết thúc trước tín hiệu. Không dùng model học cả kỳ để dự báo lại
  kỳ đó và gọi là kiểm chứng ngoài mẫu.
- Thiếu điểm hợp lệ thì báo khảo sát bốn điều kiện thị trường, cộng điều kiện
  persistence được ghi riêng. Không gọi đó là Champion đủ năm điều kiện.
- Điểm fold-OOS đã lưu có 9.023 dòng từ 01/03 đến 29/07/2026; tháng 2 thiếu.
  Join chính xác theo mã và thời gian UTC, không ghép điểm gần nhất hoặc điền
  điểm giữa các thời điểm. Các điểm này dự báo nhãn Entry đầu cũ.
- Tách chính sách khoá lịch sử (ngưỡng fold .25/.24/.21/.21), chính sách runtime
  hiện tại (.39 xác nhận, .29 sau xác nhận), và phép lọc điểm tức thời >=.39.
  Không gọi 139 tín hiệu khoá lịch sử là 139 tín hiệu theo công thức hiện tại.
  Từng model fold không có hash đã lưu; CSV và script chỉ cung cấp nguồn gốc
  theo quy trình. Các fold đã được dùng chọn chính sách, không phải holdout mới.
- Không suy diễn nhãn Entry đầu cũ thành kết quả compact. Replay bằng engine
  giá trung bình và phép đo sau Stop đã được kiểm thử.
- Dữ liệu funding có dòng không tự chứng minh bao phủ đầy đủ. Tách kết quả
  đường giá khỏi kết quả sau phí/funding đủ điều kiện thống kê.

## Giới hạn giải thích cơ chế

Funding dương là khoản Long trả cho Short; funding âm đảo chiều thanh toán.
Phân vị 80% của một chuỗi âm vẫn có thể là funding âm. Vì vậy phải kiểm tra
thêm dấu funding thực, không mặc định phân vị cao nghĩa là Long chịu cước cao.
Nguồn: https://www.binance.com/en/academy/articles/what-are-funding-rates-in-crypto-markets

OI giảm có thể phù hợp với đóng vị thế nhưng không tự chứng minh thanh lý cưỡng
bức. Tương quan đồng thời giữa pump/funding/đảo chiều chưa xác lập quan hệ nhân
quả. Không gán nhãn thao túng cho một coin chỉ từ các chỉ số này.

## Thống kê và giới hạn

Các ngưỡng/bin phải được định trước hoặc fit trên dữ liệu trước kỳ khảo sát.
Giữ nhóm thiếu/không rõ, công bố số mẫu và khoảng bất định; nhóm ít mẫu chỉ là
mô tả. Báo nhiều phép thử và mức tập trung theo mã; không chọn nhóm đẹp nhất
rồi coi là phát hiện độc lập. Kho mã đã lưu không bảo đảm bao gồm mọi mã từng
niêm yết hoặc đã huỷ niêm yết, nên phải ghi giới hạn thiên lệch sống sót.

Khoảng Wilson là tóm tắt nhị thức mang tính mô tả, không phải độ tin cậy đã
hiệu chỉnh cho mẫu phụ thuộc. Lấy mẫu 24h vẫn có thể chồng lấn đường giá 48h;
giãn 48h theo mã cũng không loại được phụ thuộc giữa các mã cùng chế độ thị
trường. Không diễn giải các dòng là những thử nghiệm độc lập hoàn toàn.

Toàn bộ nghiên cứu này là hồi cứu trên dữ liệu đã từng dùng trong nghiên cứu.
Không tự nâng model, đổi ngưỡng live, deploy hoặc gửi Telegram.
