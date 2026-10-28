# Đánh giá hệ thống Đảo Vàng — 23/09/2026

## Kết luận

**Điểm tổng thể: 5,9/10, làm tròn 6/10.** Đảo Vàng có nền tảng kiểm thử và kiểm soát bằng chứng tốt, phù hợp để tiếp tục nghiên cứu và quan sát thị trường. Bằng chứng hiện có chưa đủ để xác nhận chất lượng dự báo hoặc lợi thế sinh lời ổn định. Điểm nghẽn lớn nhất là khép kín chuỗi dữ liệu → đặc trưng → quyết định → kết quả → kiểm định độc lập.

Đây là điểm đánh giá kỹ thuật có trọng số, không phải xác suất thành công hay chứng nhận production. Chất lượng kỹ nghệ cao hơn mức trưởng thành của bằng chứng dự báo.

## Phạm vi và kiểm chứng

- Đánh giá mã nguồn đang có tại local, gồm thay đổi chưa commit; HEAD khi kiểm tra: `e1c2943`.
- Đọc các đường chạy scanner, V3, inference, feature builder, API, cấu hình, CI/CD, sao lưu và các báo cáo kiểm chứng gần nhất.
- Đọc JSON replay gốc và tính lại số dòng đủ điều kiện, mẫu Champion và trung bình lợi nhuận; không chạy lại toàn bộ backtest lịch sử trong đợt này.
- Python: **1.026 đạt, 3 bỏ qua, 57 cảnh báo**, 183,52 giây. Có cảnh báo tương thích NumPy/joblib, Pandas và tên đặc trưng sklearn.
- Frontend: build, TypeScript và bundle budget đạt; **12/12 kiểm thử Chromium đạt**. Kiểm thử trình duyệt dùng các kịch bản và dữ liệu mô phỏng, không xác nhận kết nối production thực tế.
- Ruff đạt theo phạm vi cấu hình; lưu ý cấu hình đang loại `scripts/`. Pyright đạt trên danh sách module trọng yếu giống CI.
- Frontend lint không có lỗi chặn, còn **21 cảnh báo**, chủ yếu liên quan dependency của React hooks và biến không dùng.
- Không kiểm tra trực tiếp GCP, uptime, tải thực tế hoặc thao tác khôi phục trên máy chủ. Điểm vận hành đánh giá thiết kế và mã nguồn, không phải SLA đo được.
- Không thay đổi logic, ngưỡng, model hay cấu hình vận hành trong đợt đánh giá; chỉ bổ sung tài liệu này.

## Bảng điểm

| Hạng mục | Điểm /10 | Trọng số | Nhận xét |
|---|---:|---:|---|
| Kiến trúc và khả năng bảo trì | 6,5 | 15% | Có phân lớp nghiệp vụ, nhưng API/scanner và một số component quá lớn; nghiên cứu và runtime còn liên kết chặt. |
| Kiểm thử và kỷ luật phát hành | 8,5 | 15% | Nhiều kiểm thử hồi quy có ý nghĩa; CI kiểm tra kiểu dữ liệu, build, trình duyệt; deploy đúng revision đã qua CI. Chưa đủ bằng chứng phục hồi và vận hành đầy đủ dưới tải. |
| Dữ liệu và khả năng tái lập | 6,0 | 20% | Có point-in-time, checksum, sổ sự kiện, kiểm tra thiếu dữ liệu; độ phủ funding đủ chứng cứ còn thấp và chưa khóa công thức feature cùng bundle. |
| Bằng chứng chất lượng dự báo | 3,5 | 25% | Chưa có tập tương lai đủ mạnh; số liệu Champion đủ điều kiện hiện rất ít và không hỗ trợ kết luận có lợi thế. |
| Vận hành và phục hồi | 6,0 | 15% | Có heartbeat, readiness, sao lưu kiểm checksum; còn thiếu dữ liệu V3 trong backup và tín hiệu lỗi V3 trong readiness chung. |
| Sản phẩm và khả năng giải thích | 7,0 | 10% | Có giải thích quyết định, phân biệt score/xác suất, kiểm thử mobile; nhiều lớp model và nghiên cứu làm tăng tải nhận thức. |

