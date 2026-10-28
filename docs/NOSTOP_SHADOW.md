# No-stop shadow paper trading — vận hành local

Mã: `src/dao_vang/nostop/shadow/`. Dữ liệu chạy: `data/nostop_shadow/` (không ghi vào `data_live/`). Chỉ gọi **API công khai** của Binance, không dùng khóa, không đặt lệnh.

## Chạy

```powershell
# đăng ký các ứng viên đã xác nhận (28 ứng viên Calmar > 1 ở train, val, test)
.\.venv\Scripts\python.exe -m dao_vang.nostop.shadow add --passing
# hoặc chọn tay
.\.venv\Scripts\python.exe -m dao_vang.nostop.shadow add --ids composite-2a753a0b,composite-3db01c74
# chạy bộ cấp dữ liệu + engine + trang web trong MỘT tiến trình
.\.venv\Scripts\python.exe -m dao_vang.nostop.shadow run --port 8890
# quản lý
.\.venv\Scripts\python.exe -m dao_vang.nostop.shadow list
.\.venv\Scripts\python.exe -m dao_vang.nostop.shadow pause|resume|stop <id|*>
```

Trang quản lý: `http://127.0.0.1:8890/` (chỉ bind 127.0.0.1): số shadow đang chạy/tạm dừng/dừng, lãi/lỗ từng shadow (cập nhật theo giá mark mỗi phút), hôm nay, MaxDD, số vị thế, gross, Calmar nghiên cứu, đường vốn, vị thế, lệnh gần nhất, nút Pause/Resume, và thông số hệ thống (API weight, RAM, độ trễ nến).

## Cách tiết kiệm tài nguyên

- **Một feed dùng chung**: bảng nến 4h của 116 coin nằm trong bộ nhớ, tạo từ dữ liệu nghiên cứu rồi bổ sung bằng klines công khai. Khởi động lần đầu: 116 lệnh klines + 116 lệnh fundingRate (~60 s). Trạng thái ổn định: **116 lệnh klines mỗi nến 4h**, 1 lệnh `premiumIndex` mỗi 8h cho funding, 1 lệnh `ticker/price` mỗi phút cho giá mark. Số shadow không làm tăng số lệnh API.
- **Một lần tính đặc trưng mỗi nến** cho mọi shadow (cache `Ctx` dùng chung), mỗi shadow chỉ tính trọng số của chính nó.
- **Shadow là phép phát lại tất định** từ (spec, nến bắt đầu, bảng nến chung) bằng đúng engine và mô hình chi phí của backtest, nên không có cơ sở dữ liệu theo shadow, khởi động lại không lệch trạng thái.
- Đo thực tế: 28 shadow, chu kỳ đầu 58 s (gồm tải dữ liệu), RAM ≈ 166 MB, đĩa ≈ 10 MB (`bars.npz` nén + JSON trạng thái).
- Đồng hồ: đo lệch giờ máy so với sàn mỗi giờ; một nến chỉ được coi là đã đóng khi `closeTime` nhỏ hơn giờ sàn. Tự giãn cách 0,15 s giữa các lệnh, dừng khi gặp 418/429, thử lại theo cấp số nhân khi chu kỳ lỗi.

## Hành vi và giới hạn

- Quyết định tại đóng nến t, khớp tại giá mở nến t+1 (lúc đồng bộ ~20 s sau mốc nến), phí và trượt giá theo bậc thanh khoản, funding theo mốc 00/08/16 UTC. Không có hàng chờ, khớp từng phần hay tác động giá.
- Shadow bắt đầu ở nến đang chạy khi đăng ký với vốn 10.000 USDT và **mở ngay danh mục mục tiêu của quyết định gần nhất** (như một bot đã chạy liên tục sẽ đang nắm giữ), nên không phải chờ 2–7 ngày tới kỳ tái cân bằng. Các quyết định sau đó chạy theo lịch của từng ứng viên (mỗi 2, 3 hoặc 7 ngày, tại đóng nến 20:00 UTC, tức 00:00 UTC). Giá khớp ban đầu là giá mở nến bắt đầu.
- Kiểm tra tương thích với backtest: trên 6 ứng viên, lợi nhuận phát lại qua pipeline live (dữ liệu seed + API) từ 01/08 đến 31/08 trùng backtest ở 4 chữ số thập phân với 5 ứng viên; `composite-689d0027` lệch +1,0 điểm % (7,6% so với 6,6%) do trạng thái hysteresis khởi tạo từ cửa sổ dữ liệu ngắn hơn.
- Vũ trụ cố định 116 coin của dữ liệu nghiên cứu; coin bị hủy niêm yết hoặc lỗi dữ liệu thành NaN (không giao dịch), hiển thị trong thanh hệ thống.
- Các shadow ALPHA-01…21 cũ (cổng 8899, có trailing stop) không bị chạm vào.
