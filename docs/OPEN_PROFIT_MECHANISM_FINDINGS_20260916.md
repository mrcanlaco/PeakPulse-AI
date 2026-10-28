# Open-profit batch 01: lợi nhuận đến từ đâu?

Ngày 16/09/2026. Đã chạy đủ 120 cấu hình trên cửa sổ UTC 01/02–01/08/2026.
Đây là kết quả khám phá từ dữ liệu lịch sử đã được xem, không phải holdout mới,
chứng nhận lợi nhuận thực hay căn cứ triển khai giao dịch tự động.

## Kết luận chính

Có 23/120 cấu hình có lợi nhuận mô phỏng dương. Tuy nhiên, chưa tìm thấy bằng
chứng đủ mạnh cho một lợi thế giao dịch ổn định. Cấu hình đứng đầu phụ thuộc
mạnh vào hai sự kiện cực đoan, đường đi của vốn và việc rút lãi. Funding của
chính hai sự kiện này còn thiếu, nên chưa thể chứng nhận lợi nhuận sau chi phí.

Điều đáng nghiên cứu tiếp không chỉ là “pump rồi dump”, mà còn là giai đoạn
tiếp diễn của pump, funding âm trong khi giá tăng, và thời điểm chuyển pha.
Đây là giả thuyết rút ra để kiểm định sau, không phải quy luật nhân quả đã chứng minh.

## Phạm vi đã chạy

- 18.810 dòng tín hiệu, 180 mã đã pump ít nhất 15%; không phải toàn thị trường.
- Năm hướng: long theo đà, short đảo chiều, short đảo chiều có funding,
  chuyển long/short, và short coin kết hợp long BTC.
- Giữ 12/48/168 giờ; đòn bẩy 1/2/5/10; tổng phí và trượt giá hai chiều 20/60 bps.
- Không TP/SL chủ động. Có mô phỏng thanh lý theo OHLC và maintenance giả định 1%.
- Vốn ban đầu 10.000 USD; tối đa mười tranche 1.000 USD; một vị thế hoặc một
  cặp tại một thời điểm. Không nạp thêm, không tự bù lỗ tranche còn sống.
- Sau lệnh đóng, equity vượt 1.000 USD được chuyển vào kho tiền bảo vệ;
  tiền này không được tái đầu tư trong cấu hình cơ sở.

Tất cả 120 trial có đường giá xác định theo dữ liệu hiện có, không có gap giá
sau entry. Điều này KHÔNG xác minh được funding, thanh khoản hay thanh lý thật.
Các cấu hình dùng cùng lịch sử và có giao dịch trùng nhau, không phải 120 mẫu độc lập.

## Kết quả theo nhóm

| Nhóm | Số cấu hình dương / 24 | Cấu hình có profit cao nhất trong nhóm | Profit trên 10.000 USD |
|---|---:|---|---:|
| Long theo đà | 11 | 168h, 2x, 20 bps | +22.116,82 |
| Chuyển long/short | 1 | 168h, 5x, 60 bps | +13.342,14 |
| Short có funding | 7 | 48h, 10x, 20 bps | +2.900,36 |
| Short đảo chiều | 2 | 48h, 5x, 20 bps | +582,72 |
| Short coin + long BTC | 2 | 168h, 2x, 20 bps | +357,65 |

Đây là các cực đại đã chọn trên 24 cấu hình mỗi nhóm, không phải ước lượng
hiệu suất tương lai. Nhóm short không dùng đủ năm điều kiện Champion/LightGBM;
không được coi bảng này là đánh giá trực tiếp mô hình V3 hiện hành.

Ba cấu hình đứng đầu của nhóm chuyển hướng, short có funding và short đảo
chiều đều đã đốt hết mười tranche trong mô phỏng. Chúng vẫn có profit tổng
dương vì tiền đã rút vượt vốn ban đầu; nhưng không còn vốn giao dịch nếu
không nạp lại. “Hết vốn vận hành” khác với “mất toàn bộ tài sản”.

### Một dấu vết ít tập trung hơn, không phải chọn lại winner

Trong 23 cấu hình dương, 20 cấu hình có tổng P&L của hai lệnh lớn nhất vượt
profit ròng. Một đối chiếu đáng lưu ý trong grid có sẵn là long theo đà 48h,
1x: profit +3.405,42 USD ở 20 bps và +3.094,91 USD ở 60 bps, với 86 lệnh và
không cháy tranche trong mô phỏng. Ở 20 bps, hai lệnh lớn nhất là ORDI
(+1.180,66 USD) và VELVET (+1.002,57 USD); P&L cộng của 84 lệnh còn lại vẫn
dương +1.222,19 USD. Đây vẫn chỉ là phân rã tĩnh, không phải thử loại lệnh.

