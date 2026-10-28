# Bước hoàn thiện tiếp theo: kiểm tra kích thước lệnh

## Kết quả chính

Đã bổ sung một công cụ đối chiếu từng chân lệnh của backtest với snapshot bộ lọc kích thước Binance USD-M. **Không sửa kết quả backtest cũ, không tính lợi nhuận mới và không gửi lệnh thật.**

Với quy định lấy ngày 18/09/2026, trong 10.336 record thực hiện của 40 cấu hình:

- **5.743** vượt qua các kiểm tra kích thước đang xét.
- **4.593**, khoảng **44,4%**, không vượt qua.
- **0** record thiếu dữ liệu bộ lọc trong snapshot cụ thể này.
- Tổng cộng 10.980 chân lệnh; 644 record hedge, trong đó 322 có cả hai chân vượt qua kiểm tra.

Các record thuộc nhiều cấu hình có thể dùng cùng tín hiệu: đây không phải 10.336 quan sát độc lập. “Không vượt qua kiểm tra” theo snapshot hiện tại cũng không chứng minh sàn đã từ chối lệnh tại thời điểm lịch sử.

## Những nhánh bị ảnh hưởng

Bảng này chỉ lấy cấu hình **20 bps, rút lãi** để so sánh nhất quán. Kết quả đủ 40 cấu hình được giữ trong artifact của công cụ.

| Chiến lược | Record thực hiện cũ | Đạt kiểm tra kích thước | Không đạt |
|---|---:|---:|---:|
| Long theo đà 48h, 1x | 176 | 133 | 43 |
| Long theo đà 48h, 2x | 177 | 171 | 6 |
| Long theo đà 168h, 2x | 53 | 53 | 0 |
| Long theo đà + funding âm, 1x | 159 | 159 | 0 |
| Short suy yếu sau pump, 1x | 163 | 149 | 14 |
| Short suy yếu sau pump, 2x | 81 | 81 | 0 |
| Short thêm funding dương/tăng, 2x | 62 | 62 | 0 |
| Đổi long/short theo pha, 1x | 165 | 94 | 71 |
| Short coin + long BTC, gross 2x | 161 | 73 | 88 |
| Long và thoát theo pha suy yếu | 1.387 | 549 | 838 |

## Điều này giúp hiểu cơ chế gì?

**1. Vốn teo lại tạo ra một đường giao dịch không chắc có thể thực hiện.** Nhánh hedge và thoát theo pha có nhiều record không đủ kích thước sau khi vốn giảm. Không thể dùng việc tài khoản mô phỏng vẫn chạy tới cuối năm làm bằng chứng rằng chiến lược vẫn hoạt động được ngoài đời.

**2. Tái đầu tư còn có vấn đề ở đầu kia: lệnh quá lớn.** Có 53 chân vượt `maxQty` market hiện tại, đều ở M48_2 giữ lãi: 32 ở mức chi phí 20 bps và 21 ở 60 bps. Ví dụ một record dự kiến khoảng 76,98 triệu đơn vị trong khi trần hiện tại là 3 triệu. Đây là giới hạn của một lệnh market đơn; chưa mô phỏng chia lệnh hoặc tác động thị trường, nên không kết luận rằng không thể giao dịch bằng cách khác.

**3. Đạt điều kiện kích thước không đồng nghĩa tín hiệu tốt.** Nhánh short thêm funding dương/tăng vượt kiểm tra kích thước ở toàn bộ 62 record của cấu hình trên, nhưng baseline vẫn lỗ. Ngược lại, một nhánh lời lớn vẫn có thể phụ thuộc vào sự kiện hiếm và lịch cấp vốn. Phải tách chất lượng tín hiệu, quy mô lệnh và quản lý vốn thành các câu hỏi khác nhau.

## Công cụ kiểm tra những gì?

