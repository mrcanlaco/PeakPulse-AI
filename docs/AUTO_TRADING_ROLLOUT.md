# Đảo Vàng: triển khai Cross Short 500 USDT

## Trạng thái bàn giao

Đây là phần mềm chuẩn bị và thử nghiệm giao dịch, **chưa phải nghiệm thu tiền thật**.
Mặc định `execution.enabled=false`, `environment=simulation`, `live_activated=false`.
Trong đợt triển khai này không đặt lệnh Binance, không triển khai GCP và không thay bí mật.
Các thay đổi có sẵn trong workspace được giữ nguyên.

| Giai đoạn | Đã triển khai trong mã | Điều kiện còn phải thực hiện thực tế |
|---|---|---|
| 1. Dữ liệu/vận hành | Manifest checksum model, mã nguồn và chính sách; funding có phản hồi gốc và độ phủ; sức khỏe V3/execution; snapshot, phục hồi và quay lui | Kiểm tra độ phủ dữ liệu thật, diễn tập phục hồi trên GCP và kiểm định lại model sau đổi công thức |
| 2. Chiến lược | Replay một ví chung; chi phí, funding, tài sản chưa chốt, tier duy trì và thanh lý tại các mốc quan sát; baseline cùng dữ liệu | Chuẩn bị dữ liệu lịch sử theo thời điểm, cả coin hủy niêm yết, chứng nhận tiers/funding và đo hiệu quả thực |
| 3. Thực thi | Demo/mainnet tách khóa và trạng thái; ý định bền vững, đối soát, TP reduce-only, user stream, dừng mở mới | Kiểm chứng hợp đồng API bằng khóa Binance Demo; rà soát các tình huống đặc thù tài khoản |
| 4. Quan sát | Dashboard, API điều khiển, nhật ký và bộ đánh giá điều kiện chuyển tiếp | Ít nhất 28 ngày/100 sự kiện độc lập; ba cửa sổ; bằng chứng lợi thế sau mọi chi phí |
| 5. Tiền thật | Khóa kích hoạt, báo cáo được pin checksum, điều kiện tăng 1→3→5 vị thế | Người dùng chủ động kích hoạt sau khi đạt bằng chứng; chạy từng mức ít nhất 14 ngày/20 vòng hoàn tất |

Không dùng kết quả V3 cũ (vốn có stop và nhiều lần vào) để chứng nhận chiến lược Cross một lần vào không stop này.

## Hợp đồng giao dịch

- Vốn chuẩn 500 USDT; Cross x5; chỉ Short USDT perpetual; khoảng 25 USDT danh nghĩa mỗi lần vào.
- Mặc định một vị thế; tối đa các mức 1, 3, 5. Mỗi coin một vị thế; mỗi episode chỉ thử vào một lần. Không DCA, rút/nạp, chuyển tiền hoặc tăng khối lượng để đáp ứng minimum của sàn.
- ATR dùng trung bình 14 true range từ 15 nến giờ liên tiếp đã đóng. Thiếu nến/độ mới thì loại tín hiệu, không bù bằng giá giả để giao dịch.
- Mục tiêu ban đầu = min(5, khối lượng × 2 × ATR − dự toán phí hai chiều − dự toán trượt giá). Dưới 0,50 USDT thì bỏ qua.
- Phí dự toán mặc định 0,05% mỗi chiều, không phải xác nhận mức phí tài khoản. Giá khớp/phí thực lấy từ lịch sử fills. Khi mở Demo cần đối chiếu fee tier; phí bằng tài sản khác USDT hiện chặn đối soát và yêu cầu kiểm tra.
- TP BUY LIMIT GTC reduce-only, cùng vị thế One-way. TP có thể khớp một phần hoặc không khớp. Giá TP dựa trên fill thật, chi phí và funding; không đổi mục tiêu vì ATR mới. Trần 5 USDT là mục tiêu, không phải đảm bảo lợi nhuận thực nhận.
- Không tạo SL hoặc thoát theo thời gian. Drawdown đạt 20% từ đỉnh tính cả lỗ chưa chốt: chốt trạng thái dừng mở mới, giữ TP và vị thế. Chỉ người dùng bật lại, khi drawdown đã dưới 20%; mốc đỉnh không bị xóa.
- Cross có thể ảnh hưởng toàn bộ ví Futures; 5 USDT là ký quỹ ban đầu, không phải giới hạn lỗ.

## Các lớp trạng thái

