# Annual profit research — quy tắc khóa trước kết quả

Mục tiêu người dùng: từ kết quả đã có, tạo chiến lược giao dịch và chạy
backtest trong một năm. Ngày đăng ký: 18/09/2026. Chưa đọc outcome của batch này.

## Cửa sổ, dữ liệu, phạm vi

- Một năm đầy đủ: [2025-09-01 00:00, 2026-09-01 00:00) UTC; warmup từ
  2025-08-01. Chọn 12 tháng lịch đã kết thúc, không annualize sáu tháng.
- Universe: mọi file giá USDT trong kho local tại lúc đóng băng manifest,
  không chỉ các coin/tín hiệu thắng trước đây. Chấp nhận coin mới niêm yết
  giữa kỳ sau đủ warmup giá; không yêu cầu nó sống đủ cả năm.
- Đây vẫn là local-universe, chưa chứng minh bao gồm mọi coin đã hủy niêm
  yết. Phải công bố selection/survivorship bias, ngày bắt đầu/kết thúc và gap.
- Tạo feature trực tiếp từ giá 5m. Không dùng cohort cũ đã lọc nhãn tương lai,
  không ML, không dùng max-return/label/MFE/MAE làm đầu vào.
- Tín hiệu mỗi giờ UTC, ngay sau nến kết thúc giờ. Cần đủ 289 close liên tục
  để ret24h = close hiện tại / close 288 nến trước - 1; ret1h dùng 12 nến.
  High24h là max high của 288 nến vừa kết thúc; distance = close/high24h-1.
  Decision tại biên giờ, feature cutoff là close_time trước biên giờ.
  Entry trễ một nến: open ở decision+5 phút, không khớp giả định ngay biên giờ
  vừa nhận dữ liệu. Ghi riêng feature_cutoff, decision_time, entry_time.
- Lọc điều kiện trước cooldown 24h theo mã; cùng lúc ưu tiên pump24h giảm
  dần rồi mã tăng dần. Một trade/cặp đang mở chiếm vốn, không vào chồng lấn.
- Funding chỉ dùng settlement đã xảy ra và được coi khả dụng sau 60 giây.
  Last funding phải không quá 8h+60s so với tín hiệu; thiếu/stale thì không
  được dùng để kích hoạt chiến lược yêu cầu funding. So sánh change8h với
  settlement khả dụng tại decision trừ 8h, cùng giới hạn staleness đo từ
  event timestamp tới mốc so sánh đó. Chọn hàng mới nhất có event+60s <=
  mốc so sánh. Ghi event_time, available_time, rate và source row/hash của
  cả hai hàng. Không có hàng đạt điều kiện thì feature funding là missing.
- Download funding phân trang đầy đủ vào cache nghiên cứu riêng; không
  sửa data lake gốc. Ghi rõ nguồn, khoảng yêu cầu, số trang, lỗi, checksum
  nếu nguồn cung cấp. Không coi file 500 dòng là lịch sử đủ một năm.
- Preflight trước outcome phát hiện BTC thiếu giá 01–24/08/2026 trong lake
  gốc (không phải thiếu warmup). Được bổ sung nến thiếu vào research cache
  giá riêng từ archive Binance có checksum hoặc REST có provenance; không
  sửa lake gốc. Giữ nguyên cửa sổ một năm và mọi chiến lược. So khớp phần
  giao nhau, ghi conflicts và không âm thầm chọn nguồn có lợi. Runner phải
  dùng và hash snapshot cache đã bổ sung, không lách gap bằng bỏ tháng/mã.

## Mười chiến lược cố định

Đặt M = pump24h >=15% và ret1h >0.
Đặt E = pump24h >=25%, distance_high24h <=-2%, ret1h <0.

