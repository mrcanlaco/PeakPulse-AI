# V3 — cải tiến và kiểm chứng, 22/09/2026

Trạng thái: **đã nghiệm thu phần cải tiến phần mềm và kiểm chứng lịch sử tại local**.
Kết quả này **không xác nhận V3 có lợi thế sinh lời**.
Chưa deploy GCP, chưa gửi Telegram thật, không có giao dịch thật trong đợt này.

## Những gì đã được kiểm tra

- Giữ nguyên cấu hình V3, quy tắc mô phỏng và tập tín hiệu lịch sử làm đối chứng.
  Dấu SHA-256 đối chiếu nằm trong `V3_IMPROVEMENT_PLAN_20260922.md`.
- Phần giải thích mới tách checklist năm đặc trưng khỏi điều kiện chọn thực tế.
  Review Sol phát hiện bốn điểm cần sửa; bản sửa đã được review lại và đạt
  ở phần giải thích chọn tín hiệu (không bao gồm nghiệm thu mô phỏng tài chính).
- Bản sửa tiếp theo đã qua 31 kiểm thử selector/explanation và hai kiểm thử
  giao diện mới dùng dữ liệu mô phỏng cho các trạng thái xác nhận giữ từ trước,
  5/5 chưa được chọn, thiếu funding, cooldown và dữ liệu cũ. Build đạt; ảnh
  viewport 390×844 đã được xem. Sol chạy lại 44 kiểm thử Python tập trung và
  hai kiểm thử trình duyệt, đều đạt.
- Bộ nhận diện mẫu hình đã bổ sung kiểm tra nguồn mẫu, mốc huấn luyện và tách
  số dòng huấn luyện khỏi số sự kiện kiểm định. Sai số hiệu chuẩn bằng 0 không
  còn bị đánh đồng với thiếu dữ liệu. Chưa tự nâng nhãn chất lượng hay đổi mẫu
  đang phục vụ tín hiệu.
- Lần chạy lại toàn bộ kiểm thử đơn vị sau bản sửa kiểu số: 990 đạt,
  53 cảnh báo thư viện đã có từ trước (90,66 giây). Review cuối đã đạt;
  kiểm thử phần mềm không phải bằng chứng lợi nhuận.

## Báo cáo mẫu hình mới nói gì?

Báo cáo riêng ở `artifacts/v3_improvement_20260922/pattern_research/report.json`
vẫn dùng dữ liệu nhãn Entry-1 cũ. Nó không phải kiểm định kết quả theo giá vào
trung bình của V3.

| Mẫu | Số dòng dùng xây mẫu | Số sự kiện hỗ trợ ở phần chọn quy tắc | Số sự kiện kiểm định đủ tiêu chí đưa vào bảng |
|---|---:|---:|---:|
| pattern_01 | 73 | 0 | 0 |
| pattern_02 | 182 | 1 | 0 |
| pattern_03 | 58 | 0 | 0 |
| pattern_04 | 78 | 0 | 0 |
| pattern_05 | 2.218 | 97 | 15 |

Ở pattern_05, 7/15 nhãn Entry-1 đạt mục tiêu; cận dưới Wilson 95% khoảng 24,8%.
Đây là thống kê thăm dò trên lịch sử đã sử dụng, không chứng minh mẫu tốt hơn
Champion và không phải xác suất thắng của tín hiệu tiếp theo. Không có mẫu nào
được nâng lên chất lượng đã xác nhận.

Số 0 ở cột cuối có thể do thiếu hỗ trợ tại phần chọn quy tắc, không có nghĩa
toàn bộ thị trường chưa từng xuất hiện mẫu đó. Không cộng số dòng xây mẫu thành
số giao dịch độc lập.

### Biên độ đường giá theo mẫu, khi có dữ liệu

Nguồn riêng: `mechanisms/mechanism_study.json`, bỏ trùng theo `source_event_id`,
tính trên 576 nến sau Entry-1. Template nghiên cứu có checksum
`203f524ead8000a9cb07b4970d3542c90388c08c4124bde8dab1f3fcf4fc2ac9`;
không phải template đang phục vụ tín hiệu. Bảng chỉ lấy dòng sau mốc kết thúc
fit của template; chúng vẫn thuộc lịch sử đã xem, không phải holdout mới.

| Nhãn mẫu | Số sự kiện nguồn | Trung vị giá tăng tối đa, bất lợi nếu short | Trung vị giá giảm tối đa, thuận lợi nếu short |
|---|---:|---:|---:|
| pattern_02 | 1 | 70,02% | 45,12% |
| pattern_05 | 75 | 18,72% | 23,24% |
| unknown | 3 | 27,75% | 28,85% |

Cả 79 đường giá này đủ nến. Các biên độ được quan sát trên cả cửa sổ 48h,
không bị cắt tại stop; không nói thứ tự xảy ra, khả năng khớp lệnh hay lợi
nhuận đạt được. Chúng không phải kết quả theo giá vào trung bình. Mẫu có một
sự kiện không đủ để ước lượng rủi ro ổn định; các mã lặp cũng gây phụ thuộc.