Điểm có trọng số: **5,925/10**. Điểm giao diện là sơ bộ dựa trên mã nguồn và kiểm thử, chưa phải nghiên cứu người dùng.

## Những nền tảng nên giữ

1. **Kiểm soát bằng chứng:** tách chỉ số huấn luyện, lịch sử tái sử dụng và quan sát tương lai; không tự nâng challenger hay pattern thành chất lượng đã xác nhận.
2. **Inference có điều kiện chặt:** checksum model/calibrator, kiểm tra dữ liệu hữu hạn, chất lượng và độ mới; dữ liệu thiếu không tự biến thành bằng chứng tích cực.
3. **Mô phỏng có hợp đồng rõ:** giá vào trung bình theo khối lượng, phí, funding, xử lý stop và tách đường giá sau stop khỏi kết quả giao dịch.
4. **Truy vết quyết định V3:** lưu trạng thái chọn thực tế, lý do không chọn và quan sát bền vững; thông báo có sổ theo dõi và cơ chế thử lại.
5. **Triển khai có kỷ luật:** release theo đúng SHA đã kiểm tra, có khóa scanner và snapshot nguyên tử cho các đường đọc.

## Các phát hiện cốt lõi

### 1. Chưa khép kín đánh giá tài chính cho quan sát V3 mới

`src/dao_vang/scanner/research_v3.py:480` truyền `funding=[]` và không có chứng nhận độ phủ; dòng 488 luôn ghi `funding_verified=False`. Đây là giới hạn có công bố, không phải lỗi che giấu chi phí. Tuy nhiên, thêm nhiều quan sát theo đường chạy hiện tại vẫn chưa tự tạo ra tập kết quả tài chính đã xác minh.

Tệp `artifacts/v3_improvement_20260922/verified_replay_numeric_fix/verified_replay.json` có 153 dòng, 149 sự kiện nguồn duy nhất, 53 dòng đủ điều kiện tài chính — **34,6%**. Phần bị loại không thể được giả định là thiếu ngẫu nhiên.

| Nhóm Champion | Tổng dòng | Đủ điều kiện tài chính | Chạm target | Trung bình net return trên vốn danh nghĩa dự kiến |
|---|---:|---:|---:|---:|
| Bộ chọn lịch sử | 21 | 11 | 6/11 | −0,346% |
| Runtime tham chiếu | 4 | 3 | 0/3 | −10,537% |

Hai nhóm được giữ riêng; không cộng thành số giao dịch độc lập. Đây là mô phỏng trên lịch sử đã xem, không phải ROI tài khoản hay hiệu quả live. Mẫu quá nhỏ để kết luận chiến lược chắc chắn không hiệu quả, nhưng không hỗ trợ tuyên bố đã có lợi thế.

**Cải tiến:** đưa funding thực và bằng chứng tải đầy đủ vào pipeline đánh giá outcome; dùng chung bộ máy đánh giá cho replay và quan sát tương lai. Mỗi sự kiện có trạng thái rõ: đang chờ, đủ bằng chứng, hoặc bị loại kèm lý do. Đối chiếu cùng đầu vào phải cho cùng kết quả và dấu kiểm tra.

### 2. Chưa khóa phiên bản công thức feature cùng model

Bundle frozen đang cấu hình dùng nhãn v1, mục tiêu giảm 8%/24h. Metadata có danh sách cột và checksum model/calibrator, nhưng chưa có định danh nội dung cho mã tạo feature. V3 cũng kiểm checksum model và danh sách cột, còn bộ tạo feature dùng mã nguồn hiện tại.

Các sửa đổi ngày 22/09 đã thay đổi cách tính return khi thiếu nến và cách giữ thiếu dữ liệu BTC. Đây là sửa đổi đúng về dữ liệu, nhưng tên cột không đổi chưa bảo đảm tương đương với feature lúc huấn luyện. Tài liệu `docs/SIGNAL_ACCURACY_20260922.md` cũng yêu cầu tái tạo feature và kiểm định lại. Chưa đo mức ảnh hưởng tới precision hoặc calibration hiện tại.

