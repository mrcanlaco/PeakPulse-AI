"""Nghiên cứu trên Nguyên tắc cải tiến:
- Train: 2020-01-01 đến 2023-12-31
- Validation: 2024-01-01 đến 2025-12-31
- Test: 2026-01-01 đến 2026-09-29
- Mục tiêu: Toàn giai đoạn CAGR / MaxDD > 3.0 (Calmar Ratio > 3.0) -> Ứng viên /goal
"""

from dataclasses import dataclass
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = Path("D:/SharedMarketData/multiyear_2020_2026")
KLINES_DIR = DATA_DIR / "klines_1h"
FUNDING_DIR = DATA_DIR / "funding_8h"
ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "walkforward_2020_2026"

TRAIN_START = pd.Timestamp("2020-01-01 00:00:00", tz="UTC")
TRAIN_END = pd.Timestamp("2023-12-31 23:59:59", tz="UTC")

VAL_START = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
VAL_END = pd.Timestamp("2025-12-31 23:59:59", tz="UTC")

TEST_START = pd.Timestamp("2026-01-01 00:00:00", tz="UTC")
TEST_END = pd.Timestamp("2026-09-29 23:00:00", tz="UTC")

FULL_START = TRAIN_START
FULL_END = TEST_END

UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LTCUSDT", "BCHUSDT"]

# Phí giao dịch và trượt giá bảo thủ (Conservative institutional cost model)
TAKER_FEE_BPS = 5.0       # 0.05% phí sàn Binance VIP0 taker (hoặc 0.02% maker)
SLIPPAGE_BPS = 5.0        # 0.05% trượt giá 1h execution
TOTAL_ONE_WAY_BPS = 10.0  # 0.10% tổng chi phí một chiều

INITIAL_CAPITAL = 100_000.0
CALMAR_GOAL_THRESHOLD = 3.0  # CAGR / MaxDD > 3.0
