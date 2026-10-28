# Annual backtest — trạng thái triển khai và tiêu chí hoàn tất

Mục tiêu giữ nguyên: tạo chiến lược từ kết quả trước và thực sự chạy backtest
trong một năm, không thay bằng chỉ viết protocol hay annualize sáu tháng.

## Trạng thái ngày 18/09/2026, trước outcome

- Đã đọc lại worktree và kết quả sáu tháng, không dựa vào bộ nhớ hội thoại.
- Đã chốt 10 chiến lược x 2 mức phí x 2 chính sách rút lãi = 40 trial trong
  `docs/ANNUAL_PROFIT_PROTOCOL_20260918.md`.
- Cửa sổ [2025-09-01, 2026-09-01) UTC là 365 ngày thực; warmup từ 2025-08-01.
- Kho có 328 file giá. Kiểm tra trực tiếp BTC có giá từ 2024-01-01 tới
  2026-09-15 23:55 UTC; RAVE bắt đầu 2025-12-14, H bắt đầu 2025-06-25.
  Không đòi mọi mã có đủ một năm trước khi được đưa vào universe.
- Kiểm tra trực tiếp BTC/RAVE/H/BR funding riêng đều 500 dòng. Ngoài ra có
  `D:/Quant-trading/data_lake/funding/vision_backfill_funding.parquet`:
  98.672 dòng, 50 mã, từ 2025-05-01 tới 2026-06-16. H có 2.492 dòng trong
  kho bổ sung từ 2025-06-25 tới 2026-06-13. Nguồn này có thể dùng đối chiếu
  hoặc fallback có provenance; không tự coi nó phủ mọi mã/khoảng thời gian.
- Sol Medium đã review protocol lần đầu: yêu cầu làm rõ entry latency,
  funding ownership/availability, PHASE causality, hedge arithmetic và
  snapshot identity. Các điểm đã được bổ sung TRƯỚC outcome. Chưa review
  implementation hay kết quả một năm.
- Không có actual annual outcome nào tại checkpoint này.
- Kiểm tra độc lập public REST `/fapi/v1/fundingRate` với requested window
  2025-08-01..2026-09-01 và limit=2 trả HTTP 200 cho BTC/H/RAVE. BTC/H bắt
  đầu trong 01/08/2025; RAVE bắt đầu sau niêm yết tháng 12/2025. Funding
  historical endpoint có thể truy cập, chưa chứng minh full pagination đã
  hoàn tất. Không cần giả định chỉ lấy được 500 bản ghi gần nhất.

## Worker và phạm vi sở hữu

Native multi-agent hiện không có handle Luna/Sol cũ. Shim 1devtool trong
skill không còn tồn tại. Đã chuyển sang CLI `codex exec`, giữ model chính xác.

1. Data worker: `gpt-5.6-luna`, reasoning `max`, CLI session **12499**, PID
   **16504**, khởi động 06:44:42 giờ máy 18/09. Sở hữu:
   `scripts/annual_profit_data.py`, `tests/unit/scripts/test_annual_profit_data.py`,
   `artifacts/annual_profit_20260918/data/*`.
   Nhiệm vụ: audit universe, tải funding full-window có phân trang/cache/rate
   limit/provenance, chạy actual data preparation. Không được sửa data lake.
2. Runner worker: `gpt-5.6-luna`, reasoning `max`, CLI session **87319**, PID
   **19304**, khởi động 06:49:16. Sở hữu:
   `scripts/backtest_annual_profit.py`,
   `tests/unit/scripts/test_backtest_annual_profit.py`,
   `artifacts/annual_profit_20260918/backtest/*`,
   `docs/ANNUAL_PROFIT_RESULTS_20260918.md` do runner sinh.
   Đã được yêu cầu đọc protocol SAU bổ sung của Sol; chỉ build/tests/input
   validation, không tự chạy outcomes. Parent phải preflight và chạy đủ 40.
3. Sol protocol review session **24061** đã kết thúc exit 0. Cần review code
   và artifact riêng sau khi hai worker hoàn tất.
4. Sol Medium data-code review đang chạy ở session **20884**, khởi động
   khoảng 06:59:17; final được CLI ghi vào
   `artifacts/annual_profit_20260918/review/data_review.md`. Chỉ review,
   không sửa source hoặc chạy thêm downloader.

