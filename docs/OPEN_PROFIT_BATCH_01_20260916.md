# Open-profit batch 01 — đăng ký trước kết quả

Đăng ký ngày 16/09/2026 trước khi tính kết quả của batch. Đây là tìm kiếm
khám phá hữu hạn, không phải chứng nhận lợi nhuận hay cấp quyền giao dịch thật.

## Phạm vi đã khoá

- Nguồn tín hiệu: toàn bộ dòng pump >=15% trong cohort_pre_outcome.csv của
  khảo sát V3 sáu tháng; không chỉ các dòng selected_24h. Đây là universe coin
  đã pump, không phải toàn thị trường; nguồn PIT đã qua lọc nhãn 24h cũ.
- Cửa sổ tín hiệu và chốt sổ: [01/02/2026, 01/08/2026) UTC. Ngày cuối tháng 7
  thiếu một phần feature. Giá và funding từ kho D:/Quant-trading/data_lake,
  chỉ đọc. Các tháng này là lịch sử đã xem, không phải holdout mới.
- Không ML, không fitting, không dùng MFE/MAE/nhãn tương lai để chọn lệnh.
- Lọc điều kiện trước cooldown 24h theo mã. Cùng thời điểm: pump giảm dần,
  rồi symbol tăng dần. Tài khoản chỉ giữ một trade hoặc một cặp tại một thời
  điểm; không nhân vốn cho các tín hiệu chồng lấn.
- Tín hiệu chỉ dùng nến đã đóng. Entry tại open nến 5m kế tiếp. Không được
  dùng high/low nến tín hiệu như diễn biến sau entry.

## 120 cấu hình cố định

Năm family:

1. momentum_long: pump24h >=15%, return1h >0; long coin.
2. exhaustion_short: pump24h >=25%, distance_high24h <=-2%, return1h <0;
   short coin.
3. funding_fade_short: exhaustion_short cộng percentile funding >=80%,
   funding_change8h >0, persistence >0; short coin.
4. regime_switch: pump24h >=25%; short khi distance <=-2% và return1h <0;
   long khi return1h >0; còn lại không vào.
5. hedged_fade: điều kiện exhaustion_short; short coin và long BTC, mỗi leg
   một nửa gross notional và một nửa margin; loại coin BTC để tránh self-hedge.

Mỗi family kết hợp horizon 12/48/168 giờ, leverage 1/2/5/10 và tổng phí cộng
trượt giá hai chiều 20/60 bps: 5 x 3 x 4 x 2 = 120 trial. Đây là ngân sách
tính toán batch đầu, không phải giới hạn đòn bẩy do người dùng đặt ra.
Không stop hoặc TP chủ động trong batch này. Exit theo thời gian, proxy
liquidation hoặc cutoff. Tiền mặt không giao dịch là comparator 0 lợi nhuận.
Không thêm cấu hình sau khi nhìn kết quả để thay winner của cùng batch.

## Kế toán tài khoản

Vốn mới C=10.000 USD, dự trữ U=10.000, vault W=0. Cấp 1.000 cho tranche
đầu; phần lỗ làm giảm equity tranche, không tự bù lại 1.000. Khi tranche
không còn vốn, lấy tranche tiếp theo từ U, tối đa 10 tranche. Tái sử dụng
tranche còn sống cho trade tiếp theo với leverage cố định theo cấu hình.
Sau trade đã đóng, phần equity vượt seed 1.000 được chuyển vào W. Không
rút lãi MTM chưa đóng và không tái nạp W. Tổng lợi nhuận = W+U+E-C.
Phí/funding đã nằm trong trade return thì không trừ lại trong account ledger.

## Mô phỏng theo giả định, không phải liquidation thực

Mọi kết quả batch đều PROVISIONAL, kể cả dương. Chưa xác minh continuous
mark price, lịch sử margin tiers/giới hạn leverage, funding coverage và khả
năng khớp thực. Không gọi cấu hình 10x là được sàn chấp nhận tại từng thời điểm.