`data_dir/execution/{simulation,demo,live}/state.sqlite3` có signals, trades, journal,
ledger, commands và state. SQLite FULL/WAL; một worker sở hữu khóa hệ điều hành.
Web chỉ ghi hộp lệnh, không giữ API key và không gửi lệnh Binance.

Các nguồn vào là `predictions` của scanner, không phải `alert_history` hay Telegram.
Tín hiệu phải khớp manifest/model/label, có episode, trạng thái xác nhận, đủ chất lượng,
đạt ngưỡng đóng băng và còn hạn. Mỗi observation được lưu riêng, kể cả bị loại.
Không ghi nhận một lần quan sát bị loại là đã giao dịch cả episode.

Entry và TP đều lưu ý định trước khi gửi. Timeout không đồng nghĩa thất bại.
Đối soát tìm theo clientOrderId trước khi quyết định. Trạng thái không xác định sẽ
dừng mở mới; không tự gửi lại entry. Nếu phục hồi thiếu ý định gốc nhưng sàn có
lệnh, bot yêu cầu kiểm tra và không tự suy ra mục tiêu TP mới.

User stream đánh thức bộ đối soát; REST xác nhận trạng thái và khôi phục sau restart.
Mất stream chặn mở mới, vẫn thử đối soát/quản lý TP qua REST. Lỗi vị thế, phí,
funding hoặc TP có nhật ký và trạng thái dừng trên dashboard. Chưa có thông báo
vận hành mới gửi ra Telegram trong luồng execution.

Đóng thủ công cần xác nhận; hủy TP, xác minh kết quả rồi gửi BUY MARKET reduce-only.
Một TP đã khớp trong lúc hủy không được biến thành vị thế Long mới.

## Chạy thử local

### Theo dõi tài khoản thật, chưa giao dịch

`configs/live.yaml` hiện bật `account_monitor.enabled: true`, còn
`execution.enabled: false`, `execution.live_activated: false`. Web khởi động
bộ đọc độc lập mỗi 15 giây. Kết nối chỉ cho phép các endpoint GET trong danh sách
đọc tài khoản; POST/PUT/DELETE bị chặn trước khi ra mạng. Không dùng luồng đặt
lệnh, không đổi Hedge/One-way, margin, đòn bẩy hoặc hủy lệnh.

Nhập khóa HMAC trong terminal tương tác trên máy chạy web (không nhập qua chat/web):

```powershell
.venv\Scripts\dao-vang.exe execution tools connect-account configs/live.yaml
.venv\Scripts\dao-vang.exe execution tools check-account configs/live.yaml
```

Lệnh đầu nhập ẩn cả Key/Secret, lưu `.env.binance-readonly` đã được Git bỏ qua;
Windows giới hạn ACL cho tài khoản đang chạy, POSIX dùng quyền 0600. `--replace`
chỉ dùng khi chủ động đổi khóa. Không ghi đè `.env` hoặc khóa thực thi. Có thể cấp
hai biến `DAO_VANG_ACCOUNT_MONITOR__API_KEY`/`DAO_VANG_ACCOUNT_MONITOR__API_SECRET`
trên máy chủ thay cho file. Docker cần cấp các biến này vào môi trường web;
file khóa local không tự được đưa vào container. Không cấp quyền rút tiền.

Trang `#account` hiển thị **TIỀN THẬT · CHỈ ĐỌC**, tài sản USDT, cả hai phía của
vị thế Hedge, lệnh chờ thông thường và phí/funding đã đọc từ income. Phí/funding
khởi đầu lấy tối đa 7 ngày gần nhất, không phải toàn bộ lịch sử. Lệnh điều kiện
/algo và lịch sử fills chưa nằm trong danh sách này. Tài sản khác USDT không được
cộng vào thẻ số dư. Mốc đỉnh bắt đầu từ quan sát đầu tiên, không tự giả định 500.

Trạng thái được lưu riêng dưới `data_dir/account_monitor/live/<key hash>/`,
không dùng làm bằng chứng chiến lược, không chung sổ với execution. Đổi khóa
chuyển sang sổ mới để không lẫn tài khoản. Dashboard không có nút đặt/hủy/đóng
lệnh trong chế độ này; API điều khiển và bộ thực thi cũng chặn khi monitor bật.
Chỉ chuyển sang vận hành giao dịch bằng quy trình nghiệm thu riêng, không tự
bật giao dịch sau khi kết nối tài khoản thành công.

