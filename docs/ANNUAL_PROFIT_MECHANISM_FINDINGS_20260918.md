# Kiểm định một năm: tìm lợi nhuận và hiểu nguồn lợi nhuận

Ngày 18/09/2026. Đã chạy thực tế đủ cửa sổ **01/09/2025–31/08/2026 UTC**, 328 mã, 10 chiến lược × 2 mức chi phí × 2 chính sách rút lãi = **40 đường tài khoản**. Có **14/40 cấu hình có lãi mô phỏng**, nhưng chưa chứng minh được lợi thế bền vững có thể đem giao dịch thật.

Kết luận chính: cấu hình lời nhiều nhất phụ thuộc mạnh vào RAVE và đường đi của vốn. Điều học được đáng tin hơn việc chọn hàng đứng đầu là: **pump không đồng nghĩa sắp dump; funding và cách phân bổ/rút vốn có thể quyết định kết quả; tài khoản có lãi tích lũy vẫn có thể hết khả năng tiếp tục giao dịch.**

## 1. Kết quả đầy đủ theo nhóm chiến lược

Vốn ban đầu 10.000 USD, mười phần vốn 1.000 USD, chỉ một phần hoạt động mỗi lúc. Phần tiếp theo chỉ được cấp khi phần trước cháy hết; không bù vốn cho phần đang thua nhưng chưa về zero. Lãi vượt seed được rút sang kho riêng trong chế độ rút lãi. Đây không phải mười vị thế đồng thời.

Số dưới đây là **lãi/lỗ toàn tài khoản**, bao gồm định giá lệnh còn mở tại cuối kỳ; đơn vị USD. Chi phí 20/60 bps tương ứng giả định tổng phí/trượt giá hai chiều 0,20%/0,60% trên notional tham chiếu, được tính theo từng lượt khớp.

| Chiến lược | Rút lãi, 20 bps | Rút lãi, 60 bps | Giữ lãi, 20 bps |
|---|---:|---:|---:|
| M48_1: long theo đà, 48h, 1x | +85,31 | −236,94 | −108,91 |
| M48_2: long theo đà, 48h, 2x | +14.093,49 | +13.238,70 | +14.100,28 |
| M168_2: long theo đà, 168h, 2x | +1.145,90 | +762,24 | −3.771,11 |
| NEG48_1: long theo đà và funding âm, 48h, 1x | +514,60 | +290,09 | +95,22 |
| E48_1: short suy yếu sau pump, 48h, 1x | −219,10 | −415,90 | −4.678,94 |
| E48_2: short suy yếu sau pump, 48h, 2x | +1.240,20 | +887,05 | −10.000,00 |
| POS48_2: short, thêm funding dương và tăng, 48h, 2x | −510,37 | −712,54 | −10.000,00 |
| SWITCH48_1: đổi long/short theo pha, 48h, 1x | −999,40 | −999,70 | −999,40 |
| HEDGE48_2: short coin + long BTC, gross 2x | +1.135,53 | +928,83 | −1.000,00 |
| PHASE48_1: long, thoát khi đà suy yếu, tối đa 48h | −864,76 | xấp xỉ −1.000,00 | xấp xỉ −1.000,00 |

Giữ tiền mặt là đối chứng lãi/lỗ 0. Bảng đủ 40 cấu hình, kể cả giữ lãi ở 60 bps, nằm trong [báo cáo máy sinh](ANNUAL_PROFIT_RESULTS_20260918.md). Điều kiện chính xác đã khóa trong [protocol](ANNUAL_PROFIT_PROTOCOL_20260918.md): M là pump24h ≥15% và ret1h >0; E là pump24h ≥25%, giảm từ đỉnh 24h ít nhất 2% và ret1h <0. Không đổi ngưỡng sau khi nhìn kết quả.

## 2. Cấu hình +14.093 USD thực sự kiếm tiền từ đâu?

M48_2, 20 bps, rút lãi: 177 lệnh được thực hiện, cháy ba phần vốn. Cuối kỳ:

- Kho lãi đã tách: **18.050,28 USD**.
- Vốn dự phòng chưa dùng: **6.000 USD**.
- Phần vốn đang hoạt động, đã MTM: **43,21 USD**.
- Tổng tài sản 24.093,49; trừ vốn ban đầu 10.000 = **+14.093,49 USD**. Không cộng trùng tiền rút và equity.

| Phân rã đóng góp tĩnh | USD |
|---|---:|
| RAVEUSDT | +14.843,43 |
| COAIUSDT | +1.253,25 |
| Tất cả phần còn lại | −2.003,20 |