Không nhầm 75 sự kiện này với 15 nhãn kiểm định ở bảng phía trên: hai tập có
nguồn, điều kiện đủ tiêu chí và định nghĩa kết quả khác nhau. Toàn tập cơ chế
gán 141/149 sự kiện nguồn vào pattern_05 (66 trước/đúng mốc fit, 75 sau mốc
fit). Vì vậy, nhãn này hiện khá rộng; chưa thể dùng nó như bằng chứng tín hiệu
đã có chất lượng cao. Dữ liệu thiếu/unknown không bị ép vào mẫu gần nhất.

## Dữ liệu cho mô phỏng chính xác

- Tập gốc có 153 dòng thuộc hai cách chọn tín hiệu, tương ứng 149 sự kiện nguồn;
  bốn sự kiện xuất hiện ở cả hai cách chọn. Không xem 153 dòng là 153 mẫu độc lập.
- Kiểm tra đầu vào ban đầu tìm đủ giá vào và 576 nến tiếp theo cho cả 153 dòng.
- Dấu kiểm tra tài liệu giao thức funding lệch do CRLF/LF: chuyển đúng cách xuống
  dòng về LF cho kết quả khớp nguyên bản. Ngoại lệ chỉ cho định dạng xuống dòng
  đã được kiểm thử; dữ liệu giá/funding vẫn phải khớp chính xác từng byte.
- Bốn mã APRUSDT, CLOUSDT, HEMIUSDT, LIGHTUSDT có funding được đánh dấu chưa đầy
  đủ trong cache nguồn. Không tự công nhận đủ bằng chứng chỉ vì đã có một số dòng.

Đã nghiệm thu bộ mô phỏng lịch sử theo quy tắc V3 đã đóng băng: khớp entry,
giá trung bình, phí, funding, stop, giá cuối kỳ và quan sát giá sau stop được
tách riêng. Đây không phải bảo đảm khớp lệnh thực tế.

Kiểm tra đầu vào cuối cùng chấp nhận **53/153**
dòng làm đầu vào mô phỏng tài chính: 47 dòng theo bộ chọn lịch sử, 6 dòng runtime.
81 dòng thiếu bằng chứng đầy đủ về quá trình tải funding; 19 dòng còn lỗi funding
chưa đầy đủ. Các nhóm lỗi có thể có nhiều lý do đồng thời. Đây là số dòng đủ
nguồn đầu vào, không phải số lệnh thắng/lỗ.

Root đã chạy lại mô phỏng vào `root_verified_check/`: 153/153 dòng khớp bản
worker về khóa dòng, hash kết quả, trạng thái đủ điều kiện tài chính và lợi
nhuận ròng trên vốn danh nghĩa dự kiến. Sol cũng đối chiếu độc lập 153 dòng
không có sai lệch. Các lỗi phát hiện qua review về nối trang, bằng chứng trang
cuối và kiểu số nguyên của metadata đều đã sửa, kiểm thử và review lại đạt.
Không sửa nguồn để làm đẹp kết quả.

Bộ kết quả mới nhất nằm ở `input_audit_numeric_fix/` và
`verified_replay_numeric_fix/`. Root đối chiếu với bản trước: cả 153 dòng
giữ nguyên hash kết quả, trạng thái đủ điều kiện và lợi nhuận ròng. Vẫn có
53 dòng đủ điều kiện, không có dòng thiếu nguồn nào được tự nâng cấp.

### Kết quả Champion đã đối chiếu

Không gộp hai cách chọn tín hiệu thành một tập độc lập:

- Bộ chọn lịch sử: 21 dòng Champion, trong đó 11 đủ nguồn funding để tính
  tài chính; 6/11 đạt target. Trung bình lợi nhuận ròng trên vốn danh nghĩa dự
  kiến của 11 dòng là khoảng **−0,35%**.
- Bộ chọn runtime tham chiếu: 4 dòng Champion, trong đó 3 đủ nguồn funding;
  0/3 đạt target. Trung bình tương ứng khoảng **−10,54%**.

Đây là kết quả mô phỏng trên phần dữ liệu đủ điều kiện, không phải lợi nhuận
tài khoản hay ROI sau đòn bẩy. Không thể giả định phần thiếu funding là ngẫu
nhiên; mẫu rất nhỏ và lịch sử đã được xem. Không suy rộng các trung bình này
ra mọi tín hiệu.
Nhãn target mô tả chạm mục tiêu theo hợp đồng V3, không đồng nghĩa mọi giao
dịch timeout đều lỗ. Chưa có cơ sở từ kết quả này để khẳng định lợi thế sinh lời.

## Nghiên cứu cơ chế

Định nghĩa nhóm đường giá được chốt ở `V3_MECHANISM_PROTOCOL_20260922.md` trước
khi tính bảng so sánh. Các nhóm gồm giảm một chiều, tăng một chiều, chạm cả hai
biên, đi ngang theo giá cuối kỳ, trung gian và thiếu dữ liệu. Đây là mô tả đường
giá Entry-1, tách biệt với mục tiêu V3 tính từ giá trung bình.