Proxy ghi rõ: trade OHLC được dùng làm mark proxy; maintenance ratio giả định
1% gross notional hiện tại. Trên mỗi leg, quantity cố định từ entry và margin
được cấp. Liquidation proxy xảy ra nếu margin + P&L chưa thực hiện - chi phí
và funding luỹ kế <= 1% |quantity x adverse_price|. Dùng low cho long và high
cho short; khi chạm, giả định mất toàn bộ margin leg, không cứu hộ, không dùng
công thức 1/leverage làm giá thanh lý. Đây là phép stress theo giả định, không
chứng minh giá thanh lý thật hay cận trên/cận dưới lợi nhuận thực tế.

Hai leg hedge dùng margin riêng, không bù/net margin; một leg cháy không tự
đóng leg kia. Thu phí entry và exit trên notional khớp của từng leg. Funding
quan sát được tính đúng dấu từng leg và thời điểm nắm giữ. Thiếu lịch sử hoặc
mark settlement phải có flag; dùng close proxy chỉ khi rate thực có, không
biến proxy thành coverage. Funding vắng mặt được giả định bằng 0 cho scenario
cơ sở, không gọi là miễn funding thật. Báo độ nhạy chi phí funding thiếu thay
vì chứng nhận net profit; mức funding bất lợi 10bps/notional mỗi 8h là stress
diagnostic đã đăng ký, không phải trial mới để chọn winner.

Mọi gap giá phải được báo và không coi như loss/zero return. Open trade tại
cutoff được định giá, giữ riêng unrealized P&L, không rút vào W. So sánh cùng
calendar cutoff, báo riêng mức censored theo horizon. Đường tài sản chỉ quan
sát tại sự kiện đóng lệnh không được gọi là full intratrade max drawdown.

Làm rõ trước kết quả: nếu trade đã được chọn vào nhưng đường giá tương lai
thiếu, không được hồi tố bỏ trade rồi tái dùng vốn cho trade khác. Đường tài
khoản bị đánh dấu unresolved/non-rankable và vốn bị giữ tới cutoff; không
giả định P&L bằng 0. Thiếu dữ liệu entry có thể ghi rejected-at-entry riêng.

## Chọn ứng viên và giải thích cơ chế

Lưu cả 120 trial, error, missing data và các đường vốn; không chỉ winner.
Xếp hạng khám phá theo tổng profit trên C cố định; báo kèm độ nhạy cost,
leverage, month, mã, số lệnh, lợi nhuận còn mở, vốn bị chiếm dụng, burns,
operating exhaustion và wealth ruin. Không coi 120 trial là 120 quan sát độc
lập để tính xác suất ruin. Không kết luận một account path là xác suất thật.

Phân tích winner có phụ thuộc một coin/tháng, chênh lệch long/short,
funding giả định, vài cú tăng/giảm cực đoan hoặc leverage không. Đối chiếu
cấu hình tương ứng 1x, chi phí cao và horizon khác; đó là kiểm tra độ nhạy,
không phải chứng minh nhân quả. Báo cả giả thuyết bị phản bác. Nếu không có
ứng viên đáng tin cậy sau các kiểm tra, kết luận chưa tìm thấy thay vì tối ưu
tiếp đến khi có số đẹp. V3 là tham chiếu khác contract, không gộp precision
cũ với profit toàn tài khoản mới.

Diagnostic đã đăng ký trước outcome: giữ nguyên candidate đứng đầu theo
profit cơ sở và chạy lại cùng chuỗi cơ hội với withdraw_profits=False để
phân biệt ảnh hưởng rút lãi/bảo vệ vốn khỏi edge tín hiệu. Đây không phải
candidate bổ sung để chọn lại winner. Không diễn giải thay đổi profit của
một path là bằng chứng chiến lược rút lãi luôn tốt hơn.
