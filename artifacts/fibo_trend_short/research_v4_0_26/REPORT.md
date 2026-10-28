# Kế hoạch xác nhận OOS cho Fibo Trend Short

**Chưa có bằng chứng để duyệt chiến lược. Kế hoạch OOS chưa được kích hoạt.** Backtest tiếp tục giới hạn đến hết 2025. Vòng này chỉ dùng các đường NAV đã lưu để ước lượng quy mô quan sát cần thiết; không tối ưu thêm tín hiệu.

## Quy mô mẫu theo giả định lợi thế

Bảng dưới giả định lợi thế tăng trưởng ròng 10%/năm, mức phát hiện mục tiêu 80% và xét đồng thời 12 kết luận (6 cấu hình × 2 mức chi phí). Đây là giả định để lập kế hoạch, không phải dự báo lợi nhuận. Khoảng số liệu phản ánh hai cửa sổ lịch sử 2020–2025 và 2024–2025, cùng độ dài khối 1, 4 và 8 tuần.

| Cấu hình | Tuần ước lượng ở bản chuẩn | Tuần ước lượng ở bản stress | Khả năng phát hiện sau 52 tuần ở bản chuẩn |
|---|---:|---:|---:|
| M6 khối lượng cố định | 5351–13646 | 7098–15953 | 0.8–1.1% |
| M6 khối lượng theo stop | 442–876 | 447–778 | 3.7–7.4% |
| Elite + Sniper | 169–418 | 188–417 | 7.9–24.0% |
| Sniper | 233–514 | 223–500 | 6.3–16.0% |
| Sniper tối đa 24 giờ | 142–282 | 144–285 | 12.6–29.9% |
| Sniper RR ≥ 1 tối đa 24 giờ | 128–228 | 113–206 | 16.5–33.8% |

Các con số dùng xấp xỉ chuẩn với phương sai suy ra từ khối lợi nhuận tuần lịch sử. Thay đổi chế độ thị trường, sai số ước lượng phương sai và phụ thuộc kéo dài hơn khối có thể làm chúng sai. Đường NAV lịch sử còn dùng quy ước đặt lại trạng thái mỗi năm. Không thể diễn giải số tuần này là thời gian chắc chắn chứng minh được alpha. Công thức lập kế hoạch theo [NIST](https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm); phân bổ sai số cho nhiều kết luận theo [Bonferroni](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm).

Bộ JSON giữ đầy đủ giả định lợi thế 5%, 10%, 15%/năm; các mốc 13, 26, 52, 104, 156 tuần; và trường hợp một hoặc 12 kết luận. Không chọn kết quả thuận lợi nhất để làm ngưỡng duyệt.

## Những gì đã đạt và còn thiếu

Đã đối chiếu 72 đường NAV với hồ sơ v4.0.25, giữ đúng hai mức phí từng lần khớp. Bản chuẩn dùng phí taker 2,5 bps cộng trượt giá 10 bps; bản stress dùng 5 bps cộng 50 bps, không giảm phí BNB.

Nhật ký giữ nguyên 24 mục nghiên cứu, 0 mục được xác nhận là alpha. Các thành phần quản trị rủi ro và các phép kiểm tra âm vẫn được lưu để tái sử dụng.

Funding rate lịch sử đã có; 7,330 kỳ của 128 mã còn cần giá mark thanh toán chính xác. Danh sách đầy đủ nằm trong EXACT_MARK_DATA_REQUEST.json của v4.0.21. Thay thế các giá xấp xỉ này chưa được chứng minh sẽ làm chiến lược có lợi thế.

## Phương án OOS chờ quyết định phạm vi

Dự thảo giữ nguyên sáu cấu hình và hai mức chi phí, mỗi cấu hình có tài khoản mô phỏng riêng. Phải chốt ngày bắt đầu, thời hạn và cách kết luận trước quan sát được chấm điểm; không chọn cấu hình thắng sau khi xem kết quả, không dừng sớm chỉ vì vừa có lãi. Cổng chọn chiến lược lịch sử vẫn là CASH.

Luồng dữ liệu mới còn cần lịch chọn coin PIT cập nhật, danh tính hợp đồng, báo giá thực thi và funding đúng thời điểm. Bản v4.0.25 xác nhận phát lại lịch sử với lịch coin đã lưu, chưa chứng nhận các bộ phận trực tuyến này.

Phạm vi OOS mới vẫn chờ lựa chọn của người dùng: quan sát paper phát sinh sau khi khóa mô hình, hoặc chỉ đánh giá walk-forward hồi cứu đến hết 2025. Lựa chọn thứ hai không tạo ra holdout chưa từng được xem. Chưa đọc dữ liệu thị trường sau 2025, chưa chạy paper trading và chưa đặt lệnh.
