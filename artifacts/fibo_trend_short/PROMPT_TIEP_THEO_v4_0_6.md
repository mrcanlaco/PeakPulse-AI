Hãy tiếp tục từ hồ sơ PeakPulse AI Fibo Trend Short v4.0.6 trong C:/Rapid Coding/dao_vang/artifacts/fibo_trend_short.

Đọc VERSION_MANIFEST_v4_0_6.json, FINAL_METHOD_VERIFICATION_v4_0_6.json, METHOD_DELIVERY_v4_0_6.json, METHOD_PIT_FUNDING_v4_0_6.json và PHUONG_PHAP_FIBO_SHORT_v4_0_6.md trước khi sửa. Kiểm tra hash và tái lập các phép đối chiếu; không dùng tuyên bố 19 Closed của phiên bản trước để thay cho kiểm chứng.

Các lỗi fixed sizing, hệ số dưới 55 phải là 0,80x, phí trong thống kê, pivot 2/2, chốt sổ cuối IS và stop khi nhảy giá đã có bản sửa cùng kiểm thử. Giữ nguyên mọi artifact v4.0.6 trở về trước; tạo phiên bản kế tiếp cho mọi thay đổi.

Chưa duyệt live. Các việc cần đóng tiếp bằng bằng chứng:
1. Xác nhận rủi ro kinh tế: CI PIT đi qua 0, IS có thể âm khi phí tăng và drawdown lớn. Không tối ưu tiếp trên 2026 rồi gọi đó là OOS. Nếu thiết kế phương pháp mới, khóa protocol trước một tập forward mới và báo đầy đủ mọi biến thể thử.
2. Tích hợp một profile M6B có tên riêng vào scanner/paper, dùng đúng pivot 2/2, pump50, gate, PIT theo tháng và stop/TP/cooldown của hồ sơ. So sánh ứng viên và fill từng lệnh với bộ nghiên cứu. Scanner mặc định hiện khác cấu hình nghiên cứu.
3. Hoàn thiện sự kiện khớp lệnh paper: tick/lot/notional, spread/độ trễ, partial fills, phí theo từng fill, funding theo mark và thời điểm thực, margin/forced exit. Không gán kết quả khối lượng liên tục cho lệnh đã làm tròn. Không kích hoạt lệnh tiền thật.
4. Đối chiếu registry listing/delisting và thay đổi lịch funding, chỉ rõ vùng thiếu dữ liệu. Dùng dữ liệu funding đã có, không bỏ qua funding ở danh mục PIT.
5. Khóa hash policy trước paper mới; tối thiểu 90 ngày và 50 lệnh đóng để bắt đầu review vận hành, không coi ngưỡng này tự động chứng minh lợi nhuận. Báo cả ứng viên bị từ chối, lệnh đang mở, chi phí và drawdown.

Xuất JSON kết quả, ledger, báo cáo sinh từ JSON, kiểm thử âm, manifest và ma trận Closed/Partial/Open theo từng yêu cầu. Nêu rõ nghiệm thu kỹ thuật và nghiệm thu live là hai kết luận riêng. Nếu còn chưa duyệt, cung cấp ngay prompt sửa tiếp có bằng chứng cụ thể; không che kết quả âm hoặc đổi nhãn validation đã dùng thành holdout mới.
