# V3: phạm vi đã chốt ngày 2026-09-15

## Mục tiêu và phạm vi

Nâng khả năng đạt mức giảm 20% từ giá trung bình của các Entry đã khớp trong
48 giờ tính từ Entry đầu. Giữ Champion đang chạy làm bản đối chiếu; không tự
thay ngưỡng hoặc model dựa trên kết quả chọn lọc từ lịch sử.

Triển khai local trước. Việc triển khai GCP được quyết định riêng sau review.
Không gửi tin Telegram thực trong quá trình kiểm thử.

## Hai kết quả phải tách biệt

- Giao dịch mô phỏng: TP trước Stop là thắng; Stop trước TP là thất bại.
- Theo dõi giá: khi Stop, đóng băng giá trung bình và tiếp tục quan sát đến hạn
  48h ban đầu, không thêm Entry. Giá đạt mục tiêu sau Stop không biến lệnh đã
  dừng lỗ thành lệnh thắng và không tạo lợi nhuận giả định.
- Dữ liệu thiếu và thứ tự intrabar không rõ phải được thể hiện; không dùng dữ
  liệu thiếu như một thất bại chắc chắn hay thành công chắc chắn.

## Phân loại và chất lượng

Khám phá mẫu hình từ dữ liệu đã có: giá, khối lượng, funding, OI và các đặc trưng
khả dụng. Fit mẫu hình trên tập phát triển; kiểm chứng theo thời gian trên tập
riêng, loại giao thoa cửa sổ nhãn 48h. Lịch sử đã dùng để chọn Champion là dữ
liệu nghiên cứu tái sử dụng, không phải bằng chứng forward mới.

Mỗi tín hiệu có loại mẫu hình, giai đoạn, trạng thái xác định/chưa xác định,
mẫu gần nhất và điểm chưa khớp khi có dữ liệu. Độ giống mẫu không phải xác suất
đạt TP. Diễn giải mô tả liên hệ quan sát, không khẳng định quan hệ nhân quả.

Nhãn chất lượng cao chỉ được cấp khi vượt tiêu chí bằng chứng được công bố
trong báo cáo/artifact. Không đủ bằng chứng thì giữ trạng thái chưa xác nhận.
Giao diện có bộ lọc chất lượng cao; bộ lọc không thay đổi điều kiện Champion.

## Telegram

Gửi mọi tín hiệu Champion đủ điều kiện theo luồng được cấu hình, kèm mẫu hình,
giai đoạn và chất lượng. Cập nhật trả lời vào tin gốc khi khớp thêm Entry,
TP/Stop/hết hạn và kết quả theo dõi giá sau Stop. Có lưu trạng thái chống lặp
khi scanner khởi động lại và xử lý gửi lỗi. Giữ quy tắc phân kênh nghiên cứu.

## Nghiệm thu

1. Kiểm thử TP trước Stop, Stop trước TP rồi đạt mục tiêu, timeout, thiếu nến,
   Stop/TP cùng nến, và việc không khớp thêm Entry sau Stop.
2. Kiểm thử dữ liệu phân loại thiếu, mẫu xa/không rõ, artifact không đủ bằng
   chứng, ranh giới tập dữ liệu và việc không dùng nhãn tương lai khi phân loại.
3. Kiểm thử Telegram bằng đối tượng giả: gửi ban đầu, trả lời đúng tin gốc,
   chống lặp, lỗi gửi và phân kênh.
4. Build giao diện và kiểm tra phân biệt hai kết quả, bộ lọc và nhãn chưa rõ.
5. Chạy nghiên cứu trên dữ liệu local khả dụng, công bố số mẫu và giới hạn;
   không tuyên bố cải thiện xác suất nếu chưa có bằng chứng.

## Bằng chứng lịch sử cần đối chiếu

`V3_VARIABLE_SEARCH_REPORT.md`: biến thể đứng đầu 31 biến thể có 18 tín hiệu,
precision 50%, EV bảo thủ +1.8%, chỉ 1/4 folds dương. Báo cáo đào sâu dùng
23 tín hiệu, precision 52.2%. Không gộp hai kết quả hoặc coi chúng là cùng một
thí nghiệm. Cần kiểm tra script nguồn, hợp đồng nhãn và các khoảng thời gian.
