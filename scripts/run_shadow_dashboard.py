#!/usr/bin/env python3
"""Launcher for PeakPulse AI Shadow Paper Trading Web Hub.

Chạy máy chủ Dashboard quản lý các Shadow Paper Bots local:
  http://127.0.0.1:8000
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import uvicorn
from dao_vang.shadow.web_dashboard import app

if __name__ == "__main__":
    print("=" * 80)
    print("  PEAKPULSE AI - SHADOW PAPER TRADING LOCAL HUB")
    print("  Truy cap Web Dashboard tai: http://127.0.0.1:8000")
    print("  Mo phong nhieu Shadow Bot chay dong thoi ma chi dung 1 Shared Feed!")
    print("=" * 80)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