### Mô phỏng/Demo có bộ thực thi

Đặt `account_monitor.enabled: false` trong cấu hình thử nghiệm riêng trước khi
chạy execution; không dùng cấu hình chỉ đọc tài khoản thật cho mô phỏng.

1. Sao chép cấu hình scanner đang dùng thành một cấu hình thử nghiệm riêng; thêm
   block `execution` từ `configs/trading.example.yaml`. Dùng cùng cấu hình cho
   scanner, web và execution; không đổi policy scanner giữa lúc thu bằng chứng.
2. Khi mã nguồn đã ổn định, đóng băng manifest mới; không ghi đè manifest cũ:

```powershell
.venv\Scripts\dao-vang.exe execution tools freeze configs/trading.local.yaml artifacts/trading/cross_short_atr_v1.json
```

3. Đặt `manifest_path` đúng file trên và `execution.enabled: true` trong cấu hình
   thử nghiệm; giữ `environment: simulation`. Chạy worker:

```powershell
.venv\Scripts\dao-vang.exe execution start --config configs/trading.local.yaml
.venv\Scripts\dao-vang.exe execution tools status configs/trading.local.yaml
```

4. Web phải nạp cùng cấu hình qua `DAO_VANG_CONFIG_PATH`. Mở **Tài khoản & giao dịch**
   ở đầu ứng dụng, hoặc thêm `#account` vào URL, để xem tài sản, lỗ chưa chốt, TP,
   funding và thao tác dừng/bật/đóng tay. Cài đặt cũng có liên kết đến trang này.
5. Demo dùng `environment: demo`; khóa đặt ở biến môi trường
   `DAO_VANG_EXECUTION__API_KEY` và `DAO_VANG_EXECUTION__API_SECRET`. Không gửi khóa
   trong chat, không lưu trong YAML, không đưa vào trình duyệt.

Địa chỉ theo environment được cố định trong adapter: Demo dùng
`https://demo-fapi.binance.com`, tiền thật dùng `https://fapi.binance.com`.
Trường `base_url`/`paper_trading` cũ không thể chuyển lệnh sang host khác.

Docker có profile `trading` với service `execution`, dùng `configs/live.yaml`.
Chỉ bật profile sau khi cấu hình manifest/environment/enabled đồng nhất với web
và scanner. Không dùng cấu hình local khác policy để đánh giá scanner production.

## Kiểm định và giới hạn hiện tại

Replay nhận mảng JSON frame theo thời gian tăng dần. Mỗi frame có `at`, `market`,
`signals`, `funding`, `coverage_verified`. Mỗi coin có bid/ask/mark, trạng thái
niêm yết, khối lượng thanh khoản, filters và tiers lịch sử; liquidation fee phải
có khi mô phỏng thanh lý. Xem fixture có kiểm thử tại
`tests/unit/execution/test_cross_contracts.py` để biết dạng dữ liệu chính xác.

```powershell
.venv\Scripts\dao-vang.exe execution tools replay configs/trading.local.yaml frames.json reports/cross-comparison.json
.venv\Scripts\dao-vang.exe execution tools export-forward configs/trading.local.yaml reports/forward.json
.venv\Scripts\dao-vang.exe execution tools evidence reports/forward.json MANIFEST_ID
```

Replay đánh giá theo mốc mark được cung cấp, không tái dựng chính xác thanh lý
giữa các mốc. Mất giá khi còn vị thế khóa khả năng đánh giá, không tự giải phóng
vốn. Funding giữ đúng dấu và không tính hai lần. Cuối kỳ mọi vị thế còn mở phải
được định giá; nếu thiếu giá cuối kỳ thì không có ending_equity hợp lệ.

Paper broker lấy giá công khai mainnet và funding thật nhưng khớp TP theo những
lần quan sát, không mô phỏng hàng đợi lệnh hay chứng nhận margin tiers. Nó luôn
ghi `financially_verified=false`. Kết quả paper/replay này **không tự đủ để mở
tiền thật**. Cần hoàn thiện chứng cứ dữ liệu, stress test và xác minh kinh tế
trước khi lập báo cáo forward đã kiểm tra. Đây là giới hạn chưa nghiệm thu.
`export-forward` xuất sự kiện độc lập và đường tài sản theo ngày từ sổ quan sát;
không tự đặt các cờ chứng nhận nguồn/tài chính thành true. Không đổi các cờ này
chỉ để vượt gate; phải hoàn thiện kiểm chứng dữ liệu và mô phỏng trước.

