"""Read-only cached-data counterfactual: remove one AKE event or all AKE events."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
from account_backtest_replay import simulate
from compare_account_risk import ROOT, exchange_rules, sha, summarize, write

from dao_vang.config.settings import ExecutionConfig
from dao_vang.execution.contracts import digest


def cached_inputs(source, cache, signals, rules):
    evidence = json.loads((cache / "data_evidence.json").read_text(encoding="utf-8"))
    if evidence["failures"]:
        raise ValueError("input_cache_has_failures")
    symbols = sorted({s["symbol"] for s in signals if s["symbol"] in rules})
    prices, funding = {}, {}
    db = duckdb.connect(str(source / "working.duckdb"), read_only=True)
    fdb = sqlite3.connect(
        f"file:{(cache / 'funding.sqlite3').as_posix()}?mode=ro", uri=True
    )
    proofs = {}
    for symbol in symbols:
        proof = evidence["symbols"][symbol]
        points = {}
        for opened, closed, op, close in db.execute(
            "SELECT epoch_ms(open_time),epoch_ms(close_time),open,close FROM prices WHERE symbol=? ORDER BY open_time",
            [symbol],
        ).fetchall():
            points.setdefault(opened, {})["entry_open"] = op
            points.setdefault(closed + 1, {})["execution_close"] = close
        supplement = proof["trade_prices"]
        if "path" in supplement:
            path = Path(supplement["path"])
            if sha(path) != supplement["sha256"]:
                raise ValueError("trade_checksum_mismatch")
            for row in json.loads(path.read_text(encoding="utf-8"))["rows"]:
                points.setdefault(int(row[0]), {}).setdefault(
                    "entry_open", float(row[1])
                )
                points.setdefault(int(row[6]) + 1, {}).setdefault(
                    "execution_close", float(row[4])
                )
        mark_path = Path(proof["marks"]["path"])
        if sha(mark_path) != proof["marks"]["sha256"]:
            raise ValueError("mark_checksum_mismatch")
        for row in json.loads(mark_path.read_text(encoding="utf-8"))["rows"]:
            points.setdefault(int(row[6]) + 1, {})["mark"] = float(row[4])
        for point in points.values():
            point.setdefault("mark", math.nan)
            point.setdefault("execution_close", math.nan)
        first = int(pd.Timestamp("2026-06-24T00:00:00Z").timestamp() * 1000)
        last = int(pd.Timestamp("2026-09-24T00:00:00Z").timestamp() * 1000)
        payload, checksum = fdb.execute(
            "SELECT payload,checksum FROM windows WHERE symbol=? AND start<=? AND end>=? ORDER BY end-start LIMIT 1",
            (symbol, first, last),
        ).fetchone()
        payload = json.loads(payload)
        if digest(payload) != checksum or checksum != proof["funding"]["sha256"]:
            raise ValueError("funding_checksum_mismatch")
        funding[symbol] = [
            (int(r["fundingTime"]), float(r["fundingRate"]), float(r["markPrice"]))
            for r in payload["rows"]
            if first <= int(r["fundingTime"]) <= last
        ]
        prices[symbol], proofs[symbol] = points, proof
    db.close()
    fdb.close()
    return prices, funding, proofs


def main():
    source = ROOT / "artifacts/account_backtest_20260924_3m/warehouse"
    cache = ROOT / "artifacts/account_risk_comparison_20260924"
    out = ROOT / "artifacts/account_without_ake_20260924"
    out.mkdir(exist_ok=True)
    signals = json.loads((source / "signals.json").read_text(encoding="utf-8"))
    original = json.loads((source / "positions_5.json").read_text(encoding="utf-8"))
    event = next(
        p["event_id"] for p in original["open_positions"] if p["symbol"] == "AKEUSDT"
    )
    scenarios = [
        ("baseline", "Giữ nguyên", lambda s: True),
        ("one_event", "Bỏ đúng lệnh AKE ngày 15/07", lambda s: s["event_id"] != event),
        ("no_ake", "Bỏ toàn bộ tín hiệu AKE", lambda s: s["symbol"] != "AKEUSDT"),
    ]
    rule_path = ROOT / "artifacts/annual_execution_20260918/exchange_info_current.json"
    rules = exchange_rules(rule_path)
    prices, funding, proofs = cached_inputs(source, cache, signals, rules)
    write(out / "data_evidence.json", proofs)
    protocol = dict(
        created_at=pd.Timestamp.now(tz="UTC").isoformat(),
        omitted_event=event,
        ake_events=[s for s in signals if s["symbol"] == "AKEUSDT"],
        source_signals_sha256=sha(source / "signals.json"),
        rules_sha256=sha(rule_path),
        engine_sha256=sha(Path(__file__).with_name("account_backtest_replay.py")),
        runner_sha256=sha(Path(__file__)),
        hypothesis="Ex-post sensitivity only: remove exactly the original event, separately remove all AKE events. Reallocate freed slots normally.",
        policy="Original 500 USDT, 25 USDT notional, Cross x5, no SL/time exit, pause new entries at 20% drawdown; locked ATR TP.",
        limitations=json.loads((source / "report.json").read_text(encoding="utf-8"))[
            "limitations"
        ],
    )
    write(out / "protocol.json", protocol)
    times = [
        int(t.timestamp() * 1000)
        for t in pd.date_range(
            "2026-06-24T00:00:00Z", "2026-09-24T00:00:00Z", freq="5min"
        )
    ]
    results, regression, ledgers = [], [], []
    figure = go.Figure()
    for scenario, label, keep in scenarios:
        grouped = defaultdict(list)
        selected = [s for s in signals if keep(s)]
        for signal in selected:
            grouped[signal["at"]].append(signal)
        for rows in grouped.values():
            rows.sort(key=lambda x: (-x["probability"], x["symbol"]))
        for cost, fee, slip in [("base", 0.0005, 20), ("stress", 0.001, 50)]:
            if scenario == "baseline" and cost == "stress":
                continue
            for cap in (1, 3, 5):
                result = simulate(
                    times,
                    grouped,
                    lambda s: prices.get(s, {}),
                    rules,
                    lambda s: funding[s],
                    ExecutionConfig(
                        max_open_positions=cap, fee_rate=fee, max_slippage_bps=slip
                    ),
                )
                result.update(
                    method="historical_mark_prices_ake_counterfactual",
                    liquidation_status="unknown_historical_maintenance_brackets_and_intrabar_path",
                )
                row = summarize(result, scenario, label, {}, cap, cost, "full")
                row["omitted_events"] = len(signals) - len(selected)
                row["closed_trade_net"] = result["closed_trade_net"]
                row["open_positions"] = result["open_positions"]
                row["ake_entries"] = [
                    j
                    for j in result["journal"]
                    if j["kind"] == "entry" and j["symbol"] == "AKEUSDT"
                ]
                if scenario == "no_ake":
                    assert not row["ake_entries"]
                if scenario == "one_event":
                    assert not any(
                        j.get("event_id") == event for j in result["journal"]
                    )
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
                    ledgers.append(row["id"])
                if scenario == "baseline":
                    previous = json.loads(
                        (source / f"positions_{cap}.json").read_text(encoding="utf-8")
                    )
                    checks = {
                        k: result[k] == previous[k]
                        for k in [
                            "entries",
                            "tp_exits",
                            "stop_event",
                            "closed_trade_net",
                            "ending_equity",
                        ]
                    }
                    assert all(checks.values()), checks
                    regression.append(dict(cap=cap, checks=checks))
                results.append(row)
                write(out / f"{row['id']}.json", result)
                pd.DataFrame(result["journal"]).to_csv(
                    out / f"{row['id']}_trades.csv", index=False
                )
                if cost == "base" and scenario != "baseline":
                    frame = pd.DataFrame(result["curve"])
                    groups = frame.groupby(frame["at"] // 3600000)
                    indices = sorted(
                        set(groups.equity.idxmin())
                        | set(groups.equity.idxmax())
                        | {0, len(frame) - 1}
                    )
                    small = frame.loc[indices]
                    figure.add_trace(
                        go.Scatter(
                            x=pd.to_datetime(small["at"], unit="ms", utc=True),
                            y=small.equity,
                            mode="lines",
                            name=f"{label} · {cap} vị thế",
                        )
                    )
                print(
                    json.dumps(
                        {
                            k: row[k]
                            for k in [
                                "id",
                                "ending_equity",
                                "pnl",
                                "max_drawdown",
                                "entries",
                                "exits",
                                "open_count",
                                "errors",
                            ]
                        }
                    ),
                    flush=True,
                )
    write(
        out / "summary.json",
        dict(
            protocol=protocol,
            results=results,
            baseline_regression=regression,
            reconciled_complete_runs=ledgers,
            financially_verified=False,
            promotion_eligible=False,
        ),
    )
    pd.DataFrame(
        [
            {k: v for k, v in row.items() if k not in ["open_positions", "ake_entries"]}
            for row in results
        ]
    ).to_csv(out / "comparison.csv", index=False)
    report = [
        "# Đảo Vàng: nếu bỏ AKE",
        "",
        "**Phân tích giả định sau khi đã biết kết quả, không phải bộ lọc có lợi thế đã kiểm chứng.** Giữ nguyên cấu hình 500 USDT, Cross x5, không stop-loss. Bỏ một lệnh và bỏ toàn bộ coin là hai phép thử riêng; chỗ trống được giao dịch các tín hiệu kế tiếp bình thường.",
        "",
        "24/06–24/09/2026; tín hiệu chỉ có đến 07/09, sau đó chỉ quản lý lệnh còn mở. Mark/funding lịch sử, phí cơ sở 0,05%/chiều, trượt giá vào 0,20%. Stress phí 0,10%, trượt giá 0,50%. MMR giả định 1%, chưa mô phỏng intrabar và khớp từng phần. Model huấn luyện trùng một phần kỳ. Tất cả tài sản cuối kỳ đều gồm lãi/lỗ chưa chốt.",
        "",
        f"Có {len(protocol['ake_events'])} tín hiệu AKE trong tập đầu vào. Bỏ đúng lệnh 15/07 vẫn cho phép vào AKE khi có tín hiệu khác.",
        "",
        "| Phương án | Tối đa vị thế | Tài sản cuối* | PnL* | DD % | Vào/TP/còn mở | PnL chưa chốt |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    def fmt(x):
        return "Chưa xác định" if x is None else f"{x:.2f}"

    for r in results:
        if r["cost"] == "base":
            report.append(
                f"| {r['label']} | {r['cap']} | {fmt(r['ending_equity'])} | {fmt(r['pnl'])} | {r['max_drawdown'] * 100:.2f} | {r['entries']}/{r['tp']}/{r['open_count']} | {r['open_pnl']:.2f} |"
            )
    report.extend(
        [
            "",
            "* Có điều kiện trên tập tín hiệu quan sát được. Ngưỡng giảm 20% chỉ khóa mở mới, không đóng lệnh cũ. Mức giảm trên 100% do mẫu 5 phút vượt ngưỡng thanh lý giả định, không xác nhận số dư thật bị âm.",
            "",
            "## Vị thế còn mở",
            "",
        ]
    )
    for r in results:
        if r["cost"] != "base" or r["policy_id"] == "baseline":
            continue
        report.append(f"### {r['label']}, tối đa {r['cap']} vị thế")
        for p in r["open_positions"]:
            report.append(
                f"- {p['symbol']}: PnL chưa chốt {p['unrealized']:.2f} USDT; giữ {p['held_days']:.2f} ngày."
            )
        report.append("")
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    table = pd.DataFrame(
        [
            dict(
                Phương_án=r["label"],
                Vị_thế=r["cap"],
                Tài_sản_cuối=fmt(r["ending_equity"]),
                Lãi_lỗ=fmt(r["pnl"]),
                Giảm_từ_đỉnh=f"{100 * r['max_drawdown']:.2f}%",
                Vào=r["entries"],
                TP=r["tp"],
                Còn_mở=r["open_count"],
            )
            for r in results
            if r["cost"] == "base"
        ]
    )
    table.columns = [column.replace("_", " ") for column in table.columns]
    figure.update_layout(
        template="plotly_dark",
        height=540,
        margin=dict(l=50, r=20, t=30, b=100),
        legend=dict(orientation="h", y=-0.2),
        yaxis_title="Tổng tài sản (USDT)",
    )
    html = (
        '<!doctype html><html lang="vi"><meta charset="utf-8"><title>Đảo Vàng · Nếu bỏ AKE</title><style>body{font-family:Segoe UI,Arial;background:#0c1625;color:#e2e8f0;max-width:1400px;margin:30px auto;padding:20px}p{line-height:1.65;color:#b8c9dc}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:right;border-bottom:1px solid #334155}td:first-child,th:first-child{text-align:left}.notice{padding:18px;background:#332b15;color:#f3d894;border-radius:12px}a{color:#7dd3fc}</style><h1>Nếu bỏ AKE, tài khoản thay đổi thế nào?</h1><p>500 USDT · Short Cross x5 · Không stop-loss · 24/06–24/09/2026</p><p class="notice">Có 7 tín hiệu AKE. Bỏ đúng lệnh ngày 15/07 và bỏ toàn bộ coin cho kết quả khác nhau. Đây là giả định sau khi biết kết quả, không chứng minh bộ chọn coin tốt hơn. Tín hiệu chỉ đến 07/09; phần sau chỉ quản lý vị thế. Thanh lý dùng MMR giả định 1%; không phải lịch sử tài khoản thật.</p>'
        + table.to_html(index=False, border=0)
        + "<p>“Chưa xác định” trong các hàng trên là do chạm ngưỡng thanh lý giả định. Mức giảm trên 100% do mẫu 5 phút vượt ngưỡng, không xác nhận tài khoản thật bị âm.</p>"
        + figure.to_html(full_html=False, include_plotlyjs=True)
        + '<p>Tài sản cuối gồm lãi/lỗ chưa chốt. Chỗ trống được nhận tín hiệu tiếp theo bình thường. Bảng dùng phí 0,05%/chiều và trượt giá 0,20%; CSV có thêm mức chi phí cao hơn. Đường dừng nếu chạm ngưỡng thanh lý hoặc thiếu dữ liệu.</p><p><a href="report.md">Báo cáo và lệnh còn mở</a> · <a href="comparison.csv">Tải bảng CSV</a> · <a href="summary.json">Dữ liệu kiểm chứng</a></p></html>'
    )
    (out / "dashboard.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
