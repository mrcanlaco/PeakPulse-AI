"""Offline capacity experiment; never changes production ExecutionConfig or orders."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from account_backtest_replay import simulate
from backtest_without_ake import cached_inputs
from compare_account_risk import ROOT, exchange_rules, sha, write

from dao_vang.config.settings import ExecutionConfig


def main():
    source = ROOT / "artifacts/account_backtest_20260924_3m/warehouse"
    cache = ROOT / "artifacts/account_risk_comparison_20260924"
    out = ROOT / "artifacts/account_uncapped_20260924"
    out.mkdir(exist_ok=True)
    signals = json.loads((source / "signals.json").read_text(encoding="utf-8"))
    rule_path = ROOT / "artifacts/annual_execution_20260918/exchange_info_current.json"
    rules = exchange_rules(rule_path)
    prices, funding, proof = cached_inputs(source, cache, signals, rules)
    # More slots than distinct input symbols is mathematically non-binding
    # while the one-position-per-symbol/no-DCA invariant remains in force.
    capacity = len({s["symbol"] for s in signals}) + 1
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        source_signals_sha256=sha(source / "signals.json"),
        rules_sha256=sha(rule_path),
        runner_sha256=sha(Path(__file__)),
        engine_sha256=sha(Path(__file__).with_name("account_backtest_replay.py")),
        cache_loader_sha256=sha(Path(__file__).with_name("backtest_without_ake.py")),
        nonbinding_capacity=capacity,
        variants=[
            "5 slots + pause 20%",
            "uncapped + pause 20%",
            "uncapped + no entry pause",
        ],
        fixed_policy="500 USDT Cross x5, 25 USDT notional, no SL/time exits, one position per symbol, no DCA, available margin required; original locked ATR TP",
        no_pause_implementation="Research namespace uses None to disable the entry pause; insolvency checks still run. Production model/schema is unchanged.",
        limitations=json.loads((source / "report.json").read_text(encoding="utf-8"))[
            "limitations"
        ],
    )
    write(out / "protocol.json", protocol)
    write(out / "data_evidence.json", proof)
    times = [
        int(t.timestamp() * 1000)
        for t in pd.date_range(
            "2026-06-24T00:00:00Z", "2026-09-24T00:00:00Z", freq="5min"
        )
    ]
    summaries = []
    for exclude_ake in (True, False):
        grouped = defaultdict(list)
        selected = [s for s in signals if not exclude_ake or s["symbol"] != "AKEUSDT"]
        for s in selected:
            grouped[s["at"]].append(s)
        for rows in grouped.values():
            rows.sort(key=lambda x: (-x["probability"], x["symbol"]))
        for variant, cap, pause in [
            ("cap5", 5, True),
            ("uncapped_pause", capacity, True),
            ("uncapped_no_pause", capacity, False),
        ]:
            for cost, fee, slip in [("base", 0.0005, 20), ("stress", 0.001, 50)]:
                settings = ExecutionConfig(
                    fee_rate=fee, max_slippage_bps=slip
                ).model_dump()
                settings.update(
                    max_open_positions=cap, entry_pause_drawdown=0.2 if pause else None
                )
                result = simulate(
                    times,
                    grouped,
                    lambda s: prices.get(s, {}),
                    rules,
                    lambda s: funding[s],
                    SimpleNamespace(**settings),
                )
                result.update(
                    method="historical_mark_prices_uncapped_capacity_counterfactual",
                    liquidation_status="unknown_historical_brackets_and_intrabar_path",
                )
                run_id = f"{'no_ake' if exclude_ake else 'all_coins'}_{variant}_{cost}"
                journal = result["journal"]
                active = {}
                peak_slots = 0
                for j in journal:
                    if j["kind"] == "entry":
                        assert j["symbol"] not in active
                        active[j["symbol"]] = j
                        peak_slots = max(peak_slots, len(active))
                    elif "net" in j:
                        assert j["symbol"] in active
                        del active[j["symbol"]]
                assert peak_slots <= cap
                if cap == capacity:
                    assert (
                        peak_slots < capacity
                    )  # capacity can never reject a distinct coin
                assert len(active) == len(result["open_positions"])
                if not pause:
                    assert not result["entry_paused"]
                if result["ending_equity"] is not None:
                    expected = (
                        500
                        + result["closed_trade_net"]
                        + sum(
                            p["unrealized"] - p["entry_fee"] + p["funding"]
                            for p in result["open_positions"]
                        )
                    )
                    assert abs(expected - result["ending_equity"]) < 1e-7
                if variant == "cap5" and cost == "base":
                    old_path = (
                        (
                            ROOT
                            / "artifacts/account_without_ake_20260924/full_base_5_no_ake.json"
                        )
                        if exclude_ake
                        else source / "positions_5.json"
                    )
                    previous = json.loads(old_path.read_text(encoding="utf-8"))
                    for k in [
                        "entries",
                        "tp_exits",
                        "ending_equity",
                        "closed_trade_net",
                        "stop_event",
                        "rejections",
                    ]:
                        assert result[k] == previous[k], (run_id, k)
                paused_at = next(
                    (c["at"] for c in result["curve"] if c["paused"]), None
                )
                entries = [j for j in journal if j["kind"] == "entry"]
                summary = dict(
                    id=run_id,
                    exclude_ake=exclude_ake,
                    variant=variant,
                    cost=cost,
                    entry_pause_enabled=pause,
                    eligible_signal_events=len(selected),
                    entries=result["entries"],
                    tp=result["tp_exits"],
                    ending_equity=result["ending_equity"],
                    pnl=result["pnl"],
                    max_drawdown=result["sampled_max_drawdown"],
                    peak_concurrent_positions=peak_slots,
                    open_positions=result["open_positions"],
                    open_pnl=sum(p["unrealized"] for p in result["open_positions"]),
                    fees=result["fees"],
                    funding=result["funding"],
                    rejections=result["rejections"],
                    paused_at=paused_at,
                    last_entry_at=entries[-1]["at"] if entries else None,
                    errors=result["errors"],
                    stop_event=result["stop_event"],
                    financially_verified=False,
                    promotion_eligible=False,
                )
                summaries.append(summary)
                write(out / f"{run_id}.json", result)
                pd.DataFrame(journal).to_csv(out / f"{run_id}_trades.csv", index=False)
                print(
                    json.dumps(
                        {
                            k: v
                            for k, v in summary.items()
                            if k not in ["open_positions"]
                        }
                    ),
                    flush=True,
                )
    write(
        out / "summary.json",
        dict(
            protocol=protocol,
            results=summaries,
            baseline_regression_passed=True,
            accounting_and_capacity_checks_passed=True,
        ),
    )
    pd.DataFrame(
        [{k: v for k, v in r.items() if k not in ["open_positions"]} for r in summaries]
    ).to_csv(out / "comparison.csv", index=False)
    labels = {
        "cap5": "Tối đa 5, khóa mở mới 20%",
        "uncapped_pause": "Không giới hạn, khóa mở mới 20%",
        "uncapped_no_pause": "Không giới hạn, bỏ cả khóa mở mới",
    }
    text = [
        "# Bỏ giới hạn số vị thế — 24/09/2026",
        "",
        "Thử nghiệm trên cùng dữ liệu 24/06–24/09/2026, vốn 500 USDT, Cross x5, 25 USDT danh nghĩa/lệnh, không stop-loss. Một coin chỉ một vị thế, không DCA, phải đủ ký quỹ. Số vị thế không giới hạn không đồng nghĩa được vay thêm vốn hoặc vào lặp coin đang giữ. Không thay đổi cấu hình live.",
        "",
        "Tín hiệu chỉ có đến 07/09; phần sau chỉ quản lý vị thế. Model huấn luyện trùng một phần kỳ; loại AKE là giả định sau khi biết kết quả. TP giả định khớp khi giá đóng nến đi qua giá mục tiêu, MMR giả định 1%, chưa mô phỏng intrabar. Kết quả cuối kỳ có điều kiện trên tập tín hiệu đã quan sát, không đủ điều kiện live.",
        "",
        "| AKE | Quy tắc | Số vào | Đã TP | Mở đồng thời nhiều nhất | Còn mở | Tài sản cuối | PnL | DD |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summaries:
        if r["cost"] != "base":
            continue
        end = (
            "Chưa xác định"
            if r["ending_equity"] is None
            else f"{r['ending_equity']:.2f}"
        )
        pnl = "Chưa xác định" if r["pnl"] is None else f"{r['pnl']:.2f}"
        text.append(
            f"| {'Bỏ AKE' if r['exclude_ake'] else 'Giữ AKE'} | {labels[r['variant']]} | {r['entries']} | {r['tp']} | {r['peak_concurrent_positions']} | {len(r['open_positions'])} | {end} | {pnl} | {r['max_drawdown']:.2%} |"
        )
    text += [
        "",
        "Phí cơ sở 0,05%/chiều; trượt giá thị trường 0,20%. comparison.csv và summary.json có stress phí 0,10%, trượt giá 0,50%. Tài sản cuối bao gồm mọi vị thế còn mở. Chưa xác định nghĩa là vi phạm MMR, dữ liệu không đủ hoặc mục tiêu TP không còn biểu diễn được bằng giá dương sau funding; không giả định tài sản sau thanh lý. Giảm trên 100% là mẫu 5 phút vượt ngưỡng, không xác nhận số dư thật bị âm.",
        "",
        "## Lý do không vào hết tín hiệu",
        "",
    ]
    for r in summaries:
        if r["cost"] == "base":
            text.extend(
                [
                    f"- {r['id']}: {json.dumps(r['rejections'])}. Lỗi kết thúc: {json.dumps(r['errors'])}. Khóa từ {pd.to_datetime(r['paused_at'], unit='ms', utc=True) if r['paused_at'] else 'không khóa'}."
                ]
            )
    (out / "report.md").write_text("\n".join(text), encoding="utf-8")


if __name__ == "__main__":
    main()
