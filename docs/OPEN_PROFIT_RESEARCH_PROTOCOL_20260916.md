# OPEN PROFIT RESEARCH PROTOCOL — 2026-09-16

## Mục đích và trạng thái

Đây là protocol mới cho một nhánh nghiên cứu mở về khả năng tạo lợi nhuận ở
cấp tài khoản, gồm ba hướng **long, short và balanced**. Nhánh này không giả
định trước TP 20%, không ép mọi lệnh kết thúc sau 48 giờ và không bắt buộc
phải có stop cố định. Một vị thế được phép giữ tới khi điều kiện thoát biến
động xảy ra, bị thanh lý, hoặc tới hạn đánh giá hữu hạn; tại hạn đánh giá,
vị thế còn mở phải được mark-to-market và tính vào tài sản, không được bỏ qua.

Protocol này là research-only. Không có bảo đảm chiến lược có lãi; kết quả
null, âm, hoặc không đủ dữ liệu đều là kết quả hợp lệ và phải được báo cáo.
Tài liệu này không cấp quyền thay đổi live, rút tiền thật, hay promotion.

### Quan hệ với protocol cũ và V3

- V3 comparator hiện tại là một **mốc so sánh**, không phải anchor, mục tiêu
  lợi nhuận hay giới hạn thiết kế của nhánh open-profit.
- Tài liệu ALPHA_SEARCH_PROTOCOL_20260913.md được giữ nguyên. Các gate cũ như
  precision 50%, horizon 48 giờ, hay cấu trúc TP/stop cũ không được âm thầm
  sửa hoặc áp dụng như gate chung cho protocol mới.
- Metric lợi nhuận ở tài liệu này thay thế metric precision cũ **chỉ trong
  nhánh này**. Không được dùng nó để suy ra quyền promotion cho V3 hoặc live.
- Báo cáo phải đặt V3 comparator cạnh candidate mới trên các cohort phù hợp,
  nhưng phải ghi rõ rằng hai contract có thể khác nhau.

## 1. Ngân sách, tranches và chế độ tài khoản

### Ví dụ minh họa, không phải ràng buộc người dùng

Ví dụ tổng vốn 10.000 và chia thành 10 tranche, mỗi tranche 1.000, chỉ là
baseline minh họa để làm cho quy mô và kế toán dễ kiểm tra. Người dùng không
bị ràng buộc bởi tổng vốn 10.000, số tranche 10, hay kích thước 1.000.
Mọi nghiên cứu phải ghi rõ tổng ngân sách, số tranche và cách cấp vốn thực tế
trong manifest của trial.

### Mặc định: isolated, tuần tự, không cứu hộ

Mặc định nghiên cứu là các tranche isolated chạy tuần tự:

1. Mỗi tranche có ngân sách khởi tạo cố định và ledger riêng.
2. Chỉ mở tranche tiếp theo theo lịch đã đăng ký; không bơm thêm tiền để cứu
   một tranche đang lỗ hoặc đã cháy.
3. Lợi nhuận đã bảo vệ khỏi tranche không tự động quay lại làm vốn cho tranche
   sau. Compounding hoặc tái phân bổ lợi nhuận chỉ là một variant phải đăng ký
   trước.
4. Baseline có một protected-profit vault bên ngoài trading để giữ tiền đã rút,
   nhưng vault này không phải vốn cứu hộ và không được dùng để cứu lệnh hoặc
   mở thêm trading trong baseline. Không có rescue funding hay reserve bên
   ngoài dành cho việc tiếp tục giao dịch. Mọi khoản nạp ngoài baseline phải
   bị đánh dấu là external contribution, làm hỏng so sánh baseline nếu không
   phải một variant đã đăng ký.
5. Nếu một tranche cháy toàn bộ, khoản lỗ vẫn nằm trong tổng tài sản của
   portfolio. Nếu toàn account không còn đủ tài sản hoặc margin theo contract,
   ghi nhận account ruin và không tự khởi động lại bằng tiền ngoài.