Riêng RAVE đã lớn hơn toàn bộ lãi ròng. Nếu chỉ trừ đóng góp RAVE khỏi tổng thì còn **−749,94 USD**. Đây là phép phân rã trên các lệnh đã chạy, **không phải backtest loại RAVE/COAI**: bỏ coin sẽ thay đổi thời điểm vốn rảnh và các lệnh tiếp theo.

Ba lệnh RAVE tháng4 cho thấy rõ nguồn lời quan sát được:

| Entry UTC → exit UTC | Giá vào → ra | Lãi ròng USD | Funding USD |
|---|---|---:|---:|
| 09/04 11:05 → 11/04 11:05 | 0,36042 → 2,07221 | +5.610,77 | +3,50 |
| 11/04 11:05 → 13/04 11:05 | 2,07221 → 8,97173 | +7.224,99 | +576,56 |
| 13/04 11:05 → 15/04 11:05 | 8,97173 → 13,44629 | +2.007,67 | +1.015,19 |

Giá đã pump nhưng tiếp tục tăng qua nhiều cửa sổ48h. Funding nhận được hỗ trợ thêm, đặc biệt lệnh cuối. Điều này phản bác việc dùng riêng “pump cao” như bằng chứng chắc chắn phải short; **không chứng minh nguyên nhân là short squeeze hoặc thao túng**. Giá RAVE tháng4 đã được đối chiếu archive Binance có checksum, không phát hiện sai OHLC trong bản local; vẫn chưa xác minh khả năng khớp lệnh/mark thanh lý thực tế.

Phân bổ theo tháng entry của cùng tài khoản: 09/2025–01/2026 **−886,36**, 02–07/2026 **+15.051,80**, 08/2026 **−71,94 USD**. Lợi nhuận tập trung vào đoạn đã từng dùng để khám phá, không phải bằng chứng ngoài mẫu mới.

## 3. Vì sao 2x vượt xa 1x: không chỉ là nhân đôi lợi nhuận

Cùng lệnh RAVE 09/04 11:05, bản 1x chỉ còn **5,58 USD** vốn hoạt động trên tranche 1; bản 2x dùng **591,15 USD** trên tranche 4 sau các lần cháy trước đó. Bản 1x vẫn giữ 9.000 USD dự phòng vì phần đầu chưa về zero. Do vậy chênh lệch lợi nhuận chịu tác động rất lớn của **quy tắc cấp vốn phụ thuộc đường đi**, không thể kết luận “2x có lợi thế thị trường tốt hơn 1x”.

Đây là một phát hiện về thiết kế thử nghiệm: bước nghiên cứu tiếp nên tách lợi thế tín hiệu khỏi lịch cấp vốn, và phải áp dụng kích thước lệnh tối thiểu/lot size thực tế. Chưa thực hiện thay đổi này vào batch đã khóa.

## 4. Rút lãi bảo vệ tài sản, nhưng không tạo lợi thế tín hiệu

E48_2 rút lãi còn **11.240,20 USD** trong kho sau khi **cháy cả 10 phần vốn**, hết vốn hoạt động ngày 24/02/2026. Tổng tài sản vẫn lãi 1.240,20 nhưng chiến lược đã dừng vì không còn vốn được phép cấp. Bản giữ lãi mất trọn 10.000 USD. POS48_2 cũng cháy 10 phần trước hết tháng 01/2026, và rút lãi vẫn không đủ bù vốn ban đầu.

HEDGE48_2 rút lãi có +1.135,53 USD, phần ngoài hai coin lớn nhất còn +267,18 USD (ở 60 bps còn +66,70). Tuy nhiên cuối kỳ vốn hoạt động chỉ khoảng **0,00001146 USD**; có 47 lệnh dùng margin dưới 1 USD. Đây không phải một hệ thống đã chứng minh có thể tiếp tục vận hành ngoài đời. Kho dự phòng 9.000 USD không được dùng vì tranche vẫn chưa chính xác về zero.

Các đường SWITCH/PHASE cũng mòn vốn gần zero mà chưa kích hoạt tranche mới. Không được đọc mức lỗ chỉ khoảng1.000USD thành “rủi ro thấp”: phần vốn đang giao dịch gần như mất hết, còn số lớn nằm ngoài hoạt động.

## 5. Funding: dòng tiền thật trong mô phỏng, không phải nhãn giải thích mọi thứ

NEG48_1, 20bps, rút lãi có **+514,60 USD** tổng P&L, trong đó funding **+1.305,77 USD**; phần còn lại sau funding là **−791,17 USD**, đã gồm chi phí và hiệu ứng thanh lý nếu có. Dấu funding có ý nghĩa kinh tế, nhưng lợi nhuận vẫn tập trung: hai coin MUSDT/HUSDT đóng góp1.901,55USD, phần còn lại−1.386,95USD.

