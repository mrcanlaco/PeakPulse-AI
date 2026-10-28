"""Launcher script for PeakPulse Quantitative Shadow Paper Supervisor & Dashboard.
Runs single shared market feeder + single coordinator + lightweight FastAPI web dashboard.
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

# Add src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import uvicorn
from dao_vang.shadow.server import app, seed_candidates_from_catalog, get_coordinator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("shadow.launcher")


def main():
    parser = argparse.ArgumentParser(description="PeakPulse Shadow Supervisor Launcher")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8899, help="Port (default 8899)")
    parser.add_argument("--seed-only", action="store_true", help="Only seed DB candidates without starting web server")
    args = parser.parse_args()

    logger.info("Initializing SQLite database and seeding 20 candidates from catalog...")
    seed_candidates_from_catalog()

    if args.seed_only:
        logger.info("Seeding complete. Exiting (--seed-only specified).")
        return

    logger.info(f"Starting Shadow Paper Coordinator and Web Dashboard at http://{args.host}:{args.port}")
    # Pre-initialize coordinator
    get_coordinator()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
