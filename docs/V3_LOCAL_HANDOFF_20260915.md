# V3 — bàn giao local

## Những gì thay đổi

- Giữ điều kiện chọn Champion và cơ chế xác nhận hiện tại.
- Nhận diện mẫu hình và giai đoạn bằng các đặc trưng giá, khối lượng, funding,
  OI đang có. Mẫu hình xa hoặc thiếu dữ liệu được ghi chưa xác định, kèm mẫu gần
  nhất và các điểm khác biệt. Độ giống mẫu không phải xác suất thắng.
- Bộ lọc chất lượng cao trên giao diện chỉ nhận chứng nhận rõ từ backend;
  chất lượng dữ liệu cao không đồng nghĩa hiệu quả tín hiệu cao.
- TP/Stop vẫn theo giá trung bình các Entry đã khớp. Sau Stop, thêm phép theo
  dõi giá với giá trung bình đóng băng, không khớp thêm Entry, giữ hạn 48h ban đầu.
- Telegram lưu trạng thái gửi và ID tin gốc, cập nhật Entry/TP/Stop/hết hạn và
  kết quả sau Stop trong cùng luồng. Bộ lọc giao diện không chặn tin hợp lệ.

## Nghiên cứu local

Từ thư mục gốc dự án, chạy:

```powershell
.venv/Scripts/python.exe -m dao_vang.cli.main experiment research-v3-patterns
```

Lệnh đọc dữ liệu lịch sử, tạo `artifacts/v3_pattern_research_report.json` và
`artifacts/v3_pattern_model.json`. Scanner dùng thiết lập
`research_v3_pattern_artifact` (mặc định là đường dẫn artifact nói trên).
Artifact thiếu/hỏng làm phân loại trở về chưa xác định; không thay Champion.

## Cách đọc bằng chứng

Bảng lịch sử `distribution_v3_training.duckdb` có 4.890 dòng nhưng nhãn đang là
Entry đầu, chưa phải kết quả compact theo giá trung bình. Báo cáo mới phải ghi
rõ giới hạn này. Nếu thiếu điểm tham chiếu có nguồn xác định, phép kiểm chứng
đủ 5 điều kiện không được coi là đã thực hiện.

Kết quả cũ đã dùng để chọn nhiều biến thể là dữ liệu tái sử dụng. Không có tuyên
bố xác suất V3 đã tăng từ lần triển khai này. Nhãn chất lượng cao vẫn chưa xác
nhận cho đến khi có đủ bằng chứng đúng chuẩn. Báo cáo audit chi tiết nằm trong
`V3_EVIDENCE_AUDIT_20260915.md` và `V3_TRAINING_LABEL_COMPATIBILITY_20260915.md`.

Phép theo dõi giá sau Stop không phải lợi nhuận của một lệnh đã đóng. Trạng thái
giá chạm TP/Stop cũng không chứng minh lợi nhuận sau chi phí nếu funding chưa
được kiểm chứng; API giữ riêng eligibility và lý do loại khỏi thống kê.

Đối chiếu hồi cứu đúng 23 tín hiệu cũ đã chạy bằng
`scripts/replay_v3_champion_audit.py`: 6 đường giá đủ 48h, gồm 4 TP và 2 timeout;
17 tín hiệu thiếu nến bị loại rõ ràng. Cả 6 chưa đủ xác nhận bao phủ funding,
nên không có kết quả đủ chuẩn bằng chứng lợi nhuận. Đây không phải mẫu độc lập
để tuyên bố cải thiện. Xem `V3_COMPACT_REPLAY_20260915.md` để kiểm tra từng dòng.

## Phạm vi vận hành

Thay đổi được thực hiện và kiểm thử trên local. Chưa deploy GCP, chưa gửi thử
Telegram thật. Khi vận hành, dùng cấu hình kênh nghiên cứu V3 hiện có. Bộ mẫu
hình và báo cáo là artifact cần đi cùng cấu hình nếu triển khai sau này.

## Kiểm thử

Vòng tổng hợp tại thời điểm bàn giao: 94 kiểm thử backend/Telegram đạt; build
frontend đạt; 2 kiểm thử V3 trong trình duyệt đạt, gồm bố cục điện thoại, bộ lọc
chất lượng và phân biệt kết quả sau Stop. Các kiểm thử dùng transport giả,
không gửi tin ra ngoài. Có một cảnh báo tương thích Pandas từ script cũ.