Bộ gate kiểm tra 28 ngày, 100 episode độc lập (tách theo coin/thời gian), ba cửa
sổ, tài sản ròng >500, drawdown <20%, không lỗi nghiêm trọng, không tiền ngoài và
không bỏ lỗ chưa chốt. Khoảng tin cậy dùng block bootstrap 7 ngày trên thay đổi
tài sản toàn danh mục để giữ phụ thuộc giữa coin đồng thời. Report JSON là đầu
vào của người vận hành, không tự chứng minh tính thật của các cờ attestation;
phải kiểm chứng nguồn và pin SHA256 trước khi dùng.

Giai đoạn tiền thật dùng khóa khác: `LIVE_API_KEY`/`LIVE_API_SECRET` dưới cùng
prefix. Cần đồng thời `live_activated`, manifest khớp, evidence_path và
evidence_sha256 hợp lệ. Không có nút bật tiền thật từ web. Không tự nâng model.

## Sao lưu và phục hồi

Backup định kỳ dừng cả execution nếu đang chạy, cùng web/scanner; snapshot gồm
JSON/SQLite/DuckDB dưới data và artifacts đầy đủ, kể cả model V3 ngoài frozen_models.
Raw/normalized vẫn đi theo nhánh sao lưu data lake riêng; không gọi đó là cùng
một snapshot lịch sử bất biến. Snapshot artifacts đầy đủ có thể tăng dung lượng
và thời gian dừng; cần đo khi diễn tập trên máy chủ.

Phục hồi runtime kiểm checksum/path trước khi thay file, giữ bản trước và WAL/SHM
để quay lui. Khi thành công, trạng thái mở lệnh mới bị khóa `restored_requires_review`.
Đối soát với sàn và xem lại mốc đỉnh trước khi bật lại; rollback phần mềm không
đóng vị thế. Các snapshot cũ chỉ có DuckDB vẫn được đọc nhưng không phải phục hồi
execution/V3 đầy đủ.

Các lệnh `execution tools snapshot` và `restore-check` phục vụ diễn tập vào thư
mục mới. Không gọi script restore production trong quá trình chạy kiểm thử.

## Kiểm tra trong đợt triển khai

Dashboard tài khoản có đường tài sản 24 giờ/7 ngày/30 ngày, danh sách vị thế bot
và vị thế ngoài sổ, 100 giao dịch kết thúc gần nhất, tín hiệu và nhật ký yêu cầu.
Dữ liệu được đọc qua API có xác thực từ sổ đối soát, làm mới mỗi 10 giây.
Không có tài khoản thì không thay bằng số dư cấu hình 500 USDT. Phí chỉ lấy từ
fills (không cộng lại income COMMISSION); funding giữ đúng dấu. Tổng phí/funding
là phần đã ghi nhận trong môi trường đó, chưa khẳng định bao phủ toàn bộ lịch sử.
Tiến trình chỉ đếm tín hiệu của manifest hiện tại và dừng thời gian ở bản ghi
tài khoản gần nhất; các bộ đếm không thay thế nghiệm thu tài chính hoặc liên tục dữ liệu.
Khi dữ liệu cũ/mất kết nối, giữ số liệu cũ có cảnh báo và khóa bật lại/đóng tay;
vẫn cho gửi yêu cầu dừng mở mới nếu dịch vụ được cấu hình bật.
Thay đổi mã execution làm checksum manifest cũ không còn khớp; cần phiên bản
chiến lược và kỳ quan sát mới, không chỉnh manifest cũ để hợp thức hóa bằng chứng.

- Bộ backend toàn ứng dụng: 1.069 bài đạt, 3 bài bỏ qua theo cấu hình.
- Sau các bổ sung cuối về xuất báo cáo và độ mới dữ liệu: 76 bài liên quan
  execution, API điều khiển và lựa chọn V3 đạt.
- Frontend build và kiểm tra dung lượng bundle đạt; 13 bài trình duyệt đạt.
  Kiểm tra riêng dừng mở mới/xác nhận đóng thủ công được chạy lại và đạt;
  ảnh giao diện đã được kiểm tra.
- Kiểm tra kiểu dữ liệu các module mới cùng API/config: không lỗi; lint phần
  execution đạt; hai script sao lưu/phục hồi hợp lệ về cú pháp shell.
- Chưa kiểm thử lệnh thật với Binance Demo/mainnet hoặc thực thi phục hồi production.