149 sự kiện nguồn đều khớp chính xác thời điểm với bảng đặc trưng đã đóng băng.
Bảng có đủ chín cột giải thích đã chọn; phân tích báo thiếu dữ liệu ở cấp từng
giá trị. Bản nghiên cứu đã xuất, 14 kiểm thử đạt; Sol review PASS và đối chiếu
độc lập toàn bộ 153 đường giá, không thấy sai lệch về nhóm, biên độ hay mốc
chạm biên. Đây là nghiệm thu phương pháp mô tả, không xác nhận lợi nhuận.

Trong 149 sự kiện nguồn không trùng, có 53 đường giá chạm biên giảm 20% mà
không chạm biên tăng 20%, 49 trường hợp ngược lại, 20 chạm cả hai biên, 11 đi
ngang theo định nghĩa giá cuối kỳ và 16 trung gian. Đây là toàn bộ tập nghiên
cứu, không phải riêng Champion, và mốc tính là Entry-1 chứ không phải giá vào
trung bình. Không suy ra thứ tự chạm biên hoặc lợi nhuận từ bảng này.

Riêng Champion theo bộ chọn lịch sử có 21 dòng: 6 giảm một phía, 6 tăng một
phía, 5 chạm cả hai biên, 3 đi ngang và 1 trung gian. Nhóm runtime chỉ có 4
dòng; không cộng hai nhóm thành các giao dịch độc lập. Các số đếm đã được
đối chiếu, nhưng không chứng minh nguyên nhân thanh lý hoặc lợi thế giao dịch.

### Điều học được về cơ chế, trong giới hạn tập dữ liệu này

- Pump lớn chưa phân biệt được hướng tiếp theo: trung vị tăng 24h của nhóm
  giảm một phía là 36,87%, còn nhóm tăng một phía là 37,97%; khoảng tứ phân vị
  chồng lấn đáng kể. Không có cơ sở từ bảng này để tăng ngưỡng pump rồi tuyên
  bố tín hiệu tốt hơn.
- Funding tăng không đồng nghĩa chắc chắn sắp dump. Trung vị thay đổi funding
  8h ở nhóm tăng một phía là 0,0001158, cao hơn nhóm giảm một phía 0,000069.
  Đây là giá trị dạng tỷ lệ gốc, không phải xác suất hay lợi nhuận.
- Nhóm chạm cả hai biên có trung vị pump 46,44% và OI tăng 4h 23,21%.
  Quan sát này gợi ý một giả thuyết về biến động hai chiều cần kiểm chứng mới,
  không phải bằng chứng rằng OI gây thanh lý hay chỉ báo nên short/long.

Những so sánh trên dùng 149 sự kiện nguồn của toàn tập đã chọn, không chỉ
Champion. Chúng là mô tả sau khi phân nhóm kết quả, không phải bộ phân loại
đã được kiểm định. Giữ nguyên ngưỡng và không nâng nhãn chất lượng từ chúng.

## Trạng thái nghiệm thu

- Giải thích chọn tín hiệu: đạt review; build cuối và bốn kiểm thử V3 trên
  trình duyệt đạt, gồm mobile và diễn biến sau stop.
- Bằng chứng mẫu hình: đạt review. Bản sửa lưu model cũ qua 33 kiểm thử, liên
  kết checksum với model đang phục vụ và báo cáo nghiên cứu được đối chiếu đúng.
- Nghiên cứu cơ chế: đạt review trong phạm vi mô tả lịch sử.
- Audit và mô phỏng tài chính: đạt review sau các bản sửa; 38 kiểm thử tập
  trung đạt, số liệu và bằng chứng nguồn đã được đối chiếu độc lập.
- Báo cáo bàn giao: Sol review đạt về số liệu, mẫu số và giới hạn diễn giải.

## Bàn giao và giới hạn

Đối chiếu từng yêu cầu và bằng chứng nằm ở `V3_COMPLETION_AUDIT_20260922.md`.
Không còn phát hiện review chưa xử lý trong phạm vi đợt cải tiến này.
Các báo cáo review nằm dưới `artifacts/v3_improvement_20260922/`, gồm
`sol_selection_pattern_final.md`, `sol_pattern_roundtrip_review.md`,
`sol_mechanisms_review.md`, `sol_financial_replay_review.md`,
`sol_pagination_final_review.md`, `sol_numeric_final_review.md` và
`sol_handoff_evidence_review.md`. Các bản yêu cầu sửa được giữ lại để truy vết;
kết luận sau bản sửa tương ứng mới là trạng thái cuối cùng.

Thu thập mẫu tương lai là bước nghiên cứu tiếp theo, không thể thay bằng lịch
sử đã xem. Không có triển khai giao dịch hoặc tự nâng nhãn chất lượng trong
đợt cải tiến này.