Chạy đồng thời là một variant riêng. Variant concurrent phải bị giới hạn bởi
đúng một ngân sách tổng đã đăng ký: tổng initial margin, free margin bị khóa,
pending fees và nghĩa vụ funding của mọi tranche không được vượt ngân sách
đó. Không được nhân bản cùng một đồng vốn thành nhiều đường backtest.

Người dùng không đặt drawdown cap. Vì vậy nghiên cứu không tự loại một
candidate chỉ vì drawdown cao, và có thể để đường vốn đi tới mất toàn bộ
tranche hoặc toàn account. Tuy nhiên, mỗi báo cáo bắt buộc phải trình bày xác
suất ruin, đuôi lỗ và vốn bị chiếm dụng; chấp nhận ruin không biến ruin thành
dữ liệu thành công.

### Leverage

Không áp một leverage cap tùy ý do người dùng đặt ra. Dải leverage nghiên cứu
phải vẫn nằm trong giới hạn thực tế point-in-time của instrument, account và
venue: position limit, initial/maintenance margin tier, lot/notional minimum,
borrow/short availability, funding, và mọi giới hạn thanh lý. Không được
gọi leverage cao hơn giới hạn đó là lợi nhuận hợp lệ bằng cách ngoại suy.

## 2. Định nghĩa tài sản và lợi nhuận

### Công thức duy nhất cho tổng lợi nhuận

Tại mỗi thời điểm chốt sổ, dùng ba bucket tài sản không chồng lấn:

~~~text
Tổng lợi nhuận
  = protected-profit vault balance (W)
  + unallocated research reserve cash (U)
  + allocated tranche marked-to-market equity (E)
  - cumulative new external capital contributions (C)
~~~

Trong đó:

- **W** là số dư hiện tại của protected-profit vault. Cumulative withdrawal
  history được lưu riêng; không thay số dư hiện tại bằng tổng lịch sử để tránh
  double-count.
- **U** là tiền mặt research chưa phân bổ vào tranche, sau phí và nghĩa vụ đã
  phát sinh; U không nằm trong E.
- **E** là cash/collateral, margin và unrealized P&L của các tranche đang
  được phân bổ, mark-to-market theo contract; E không chứa U hoặc W.
- **C** là tổng vốn mới thực sự đi từ bên ngoài vào research portfolio, gồm
  vốn ban đầu và nạp thêm; chuyển tiền giữa W, U và E không làm tăng C.

Chuyển U/E sang vault một khoản x làm W tăng x và U/E giảm x; tái đầu tư từ
vault làm W giảm x và U/E tăng x. Cả hai là internal transfer, không phải
alpha hoặc external contribution mới, nên tổng lợi nhuận giữ nguyên. Chỉ tiền
mới từ bên ngoài mới tăng C. Withdrawal event, reinvestment event và số dư
trước/sau đều phải nằm trong ledger.

Ledger phải có một dòng cho deposit, fill, fee, slippage, funding, liquidation,
mark-to-market, withdrawal và đóng vị thế. Phí, lỗ, funding và liquidation đã
giảm cash/equity hoặc trade P&L thì không được trừ lại lần thứ hai. Lỗ của
tranche đã cháy, vị thế đang lỗ, phí chưa kết toán, funding, slippage và phí
thanh lý đều phải còn trong ledger.

### Quy tắc rút lợi nhuận

Chỉ được ghi một withdrawal là profit withdrawal khi đồng thời:

- lợi nhuận đã **realized net** sau fee, slippage, funding và nghĩa vụ liên
  quan;
- số tiền thực sự là free margin sau khi tính cả lỗ chưa thực hiện và margin
  cần thiết của vị thế đang mở;
- withdrawal event và số dư trước/sau được ghi đầy đủ trong ledger.

Không được rút dựa trên unrealized gain rồi gọi đó là realized profit. Không
được dùng protected withdrawal để che một tranche đang lỗ, hoặc tính cùng một
chuyển tiền vừa là withdrawal vừa là alpha. Nếu tiền từ W được nạp trở lại
U/E, ghi đó là internal transfer: giảm W và tăng U/E; C không đổi. Chỉ vốn
mới từ bên ngoài mới làm tăng C.