POS48_2 nhận funding ròng+181,54USD nhưng vẫn lỗ510,37USD. Funding dương/tăng tại entry không bảo đảm short sẽ thắng. E48_2 short còn trả funding ròng2.216,33USD trong đường tài khoản được thực hiện.

[Binance mô tả funding](https://www.binance.com/en/academy/articles/what-are-funding-rates-in-crypto-markets) là khoản thanh toán giữa hai phía hợp đồng perpetual nhằm gắn giá hợp đồng với thị trường giao ngay. Dòng tiền này không tự chứng minh ai bị ép đóng vị thế. Để kiểm chứng squeeze/crowding cần thêm OI, thanh lý, basis và dòng lệnh có thời điểm đáng tin; batch này chưa có bằng chứng nhân quả đó.

## 6. Kiểm chứng và giới hạn

- Actual run hoàn tất exit0; snapshot `3f2865593e62a24224d9db3231e4ef69d5487d41198225c72b952c00e41bcdd5`.
- 83 bài kiểm thử tập trung vượt qua; Sol Medium đã review các sửa lỗi kế toán hedge, thanh lý trước gap và provenance. **Review kết quả cuối PASS**, không tìm thấy lỗi trọng yếu trong phạm vi kiểm tra; báo cáo tại `artifacts/annual_profit_20260918/review/annual_results_review.md`. PASS xác nhận tính nhất quán của nghiên cứu, không xác nhận lợi nhuận giao dịch thật.
- Root kiểm tra40trial duy nhất và10.336record được thực hiện, tổng W+U+E−C, tổng P&L record, realized+unrealized, phân bổ coin/period đều khớp; sai lệch floating-point lớn nhất khoảng8,2e−11USD.
- Kiểm tra đầy đủ28.163tín hiệu: entry trễ5phút, feature cutoff trước decision, funding khả dụng sau60giây, tuổi funding hợp lệ, cooldown24h và cửa sổ entry đều đạt.
- 30.265.917 nến giá hợp lệ, không invalid/duplicate conflict; bản giá sạch328/328ready. 504.066hourly decisions không có feature hợp lệ, bao gồm chưa niêm yết/chưa đủ warmup; không được gọi toàn bộ là missing market data.
- Funding317mãcomplete,11partial.17event có mark không hợp lệ gồm4bị thiếu và13giữ marknull; đều trước thời điểm đủ warmup của mã. Đây không phải attestation rằng nguồn funding hoàn hảo.
- Thanh lý là proxy OHLC/MMR1%, không có lịch tier/mark liên tục; chưa mô phỏng lot size, minimum notional, chiều sâu sổ lệnh hoặc ADL. Kết quả không phải lợi nhuận thực thi đã xác minh.
- Universe local có thiên lệch lựa chọn/sống sót và gồm cả TradFi perps; không suy rộng mọi kết quả cho crypto. Sáu tháng02–07/2026 là lịch sử đã tái sử dụng, cả năm không phải holdout.
- Các cột gap/censored trong báo cáo máy sinh là số **candidate trước lọc vốn/overlap**, không phải số lệnh tài khoản đang mở. Từng tài khoản thực tế có0hoặc1vị thế/cặp còn mở tại cutoff.
- Đây là nghiên cứu mở rộng **không ML**, không phải backtest đối chứng chính xác V3Champion đủ5điều kiện và không tái hiện hai giao dịch AKE/BR của người dùng khi chưa có timestamp/khối lượng cụ thể.

## 7. Hướng nghiên cứu tiếp, không phải khuyến nghị đặt lệnh

Giữ M48_2 như ứng viên **nhạy sự kiện cực đoan**, không nâng lên chiến lược sản xuất chỉ vì đứng đầu. NEG48_1 là giả thuyết về funding đáng kiểm chứng, nhưng chưa đủ lợi thế rộng. HEDGE cần thiết kế cấp vốn có thể thực thi trước khi đánh giá bền vững.

Ưu tiên tiếp theo: lot size/minimum notional và quy tắc đóng tranche nhỏ được khóa trước; so sánh tín hiệu trên lịch vốn chuẩn hóa; walk-forward trên giai đoạn chưa dùng; kiểm định độ tập trung theo sự kiện và coin; thu thập OI/thanh lý/basis để phân biệt tiếp diễn xu hướng với squeeze. Không chỉnh các ngưỡng hiện tại để làm đẹp năm đã quan sát.

**Chưa có cơ sở để cam kết chiến lược có lợi nhuận bền vững hoặc tự động đưa kết quả này lên giao dịch thật.** Không có lệnh, triển khai, Telegram hay rút tiền thật trong nghiên cứu này.