**Cải tiến:** tạo manifest cho mỗi phiên bản chiến lược gồm model, calibrator, mã tạo feature, chính sách dữ liệu thiếu, label, selector, execution policy và cấu hình universe. Lưu manifest ID trên từng dự báo. Khi công thức đổi, tạo phiên bản evidence mới; tái tạo dữ liệu, đánh giá và hiệu chuẩn lại trước khi dùng thống kê cũ để mô tả phiên bản mới. Chặn công bố chất lượng khi hợp đồng không khớp.

### 3. Sao lưu hiện tại chưa đủ để phục hồi V3

`scripts/backup_to_gdrive.sh:95–107` sao lưu DuckDB, JSON ở thư mục gốc và `artifacts/frozen_models`; phần data lake chỉ đồng bộ `raw` và `normalized`. Trong khi đó V3 lưu `research_v3/observations.sqlite`, `research_v3/telegram_notifications.sqlite` và trạng thái dưới thư mục con. Model tham chiếu V3 nằm ngoài `frozen_models` theo cấu hình live. Script khôi phục hiện tập trung vào DuckDB.

**Tác động:** một bản backup thành công theo script này chưa đủ khôi phục lịch sử quan sát, trạng thái episode/cooldown, lịch sử thông báo và bundle V3 trên máy mới. Chưa kiểm tra có cơ chế backup ngoài repository bù cho thiếu hụt này hay không.

**Cải tiến:** lập danh mục tất cả kho trạng thái và artifacts đang hoạt động, đưa vào snapshot nhất quán; khôi phục thử trên thư mục/máy sạch. Tiêu chí nghiệm thu: khớp số sự kiện và checksum, giữ episode/cooldown, không phát lại thông báo đã hoàn tất; đo thời gian phục hồi và mức mất dữ liệu tối đa.

### 4. Readiness chung có thể xanh khi V3 lỗi

`src/dao_vang/scanner/daemon.py:827` ghi cảnh báo rồi tiếp tục khi V3 thất bại. `/api/ready` tại `src/dao_vang/web/api_server.py:1365` chỉ tổng hợp heartbeat scanner và dung lượng đĩa. Workflow giám sát production chỉ gọi health/ready. Vì thế một chu kỳ scanner có thể hoàn tất nhưng nhánh V3 bị lỗi mà monitor này chưa nhận ra.

Việc giữ scanner chạy khi nhánh phụ lỗi là hợp lý; thiếu sót nằm ở khả năng quan sát sức khỏe riêng của từng nhánh.

**Cải tiến:** thêm trạng thái V3 đang bật, lần thành công gần nhất, độ mới feature/snapshot, độ phủ outcome/funding, hàng đợi và lỗi gửi thông báo. Kiểm thử lỗi V3 có chủ đích phải tạo trạng thái degraded rõ ràng và được monitor phát hiện, đồng thời các nhánh còn tốt tiếp tục chạy.

### 5. Phức tạp phần mềm đang tăng nhanh hơn bằng chứng lợi ích

Đếm cả dòng trống: API 5.239 dòng, scanner daemon 2.269 dòng, SignalFeed 1.902 dòng, MainWorkspace 1.729 dòng. Đây là chỉ báo chi phí bảo trì, không tự nó chứng minh lỗi hiệu năng. Bộ tạo feature chính còn tái tạo toàn bảng khi pipeline thay đổi; cần đo trước khi tối ưu.

Ở mặt nghiên cứu, pattern_05 nhận 141/149 sự kiện trong tập cơ chế; báo cáo pattern khác chỉ có 15 nhãn kiểm định đủ tiêu chí, 7 đạt target. Hai tập không cùng mẫu số. Nhãn pattern hiện quá rộng để coi là phân nhóm có khả năng phân biệt hữu ích nếu chưa kiểm định bổ sung.