Update sau checkpoint: data script đã được tạo (first draft khoảng 1.942
dòng); test file/data cache chưa có ở lần kiểm tra 07:00. Runner vẫn đang
triển khai. Parent chạy lại 27 tests của account/search cũ: đều pass. Parent
đã lưu các phát hiện preflight về cache reuse, bounds và pagination tại
`artifacts/annual_profit_20260918/review/coordinator_data_findings.md`.
Đợi owner kết thúc trước khi sửa các file họ đang sở hữu; sau đó yêu cầu
Luna xử lý các finding được xác minh, không bỏ qua vì lượt mới dùng cache mới.

## Phát hiện bắt buộc xử lý trước annual run (07:06)

- Parent feature-only benchmark BTC: 8.160/8.760 quyết định giờ hợp lệ;
  107.136 bar warmup+year. Query độc lập xác định gap từ 2026-08-01T00:00
  tới 2026-08-25T00:00: thiếu 6.912 nến (24 ngày), cộng thời gian khôi phục
  warmup khiến thiếu 600 hourly decisions. KHÔNG được chạy và gọi nguồn
  nguyên trạng là đủ một năm, hoặc bỏ tháng 8 để qua gate.
- Đã bổ sung protocol trước outcome cho phép repair vào research price
  cache riêng, không sửa raw lake và không thay cửa sổ/strategy.
- Luna Max price worker session **81976**, khởi động khoảng 07:06, sở hữu
  `scripts/annual_profit_prices.py`, `tests/unit/scripts/test_annual_profit_prices.py`
  và `artifacts/annual_profit_20260918/prices/*`. Nhiệm vụ audit gap mọi mã,
  tải gap-month archive có checksum, merge không silent conflicts, chạy
  actual preparation; root dùng `prices/klines/5m` thay original root khi
  runner preflight cho phép. CLI final tại `review/prices_worker_final.md`.
- Sol data review **20884 đã kết thúc exit 0**, report tại `review/data_review.md`
  nêu 6 material findings: cache integrity, completion overclaim, empty
  terminal pagination, duplicates/marks/schema, snapshot provenance và
  Retry-After toàn cục. Phải giao Luna fix sau khi data owner xong.
- Protocol cutoff MTM tính funding event đúng cutoff; downloader cần end
  exclusive cutoff+1ms. Ghi tại coordinator_data_findings.md; phải áp dụng
  trước freeze annual outcome, không chỉ dựa default end-exclusive cũ.
- Parent đã chạy `test_annual_profit_data.py`: 8/8 pass ở bản nháp ngày
  18/09 07:08. Các tests này CHƯA bao phủ hết findings của Sol/coordinator;
  không coi test pass là data-preflight PASS. Chưa có manifest funding ở lần
  kiểm tra đó. Runner đã có khoảng 45KB code và còn đang viết.

Các session cũ **8100** (sandbox helper ACL) và **87258** (runner trước sửa
timing) đã được parent kết thúc có chủ đích trước thay đổi/outcome. Không
restart chúng hoặc nhầm với hai worker hiện tại.

Phải xác nhận process/session hiện còn live trước khi chờ. Timeout quan sát
không phải process đã chết. Không chạy trùng downloader/runner đang sống.

## Ma trận hoàn tất — chưa được đánh dấu goal complete

| Yêu cầu | Bằng chứng cần kiểm tra | Hiện trạng checkpoint |
|---|---|---|
| Chiến lược cụ thể từ phát hiện trước | Protocol + định nghĩa thực thi khớp 10 ID | Protocol có, code pending |
| Actual backtest đủ 365 ngày | Artifact window, source rows và executions, lệnh chạy thành công | Pending |
| Không dùng cohort lọc nhãn tương lai | Code tạo feature raw + tests timing/gaps | Pending |
| Funding có nguồn/coverage và không giả zero là đủ | Manifest pagination/archive, cache hashes, gaps, executed audit | Pending |
| 40 cấu hình được chạy và lưu cả lỗ | Trial IDs/count + results, không cherry-pick | Pending |
| Kế toán vốn/rút lãi/liquidation/censoring đúng | Tests + độc lập W+U+E-C=sumPnL | Pending |
| Phân tích cơ chế, concentration và tháng | Báo cáo dựa trên lệnh account thực hiện | Pending |
| Giới hạn dữ liệu/local universe/proxy/không holdout | Report + source manifest | Protocol đã nêu, report pending |
| Review đúng Sol Medium, implementation Luna Max | CLI model/effort + verdict trên artifact thực | Protocol review xong; final pending |
| Không ảnh hưởng production/không trade thật | git scope và tác vụ đã chạy | Đang giữ nguyên |

