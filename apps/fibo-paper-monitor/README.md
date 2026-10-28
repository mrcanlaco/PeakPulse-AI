# PeakPulse — Paper OOS Monitor

Trang theo dõi cục bộ tại **http://127.0.0.1:8766**, chế độ tiết kiệm cập nhật mỗi 60 giây khi tab đang hiển thị. Tab ẩn ngừng thăm dò; khi mở lại cập nhật ngay. Nút Làm mới vẫn tải ngay theo yêu cầu. Khởi chạy bằng `start.ps1` trong thư mục này. Mở lại trang sau khi khởi chạy; script nhận diện phiên bản đang chạy để tránh tạo trùng.

Trang đọc `artifacts/fibo_trend_short/paper_oos_v1/PROTOCOL.json`, `STATUS.json`, danh mục có hiệu lực và `paper.sqlite3`. SQLite được mở bằng `mode=ro` và `query_only=ON`, cùng một transaction cho nhật ký và snapshot. Trang không nhập engine giao dịch, không gọi Binance, không sửa nguồn hoặc hồ sơ nghiên cứu. Dịch vụ chỉ lắng nghe trên localhost; không mở ra internet.

Hiển thị NAV và MaxDD của 12 tài khoản riêng, so sánh chuẩn/stress theo sáu chính sách, vị thế mở, tối đa 100 lệnh đóng gần nhất mỗi tài khoản, hoạt động H1, sự cố và danh mục coin. Phí, trượt giá và funding lấy từ giao thức/nhật ký. PnL và chi phí theo đơn vị NAV khởi tạo 100, không phải USD.

MaxDD được tính trên mọi điểm NAV đã ghi nhận, kể cả nhiều lần thay đổi trong cùng timestamp. Bộ nhớ biểu đồ giữ các điểm đầu/cuối/cực trị theo giờ trong 7 ngày gần nhất, theo ngày với phần cũ hơn; tối đa 1.200 điểm xuất ra mỗi tài khoản. Nhật ký gốc giữ đầy đủ. Không cộng NAV các tài khoản hoặc gọi lợi nhuận tạm thời là alpha. Không có kiểm định ý nghĩa thống kê giữa kỳ.

Mỗi lần thăm dò tự động chỉ đọc endpoint trạng thái nhỏ, không mở SQLite hoặc dựng lại biểu đồ. Trình duyệt chỉ lấy bảng số liệu và vẽ lại khi revision thay đổi; nút Làm mới có thể ép tải lại. Nếu mất kết nối, thời gian chờ tăng dần đến 5 phút. Dữ liệu HTTP dùng JSON gọn và gzip mức 1; các tệp giao diện có bản nén trong bộ nhớ và ETag để tải lại bằng phản hồi 304 khi không đổi. Không có tác vụ định kỳ trong dashboard khi không ai truy cập. Phần thu thập paper riêng không bị đổi lịch hoặc logic.

Giao thức được kiểm SHA256 mỗi lần đọc; nhật ký được kiểm chuỗi hash khi tải vào bộ nhớ và khi có bản ghi mới, snapshot được đối chiếu với bản ghi cuối cùng. Bộ nhớ đệm chỉ tồn tại trong tiến trình dashboard. Heartbeat quá 180 giây hoặc dữ liệu nến chậm quá 600 giây được cảnh báo; lỗi API làm rõ rằng các số liệu còn trên màn hình thuộc lần đọc trước. Màu xanh phản ánh tính mới của dữ liệu, không phải chứng nhận tiến trình bởi hệ điều hành. Việc kiểm tra PID thực tế thuộc lịch giám sát paper riêng.

Khởi chạy dashboard không tự khởi chạy, dừng hay khởi động lại paper runner. Sau khi máy khởi động lại, có thể chạy lại `start.ps1`; chưa cài dịch vụ tự khởi động. Mọi log của giao diện nằm trong `runtime/`, tách khỏi hồ sơ nghiên cứu đã khóa.
