# So sánh biện pháp quản lý lỗ — 24/09/2026

Nghiên cứu theo yêu cầu người dùng, không thay đổi cấu hình tài khoản thật, không gửi lệnh và không tự triển khai phương án thắng lên live.

## Thiết kế trước khi xem kết quả

Dùng lại 165 sự kiện tín hiệu đã dựng cho kỳ 24/06–24/09/2026. Giữ cùng thứ tự ưu tiên tín hiệu, giá, quy tắc khối lượng, Cross x5, vốn ban đầu 500 USDT, không DCA. Ngoại trừ phương án nửa vốn, giữ 25 USDT danh nghĩa/lệnh. TP vẫn ATR14 nến giờ đã đóng × 2, mục tiêu ròng 0,50–5 USDT. Mỗi phương án chạy với tối đa 1, 3 và 5 vị thế.

12 phương án được định trước: gốc không cắt lỗ; giới hạn lỗ ròng 2,5 / 5 / 10 USDT; stop cách giá vào 2 ATR; thời gian giữ tối đa 24 / 72 giờ; đóng danh mục khi giảm từ đỉnh 10% / 20%; giảm danh nghĩa xuống 12,5 USDT không cắt lỗ; kết hợp lỗ 5 USDT với 72 giờ; kết hợp lỗ 2,5 USDT với 24 giờ. Giảm vốn vẫn phải đạt giá trị lệnh tối thiểu và TP ròng 0,50 USDT; không tự tăng khối lượng.

Mỗi cấu hình được chạy hai mức chi phí: phí 0,05%/chiều và trượt giá thị trường 0,20%; kiểm tra nhạy cảm với phí 0,10%/chiều và trượt giá 0,50%. TP LIMIT giả định khớp đúng giá mục tiêu khi giá đóng nến đi qua; chưa có hàng chờ hoặc khớp từng phần.

Ngưỡng cắt lỗ quan sát tại đóng nến Mark 5 phút. Lệnh mua đóng được mô phỏng tại giá mở nến giao dịch kế tiếp cộng trượt giá bất lợi, không tại mức stop. Vì vậy lỗ có thể vượt ngưỡng. Đây là đóng theo quan sát 5 phút, chưa phải mô phỏng stop-market đặt sẵn trên sàn hoặc bảo đảm tránh thanh lý trong nến. Stop ATR khóa ATR tại lúc vào. Thoát theo thời gian đóng cả lệnh lời và lỗ. Đóng danh mục sẽ khóa mở mới đến hết kỳ, không tự khôi phục. Ưu tiên kiểm tra ngưỡng ký quỹ duy trì trước xử lý thoát lệnh; nếu đã vi phạm thì dừng, không giả định cứu được tài khoản.

Chạy thêm ba cửa sổ không chồng lấn, mỗi cửa sổ bắt đầu lại từ 500 USDT và không mang vị thế sang: 24/06–24/07, 24/07–24/08, 24/08–08/09. Đây là kiểm tra độ nhạy theo giai đoạn, không phải ngoài mẫu hay walk-forward chọn tham số. Không cộng PnL của các cửa sổ để thay kết quả tài khoản liên tục.

## Đo lường và điều kiện diễn giải

Lưu tài sản gồm lãi/lỗ chưa chốt, giảm từ đỉnh, phí, funding, số vào/thoát, lý do thoát, lệnh mở cuối kỳ, thời gian giữ, tỷ lệ thắng và lệnh đóng lỗ nhất. Tài sản cuối kỳ chỉ có khi toàn bộ đường mô phỏng chạy xong; lỗi dữ liệu hoặc chạm ký quỹ duy trì làm kết quả chưa xác định. Lệnh còn mở được định giá, không loại bỏ để tăng tỷ lệ thắng. Tỷ lệ thắng chỉ tính lệnh đã đóng và phải đọc cùng tồn kho mở.

Các giới hạn từ nghiên cứu trước vẫn còn: model huấn luyện trùng một phần kỳ; bộ dựng tín hiệu không tái hiện trọn vẹn scanner; dữ liệu metrics đến 07/09; danh sách coin và bộ lọc sàn chưa theo từng thời điểm; ký quỹ duy trì giả định 1%; chưa có mô phỏng toàn bộ sổ lệnh. Vì vậy kết quả ba tháng chỉ là diễn biến tài khoản có điều kiện trên tập tín hiệu quan sát được; khoảng sau 07/09 không được coi là thực tế không có cơ hội mới.