## Hành động tiếp theo

1. Poll đúng hai session/PID hiện có, đọc file/test đã tạo; không khởi động
   lại chỉ vì output yên lặng.
2. Khi data worker xong, kiểm tra schema/cache manifest và coverage, đối
   chiếu bổ sung bulk funding nếu cần. Tải public REST chỉ tối đa một request
   mỗi giây trên worker, tôn trọng 429/418; không né giới hạn.
3. Review runner theo timing addendum, kiểm thử độc lập các điểm nguy hiểm;
   chạy Sol Medium trên code thực. Không thêm chiến lược sau xem kết quả.
4. Parent chạy actual 40 trial một năm khi input/preflight đạt; giữ handle
   nếu job dài. Lưu đủ artifacts, đối chiếu sổ vốn và report.
5. Chỉ gọi goal complete sau khi mọi yêu cầu trên có bằng chứng trực tiếp.

Quyền hiện tại: filesystem/network unrestricted, approval never. Không truyền
`sandbox_permissions` vào exec. CLI worker dùng `-s danger-full-access` do
workspace-write helper của Windows lỗi ACL; scope tác vụ vẫn bị giới hạn
bởi yêu cầu trong prompt. Không thay model nếu có lỗi model availability.

## Cập nhật thực tế 18/09 khoảng 07:23 local

- Lượt tải funding đầu tiên đã đạt 328/328 file, 526.194 rows, báo 0
  partial/failed/conflict. Data owner đang kiểm tra cache-resume và chưa
  bàn giao; không chạy downloader trùng. Vẫn cần fix findings của Sol,
  xác minh reuse, và mở rộng end-exclusive thêm 1 ms theo protocol.
- Root kiểm tra độc lập 280 file/444.185 rows trong lúc job chạy: SHA256,
  row count, schema bốn cột, stored symbol đều khớp sidecar. Kiểm tra riêng
  BTC/H/AKE/BR không thấy null hoặc nonpositive settlement mark. Đây không
  phải chứng nhận coverage full lifecycle hay net-profit.
- Root chạy tổng hợp tests runner 14 + data 8 + account/search 27: 49 pass.
  Hai fixture runner hỏng ban đầu đã được owner sửa. Notes còn lại tại
  `review/coordinator_runner_findings.md`.
- Runner owner đang tích hợp funding JSON sidecar và chặn raw BTC có gap,
  chưa chạy outcomes. Cần review bản cuối bằng Sol khi một slot rảnh.
- Price repair owner đã tạo script khoảng 66KB và còn viết tests. Gap-month
  thực tế: August 2026 cho 323 symbols, December 2025 riêng LITUSDT;
  CVX July gap ở trước warmup nên không cần sửa cho window này.
- Ba session vẫn là data 12499/PID16504, runner 87319/PID19304,
  prices 81976/PID4692. Chờ ownership kết thúc rồi mới dispatch fixes.
- Actual one-year 40-trial outcomes vẫn chưa chạy; goal chưa hoàn tất.

## Cập nhật 18/09 khoảng 07:37 local — ưu tiên tiếp theo

- **Data owner 12499/PID16504 đã EXIT 0**, 9 focused tests + Ruff pass;
  actual 328 funding files, 526.194 rows, 737 pages. Không poll/restart owner
  cũ. Đã dispatch Luna Max follow-up sửa toàn bộ Sol findings + cutoff1ms:
  **session83515/PID26100**, live. Scope data script/tests/cache only.
  Output redirect để tránh cumulative diffs:
  `review/data_fixes_worker.log`; final `review/data_fixes_final.md`.
  Giữ verified prefix, chỉ tải bounded suffix nếu hợp lệ, không retải năm.
- **Price run đã xử lý 328/328**, ready327, fail/incomplete1 (LIT), còn210
  bars Dec23 00:00–17:30 UTC. Worker **81976/PID4692** còn live, sở hữu
  price script/tests/cache. Không sửa đồng thời hoặc chạy job trùng.
