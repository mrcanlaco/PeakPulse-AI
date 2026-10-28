# Tái kiểm tra sáu cấu hình Fibo Trend Short trên vũ trụ đã sửa

**Chưa cấp duyệt giao dịch thật.** Vòng này giữ nguyên sáu cấu hình đã có, chạy trên danh sách coin theo thời điểm và vòng đời hợp đồng đã sửa, không dò thêm ngưỡng tín hiệu. Chỉ dùng dữ liệu thị trường đến hết 2025.

Bản chuẩn: taker VIP6 2,5 bps và trượt giá 10 bps. Bản stress: taker Regular 5 bps và trượt giá 50 bps. Tất cả tính mỗi lần khớp, kể cả thoát từng phần, không giảm phí BNB; funding lịch sử có dấu tính theo lượng còn mở.

Biểu phí VIP6/Regular được dùng làm hai mức giả định cố định để so sánh toàn kỳ. Đây không phải bản phục dựng biểu phí hay cấp VIP thực tế của tài khoản ở từng năm lịch sử.

## NAV toàn kỳ 2020–2025

| Cấu hình | Chuẩn | MaxDD | Số lệnh | Stress | MaxDD | Số lệnh |
|---|---:|---:|---:|---:|---:|---:|
| M6 khối lượng cố định | -16.89% | 66.84% | 1255 | -91.35% | 94.42% | 1225 |
| M6 khối lượng theo stop | -1.61% | 28.72% | 1124 | -40.22% | 48.28% | 1149 |
| Elite + Sniper | +26.19% | 15.33% | 790 | -14.48% | 26.16% | 813 |
| Sniper | +14.54% | 18.05% | 940 | -23.05% | 31.54% | 969 |
| Sniper tối đa 24 giờ | +7.14% | 18.45% | 1263 | -35.57% | 37.92% | 1277 |
| Sniper RR ≥ 1 tối đa 24 giờ | +7.91% | 17.34% | 1025 | -30.13% | 34.68% | 1043 |

Mỗi năm đặt lại trạng thái và ngừng mở lệnh trong 5 ngày cuối năm, sau đó nối NAV theo vốn cuối năm trước. Quy ước này giữ nguyên để đối chiếu họ cấu hình cũ. Phép kiểm tra danh mục liên tục riêng đã được lưu ở v4.0.19. Các số là lợi nhuận trên NAV sau chi phí, không phải tổng lợi nhuận lệnh.

Cả sáu cấu hình đều âm ở bản stress toàn kỳ. Không có cấu hình nào có cận dưới CI 95% của lợi nhuận tuần toàn kỳ lớn hơn 0 ở bản chuẩn. Kết luận này không đồng nghĩa đã chứng minh lợi thế bằng 0; bằng chứng hiện có chưa đủ để xác nhận lợi thế.

## Giai đoạn 2024–2025 hồi cứu

| Cấu hình | Chuẩn | CI 95% trung bình tuần chuẩn | Stress | CI 95% trung bình tuần stress |
|---|---:|---:|---:|---:|
| M6 khối lượng cố định | +66.06% | [-0.1989%; +1.3555%] | -24.93% | [-1.0191%; +0.6569%] |
| M6 khối lượng theo stop | +19.73% | [-0.0383%; +0.3863%] | -3.04% | [-0.2411%; +0.1742%] |
| Elite + Sniper | +15.32% | [-0.0017%; +0.2788%] | +3.91% | [-0.1094%; +0.1791%] |
| Sniper | +18.80% | [+0.0032%; +0.3335%] | +4.76% | [-0.1200%; +0.2075%] |
| Sniper tối đa 24 giờ | +13.89% | [+0.0048%; +0.2416%] | -4.81% | [-0.1712%; +0.0688%] |
| Sniper RR ≥ 1 tối đa 24 giờ | +21.46% | [+0.0727%; +0.2992%] | +1.70% | [-0.0908%; +0.1205%] |