**Cải tiến:** giữ modular monolith, tách API theo nghiệp vụ, tách điều phối scanner khỏi collection/scoring/outcome, chuyển logic nghiên cứu dùng chung khỏi script sang thư viện có kiểm tra kiểu dữ liệu. UI ưu tiên trạng thái quyết định, lý do, độ mới và mức bằng chứng. Chỉ đưa pattern hoặc mô hình phức tạp vào đường chọn khi cho thấy cải thiện trên tập độc lập.

## Thứ tự triển khai đề xuất

| Ưu tiên | Công việc | Tiêu chí hoàn tất |
|---|---|---|
| P1 — bảo toàn dữ liệu | Bổ sung backup/restore toàn bộ V3 và model đang dùng | Phục hồi trên môi trường sạch, đối chiếu sự kiện/trạng thái và không gửi trùng. |
| P1 — tính nhất quán | Manifest phiên bản feature–model–label–policy; đánh giá lại sau sửa feature | Mỗi dự báo truy được đầy đủ phiên bản; mismatch bị nhận diện; thống kê tách theo phiên bản. |
| P1 — bằng chứng kết quả | Tích hợp funding có chứng nhận và outcome dùng chung | Mọi sự kiện trưởng thành có kết quả đủ chứng cứ hoặc lý do loại; cùng dữ liệu replay/runtime cho cùng kết quả. |
| P1 — phát hiện sự cố | Sức khỏe và cảnh báo riêng cho V3 | Lỗi V3 không bị readiness chung che khuất; có độ mới và tồn đọng theo từng nhánh. |
| P2 — chất lượng dự báo | Đóng băng protocol mới, so sánh baseline và challenger trên dữ liệu tương lai | Đánh giá ghép cặp, gộp theo sự kiện/coin/thời gian, chi phí/funding đầy đủ và khoảng bất định. |
| P2 — bảo trì và trải nghiệm | Tách các module lớn; đơn giản hóa màn hình quyết định | Giữ nguyên hành vi đã khóa; kiểm thử chuỗi scanner → lưu → API → UI → thông báo mô phỏng đạt. |

Có thể bắt đầu thu thập dữ liệu thô tương lai ngay, nhưng chỉ công nhận một tập đánh giá sau khi đóng băng đầy đủ phiên bản và quy tắc. Thời gian đạt đủ sự kiện phụ thuộc thị trường, không thể hứa hoàn tất bằng lịch triển khai phần mềm.

## Hướng nghiên cứu mô hình có giá trị nhất

- So sánh một baseline đơn giản với Champion hiện tại trên cùng tập sự kiện, cùng timestamp và cùng hợp đồng outcome. Ghi cả tín hiệu bị loại để đo recall và thiên lệch chọn mẫu.
- Tách ba câu hỏi: có biến động đáng chú ý không; thời điểm chọn đã phù hợp chưa; execution policy tạo kết quả gì. Giả thuyết về hướng giảm, tiếp tục tăng và biến động hai phía cần được thử riêng, không suy từ pump/funding lớn thành xác suất giảm.
- Giới hạn số giả thuyết, chốt tiêu chí trước khi xem kết quả, giữ tập tương lai chưa dùng để chỉnh ngưỡng. Các cửa sổ lịch sử đã khai thác chỉ dùng thăm dò.
- Tham chiếu gate hiện có trong cấu hình V3: ít nhất 100 sự kiện tương lai trưởng thành, ba cửa sổ thời gian, các điều kiện EV và bất định; không coi số lượng mẫu tối thiểu là đủ nếu các gate còn lại không đạt.
- Báo cáo hiệu quả tăng thêm của từng feature/gate/pattern, độ phủ, chi phí, độ nhạy theo giai đoạn và mức tập trung vào một số coin. Bỏ thành phần không chứng minh được lợi ích.

Ưu tiên đầu tư là **bằng chứng có thể tái lập, thu thập liên tục và phục hồi được**, sau đó mới tăng độ phức tạp mô hình hoặc số tính năng.
