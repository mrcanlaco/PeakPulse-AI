# Backtest sơ bộ tài khoản Đảo Vàng — 24/09/2026

Đây là mô phỏng sơ bộ trên tín hiệu dựng lại. Không phải kết quả giao dịch thật hoặc bằng chứng lợi nhuận ngoài mẫu. Đường biểu đồ dừng khi dữ liệu hoặc giả định thanh lý không cho phép tiếp tục; không kéo ngang đến cuối kỳ và không coi số dư thiếu là 0.

Kỳ yêu cầu: **24/06/2026 00:00–24/09/2026 00:00 UTC** (92 ngày). Vốn 500 USDT, Short Cross x5, khoảng 25 USDT danh nghĩa/vị thế, không DCA/stop-loss, TP ATR14 × 2, mục tiêu ròng 0,50–5 USDT.

| Giới hạn vị thế | Đã vào | Đã TP | Còn mở lúc dừng | Tài sản cuối 3 tháng | Giảm từ đỉnh (mẫu 5 phút) | Dừng do | Thời điểm dừng | Phí đã tính | Funding ròng đã tính |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 10 | 9 | 1 | Chưa xác định | 100.62% | Chạm ngưỡng thanh lý ước tính | 13/08/2026 19:55 UTC | 0.2015 | -4.2767 |
| 3 | 16 | 14 | 2 | Chưa xác định | 100.03% | Chạm ngưỡng thanh lý ước tính | 13/08/2026 20:00 UTC | 0.3329 | -8.2008 |
| 5 | 17 | 15 | 2 | Chưa xác định | 99.82% | Chạm ngưỡng thanh lý ước tính | 13/08/2026 20:00 UTC | 0.3568 | -8.2006 |

## Giới hạn nghiệm thu

- Model hiện tại huấn luyện đến 2026-07-28T19:05:39.999000+07:00, đóng băng 2026-09-06T10:57:16.293277+07:00; trùng một phần kỳ kiểm tra.
- Có 379,685 dòng ứng viên; 255,121 đủ dữ liệu theo bộ kiểm tra; 165 sự kiện được chọn.
- Đã tra danh mục kho Tardis/Drive của người dùng: 767 mã xuất hiện trong kỳ, dữ liệu gốc đến 2026-09-18. Đầu vào mô hình được dựng lại từ dữ liệu nến và phái sinh; chưa chạy mô phỏng toàn bộ L2.
- Đã khôi phục và kiểm tra checksum hai file trades AKE/HOT ngày 01/08: 6,943,364 giao dịch, 576 nến; OHLC khớp hoàn toàn với Parquet trong kho chính.
- Nguồn metrics gốc kết thúc 2026-09-07 23:55:00+00:00. Những ngày thiếu dữ liệu không được xem là không có tín hiệu.
- Bộ dựng tín hiệu theo coin tăng giá và ngưỡng model chưa tái hiện đầy đủ bộ lọc pump, danh sách coin được giữ lại và lịch sử episode của scanner.
- Funding lấy từ lịch sử Binance có phân trang và lưu checksum. Phí giả định 0,05% mỗi chiều, trượt giá vào lệnh 0,20%; chưa xác nhận bậc phí tài khoản.
- Định giá dùng Mark Price lịch sử của Binance. TP giả định khớp khi giá đóng nến giao dịch đi qua mức LIMIT. Chưa mô phỏng hàng chờ/khớp từng phần bằng L2.
- Ngưỡng ký quỹ duy trì 1% là giả định kiểm tra. Chạm ngưỡng này làm dừng mô phỏng; không xác nhận giá thanh lý hoặc tài sản sau thanh lý thực tế tại Binance.
- Dùng quy tắc khối lượng/giá từ snapshot sàn hiện có. Danh sách coin theo từng thời điểm, dữ liệu hủy niêm yết và bậc ký quỹ lịch sử chưa được xác minh đầy đủ.
- Mẫu 5 phút có thể nhảy qua ngưỡng thanh lý, tạo mức giảm tính toán vượt 100%. Đây không phải xác nhận tài khoản thực bị âm; mô phỏng dừng và để trống tài sản cuối kỳ.

Dữ liệu bổ sung: [Binance Funding Rate History và Mark Price Klines](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data). Các phản hồi đã được lưu cùng checksum trong thư mục kết quả.

## Lệnh còn mở khi mô phỏng dừng

### Tối đa 1 vị thế

- AKEUSDT: vào 15/07/2026 06:05 UTC, giá 0.0003699586, lượng 67305; định giá cuối đã ghi 0.0073595, PnL chưa chốt -470.43 USDT; giữ 29.57 ngày.

Chạm ngưỡng MMR giả định lúc 13/08/2026 19:55 UTC: tài sản mẫu -3.22 USDT, MMR giả định 5.49 USDT. Không suy ra số dư sau thanh lý.

### Tối đa 3 vị thế

- HOTUSDT: vào 05/07/2026 14:40 UTC, giá 0.0003730524, lượng 66747; định giá cuối đã ghi 0.00032003, PnL chưa chốt 3.54 USDT; giữ 39.22 ngày.
- AKEUSDT: vào 15/07/2026 06:05 UTC, giá 0.0003699586, lượng 67305; định giá cuối đã ghi 0.00815698, PnL chưa chốt -524.11 USDT; giữ 29.58 ngày.

Chạm ngưỡng MMR giả định lúc 13/08/2026 20:00 UTC: tài sản mẫu -0.15 USDT, MMR giả định 5.78 USDT. Không suy ra số dư sau thanh lý.

### Tối đa 5 vị thế

- HOTUSDT: vào 05/07/2026 14:40 UTC, giá 0.0003730524, lượng 66747; định giá cuối đã ghi 0.00032003, PnL chưa chốt 3.54 USDT; giữ 39.22 ngày.
- AKEUSDT: vào 15/07/2026 06:05 UTC, giá 0.0003699586, lượng 67305; định giá cuối đã ghi 0.00815698, PnL chưa chốt -524.11 USDT; giữ 29.58 ngày.

Chạm ngưỡng MMR giả định lúc 13/08/2026 20:00 UTC: tài sản mẫu 0.94 USDT, MMR giả định 5.78 USDT. Không suy ra số dư sau thanh lý.

## Tái lập và bàn giao

Nguồn chính: `C:/Quant-trading/data_lake`, bổ sung các khóa giá còn thiếu từ `D:/Quant-trading/data_lake`. Kho gốc không bị sửa. Lệnh chạy:

```powershell
.venv\Scripts\python.exe -X utf8 scripts/backtest_account_3m.py --lake C:/Quant-trading/data_lake --supplement-lake D:/Quant-trading/data_lake --output artifacts/account_backtest_20260924_3m/warehouse --prepare --run --mark-prices
.venv\Scripts\python.exe -X utf8 scripts/report_account_backtest.py artifacts/account_backtest_20260924_3m/warehouse
```

Bỏ `--prepare` để dùng lại dữ liệu dựng đã lưu. Kết quả chi tiết, phản hồi funding/Mark có checksum, lịch sử lệnh CSV và dashboard HTML nằm trong thư mục output. 22 kiểm thử kế toán, trạng thái dừng, funding và hợp đồng Cross đã đạt. Cấu hình giao dịch live không thay đổi; không dùng khóa tài khoản thật trong lượt backtest.