Theo tháng entry, cấu hình 48h/1x có năm tháng P&L dương và tháng 7 âm;
không phải năm tháng holdout độc lập. Vốn tranche cuối chỉ còn 130,82 USD,
dự trữ 9.000 USD và kho bảo vệ 4.274,60 USD. Kết quả này gợi ý hướng tiếp
diễn đáng xác minh thêm, chứ chưa xác nhận lợi thế. Nó chịu cùng vấn đề
funding và chọn mẫu; chưa được chạy riêng hai diagnostic chỉ đăng ký cho
cấu hình đứng đầu. Không đổi winner hoặc bổ sung cấu hình sau kết quả.

## Cấu hình đứng đầu: kiểm tra sổ vốn

Quy tắc: pump 24h >=15%, return 1h >0, long tại open nến 5m tiếp theo, giữ
168h nếu không thanh lý; 2x và 20 bps tổng phí/trượt giá hai chiều.

| Khoản | USD |
|---|---:|
| Vốn ban đầu | 10.000,00 |
| Tiền đã chuyển vào kho bảo vệ | 25.976,66 |
| Vốn dự trữ chưa cấp | 6.000,00 |
| Equity tranche còn lại, không có vị thế mở | 140,16 |
| Tổng tài sản cuối kỳ | 32.116,82 |
| Profit tổng sau chi phí đã mô hình hóa | +22.116,82 |

27 lệnh được thực hiện, 1.840 cơ hội bị bỏ qua vì vốn đang bận; 24 thoát theo
thời gian và 3 thanh lý proxy. Cấp bốn tranche, cháy ba tranche. Không còn lãi
chưa chốt ở cutoff. Tổng P&L của 27 lệnh khớp với tổng tài sản trừ vốn mới.
Không dùng tổng tiền đã rút làm profit vì còn phải tính phần vốn đã mất.

## Hai lệnh chi phối kết quả

| Lệnh đã thực hiện, UTC | P&L mô phỏng USD |
|---|---:|
| RAVEUSDT, 09/04 12:05–16/04 12:05 | +18.106,19 |
| HUSDT, 10/06 00:05–17/06 00:05 | +5.124,89 |
| Tất cả 25 lệnh còn lại | -1.114,26 |

Hai lệnh đóng góp 23.231,08 USD, bằng khoảng 105% profit ròng. Đây chỉ là
phân rã P&L của đường vốn đã xảy ra. KHÔNG phải backtest loại hai mã: nếu bỏ
lệnh, thứ tự vào lệnh và số vốn cho những lệnh sau sẽ thay đổi.

Đối chiếu trực tiếp Parquet với timezone UTC:

- RAVE: entry 0,36384; exit 14,9446, tương đương giá tăng khoảng 4.007,46%
  trong dữ liệu bảy ngày. Không có bản ghi funding nào trong cửa sổ lệnh;
  file funding chỉ bắt đầu từ 06/06. Kết quả cơ sở đã giả định funding bằng 0.
  Cần xác minh nguồn giá, điều chỉnh mã/hợp đồng, funding và khả năng khớp của
  biến động cực đoan này trước khi coi đây là lợi nhuận có thể thực hiện.
- H: entry 0,10086; exit 0,28262, giá tăng khoảng 180,21%. Return trên margin
  ở 2x gồm +360,42% từ giá, +323,76% từ funding quan sát và -0,76% chi phí,
  tổng +683,42%. Có 64 settlement quan sát, 56 rate âm; nhưng file chỉ bắt
  đầu từ 13/06 11:00 UTC, thiếu phần đầu của lệnh bắt đầu 10/06.
- Cả hai file funding hiện chỉ có 500 dòng. Có file không đồng nghĩa có đủ
  lịch sử; không được diễn giải đoạn thiếu là thị trường thực sự không thu phí.

Funding âm cộng giá tăng phù hợp với giả thuyết phe short đang chịu chi phí
trong một đợt tăng tiếp diễn. Tuy nhiên, riêng dữ liệu giá và funding không
chứng minh có short squeeze, thao túng, hay ai đã buộc phải đóng vị thế.

## Đối chứng đã khóa trước khi xem kết quả

| Thay đổi so với cấu hình đứng đầu | Profit USD |
|---|---:|
| Cơ sở: 168h, 2x, rút lãi | +22.116,82 |
| Tổng phí/trượt giá 60 bps | +21.396,88 |
| Funding stress bất lợi thêm 10 bps/notional hiện tại mỗi 8h | +18.413,98 |
| Không chuyển lãi vào kho bảo vệ, tiếp tục để vốn chịu rủi ro | -3.838,33 |
| 168h, 1x | +992,40 |
| 168h, 5x | +6.752,74 |
| 168h, 10x | -10.000,00 |
| 48h, 2x | +3.604,61 |
| 12h, 2x | -1.474,30 |

