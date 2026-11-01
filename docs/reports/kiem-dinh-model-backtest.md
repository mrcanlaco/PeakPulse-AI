# Kiểm Định Model & Backtest Trên Dữ Liệu Lịch Sử

## Goal
Xây dựng pipeline backtest toàn diện dùng 2.6 năm dữ liệu Binance (327 coins, 52M+ rows từ `D:\Quant-trading\data_lake`) để kiểm định model chính xác hơn, train LightGBM trên tập dữ liệu lớn hơn 100x, và đo lường accuracy thực tế qua nhiều regime thị trường.

## Data Source
- `D:\Quant-trading\data_lake\klines\5m\` — 327 coins × 5m Parquet (2.2 GB)
- `D:\Quant-trading\data_lake\quant_master.duckdb` — 52.5M rows consolidated
- Time range: 2024-01-01 → 2026-08-28 (~948 days)
- Schema: `symbol, open_time, close_time, open, high, low, close, volume, quote_volume, taker_buy_volume`

## Tasks

- [ ] Task 1: Tạo `HistoricalDataAdapter` — bridge data_lake Parquet vào dao_vang pipeline → Verify: `uv run pytest tests/ -k "historical_adapter"` pass, load BTCUSDT 2024 data thành công
- [ ] Task 2: Tạo `FullBacktestRunner` CLI — chạy toàn bộ pipeline (features → labels → scoring → outcomes) trên dữ liệu lịch sử, output DuckDB backtest results → Verify: `dao-vang backtest run --data-dir D:\Quant-trading\data_lake --start 2025-01-01 --end 2025-06-30` chạy không lỗi
- [ ] Task 3: Train LightGBM trên dữ liệu lớn — Walk-Forward 10-fold trên 2024-01 → 2026-08, embargo 48h, dùng cả 327 coins → Verify: Precision ≥ 0.35 trên mỗi OOS fold, ECE ≤ 0.05
- [ ] Task 4: Regime-Conditioned Backtest — đo accuracy theo từng regime (TRENDING_BULL, TRENDING_BEAR, HIGH_VOL_CHOP, SIDEWAY) dùng `regime_classifier.py` → Verify: Báo cáo precision per-regime, identify regime yếu nhất
- [ ] Task 5: Stress Test trên Black Swan events — backtest riêng trên: LUNA crash (05/2024), BTC halving (04/2024), FTX aftermath, ETF approval rally → Verify: Model không generate false alerts trong crash events
- [ ] Task 6: Feature Importance & Ablation Study — SHAP trên LightGBM, loại bỏ từng nhóm feature, đo delta precision → Verify: Bảng ranking top 10 features, xác định features thừa
- [ ] Task 7: Compare Champion vs Challenger trên dữ liệu lịch sử — LogisticRegression (champion) vs LightGBM (challenger) vs ensemble trên cùng test periods → Verify: Bảng so sánh precision/recall/brier/ECE per model per period
- [ ] Task 8: Sinh Release-Grade Report — Bootstrap 95% CI, reliability curve, precision per-month, per-regime → Verify: `artifacts/backtest_report_YYYYMMDD.json` với đầy đủ metrics

## Done When
- [ ] LightGBM bundle đạt Precision ≥ 0.35 CI Lower ≥ 0.25 trên ≥ 5 OOS folds
- [ ] ECE ≤ 0.05 qua tất cả regimes
- [ ] Có báo cáo so sánh Champion vs Challenger rõ ràng
- [ ] Model không false-fire trong stress test events

## Notes
- **Binance API Limitation**: `/futures/data/*` endpoints (OI, taker, ratios) chỉ cho phép lookback ~30 ngày. Chỉ `/fapi/v1/fundingRate` cho phép truy xuất lịch sử đầy đủ.
- **Chiến lược dữ liệu**:
  - Funding rate: toàn bộ 2024-01 → 2026-08 (2.6 năm, ~327 coins)
  - OI/taker/ratios: chỉ 30 ngày gần nhất (tất cả coins)
  - Klines: đã có sẵn 2.6 năm × 327 coins trong data lake
- **Backtest strategy**: Features phụ thuộc OI/taker sẽ NULL cho dữ liệu trước 30d → chỉ dùng price + funding features cho backtest lịch sử dài, dùng full features cho 30 ngày gần nhất
- Walk-Forward trên 2.6 năm × 327 coins sẽ mất vài phút — cần chunked processing
- Kết quả backtest sẽ quyết định có promote LightGBM lên champion hay không