| ID | Entry | Side | Thoát tối đa | Leverage |
|---|---|---|---:|---:|
| M48_1 | M | long coin | 48h | 1x |
| M48_2 | M | long coin | 48h | 2x |
| M168_2 | M | long coin | 168h | 2x |
| NEG48_1 | M và last funding <0 | long coin | 48h | 1x |
| E48_1 | E | short coin | 48h | 1x |
| E48_2 | E | short coin | 48h | 2x |
| POS48_2 | E và last funding >0 và change8h >0 | short coin | 48h | 2x |
| SWITCH48_1 | pump24h >=25%; long nếu ret1h >0, short nếu E | long/short | 48h | 1x |
| HEDGE48_2 | E, loại BTC self-hedge | short coin + long BTC | 48h | 2x |
| PHASE48_1 | M | long coin | 48h hoặc phase exit | 1x |

PHASE48_1: ở decision giờ đầu tiên STRICTLY sau entry có ret1h <0 và
distance_high24h <=-5%, thoát tại open decision+5 phút. Ret/high dùng chính
rolling windows 12/288/289 nến đóng như entry. Không dùng low/high tương lai để
quyết định exit; nếu không có phase exit thì giữ tối đa 48h. Đây là thoát
theo tín hiệu, không phải giả định có thể khớp stop tại giá cố định.

M168_2 là tham chiếu nhạy outlier, không ưu tiên chỉ vì đứng đầu batch cũ.
NEG/POS là kiểm tra giả thuyết funding, không khẳng định đã nhận diện squeeze.
Không thêm cấu hình/đổi threshold sau khi nhìn lợi nhuận batch này.

## 40 đường tài khoản và kế toán

Mỗi chiến lược chạy tổng phí/trượt giá hai chiều 20/60 bps và hai chính sách
rút lãi/không rút lãi: 10 x 2 x 2 = 40 đường tài khoản. Cả hai chính sách
được đăng ký trước, không chọn chính sách sau khi xem đường vốn.

Vốn mới C=10.000 USD; mười tranche seed 1.000; lỗ làm nhỏ tranche, không bù
lại. Chỉ cấp tranche kế tiếp khi tranche cũ hết vốn. Không nạp thêm tiền.
Rút lãi = chuyển phần vượt seed sau trade đóng vào vault W, không tái nạp.
Không rút lãi = giữ toàn bộ equity tranche chịu rủi ro. Profit = W+U+E-C.
Hai leg hedge có quantity/margin riêng mỗi leg một nửa; 2x trên từng nửa
tạo tổng gross notional bằng 2x equity tranche, không phải 4x. Tính phí trên
notional mỗi leg; return cặp = 0,5*return_coin + 0,5*return_BTC. Không net
margin. Leg thanh lý mất toàn bộ nửa margin của nó, không thu funding sau
thời điểm kết thúc; leg còn lại tiếp tục, vốn cặp chưa được tái sử dụng.

Giữ engine account đã kiểm thử, nhưng kiểm tra lại seams dữ liệu mới.
Funding theo settlement thực và notional hiện tại, đúng dấu. Timestamp
settlement vài mili giây sau biên nến phải được xử lý đúng thứ tự sự kiện,
không lùi funding về trước khi nó được quan sát. Open tại cutoff là MTM,
không rút lãi chưa thực hiện và không thu phí exit giả định như đã khớp.

### Khóa thứ tự sự kiện trước outcome (review Sol, 18/09)

- Tại cùng timestamp: hoàn tất xử lý rủi ro của nến vừa kết thúc; đóng lệnh
  time/phase đã hẹn tại open; funding cho các vị thế còn tồn tại; decision
  mới từ dữ liệu khả dụng; rồi entry đã hẹn. Cấm vị thế mới nhận/trả funding
  tại đúng timestamp entry; lệnh đã thoát ở đúng timestamp settlement cũng
  không nhận/trả settlement đó. Funding cashflow nằm trong (entry, exit),
  không áp dụng độ trễ khả dụng 60s vốn chỉ dành cho feature tín hiệu.
- Tại cutoff không có fill đóng: vị thế còn mở chịu settlement tới và gồm
  cutoff, rồi được MTM. Phải tách trường hợp này khỏi exit thật.
  Vì vậy cache funding phải bao gồm cả event đúng cutoff: nếu downloader
  dùng end-exclusive thì yêu cầu tới cutoff+1ms (2026-09-01T00:00:00.001Z),
  không kéo dài trading window hoặc dùng event xảy ra sau cutoff.