- Root tìm ra **LIT là reused ticker / lifecycle identity issue**, không
  đơn thuần gap: hợp đồng Litentry cũ dừng Jan31 2025; Lighter LITUSDT mới
  bắt đầu Dec23 2025 17:30 UTC theo Binance primary announcements. Raw
  Aug–Nov2025 toàn OHLC0.592/volume0, Dec22 cũng stale0.592; first new bar
  đúng17:30 open3.734 close3.925. Chi tiết/source/action tại
  `review/coordinator_price_identity_findings.md`. Sau owner bàn giao,
  Luna cần giữ LIT trong328 nhưng research segment chỉ từ actual launch,
  có provenance và289-close warmup; không fill gap, không drop cảsymbol.
  Không sửa raw lake. Không cần thay chiến lược/threshold/outcome-basedfilter.
- Root broad scan328 tìm UTCmonths >=1000flat-zero-volume bars: chỉLIT
  vàCRM. CRM có giá đa dạng/volume dương nên KHÔNG tự ý loại. Universecó
  stock-labelled USDTcontracts, không gọi cả328 là crypto-only.
- BTC repaired114048bars, đủ8760hourlyfeatures. Root so sánh tất cả8760
  FeatureRow gồmfunding với reference `_feature_for_decision`:0mismatches.
  Optimizedstream0.075sec vsdraft4.685sec (không bao gồmload~2sec).
- Root latestannual-focusedtests32pass (runner14/data9/prices9); old27
  tests pass earlier. Runnerowner **87319/PID19304** còn live, đã tíchhợp
  funding sidecar và optimizedfeatures; chờfinal rồiSolMediumcode review.
- Chưaannualoutcomes. Không coi327ready là đủ frozen328universe. Không
  đổi protocol đanghash bởiworker nếu chưa phối hợp/bàn giao. Lifecycle
  cleanup phù hợp rulecoinmới/warmup đã có; phải ghi rõ provenance/report.

## Cập nhật 18/09 khoảng 07:52 local — ownership mới

- Runner **87319/PID19304 EXIT0**, final17 tests + Ruff/compile pass;
  chưa actualoutcomes. Price **81976/PID4692 EXIT0**, final9tests pass,
  324checksumarchives,328outputs/327ready+LITpartial. Không poll/restart
  hai worker cũ. Price final: `review/prices_worker_final.md`.
- **Luna LIT lifecycle fix session43722/PID28696** đang chạy, sở hữu
  price script/tests/prices artifacts. Prompt bounded theo officiallaunch,
  giữ328universe, khôngglobalzerovolumefilter, khôngretảiallarchives,
  cần actualresume + tests + provenance/policy-aware cache reuse.
  Log `review/lit_lifecycle_worker.log`, final `review/lit_lifecycle_final.md`.
- **Sol Medium runner review session7456/PID17220** đang chạy, READONLY
  trên runner/account/tests, final `review/runner_review.md`, log
  `review/runner_review_worker.log`. Đã giao đầy đủtiming/capital/hedge/
  funding/gaps/provenance/report semantics. Data/LITpending được nêu rõ.
- **Luna data fixes session83515/PID26100** vẫn active, đã bắt đầu sửa
  globalRetryAfter và strictdata/cache/provenance cùngcutoffsuffix. Không
  launch downloader khác hoặc sửaownedfiles khi ownercònactive.
- Root kiểm tra độc lập all328priceoutputs:30.307.389rows, hashes/schema/
  rowcount/storedsymbol đều khớp; không thay choidentityvalidationLIT.
- Root tải RAVE Apr2026 vàH Jun2026 archives+checksum trongmemory:8640rows
  mỗi mã,0missing/0OHLCmismatch vsraw. Chi tiết/sourceSHA tại
  `review/outlier_price_source_check.md`. Không newannualoutcomes.
- `review/mechanism_interpretation_notes.md` chứa officialfunding sources
  và ranh giới causalclaims; funding cashflows phải theoactualevents,
  không universal8h; không gọi10strategies là exactV3Champion comparison.
- Bước tiếp: đọc Sol findings, boundedLunafix runner nếu cần khi slotrảnh;
  verify fundingextension+LITcurrentsegment all328; freshcompactpreflight;
  actual40trialone-year run, independentledger+resultsreview. Chưacomplete.

## Cập nhật 18/09 khoảng 07:59 local — Sol findings đang được sửa

