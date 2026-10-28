#!/usr/bin/env python3
"""PeakPulse AI - Autonomous Trading & Scanning Orchestrator.

Điều phối tự động toàn diện:
1. Scanner Daemon (quét thị trường, phát hiện tín hiệu phân phối đỉnh)
2. Execution Engine Daemon (quản lý lệnh, cắt lỗ tự động, trailing chốt lời)
3. Web Dashboard (giao diện theo dõi vị thế, số dư, hiệu suất realtime)
4. Watchdog Process Monitor (tự động phát hiện lỗi và duy trì hoạt động liên tục)
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from dao_vang.config.settings import load_runtime_settings
from dao_vang.execution.contracts import StrategyManifest


class AutonomousOrchestrator:
    def __init__(self, config_path: str = "configs/trading_auto.yaml", run_web: bool = True):
        self.config_path = ROOT_DIR / config_path
        self.run_web = run_web
        self.processes: dict[str, subprocess.Popen] = {}
        self.running = True
        self.python_exe = sys.executable

        # Verify configuration
        if not self.config_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy file cấu hình: {self.config_path}")

        self.settings = load_runtime_settings(self.config_path)
        print("=" * 70)
        print("   PEAKPULSE AI (DAO VANG) - HE THONG VAN HANH TU DONG TOAN DIEN")
        print("=" * 70)
        print(f" * File cau hinh : {self.config_path.name}")
        print(f" * Che do Scanner: {self.settings.scanner.operating_mode}")
        print(f" * Moi truong Lenh: {self.settings.execution.environment.upper()}")
        print(f" * Auto Trading  : {'BAT' if self.settings.execution.enabled else 'TAT'}")
        print(f" * Stop Loss     : {'BAT (' + str(self.settings.execution.sl_max_loss_usdt) + ' USDT)' if self.settings.execution.enable_stop_loss else 'TAT'}")
        print(f" * Trailing TP   : {'BAT (' + str(self.settings.execution.trailing_trigger_atr) + ' ATR)' if self.settings.execution.enable_trailing_tp else 'TAT'}")
        print(f" * Max Hold Hours: {self.settings.execution.max_hold_hours}h")
        print(f" * Web Dashboard : {'http://localhost:' + str(self.settings.web.port) if self.run_web else 'TAT'}")
        print("=" * 70)

        # Verify strategy manifest if execution is enabled
        if self.settings.execution.enabled:
            manifest_file = self.settings.execution.manifest_path
            if not manifest_file or not (ROOT_DIR / manifest_file).is_file():
                print(f"[CANH BAO] Manifest chua ton tai: {manifest_file}")
            else:
                manifest_data = (ROOT_DIR / manifest_file).read_text(encoding="utf-8")
                manifest = StrategyManifest.model_validate_json(manifest_data)
                manifest.verify(ROOT_DIR, self.settings.execution)
                print(f"[OK] Da xac thuc Strategy Manifest: {manifest.identity[:16]}... (Bao ve chong gian lan)")

    def _start_process(self, name: str, cmd: List[str]) -> subprocess.Popen:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src")
        env["DAO_VANG_CONFIG_PATH"] = str(self.config_path)
        print(f"[STARTING] Khoi dong tien trinh: {name} ...")
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        self.processes[name] = proc
        return proc

    def start_all(self):
        # 1. Scanner Daemon
        scanner_cmd = [
            self.python_exe,
            "-m",
            "dao_vang",
            "scanner",
            "start",
            "--config",
            str(self.config_path),
        ]
        self._start_process("Scanner Daemon", scanner_cmd)
        time.sleep(2)

        # 2. Execution Engine Daemon
        if self.settings.execution.enabled:
            exec_cmd = [
                self.python_exe,
                "-m",
                "dao_vang",
                "execution",
                "start",
                "--config",
                str(self.config_path),
            ]
            self._start_process("Execution Engine", exec_cmd)
            time.sleep(1)

        # 3. Web Dashboard Server
        if self.run_web:
            web_cmd = [
                self.python_exe,
                "-m",
                "uvicorn",
                "dao_vang.web.app:app",
                "--host",
                self.settings.web.host,
                "--port",
                str(self.settings.web.port),
            ]
            self._start_process("Web Dashboard", web_cmd)

        print("\n[READY] Toan bo he thong da san sang va dang chay tu dong.")
        print("Nhan Ctrl+C de dung toan bo he thong an toan.\n")

    def monitor_loop(self):
        try:
            while self.running:
                for name, proc in list(self.processes.items()):
                    ret = proc.poll()
                    if ret is not None:
                        print(f"\n[CANH BAO] Tien trinh {name} da dung voi ma thoat: {ret}")
                        # Auto restart unless stopped
                        if self.running:
                            print(f"[WATCHDOG] Tu dong khoi dong lai {name} sau 5s...")
                            time.sleep(5)
                            if name == "Scanner Daemon":
                                cmd = [self.python_exe, "-m", "dao_vang", "scanner", "start", "--config", str(self.config_path)]
                            elif name == "Execution Engine":
                                cmd = [self.python_exe, "-m", "dao_vang", "execution", "start", "--config", str(self.config_path)]
                            elif name == "Web Dashboard":
                                cmd = [self.python_exe, "-m", "uvicorn", "dao_vang.web.app:app", "--host", self.settings.web.host, "--port", str(self.settings.web.port)]
                            else:
                                continue
                            self._start_process(name, cmd)
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n[STOPPING] Nhan lenh dung (Ctrl+C). Dang tat tat ca tien trinh...")
            self.stop_all()

    def stop_all(self):
        self.running = False
        for name, proc in self.processes.items():
            if proc.poll() is None:
                print(f"[TERMINATE] Dang dong {name} ...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"[KILL] Cuong che dong {name} ...")
                    proc.kill()
        print("[SHUTDOWN] He thong da tat hoan toan an toan.")


def main():
    parser = argparse.ArgumentParser(description="Khoi chay he thong Dao Vang tu dong")
    parser.add_argument(
        "--config",
        default="configs/trading_auto.yaml",
        help="Duong dan toi file cau hinh (mac dinh: configs/trading_auto.yaml)",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Khong khoi dong Web Dashboard Server",
    )
    args = parser.parse_args()

    orchestrator = AutonomousOrchestrator(
        config_path=args.config,
        run_web=not args.no_web,
    )

    def sig_handler(sig, frame):
        orchestrator.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    orchestrator.start_all()
    orchestrator.monitor_loop()


if __name__ == "__main__":
    main()
