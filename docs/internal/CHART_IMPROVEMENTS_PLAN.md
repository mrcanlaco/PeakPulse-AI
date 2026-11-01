# Bối cảnh
Người dùng yêu cầu cải thiện component `CandlestickChart` trong tab Trading. Cụ thể là biến việc hiển thị các điểm thiết lập giao dịch (Entry, SL, TP) thành một cài đặt tùy chọn thay vì hiển thị mặc định. Người dùng cũng yêu cầu thêm các tính năng giá trị cao lấy cảm hứng từ Binance Futures. Mục tiêu là cung cấp trải nghiệm biểu đồ chuyên nghiệp, có thể tùy chỉnh dựa trên nền tảng `lightweight-charts` hiện có.

# Phương pháp tiếp cận
1. **Công tắc hiển thị Thiết lập Giao dịch**
   - Thêm state boolean `showTradeSetup` (mặc định là `false`) vào `CandlestickChart.tsx`.
   - Bọc logic `candleSeries.createPriceLine` của Entry, SL, TP1, và TP2 trong điều kiện kiểm tra `showTradeSetup`.
   - Thêm một công tắc bật/tắt bên trong menu Cài đặt Biểu đồ (Chart Settings) mới để thay đổi `showTradeSetup`.
2. **Chỉ báo lấy cảm hứng từ Binance Futures (EMA)**
   - Thêm state cho `showEMA` (mặc định là `false`).
   - Tạo một tiện ích (helper utility) để tính toán Đường trung bình động hàm mũ (EMA) chu kỳ 20 và chu kỳ 50 từ giá `close` của nến. Hiện chưa có hàm tương đương trên frontend.
   - Khi `showEMA` được kích hoạt, chèn hai `LineSeries` (EMA 20 màu vàng, EMA 50 màu tím/xanh) vào instance của biểu đồ và nạp dữ liệu đã tính toán vào đó.
3. **Cải tiến Biểu đồ Khối lượng (Volume Profile)**
   - Đồng bộ màu thanh khối lượng với tiêu chuẩn của Binance: so sánh giá `close` và `open` của nến để tô màu thanh khối lượng tương ứng (`#26a69a` cho nến tăng, `#ef5350` cho nến giảm).
   - Thêm state chuyển đổi `showVolume` (mặc định là `true`) để cho phép người dùng ẩn panel histogram phía dưới nhằm giải phóng không gian theo chiều dọc.
4. **Menu Cài đặt Biểu đồ Tổng hợp**
   - Gộp các nút rải rác trên thanh công cụ (Grid, Crosshair, Auto Scale, và các công tắc mới Show Trade Setup, Show Volume, Show EMAs) vào một menu thả xuống "Settings" thống nhất, được kích hoạt bằng icon bánh răng (`Settings`) trên thanh công cụ. Điều này mô phỏng giao diện giao dịch chuyên nghiệp và làm gọn UI.

# File quan trọng & Vị trí sửa đổi
- `frontend/src/components/CandlestickChart.tsx`: 
  - Render thanh công cụ: Thay thế các nút rời rạc bằng menu thả xuống Settings thống nhất.
  - Đường giá (khoảng dòng 320): Đổi `if (tradeSetup)` thành `if (tradeSetup && showTradeSetup)`.
  - Khởi tạo biểu đồ: Thêm `LineSeries` có điều kiện cho EMA và render `HistogramSeries` có điều kiện dựa trên `showVolume`.
  - Format dữ liệu khối lượng: Map qua `data` để set `color` dựa vào `close >= open`.
- `frontend/src/utils/indicators.ts`: Tạo file mới này để chứa logic tính toán toán học `calculateEMA` nhằm tránh làm lộn xộn component biểu đồ.

# Kiểm chứng
- Khởi chạy UI và chọn một coin có chứa trade setup từ backend.
- Xác minh các đường trade setup (Entry, SL, TP) bị ẩn theo mặc định và xuất hiện chính xác khi được bật qua menu Settings mới.
- Bật EMA qua menu Settings và xác minh các đường chu kỳ 20 và 50 render rõ ràng, đè lên chuỗi nến.
- Xác minh các thanh khối lượng được mã hóa màu (đỏ/xanh) chính xác, khớp với hướng của các cây nến tương ứng.

# Giả định & Phương án dự phòng
- Giả định rằng phiên bản hiện tại của `lightweight-charts` hỗ trợ tốt việc overlay nhiều line series (thực tế là có hỗ trợ native).
- Nếu việc tính toán EMA trên frontend cho tập dữ liệu nến cực lớn làm giảm hiệu suất render, chúng ta sẽ chuyển sang Simple Moving Average (SMA) vì nó nhẹ hơn về mặt tính toán, hoặc cache lại kết quả tính toán.