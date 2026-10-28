"""Build docs/NOSTOP_CANDIDATES_20261006.md from locked-candidate results."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import OUT_DIR, ROOT
from .lab import Lab
from .registry import ROUNDS_DIR, access_summary

DOC = ROOT / "docs" / "NOSTOP_CANDIDATES_20261006.md"


def round_table() -> pd.DataFrame:
    rows = []
    for d in sorted(ROUNDS_DIR.iterdir()):
        vp = d / "val_results.parquet"
        if not vp.exists():
            continue
        v = pd.read_parquet(vp).sort_values("val_calmar", ascending=False)
        n_tr = json.loads((d / "n_trials.json").read_text())["train_configs"]
        rows.append(
            {
                "round": d.name,
                "train_configs": n_tr,
                "frozen": len(v),
                "val>1": int((v.val_calmar > 1).sum()),
                "best_val": float(v.val_calmar.max()),
                "top20_mean_val": float(v.val_calmar.head(20).mean()),
            }
        )
    t = pd.DataFrame(rows)
    t["gain_vs_prev_best_round"] = t.top20_mean_val.div(t.top20_mean_val.cummax().shift(1)) - 1
    return t


def describe(row: pd.Series) -> str:
    p = json.loads(row.params)
    if row.family == "mkt_flow":
        return f"mkt_flow L{p['L']} z{p['zwin']} thr{p['thr']} {p['asset']} {p['mode']}"
    tier = " tier-neutral" if p.get("tier_neutral") else ""
    sm = f" smooth{p['smooth_days']}d" if p.get("smooth_days") else ""
    return (
        f"{p['factors']} · q{p['q']} K{p['K']} rebal{p['rebal']}d buf{p.get('buffer', 0)}"
        f"{sm}{tier}{' ivol' if p.get('wt') == 'ivol' else ''}"
    )


def post_lock_check(start: str = "2026-09-01 00:00") -> dict | None:
    """Replay every locked spec over bars that did not exist in the research panel."""
    from .registry import load_lock
    from .shadow.binance import PublicClient
    from .shadow.book import shadow_state, shared_context
    from .shadow.feed import SharedFeed
    from .shadow.store import DATA_DIR

    feed = SharedFeed(DATA_DIR, PublicClient())
    if not feed.path.exists():
        return None
    feed.load()
    panel, _ = feed.panel()
    ctx, cost = shared_context(panel)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    i0 = int(np.searchsorted(feed.index, start_ms))
    rets, dds = [], []
    days = 0.0
    for s in load_lock()["specs"]:
        st = shadow_state(panel, ctx, cost, {"family": s["family"], "params": s["params"]}, i0, 10000.0)
        rets.append(st["return"])
        dds.append(st["max_dd"])
        days = st["days"]
    r = np.array(rets)
    return {
        "n": len(r), "pos": int((r > 0).sum()), "median_ret": float(np.median(r)),
        "median_dd": float(np.median(dds)), "worst_ret": float(r.min()), "best_ret": float(r.max()),
        "days": days, "asof": str(panel.index[-1])[:16] + "Z",
        "btc": float(panel.open[-1, panel.symbols.index("BTCUSDT")] / panel.open[i0, panel.symbols.index("BTCUSDT")] - 1),
    }


def main() -> None:
    fin = pd.read_csv(OUT_DIR / "final_results.csv")
    rob = pd.read_csv(OUT_DIR / "robustness.csv").set_index("id")
    meta = json.loads((OUT_DIR / "robustness_meta.json").read_text())
    lab = Lab()
    mx = {}
    for _, r in fin.iterrows():
        spec = {"family": r.family, "params": json.loads(r.params)}
        W, reb = lab.weights(spec)
        rows = np.flatnonzero(reb)
        w = np.abs(np.nan_to_num(W[rows]))
        w = w[w.sum(axis=1) > 0]
        mx[r["id"]] = float(np.median(w.max(axis=1))) if len(w) else 0.0
    fin["max_single_w"] = fin["id"].map(mx)
    fin["desc"] = fin.apply(describe, axis=1)
    rt = round_table()
    acc = access_summary()
    pl = post_lock_check()

    L = []
    L.append("# Ứng viên chiến lược không stop-loss — kết quả THĂM DÒ 06/10/2026\n")
    L.append(
        "> **Nhãn: thăm dò, chưa nghiệm thu theo giao thức.** Các vòng sau được thiết kế sau khi xem kết quả validation "
        "của vòng trước (R2 sau R1, R5 sau R3–R4, R6 sau R5), nên validation 2024–2025 đã bị dùng thích nghi và "
        "**không phải dữ liệu độc lập**. Niêm phong SHA-256 chỉ chứng minh spec không bị sửa sau khi đóng băng, "
        "không ngăn rò rỉ thích nghi. Test 2026 được mở một lần sau khi khóa nhưng danh sách khóa được chọn bằng "
        "validation đã nhiễm. Một vòng tuân thủ cần chốt toàn bộ tìm kiếm và chọn lọc trên train trước khi mở "
        "validation, và dùng dữ liệu chưa từng thấy (forward từ shadow) làm kiểm định độc lập.\n"
    )
    L.append(
        "Giao thức: `docs/NOSTOP_RESEARCH_PROTOCOL_20261006.md`. Mã: `src/dao_vang/nostop/`. "
        "Dữ liệu và niêm phong: `artifacts/nostop/` (`rounds/*/frozen.json+sha256`, "
        "`candidate_lock.json+sha256`, `access_log.jsonl`).\n"
    )
    n = len(fin)
    ok = int(((fin.train_calmar > 1) & (fin.val_calmar > 1) & (fin.test_calmar > 1)).sum())
    L.append("## Kết luận\n")
    L.append(
        f"- Khóa **{n} ứng viên** (đóng băng trước mỗi lần chạy validation, khóa trước test; xem nhãn thăm dò ở trên). Test 2026 "
        f"(01/01–31/08, BTC giữ nguyên −10,6%): **{int((fin.test_calmar > 1).sum())}/{n} có CAGR/MaxDD > 1**, "
        f"**{ok}/{n} đạt > 1 ở cả ba giai đoạn**, {int((fin.test_total_return > 0).sum())}/{n} có lợi nhuận dương.\n"
        f"- Trễ khớp lệnh thêm 1 nến 4h: {int((rob.test_delay1_calmar > 1).sum())}/{n} còn > 1; "
        f"thêm 3 nến (12h): {int((rob.test_delay3_calmar > 1).sum())}/{n}. Chi phí gấp đôi: "
        f"{int((fin.test_stress_calmar > 1).sum())}/{n} còn > 1 trên test.\n"
        "- Không ứng viên nào bị thanh lý ở bất kỳ giai đoạn nào. Không dùng stop-loss, trailing hay giảm vị thế theo PnL.\n"
        f"- Tương quan lợi suất ngày giữa các ứng viên trên test: trung vị {meta['test_corr_median']:.2f}. "
        "Thực chất là **một họ chiến lược** (long/short cân bằng tiền, dollar-neutral tại kỳ tái cân bằng và KHÔNG trung hòa beta; xếp hạng bằng taker-flow + funding + động lượng), "
        "không phải 31 alpha độc lập.\n"
    )
    if pl:
        L.append("## Kiểm tra mở rộng ngoài mẫu (Out-of-Window Backfill): 01/09 → 06/10\n")
        L.append(
            f"Mô phỏng lại đúng {pl['n']} spec đã khóa trên nến Binance sau khi kết thúc tập test (31/08). "
            f"Đây là dữ liệu lịch sử ({pl['days']:.0f} ngày đến {pl['asof']}, BTC {pl['btc']:+.1%}) đã có sẵn lúc khóa nhưng nằm ngoài cửa sổ nghiên cứu. Vị thế bắt đầu từ trống ngày 01/09, "
            "chi phí và funding như backtest.\n\n"
            f"- **Chỉ {pl['pos']}/{pl['n']} có lợi nhuận dương**, trung vị **{pl['median_ret']:+.1%}**, "
            f"MaxDD trung vị {pl['median_dd']:.1%}, xấu nhất {pl['worst_ret']:+.1%}, tốt nhất {pl['best_ret']:+.1%}.\n"
            "- Đây là mẫu rất ngắn (5 tuần, một giai đoạn thị trường) nên không đủ để bác bỏ hay xác nhận, "
            "nhưng nó cho thấy Calmar test > 1 chưa phải bằng chứng lợi thế bền vững. Shadow đang chạy tiếp từ thời điểm này.\n"
        )
    L.append("## Các vòng cải tiến (chỉ số: trung bình Calmar validation của top 20 đã đóng băng trong vòng)\n")
    L.append("| Vòng | Cấu hình train đã thử | Đóng băng | Val>1 | Val tốt nhất | Top20 trung bình | So với vòng tốt nhất trước |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for _, r in rt.iterrows():
        g = "" if pd.isna(r.gain_vs_prev_best_round) else f"{r.gain_vs_prev_best_round:+.0%}"
        L.append(
            f"| {r['round']} | {int(r.train_configs)} | {int(r.frozen)} | {int(r['val>1'])} | "
            f"{r.best_val:.2f} | {r.top20_mean_val:.2f} | {g} |"
        )
    L.append(
        "\nR1 (động lượng giá, funding, taker riêng lẻ, trend BTC): 0/22 vượt 1 ở validation. R2 chuyển sang tổ hợp "
        "taker-flow + funding + động lượng (sau khi thấy kết quả R1). R3 thêm hysteresis và so sánh beta-neutral/ivol "
        "(bằng chứng train: hysteresis 0,1 và K=40 tốt hơn, beta-neutral và ivol kém). R4 tinh chỉnh quanh R3. "
        "R5 thử thêm nhân tố (thanh khoản, lottery, volume surge), long-only theo chế độ BTC, và định thời BTC/ETH theo taker-flow. "
        "R6 trung hòa theo 3 bậc thanh khoản. Dừng sau R6: R4 (−9%) và R6 (−27%) không vượt vòng tốt nhất trước (R5) quá 5%.\n"
    )
    L.append("## Bảng xếp hạng (theo Calmar validation giảm dần; cột test là ngoài mẫu thật sự)\n")
    L.append(
        "| # | ID | Cấu hình | Calmar train | Calmar val | CAGR/MaxDD val | Calmar test | CAGR test (8 th., quy năm) | MaxDD test | "
        "Lợi nhuận test | Calmar test ×2 chi phí | Trọng số lớn nhất/vị thế |"
    )
    L.append("|---:|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|")
    for i, r in enumerate(fin.itertuples(), 1):
        L.append(
            f"| {i} | `{r.id}` | {r.desc} | {r.train_calmar:.2f} | {r.val_calmar:.2f} | "
            f"{r.val_cagr:.0%}/{r.val_maxdd:.0%} | {r.test_calmar:.2f} | {r.test_cagr:.0%} | {r.test_maxdd:.1%} | "
            f"{r.test_total_return:+.0%} | {r.test_stress_calmar:.2f} | {r.max_single_w:.0%} |"
        )
    t2 = fin.sort_values("test_calmar", ascending=False)
    L.append("\n### Xếp theo Calmar test (chỉ để tham khảo, không dùng để chọn lại)\n")
    L.append("`" + "`, `".join(t2.id.head(10)) + "` là 10 ứng viên có Calmar test cao nhất; "
             "3 ứng viên Calmar test ≤ 1: " + ", ".join(
                 f"`{r.id}` ({r.test_calmar:.2f})" for r in fin[fin.test_calmar <= 1].itertuples()) + ".\n")
    L.append("## Giới hạn và rủi ro cần đọc trước khi tin các con số\n")
    L.append(
        "1. **Chọn lọc nhiều lần**: 354 cấu hình đóng băng, hàng nghìn cấu hình train. Validation đã được dùng để chọn nên Calmar validation bị thổi phồng. "
        "Chỉ test 2026 là ngoài mẫu, và nó chỉ dài 8 tháng (một chế độ thị trường: BTC giảm). CAGR quy năm từ 8 tháng cực nhiễu, hãy đọc lợi nhuận tổng.\n"
        f"2. **Dò vết validation giữa các vòng**: ý tưởng vòng sau (R2, R5) được định hướng bởi kết quả validation vòng trước. Nhật ký truy cập: "
        f"{acc}.\n"
        "3. **Thiên lệch sống sót**: vũ trụ 116 coin còn tồn tại cuối 2025, không có coin đã hủy niêm yết. Ảnh hưởng chưa định lượng.\n"
        "4. **Nhân tố thanh khoản đảo dấu giữa train và validation** (illiq/big tốt nhất ở train, tệ nhất ở validation; liq/small ngược lại). "
        "Ứng viên phụ thuộc nhân tố này mong manh theo chế độ. R6 trung hòa thanh khoản (tier-neutral) nhằm loại rủi ro đó; nhóm này có Calmar validation thấp hơn, và chưa có bằng chứng độc lập rằng nó miễn nhiễm với đảo dấu.\n"
        "5. **Vòng quay rất lớn** (50–140 lần vốn/năm): kết quả nhạy với chi phí thật, trượt giá và độ sâu sổ lệnh của coin cỡ vừa/nhỏ. "
        "Chi phí mô hình 8–20 bps/chiều theo bậc thanh khoản; mô phỏng không có hàng chờ, khớp từng phần hay tác động giá.\n"
        "6. **Rủi ro đuôi không stop**: vị thế lớn nhất thường 7–13% vốn (20% ở vài ứng viên rebal 7 ngày, 33% ở `mkt_flow`). Một coin tăng 5–10× trong một nến trong khi giữ short sẽ gây lỗ khoảng 35–130% vốn tùy kích thước. "
        "Backtest 2020–2026 không thanh lý lần nào, nhưng 116 coin sống sót không bao gồm các trường hợp tệ nhất. Kiểm soát duy nhất là kích thước vị thế, bộ lọc thanh khoản và vol-target.\n"
        "7. Dữ liệu `taker_buy_volume` ở 2026 ghép từ nến 5m; 2020–2025 lấy từ bảng 4h có sẵn. Chưa đối chiếu sàn từng nến.\n"
    )
    L.append("## Ghi chú alpha để thử nghiệm\n")
    L.append(
        "- **Taker-flow + funding (carry) xếp hạng chéo, long/short cân bằng tiền (không trung hòa beta)**: họ cho kết quả tốt nhất trong tìm kiếm, nhưng nguồn lợi nhuận chưa được kiểm chứng nhân quả. Ổn định qua trễ 4h và 12h. Chưa kiểm tra riêng đóng góp của từng nhân tố sau R5.\n"
        "- **Động lượng giá thuần** (xs_mom, ts_mom_basket, trend BTC): Calmar train 1,4–4 nhưng validation < 1 (0/22 ở R1): suy giảm 2024–2025. Chỉ có ích khi kết hợp flow.\n"
        "- **Funding một mình** (short funding cao): train ổn, validation 0,5–0,8. Là một thành phần của tổ hợp chứ không đủ độc lập.\n"
        "- **Định thời BTC/ETH theo taker-flow tổng hợp** (`mkt_flow`): 1 cấu hình vượt validation (1,17) nhưng test −0,38. Chưa đạt.\n"
        "- **Không đạt**: đảo chiều ngắn hạn, low-vol, lottery, vol-shock đơn lẻ, BTC-ratio mean reversion, size đơn lẻ, pump-fade short (có TP, không stop), dump-bounce, alt-short/BTC-long. "
        "Pump-fade/dump-bounce train Calmar ≤ 0,9 (không đủ cho gate).\n"
        "- Hướng chưa thử: OI/long-short ratio (dữ liệu chỉ từ 2024 nên không train được), dữ liệu TradFi, tín hiệu sổ lệnh/L2, chọn vũ trụ theo thời điểm gồm coin bị hủy niêm yết.\n"
    )
    DOC.write_text("\n".join(L), encoding="utf-8")
    print("wrote", DOC, "|", Path(DOC).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