Funding stress là kịch bản giả định thêm chi phí, không phải cận xấu nhất của
funding thật. Không chọn lại cấu hình sau stress. Giữ 1x/2x không tạo đường
tài khoản giống nhau: thanh lý làm thay đổi thời điểm vốn rảnh và các cơ hội
tiếp theo. Vì vậy không được coi chênh lệch 1x–2x là khuếch đại tuyến tính.

Đối chứng không rút lãi cho thấy bảo vệ khoản thắng lớn có vai trò quyết định
trên đường lịch sử này. Nó không chứng minh rút lãi luôn tốt hơn, hoặc có thể
biến một tín hiệu kỳ vọng âm thành chiến lược có kỳ vọng dương.

## Phân bố theo tháng của tài khoản đứng đầu

Gán toàn bộ P&L mỗi lệnh vào tháng entry, không phải return NAV theo tháng:

| Tháng entry | P&L USD |
|---|---:|
| 02/2026 | +1.105,23 |
| 03/2026 | +886,80 |
| 04/2026 | +17.434,39 |
| 05/2026 | -478,02 |
| 06/2026 | +4.769,46 |
| 07/2026 | -1.601,05 |

Các bảng month/symbol theo toàn bộ cơ hội trong báo cáo chạy máy khác với
bảng này: nhiều cơ hội không được tài khoản thực hiện do chồng lấn vốn.

## Hiểu được gì, chưa hiểu được gì?

1. **Pump không tự động đồng nghĩa sắp dump.** Batch này bắt được các đợt
   tăng tiếp diễn rất lớn; short sau một mức giảm nhỏ từ đỉnh chưa đủ để
   bảo đảm đảo chiều. Chưa có kiểm định nhân quả hay so sánh nhóm đối chứng
   đủ mạnh để xác định khi nào pump chuyển thành dump.
2. **Lợi nhuận có thể tập trung ở đuôi phân phối.** Số lời cao nhất đến từ
   rất ít lệnh. Tỷ lệ thắng hoặc profit trung bình không thể thay thế việc
   kiểm tra từng sự kiện và xác suất gặp lại chúng ngoài mẫu.
3. **Funding không chỉ là bộ lọc tâm lý.** Nó trực tiếp thay đổi cashflow;
   H có phần funding quan sát gần bằng phần lãi từ giá. Lịch sử thiếu có
   thể làm sai cả lợi nhuận lẫn thời điểm thanh lý.
4. **Đòn bẩy và đường vốn là một phần của chiến lược.** 10x không tốt hơn
   2x; rút lãi thay đổi khả năng giữ được khoản thắng sau các tranche cháy.
5. **Hedge BTC không tự chứng minh cân bằng rủi ro.** Equal-notional không
   phải beta-neutral, và một leg cháy có thể để leg còn lại chịu rủi ro riêng.

## Điều kiện để tiến từ giả thuyết tới bằng chứng

Ưu tiên tiếp theo là xác minh hai sự kiện chi phối, bổ sung funding đầy đủ,
mark price và điều kiện hợp đồng/khớp lệnh. Sau đó khóa trước một số giả
thuyết về tiếp diễn/đảo chiều và kiểm tra trên cửa sổ chưa dùng để lựa chọn.
Không mở thêm hàng nghìn cấu hình trên cùng sáu tháng chỉ để làm số đẹp hơn.

Chưa thay đổi V3 đang chạy, chưa deploy, chưa gửi tín hiệu Telegram, chưa
đặt lệnh hay rút tiền thật. Kết quả hiện tại là ứng viên nghiên cứu, không
phải khuyến nghị dùng 2x hoặc giữ lệnh bảy ngày bằng tiền thật.

## Nguồn và kiểm tra

- Registry: `docs/OPEN_PROFIT_BATCH_01_20260916.md`.
- Kết quả đầy đủ: `artifacts/open_profit_20260916/search_results.json`.
- Báo cáo chạy: `docs/OPEN_PROFIT_SEARCH_20260916.md`.
- Nguồn giá/funding: Parquet cục bộ trong `D:/Quant-trading/data_lake`.
- 27 kiểm thử mô phỏng/account đã pass; kiểm tra độc lập 120 trial xác nhận
  bảo toàn vốn và tổng P&L. Kiểm thử đúng code không xác minh chất lượng dữ liệu.