- **Sol runner review 7456/PID17220 EXIT0**, verdict material findings,
  không chạyoutcomes. Reviewed runnerSHA
  `ea2616f3a82b7e9c9a6ffd5d548ab17ead47888a3ebde864fbcd813315d5afc1`.
  17runner tests và30runner+account tests pass nhưng không cover3defects:
  (1) hedge liquidated+cutoff/unresolved bịgộp mấtrealized/unknowncomponents
  vàBTCcoinattribution; (2) latergap erases prior known liquidation;
  (3) priceprovenance chỉhash/headerstatus chưacompareactualfiles/symbols.
- **Chi tiết đầy đủ**: `review/runner_review_detailed.md`, root khôi phục
  nguyênvăn từ Sol log. Lưu ý `-o runner_review.md` đã ghiđè detailedfile
  Sol tựtạo bằng finalsummary; file `runner_review.md` hiện chỉsummary.
  Prompt mới yêu cầu finalresponsechính làfullreport đểkhông lặp lỗi này.
- **Luna runner fixes session80225/PID27256** active, log
  `review/runner_fixes_worker.log`, final `review/runner_fixes_final.md`.
  Scope runner/tests; nếu thực sự cần được phép additivebackcompatible
  accountcomponent extension vàtests, ưu tiênannualadaptergiữenginecũ.
  Không đổi10strategies40trials, khôngoutcomes. Thêm flushedsymbolprogress
  chojobactualdài. Đã yêu cầu regressiontests3findings, lint/compile.
- Datafix **83515/PID26100**, LITfix **43722/PID28696** cònlive. Không
  restartvìquiet/no-output. Cảbahandle cóstdoutredirectlog; dùngreadtail
  bounded vàPID/readiness đểkiểmtra, khôngdumpcumulativediff.
- RAVE/H sourcechecks vàall328priceintegrity làinputevidence, chưaphảipnl.
  Actual annual40accounts/report vẫnCHƯAchạy. Chỉlaunch sauinputowners
  hoàn tất, verifiedintegration+boundedSolrecheckpassed; giữgoalfullscope.

## Cập nhật 18/09 khoảng 08:07 local — funding coverage thực tế

- Datafix actualpass mới đã tới đúngend-exclusivecutoff+1ms cho328mã:
  317complete/11partial/0failed,526194rows trước bướcquarantinecuối.
  Partial là firstsettlementmarkkhônghợp lệ; không được fakecomplete.
  Owner đang rerun11partial với nonpositive-markevent loại khỏicanonical
  cache (giữ partialflag);317complete dùngverifiedreuse, khôngRESTagain.
  Chờownerfinalđểđếmrows/statuschínhxác. Metadata thêm`*.provenance.json`,
  đếmsidecarbằnglistParquetstem, khôngglobmọiJSONthànhsymbol.
- Protocolđãcho phépobserved-fundingscenario vớicoverageflags. Saufixes
  vàreviewđạt, không tựđặt yêu cầudữ liệuhoàn hảo100% làmblocker mới.
  Chạyactual40trialsprovisional theo`outcome_run_allowed`, rồikiểmtra
  invalid/omittedsettlements cóchồnglênexecutedholdingshaykhông. Không
  dropmã/trade, khônggọinetprofitverified nếucònsource/MMR/executionproxy.
- LITownerđangfixresume/lifecycle tests. Root interimrepo-runtime check:
  9passed/1failed doISO `.000Z` vs`Z` stringcomparison, khôngphảisaiinstant.
  Notesởcoordinator_price_identity_findings.md cóvenvcommandđúng. Worker
  đangdùngruntimekhácđểtest; parentcầnruntestlại bằngrepo`.venv` sauhandoff.

## Cập nhật 18/09 khoảng 08:27 local — clean rebuild, final review

- LIT owner hoàn tất, 10 price tests passed independently. Full data/price
  suite 28 passed; runner/account/search suite 55 passed in repo runtime.
- Sol final data/price review `review/data_price_final_review.md` found one
  blocker: one-way raw-to-cache rebase cannot detect deleted prior raw rows.
  Root took the offered remedy, not a new strategy: preserved old manifest
  in `review/price_manifest_before_clean_rebuild.json`, launched clean
  `annual_profit_prices.py --no-resume --no-rest-fallback` with current raw
  hashes, cached archives reused. Session43879, log `review/price_clean_rebuild.log`.
  Wait for all328ready before actual annual run. Do not use rebase output.
- Root funding check: all17 invalid-mark records across11partial symbols
  occur before289-close warmup permits entry. Details/UTC times in
  `review/omitted_funding_event_check.md`. Keep partial coverage caveat.
