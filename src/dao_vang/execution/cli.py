"""Operator tools; none of these commands activates real trading."""

import json
from pathlib import Path

import typer

from dao_vang.config.settings import load_runtime_settings
from dao_vang.experiments.forward_test import load_frozen_model

from .contracts import canonical, source_contract
from .evidence import evaluate_evidence
from .replay import compare_replay
from .sources import freeze_manifest

app = typer.Typer(help="Đóng băng chiến lược, kiểm định và xem trạng thái giao dịch.")


@app.command("connect-account")
def connect_account(config: Path, replace: bool = False):
    """Nhập kín khóa Binance thật trên máy chủ; chỉ kiểm tra quyền đọc."""
    import getpass
    import sys

    from .account_credentials import save_credentials
    from .account_monitor import AccountMonitor, monitor_store

    settings = load_runtime_settings(config)
    if (
        not settings.account_monitor.enabled
        or settings.execution.enabled
        or settings.execution.live_activated
    ):
        raise typer.BadParameter(
            "Cần bật account_monitor và tắt execution/live_activated trước."
        )
    if not sys.stdin.isatty():
        raise typer.BadParameter(
            "Chạy trong terminal tương tác để nhập kín; không truyền khóa trên dòng lệnh."
        )
    if settings.account_monitor.credentials_file.exists() and not replace:
        raise typer.BadParameter("Đã có file khóa. Dùng --replace nếu muốn thay khóa.")
    typer.echo(
        "BINANCE THẬT — CHỈ ĐỌC. Không đặt/hủy lệnh, không đổi ký quỹ hoặc đòn bẩy."
    )
    try:
        key = getpass.getpass("API Key (nhập ẩn): ").strip()
        secret = getpass.getpass("API Secret HMAC (nhập ẩn): ").strip()
        save_credentials(
            settings.account_monitor.credentials_file, key, secret, replace=replace
        )
        del key, secret
    except (Exception, KeyboardInterrupt):
        typer.echo(
            "Không lưu được khóa. Kiểm tra định dạng HMAC/quyền ghi hoặc thử lại; khóa không được in ra."
        )
        raise typer.Exit(1) from None
    if AccountMonitor(settings).poll():
        typer.echo(
            "Đã đọc tài khoản Binance thật thành công. Chế độ chỉ theo dõi; giao dịch vẫn TẮT."
        )
    else:
        reason = monitor_store(settings).get("heartbeat", {}).get("error", "unknown")
        typer.echo(
            f"Đã lưu khóa kín nhưng CHƯA kết nối thành công: {reason}. Kiểm tra quyền đọc Futures/IP."
        )
        raise typer.Exit(1)


@app.command("check-account")
def check_account(config: Path):
    """Kiểm tra kết nối chỉ đọc; không in khóa hoặc số dư tài khoản."""
    from .account_monitor import AccountMonitor, monitor_store

    settings = load_runtime_settings(config)
    ok = AccountMonitor(settings).poll()
    typer.echo(
        json.dumps(
            {
                "connected": ok,
                "read_only": True,
                "error": monitor_store(settings).get("heartbeat", {}).get("error"),
            },
            ensure_ascii=False,
        )
    )
    if not ok:
        raise typer.Exit(1)


@app.command("snapshot")
def snapshot(data: Path, artifacts: Path, output: Path, services_stopped: bool = False):
    from .archive import capture_runtime

    if not services_stopped:
        raise typer.BadParameter(
            "Dừng scanner, web và execution trước khi chụp snapshot nhất quán."
        )
    capture_runtime(data, artifacts, output)
    typer.echo("Đã chụp dữ liệu vận hành và artifacts có checksum.")


@app.command("restore-check")
def restore_check(snapshot: Path, output: Path):
    from .archive import restore_runtime

    restored = restore_runtime(snapshot, output)
    typer.echo(f"Đã phục hồi {len(restored['files'])} file vào thư mục mới.")


@app.command("freeze")
def freeze(config: Path, output: Path):
    settings = load_runtime_settings(config)
    if not settings.scanner.frozen_model_id:
        raise typer.BadParameter("Chưa cấu hình frozen_model_id")
    info = load_frozen_model(
        settings.scanner.frozen_model_id, settings.scanner.artifact_dir
    )
    root = Path(__file__).resolve().parents[3]
    manifest = freeze_manifest(
        root,
        info.model_path.parent,
        info.model_id,
        info.label_spec["version"],
        info.threshold,
        settings.execution,
        source_contract(settings.scanner),
    )
    if output.exists():
        raise typer.BadParameter(
            "Không ghi đè manifest đã đóng băng; chọn đường dẫn mới."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"Manifest: {manifest.identity}")


@app.command("replay")
def run_replay(config: Path, inputs: Path, output: Path):
    settings = load_runtime_settings(config)
    from .contracts import StrategyManifest

    if not settings.execution.manifest_path:
        raise typer.BadParameter("Thiếu manifest_path")
    manifest = StrategyManifest.model_validate_json(
        settings.execution.manifest_path.read_text(encoding="utf-8")
    )
    manifest.verify(Path(__file__).resolve().parents[3], settings.execution)
    frames = json.loads(inputs.read_text(encoding="utf-8"))
    result = compare_replay(frames, settings.execution, manifest.identity)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical(result), encoding="utf-8")
    typer.echo("Đã xuất mô phỏng lịch sử; không phải bằng chứng cho phép tiền thật.")


@app.command("evidence")
def evidence(report: Path, manifest_id: str):
    result = evaluate_evidence(
        json.loads(report.read_text(encoding="utf-8")), manifest_id
    )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["eligible"]:
        raise typer.Exit(1)


@app.command("export-forward")
def forward(config: Path, output: Path):
    from dao_vang.web.execution_api import execution_store

    from .contracts import StrategyManifest
    from .forward_report import export_forward

    settings = load_runtime_settings(config)
    if not settings.execution.manifest_path:
        raise typer.BadParameter("Thiếu manifest_path")
    manifest = StrategyManifest.model_validate_json(
        settings.execution.manifest_path.read_text(encoding="utf-8")
    )
    manifest.verify(Path(__file__).resolve().parents[3], settings.execution)
    report = export_forward(execution_store(settings), manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical(report), encoding="utf-8")
    typer.echo(
        "Đã xuất quan sát; chưa có chứng nhận tài chính và không tự mở tiền thật."
    )


@app.command("status")
def status(config: Path):
    from dao_vang.web.execution_api import status as read_status

    typer.echo(
        json.dumps(
            read_status(load_runtime_settings(config)), ensure_ascii=False, indent=2
        )
    )