Bootstrap vòng theo khối 4 tuần, 10.000 mẫu, seed 412; lịch thứ Hai chung giữ cả tuần không giao dịch và các đoạn tuần ở biên. Các CI chưa điều chỉnh toàn bộ số lần thử. Dữ liệu 2024–2025 đã được xem trong lịch sử nghiên cứu; một CI dương trong bảng không tự trở thành bằng chứng OOS mới.

## Chọn cấu hình chỉ từ những năm trước

| Năm kiểm tra | Lựa chọn đã khóa |
|---|---|
| 2022 | CASH |
| 2023 | CASH |
| 2024 | CASH |
| 2025 | CASH |

Cổng nghiên cứu giữ nguyên: ít nhất hai năm và 60 lệnh trước đó, mọi năm trước dương ở bản chuẩn, tổng stress không âm, MaxDD từng năm không quá 15%, không thiếu nến thực thi. Lỗi thực thi được nhận trong tập huấn luyện cũng chặn xét duyệt. Không dùng chất lượng hoặc kết quả của năm kiểm tra để sửa ngược quyết định. CASH được mô hình hóa không lãi tiền mặt, không giao dịch và không phí.

| Chuỗi chọn 2022–2025 | NAV | MaxDD | Số lệnh |
|---|---:|---:|---:|
| standard_vip6 | +0.00% | 0.00% | 0 |
| stress_regular | +0.00% | 0.00% | 0 |

CASH không chứng minh alpha. Cổng này là quy tắc nghiên cứu đã đăng ký, không có nghĩa mọi chiến lược có một năm lỗ đều vô giá trị. Kết quả hồi cứu của một họ cấu hình đã phát triển trên dữ liệu cũ không thay thế quan sát OOS mới.

## Chất lượng thực thi và funding

Đã tính lại độc lập 17,757 đường thoát nguyên bản và 9,854 đường thoát 24 giờ. Có 1 đường thoát còn gắn lỗi chất lượng đầu vào; 0 lượt lệnh được nhận trong các kịch bản dính lỗi đó. Ứng viên được giữ nguyên, không loại theo thông tin tương lai. Nến không có giao dịch không đủ để xác nhận giá khớp giả định; cần dữ liệu báo giá/khớp chi tiết nếu lệnh đó được sử dụng.

Funding đã kiểm chứng cho 191 giai đoạn hợp đồng của 190 mã: 360,781 sự kiện, 1,751 phản hồi nguồn và 5 tệp lưu trữ. Tải bổ sung 30 giai đoạn; BNX trước và sau tái mở được kiểm tra riêng. Mọi khoảng giữ lệnh đều có funding liên tục; khoảng nghỉ giữa hợp đồng không được điền funding 0.

Trong các sổ lệnh có 47,300 khoản funding theo kịch bản dùng mark OPEN thay thế; 7,330 cặp mã–kỳ riêng biệt cần mark thanh toán chính xác được lưu trong `EXACT_MARK_DATA_REQUEST.json`. Funding rate là lịch sử thực; notional ở các kỳ proxy vẫn là xấp xỉ. Chưa mua dữ liệu.

## Kiểm chứng và kết luận

Đã kiểm tra độc lập 72 tổ hợp, 12,873 bản ghi giao dịch, 30,836 nhóm khớp và 87,493 khoản funding. Cả 12 tổ hợp Elite + Sniper khớp nguyên vẹn sổ lệnh và đường NAV v4.0.15. Bản sửa kiểm định chỉ chuẩn hóa kiểu chứa đường NAV giữa bộ nhớ và JSON; không thay bất kỳ giá trị hay luật giao dịch nào.

Có 9 kiểm thử đạt cho đầu vào, chọn chiến lược và lỗi so sánh JSON. Đã tái dựng 40 tổ hợp giai đoạn và 4 quyết định chọn theo thời gian. Báo cáo được kết xuất từ JSON đã kiểm chứng.

Nhật ký có 24 mục, gồm phép tái kiểm tra họ cấu hình này; không nâng mục nào thành alpha đã chứng minh. Toàn bộ cấu hình và kết quả âm được giữ lại. Chưa hoàn tất mục tiêu chiến lược có OOS được xác nhận và chưa có kết luận OK để triển khai hoặc cập nhật wiki như chiến lược đã được duyệt.