- Leverage lấy từ định nghĩa trial đã khóa; không suy đoán từ tên chiến lược.
- Khối lượng dự kiến từ margin thực của từng chân × leverage ÷ giá entry. Hedge không nhân đôi nhầm margin.
- Làm tròn xuống bằng số thập phân chính xác theo các bước khối lượng được hỗ trợ; kiểm tra `LOT_SIZE`, `MARKET_LOT_SIZE`, giới hạn min/max và `MIN_NOTIONAL`.
- Missing/invalid/unsupported filters không tự được coi là pass. Lý do được lưu theo từng chân, rồi tổng hợp cả record.
- Thống kê margin dưới 5/20 USD là chẩn đoán giả định theo từng chân, không phải ngưỡng sàn hay quy tắc tự động dừng phần vốn đang giao dịch.
- Lưu hash nguồn, bản snapshot, provenance và record kiểm tra; mặc định không ghi đè kết quả có sẵn.

## Giới hạn phải giữ nguyên

Snapshot được lấy lúc **2026-09-18T02:16:27.6921243Z**, hash `1f15b404bd1dfcf8f95e7cd0b85018e34c187e2ff8c73763bc8d2a8650f343e0`, chứa 897 symbols. Đây là quy định **hiện tại**, không phải bộ quy định lịch sử của cửa sổ 09/2025–08/2026.

Theo [tài liệu Binance](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/common-definition), các bộ lọc khối lượng áp dụng theo symbol. Kiểm tra giá trị lệnh market ở đây dùng giá entry lịch sử làm proxy, chưa xác nhận mark tương ứng. Chưa kiểm tra đầy đủ trạng thái hợp đồng, lịch tier, hạn mức vị thế, số dư khả dụng, sổ lệnh, ADL hoặc khả năng khớp.

Vì thế **không được bỏ 4.593 record rồi cộng lại P&L để gọi là lợi nhuận thực tế hơn**. Một lệnh bị bỏ hoặc đổi khối lượng sẽ làm thay đổi toàn bộ đường vốn phía sau, và cần replay riêng.

## Xác minh bản bàn giao

- Công cụ: `scripts/audit_annual_execution.py`; kiểm thử: `tests/unit/scripts/test_audit_annual_execution.py`.
- Kết quả chính thức của bước này: `artifacts/annual_execution_20260918/audit_final/annual_execution_audit.json`, chi tiết từng chân trong `annual_execution_leg_audit.jsonl`, báo cáo máy sinh trong `annual_execution_report.md` cùng thư mục.
- Sol Medium review cuối **PASS** sau khi sửa ba lỗi: grid lệch gốc không hỗ trợ trả unknown; maxQty không hợp lệ trả unknown; thiếu provenance thời gian không lấy mtime thay thế. Bản review tại `artifacts/annual_execution_20260918/review/sol_final_review.md`.
- Parent chạy độc lập 103 kiểm thử liên quan, tất cả đạt. Worker chạy toàn dự án: **822 passed, 3 skipped, 57 warnings**, Ruff đạt. Ba bài bỏ qua không được coi là đã kiểm chứng.
- Parent kiểm tra lại output cuối: số lượng record/leg khớp; thời điểm lấy dữ liệu đúng sidecar; bản sao snapshot và provenance khớp từng byte; hash mã nguồn đúng phiên bản Sol đã review.
- Sổ `accounts.json` baseline và mã `backtest_annual_profit.py` giữ nguyên hash. Không có backtest P&L mới trong bước này.

## Lượt nghiên cứu tiếp theo

Hai hướng đã đưa ra để lựa chọn: dừng và giữ phần vốn dư, hoặc cất phần dư rồi dùng phần vốn tiếp theo trong 10.000 USD ban đầu. Không nạp thêm, không tự tái sử dụng lãi đã rút. Cần khóa riêng điều kiện dừng phần vốn đang hoạt động và điều kiện một lệnh không đủ kích thước: không đủ tiền đặt một cặp hedge không chứng minh rằng vốn không thể giao dịch mã khác.

Sau khi chốt chính sách, replay phải xây lại lịch vốn và khối lượng từ đầu, rồi so với baseline. Chưa có backtest lợi nhuận mới trong bước kiểm tra này.