Cùng một tập dữ liệu đã được dùng để nhận ra lỗi AKE và thiết kế phương án sửa. Chọn phương án tốt nhất ở đây mang thiên lệch lựa chọn; không được gọi là lợi thế đã xác nhận, không tự loại AKE để làm đẹp kết quả. Không tính khoảng tin cậy lợi thế ngoài mẫu từ tập dữ liệu này.

## Tái lập

Chạy `scripts/compare_account_risk.py`, sau đó `scripts/report_account_risk.py`. Đầu ra trong `artifacts/account_risk_comparison_20260924`: giao thức và checksum, bằng chứng giá/funding, từng đường tài sản/sổ lệnh, bảng so sánh CSV/JSON và dashboard HTML. Chỉ truy cập API thị trường công khai để bổ sung Mark Price/funding của các coin mới được mở khi có phương án thoát lệnh.

## Kết quả và diễn giải

Đã chạy 72 cấu hình toàn kỳ và 108 kiểm tra cửa sổ (180 lượt). Ba cấu hình gốc khớp kết quả trước về số vào/TP, lãi đóng, thời điểm và trạng thái vi phạm MMR. Giá giao dịch thiếu trong kho cho các coin tiếp tục được giữ tháng 9 đã được bổ sung từ Binance, không ghi đè kho gốc; không còn lỗi tải bổ sung trong lần chạy cuối. Việc bổ sung giá không khắc phục phần metrics/tín hiệu thiếu sau 07/09.

Ở giới hạn 5 vị thế, cả 10 phương án có thể tính đến cuối kỳ đều lỗ. Hai phương án không thể xác định tài sản cuối là gốc không cắt lỗ và giảm nửa vốn không cắt lỗ: đều vi phạm ký quỹ duy trì giả định. Cắt lỗ 2,5 USDT/lệnh cho kết quả ít lỗ nhất trong nhóm 5 vị thế: tài sản 478,92 USDT, lỗ 21,08 USDT, giảm từ đỉnh 9,33%, 107 lệnh đóng, không còn lệnh mở; với chi phí cao hơn lỗ 25,36 USDT. Chỉ một trong ba cửa sổ độc lập cho PnL dương.

Ở giới hạn 1 vị thế, cắt lỗ 2,5 USDT kết thúc 494,93 USDT, lỗ 5,07 USDT, giảm từ đỉnh 7,16%, 64 lệnh; chi phí cao hơn lỗ 11,13 USDT. Stop giúp kiểm soát thiệt hại nhưng chưa biến bộ chọn tín hiệu thành hệ thống có lợi nhuận.

Ngoại lệ dương là giảm nửa vốn ở giới hạn 1 vị thế: tài sản 502,53 USDT (stress 502,26), nhưng chỉ vào 6 lệnh và HOT còn mở 80,39 ngày. Có 152 sự kiện bị từ chối vì hết chỗ. Khi cho 3 hoặc 5 vị thế, cùng phương án lại vi phạm MMR giả định. Vì vậy không chọn ngoại lệ này làm bằng chứng giảm vốn đã giải quyết rủi ro.

Stop 2,5 USDT không phải bảo đảm lỗ tối đa 2,5: ở giới hạn 5 vị thế, một lần đóng RED thực hiện lỗ 6,49 USDT do diễn biến giá giữa các lần quan sát/giá giao dịch. Stop-market đặt trên sàn cần kiểm tra riêng bằng dữ liệu chi tiết hơn. Thoát theo thời gian 24 giờ hoặc 72 giờ đơn lẻ vẫn có mức giảm trên 20% ở giới hạn 5 vị thế, vì giá có thể tăng mạnh trước hạn đóng.

Ưu tiên nghiên cứu tiếp: kiểm tra lại bộ chọn/điểm vào trên dữ liệu độc lập; giữ phương án lỗ 2,5 USDT làm đối chứng kiểm soát thiệt hại, không coi là cấu hình đã đủ điều kiện live. Chưa thay đổi `configs/live.yaml`, chưa đưa stop vào bộ thực thi tài khoản thật.