- Root intermediate audit allowed outcome run, price_ready=true, no schema/
  static errors, all328funding files; rerun after clean rebuild completes.
- Luna data83515 and runner80225 finishing artifact verification, no outcomes.
  Sol Medium final runner recheck session88386, log `review/runner_final_review.log`,
  final `review/runner_final_review.md`; aware prices transiently rebuilding.
- Actual annual40accounts still not run. Next: finish source/runner handoffs,
  verify clean rebuild and bounded Sol runner verdict, execute one annual job,
  then independently audit/account for results and report mechanisms honestly.

## Cập nhật 18/09 khoảng 08:34 local — actual annual batch started

- Clean price rebuild session43879 completed328/328ready, zero missing,
  no `source_snapshot_rebase` key. All328 output hashes equal the preserved
  previous manifest: clean regeneration independently reproduced the data.
- Luna data and runner owners completed. Sol runner final review PASS in
  `review/runner_final_review.md`, source SHA8fc0c643bb72597e76a518978623d87b6c84b3608c209d65921539f43de491bc.
- Full focused root suite83passed. Funding526190rows,317complete11partial;
  seventeen invalid-source events comprise4absent+13retainednullmarks,
  allbeforeentrywarmup (see timing note), not17fullyomitted.
- **Actual annual run session62115 started**, log `review/annual_actual_run.log`,
  output `backtest/`, report `docs/ANNUAL_PROFIT_RESULTS_20260918.md`.
  This is the ONE actual outcome job; do not launch duplicates. Manifest
  freeze/reverification passed and symbol progress is advancing. Wait for
  exit0/accounts.json before interpreting final accounts.
- No remaining source owners or code edits expected. After actual run:
  independent all40capital/component/fee/funding/window checks, Sol artifact
  review, Vietnamese mechanism findings and limitations; only then goalcomplete.

## Cập nhật 18/09 khoảng 08:42 local — encoding retry, not strategy retry

- Actual session62115 EXIT1 after processing325symbols: progress `print`
  hit Windows cp1252 UnicodeEncodeError on Chinese-named symbol326. This
  was a stdout encoding failure, no account outcomes/report completed.
  Preserve `backtest/manifest.json` and `review/annual_actual_run.log` as
  failed-attempt evidence; temporary trigger file was removed by runner.
- Rerun SAME reviewed source/protocol/data with Python `-X utf8`, fresh
  directory `backtest_utf8/`, log `review/annual_actual_run_utf8.log`,
  **live session68750**. Report remains `docs/ANNUAL_PROFIT_RESULTS_20260918.md`.
  Do not relaunch old62115 or duplicate current68750. No thresholds changed.
- Root checked15833complete interim trigger rows before first failure:
  exact5m entry lag, feature_cutoff<decision, funding availability+60s and
  8h+60s freshness for last/prior references all passed. Recheck full final
  trigger artifact after successful retry. Final outcome review still pending.

## Hoàn tất 18/09/2026 — annual results and independent review

- UTF-8 retry session68750 EXIT0, all328symbols and40accounts completed.
  Actual output `backtest_utf8/accounts.json`; immutable input snapshot
  `3f2865593e62a24224d9db3231e4ef69d5487d41198225c72b952c00e41bcdd5`.
- Root full28163trigger timing/cooldown/window checks passed. All40account
  capital,10336executedrecord totals, coin/period and realized/unrealized
  conservation checks passed; max floating-point residual8.2e-11USD.
- Sol Medium final artifact review session23356 PASS, report
  `review/annual_results_review.md`. Zero material findings. No actual
  unknown/gap-lock accounts, all losing/exhausted/cutoff paths retained.
- 14/40positive. M48_2withdraw20bps +14093.49USD but RAVE+14843.43,
  RAVE/COAI-excluded static remainder−2003.20; not a counterfactual rerun.
  2xvs1x heavily affected by tranche resets/sizing, not simple leverage edge.
  E48_2withdrawpositive despite10burns and operating exhaustion; hedge
  capital decays to tiny non-executable amounts, minimum notional not modeled.
- Vietnamese findings `docs/ANNUAL_PROFIT_MECHANISM_FINDINGS_20260918.md`,
  all40table `docs/ANNUAL_PROFIT_RESULTS_20260918.md`; clarified candidate
  censoring columns vs actual executed open positions. Tests83passed.
- One-year objective achieved as provisional research, not verified live
  profit or causal squeeze/manipulation proof. No deploy/trades/Telegram.