## 3. Contract dữ liệu và tính trung thực của mô phỏng

### Bằng chứng tối thiểu

Một kết quả được gọi là verified-profit evidence chỉ khi có dữ liệu point-in-
time đủ cho:

- mark-price path liên tục hoặc độ phân giải đã chứng minh được cho toàn thời
  gian vị thế;
- maintenance-margin tiers, initial margin, position limits và quy tắc
  liquidation tương ứng với thời điểm/instrument/venue;
- funding history có coverage và timestamp thật, gồm khoảng thiếu và cách
  tính funding thực tế;
- giá khớp, phí, slippage, min lot/notional, khả năng short/borrow và các
  ràng buộc account/venue;
- trạng thái cash, margin, open position và nghĩa vụ funding sau từng event.

Nếu thiếu một thành phần, nhánh đó phải ghi là **provisional scenario** hoặc
**price-only diagnostic**, không được ghi là verified profit. Không được
impute funding, mark price hay liquidation rồi báo một precision/net profit
chắc chắn.

Liquidation không được xấp xỉ bằng công thức kiểu 1/L. Phải dùng mark price,
maintenance tier và trạng thái margin của instrument/account. Tài liệu chính
thức của Binance mô tả vai trò mark price trong liquidation và giới hạn
maintenance/position theo tier:
[Mark Price](https://www.binance.com/en/support/faq/detail/360033525271) và
[Maintenance Margin](https://www.binance.com/en/support/faq/detail/360033162192).
Các URL này là tài liệu tham khảo contract, không thay thế dữ liệu PIT của
venue được nghiên cứu.

### Khoảng trống hiện biết trong workspace

Các khoảng trống sau phải được giữ nguyên trong báo cáo, không được lấp bằng
giả định:

- alpha_lab/alpha_backtester.py là backtest triple-barrier theo signal, chưa
  phải whole-account ledger có tranche, withdrawal và bankruptcy path. Không
  được dùng improvement của nó làm profit evidence trước PIT audit: MetaLabelingModel
  hiện nhận các trường tương lai như holding_bars, mfe, mae và mfe_mae_ratio,
  còn split chưa được bảo đảm sorted, purged và embargoed.
- collectors/liquidations.py hiện có đường trả trạng thái SUCCEEDED nhưng
  rows_raw=0; đó không phải coverage liquidation thực tế.
- Funding/mark data hiện có mark price tại settlement, không phải continuous
  mark-price path cho toàn bộ lifespan của vị thế.
- V3 sáu tháng dùng funding cadence heuristic, không có provider attestation;
  vì vậy compact eligibility/net return của V3 bị withheld. Kết quả
  price-only 24h/48h trong báo cáo V3 chỉ là diagnostic, không phải bằng chứng
  lợi nhuận whole-account.

Mỗi khoảng trống phải có số dòng/trade/episode bị ảnh hưởng. Không gom chúng
vào nhóm loss nếu thực tế là unknown hoặc excluded.

## 4. Candidate families được phép nghiên cứu

Candidate phải khai báo hướng exposure, vốn, leverage, điều kiện vào, điều
kiện thoát, cutoff, và contract dữ liệu trước khi đọc outcome của cohort
đánh giá.

| Family | Ý tưởng cần kiểm tra | Điều kiện bổ sung |
|---|---|---|
| Momentum long | Theo xu hướng tăng, breakout hoặc continuation | Chỉ dùng feature đã có tại signal; không mặc định TP 20% |
| Fade short | Short một đợt tăng quá đà khi có tín hiệu đảo chiều/reversion | Phải có short/borrow, funding và liquidation evidence |
| Regime switching | Long, short hoặc flat tùy regime/volatility/trend | Chuyển regime phải có timestamp và không nhìn tương lai |
| Hedged pair / carry | Long-short hoặc carry giữa legs khi dữ liệu cho phép | Hai legs, hedge ratio, funding/borrow và rủi ro basis phải được ghi; joint-margin/netting phải có PIT evidence |
| Balanced portfolio | Phối hợp long, short, cash hoặc hedge | Không được vượt tổng budget; phải tách gross/net exposure |

Balanced không đồng nghĩa với không có rủi ro. Báo cáo phải tách gross
exposure, net exposure, long/short allocation, margin và
correlation/concentration. Hedged pair/carry chỉ được chạy khi dữ liệu của cả
hai legs đủ; thiếu một leg thì ghi provisional, không suy ra hedge thành công.

### Exit và thời hạn

- Exit được phép dựa trên trend/regime reversal, volatility, trailing,
  time-in-position đã đăng ký, partial close, funding/liquidity hoặc account
  state.
- Không có fixed TP 20% và không ép mọi vị thế ra sau 48 giờ.
- Không bắt buộc fixed stop. Tuy vậy, venue liquidation, maintenance margin,
  account ruin và các exit được candidate đăng ký vẫn phải được mô phỏng.
- Mọi run phải có một **evaluation cutoff hữu hạn**. Vị thế còn mở tại cutoff
  được mark-to-market theo contract và tính vào wealth/profit distribution.
  Không được cắt bỏ open losers chỉ vì chúng chưa có exit.
- Một candidate không được đổi exit, cutoff, leverage hoặc allocation sau khi
  đã nhìn outcome của fold/forward mà không tạo trial/version mới.

Vì các candidate có horizon khác nhau, so sánh phải dùng cùng calendar cutoff
và cùng cơ hội quan sát, hoặc các cohort maturity-aligned đã đăng ký trước.
Phải tách realized-at-exit khỏi open-at-cutoff MTM và không được cho horizon
dài/ngắn tự chọn tạo censoring có lợi. Với hedge, chỉ được net margin giữa hai
legs khi venue joint-margin/netting và điều kiện PIT đã được chứng minh; nếu
không, giữ nghĩa vụ gross của từng leg và gắn nhãn provisional.

## 5. Chia dữ liệu, purge và lịch sử đã mở

### Lịch sử tái sử dụng

Toàn bộ các period đã mở trong thí nghiệm trước, gồm Feb–Jul 2026 và August
2026, là **recycled history**. Có thể dùng chúng để:

- tìm cơ chế, loại ý tưởng yếu, ước lượng phân phối và kiểm tra code;
- làm development/walk-forward và so sánh với V3;
- phát hiện unknown, data gap, concentration và failure mode.

Chúng không phải sealed confirmation và không được dùng một mình để gọi
candidate mới là verified hoặc live-profitable.

Mốc sau 2026-08-26 cũng không tự động trở thành sealed holdout. Chỉ một period
được coi là genuinely unseen nếu log chứng minh rằng outcome và các quyết định
liên quan chưa được mở/đọc trước khi candidate bị freeze. Candidate phải được
freeze (protocol, rule, parameter, budget, data contract, hash và trial log)
trước khi thu outcome của forward period đó.

### Purge theo lifespan thật

Purging không được chỉ trừ 48 giờ. Với mỗi candidate, xác định toàn bộ lifespan
thực tế của từng trade/leg: signal, fills, partial exits, funding/fees,
liquidation hoặc close; nếu còn mở thì tới evaluation cutoff. Purge:

- mọi train/validation/test row có feature hoặc outcome nằm trong khoảng
  overlapping lifespan;
- các episode cùng symbol/account bị ảnh hưởng bởi cooldown, margin, cash,
  tranche sequencing hoặc concurrent budget;
- các leg của pair/hedge nếu một leg còn sống trong khoảng đó.

Nếu chỉ có dữ liệu overlap một phần và không thể xác định purge chính xác,
nhãn là unknown/provisional, không coi là clean holdout.

## 6. Đăng ký candidate và giới hạn tìm kiếm

Trước khi replay outcome, mỗi candidate phải có registry record gồm:

1. family và exposure direction;
2. feature names, timestamp/PIT rule và phiên bản dữ liệu;
3. entry, fill, sizing, tranche allocation, leverage và concurrent budget;
4. exit rules, partial-fill rules, cutoff và open-position MTM;
5. fee, slippage, funding, borrow, mark-price và liquidation assumptions;
6. các scenario unknown (base/upside/downside) nếu contract chưa đủ;
7. danh sách parameter values hữu hạn, số trial tối đa và selection objective;
8. candidate hash, thời điểm freeze, cohort/split và người/worker tạo trial.

Grid và family phải được khai báo hữu hạn trước khi chạy. Không dùng unlimited
optimizer, random search không giới hạn, hoặc lặp lại selection đến khi có
đường lợi nhuận đẹp. Trial log phải lưu cả trial thất bại, thiếu dữ liệu,
không chạy được và bị loại; không chỉ lưu winner. Thêm family/parameter sau
khi đã xem test outcome là protocol/version mới, không ghi đè report cũ.

## 7. Cách đánh giá và metric mới

### Đơn vị đánh giá

Report tách rõ:

- trade, leg, tranche, account path, chronological window và independent
  episode;
- signal rows với actual executed positions;
- resolved, open-at-cutoff, liquidated, burned tranche, excluded và unknown;
- long, short, balanced, từng family và từng leverage/budget scenario.

Không gọi rows chồng lấn là independent events. Nếu block hoặc episode có phụ
thuộc symbol/regime, phải báo dependency và concentration cùng với khoảng tin
cậy phù hợp. Một aggregate profit duy nhất không đủ để kết luận.

### Primary profit metrics

Metric chính của protocol này là wealth/account outcome, không phải target
precision:

- tổng lợi nhuận theo công thức ở Mục 2;
- ending wealth và positive-end-wealth rate tại cutoff;
- phân phối profit: mean, median, các quantile, downside quantile và worst
  observed tail;
- ruin probability: phân phối trên các account paths của **một candidate đã
  freeze, một scenario và một chronological window** theo liquidation/
  bankruptcy contract; tách riêng tranche ruin. Không gộp các parameter trials
  khác nhau thành IID account paths để ước lượng ruin;
- thời gian tới profit dương, thời gian tới ruin, time-in-market và time-to-
  recovery nếu có;
- capital occupied: average/peak margin, free margin, gross/net exposure,
  vốn bị khóa theo tranche và phần vốn chưa phân bổ;
- toàn bộ fee, slippage, funding, borrow, liquidation loss, open losers và
  withdrawals;
- leverage, turnover, long/short balance, symbol concentration và regime
  concentration.

Không có user drawdown gate cứng trong protocol này, nhưng max drawdown,
drawdown duration, margin utilization và worst tail vẫn bắt buộc phải báo.
Nếu một candidate có profit cao đồng thời ruin cao, báo cả hai; không chọn
định nghĩa chỉ làm mất phần ruin.

Precision/TP rate, Wilson interval và EV cũ có thể xuất hiện như diagnostic
phụ để nối với lịch sử, nhưng không còn là metric thay thế cho total profit
ở nhánh này. Đặc biệt, không dùng gate precision >=50% của protocol cũ như
điều kiện phổ quát mới.

### Positive end wealth và ruin

Định nghĩa threshold phải được ghi trước trong contract:

- positive end wealth là tổng W + U + E sau MTM, lớn hơn C theo ledger;
- tranche ruin là tranche không còn khả năng đáp ứng contract margin hoặc đã
  bị liquidation toàn bộ;
- operating/trading ruin là trạng thái không còn tranche được phân bổ nào có
  thể tiếp tục theo venue/account rules mà không có rescue funding; nó có thể
  xảy ra dù W hoặc U vẫn còn.
- wealth ruin là mất toàn bộ wealth khả dụng theo ledger (W, U và E), không
  được suy ra chỉ từ việc các tranche trading đã cháy.

Nếu dữ liệu liquidation/maintenance thiếu, chỉ được báo scenario range cho
ruin và ending wealth; không gọi đó là xác suất đã xác minh.

## 8. Scenario, uncertainty và báo cáo

Với mỗi candidate, report ít nhất:

- protocol/version/hash, source và PIT coverage;
- budget, tranche mode, sequential/concurrent, leverage và venue constraints;
- số trial đã đăng ký/chạy/thất bại, selection objective và mọi thay đổi;
- counts theo row/trade/leg/tranche/account path/episode/window;
- verified, provisional, unknown, excluded và lý do từng nhóm;
- bảng wealth/profit/ruin/positive-end-wealth/capital/time/tail;
- bảng fees, slippage, funding, borrow, liquidation và withdrawal;
- bảng long/short/balanced, family, symbol, month/regime và concentration;
- V3 comparator trên cohort tương thích, kèm khác biệt contract;
- sensitivity cho dữ liệu chưa chắc (funding, mark, maintenance, slippage),
  nhưng không trộn scenario với verified result;
- kết luận null nếu không có bằng chứng ổn định.

Wilson hoặc bootstrap chỉ mô tả uncertainty của đơn vị mà nó dùng. Với trade
overlap, cùng symbol, cùng regime hoặc cùng account path, phải ghi rõ rằng
đó không phải independent-event confidence. Không dùng một tuần, một symbol
cluster, một leverage spike, hoặc việc giảm vốn triển khai để gọi là thắng.

Các nhãn kết quả được phép:

1. **Verified-profit evidence (research evidence only):** contract mark,
   maintenance, funding, execution và liquidation đủ; candidate đã freeze
   trước genuinely unseen outcomes; lợi nhuận sau mọi chi phí và phân phối
   được báo qua nhiều chronological windows.
2. **Provisional scenario:** còn unknown/gap; chỉ cho biết kết quả dưới các
   giả định đã ghi, không chứng minh lợi nhuận.
3. **Rejected / negative:** lợi nhuận âm, ruin/tail không chấp nhận được theo
   mục tiêu đã đăng ký, hoặc không ổn định.
4. **Null / insufficient evidence:** chưa đủ coverage, sample, windows hoặc
   outcome để kết luận.

Không nhãn nào ở trên tự động cấp quyền deployment, withdrawal thật hoặc
promotion. Quyền đó cần một quyết định riêng ngoài protocol.

## 9. Context từ V3 sáu tháng

V3 sáu tháng hiện có 1.933 dòng common diagnostic 24 giờ và 1.580 dòng
evidence 48 giờ; đường giá-only lần lượt là 351/1.926 và 247/1.575. Funding
không có provider attestation nên compact eligibility bằng 0 trong nghiên cứu
đó; pattern/stage classifier cũng unavailable. Đây là bằng chứng về giới hạn
contract và lý do cần whole-account ledger, không phải anchor để tối ưu
open-profit, không phải verified profit của candidate mới.

Tất cả kết quả V3/alpha đã mở, bao gồm Feb–Jul và August, tiếp tục mang nhãn
recycled history theo Mục 5. Không được viết lại report cũ để làm cho nó phù
hợp với metric mới.

## 10. Checklist trước mỗi trial và trước khi kết luận

### Trước replay

- [ ] Candidate family, long/short/balanced direction và finite parameter list
  đã được đăng ký.
- [ ] Budget, tranche mode, sequential/concurrent, leverage và no-rescue rule
  đã được freeze.
- [ ] Entry/fill/exit/cutoff/MTM/liquidation semantics đã được freeze.
- [ ] PIT feature timestamps, lifespan purge và cohort đã được freeze.
- [ ] Fee, slippage, funding, borrow, mark price và maintenance coverage đã
  được kiểm tra; unknown đã có scenario label.
- [ ] Trial log chứa candidate hash và cả trial bị loại.

### Trước khi gọi là evidence

- [ ] Tổng lợi nhuận khớp ledger và không double-count fee/loss/withdrawal.
- [ ] Mọi open loser, burned tranche, liquidation và required margin đã được
  tính tới cutoff.
- [ ] Positive end wealth, ruin probability, profit distribution, time,
  capital occupied và worst tail đều có.
- [ ] Kết quả tách verified khỏi provisional/unknown/excluded.
- [ ] Lifespan overlap đã purge; history đã mở được ghi là recycled.
- [ ] Candidate freeze xảy ra trước genuinely unseen forward period.
- [ ] Kết luận có thể là null; không có câu bảo đảm profitable.