- OHLC 5m không cho biết cực trị nằm trước hay sau funding bên trong nến.
  Với funding intrabar, kiểm tra rủi ro cả thứ tự trước và sau settlement;
  nếu bất kỳ thứ tự nào chạm maintenance thì dùng thanh lý bảo thủ vào cuối
  nến, ghi cờ intrabar_order_proxy. Không gọi đây là liquidation thật.
  Chỉ các settlement trước thời điểm leg kết thúc được tính; không kéo
  funding/biến động từ nến sau về nến trước. Nến đang giữ tới phase fill
  vẫn phải được kiểm tra rủi ro trước khi xử lý fill đó.
- Nếu liquidation và phase/time fill cùng boundary, liquidation của nến
  vừa kết thúc có ưu tiên; nếu horizon và phase fill cùng lúc, dùng time exit.
- Hash protocol, danh sách universe, từng file giá/funding trước outcomes;
  phát hiện thay đổi nguồn khi chạy thì dừng, không trộn hai snapshot.
  Manifest ghi venue Binance USD-M, hợp đồng local USDT có identity chưa
  được attested, UTC open_time và close_time=open+5m-1ms, duplicate policy.
  Duplicate xung đột không được tùy ý chọn giá có lợi; coi timestamp invalid.
  Báo số hourly decision bị thiếu warmup/giá trước entry, không chỉ gap sau entry.

Nếu funding chưa đủ: vẫn chạy scenario minh bạch với các bản ghi quan sát,
gắn cờ coverage và không gọi là net profit đã xác minh. Gap giá sau entry
không được bỏ trade để tái dùng vốn: đường vốn unresolved/non-rankable.
Không dùng khả năng nhìn thấy dữ liệu tương lai để lọc trade lúc entry.

Thanh lý chỉ là proxy OHLC với maintenance ratio giả định 1%, mất toàn bộ
margin leg nếu chạm. Chưa có historical tiers/mark liên tục/execution nên
tất cả kết quả còn provisional, kể cả đủ giá và funding. Không có trade thật.

## Đối chứng và tiêu chí báo cáo

- Giữ tiền mặt: profit 0. Đủ 40 trial, kể cả lỗ, hết vốn, unresolved.
- Đường tài sản và cashflow, số lệnh, burns, vault/reserve/equity, lãi chưa
  chốt, tổng phí/funding, gap và funding coverage; audit từng lệnh đã vào.
- Bảng tháng: phân bổ P&L theo tháng entry phải ghi nhãn rõ, không giả NAV
  monthly return. Closed-event drawdown không phải full intratrade drawdown.
- Phân rã coin/lệnh lớn nhất: phần còn lại là attribution tĩnh, không gọi
  là backtest loại coin. Ghi các đợt lời cực đoan và khả năng kiểm chứng.
- Đối chiếu 1x/2x, chi phí, rút lãi, giữ 48h/168h, phase exit, funding sign,
  long/short/hedge. Những so sánh này là mô tả, không chứng minh nhân quả.
- Báo riêng các đoạn 09/2025–01/2026, 02–07/2026, 08/2026 bằng attribution
  của đường tài khoản đầy đủ. Đoạn 02–07 đã dùng để khám phá; không gọi cả
  năm là holdout. Chưa xác minh các đoạn còn lại chưa từng được nghiên cứu.
- Xác minh số năm thực chạy, nguồn tín hiệu, không dùng nhãn tương lai,
  bảo toàn vốn, phí, funding, censoring bằng tests và review độc lập.

Không cam kết sẽ có chiến lược lời. Hoàn tất mục tiêu là có chiến lược cụ
thể, actual backtest đủ một năm và kết quả kiểm chứng được với giới hạn
được công bố; không phải ép lợi nhuận dương hoặc tự triển khai giao dịch.
