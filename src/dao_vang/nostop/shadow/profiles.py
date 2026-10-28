"""Per-shadow description: mechanism in plain language, parameters, backtest evidence.

Built once from the research artifacts (``final_results.csv``, ``robustness.csv``, rounds) and
the research engine, then stored in ``data/nostop_shadow/profiles.json`` for the dashboard.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from ..data import OUT_DIR
from ..lab import Lab
from ..registry import ROUNDS_DIR, load_lock
from .store import describe_spec

FACTOR_DOC = {
    "mom": "Động lượng giá {d}: lợi suất đóng cửa {d}. Coin tăng mạnh được ưu tiên LONG, coin yếu bị SHORT.",
    "resid": "Động lượng phần dư {d}: lợi suất {d} sau khi trừ phần chạy theo BTC (beta 60 ngày). Đo sức mạnh riêng của coin.",
    "taker": "Dòng lệnh chủ động {d}: tỷ lệ taker-mua / tổng khối lượng trung bình {d}. Áp lực mua chủ động cao → LONG, áp lực bán → SHORT.",
    "tchg": "Thay đổi dòng lệnh {d}: tỷ lệ taker-mua {d} trừ nền 30 ngày. Dòng tiền đang cải thiện → LONG.",
    "fund": "Funding (carry) {d}: trừ funding trung bình {d}. Funding cao (phe long đang trả phí) → SHORT, funding thấp/âm → LONG và ăn carry.",
    "fz": "Funding bất thường {d}: z-score funding {d} so với nền 30 ngày, đảo dấu. Funding tăng đột biến → SHORT.",
    "lot": "Hiệu ứng xổ số {d}: trừ mức tăng 1 ngày lớn nhất trong {d}. Coin vừa có phiên pump mạnh bị SHORT.",
    "vsurge": "Bùng nổ khối lượng: khối lượng 3 ngày / trung bình {d}. Khối lượng tăng vọt → ưu tiên LONG.",
    "vcalm": "Khối lượng lắng: trừ đi tỷ số (khối lượng 3 ngày / trung bình {d}). Khối lượng yên → ưu tiên LONG.",
    "liq": "Thanh khoản tốt {d}: trừ chỉ số Amihud {d}. Coin thanh khoản cao → LONG, kém thanh khoản → SHORT (có tilt thanh khoản).",
    "illiq": "Kém thanh khoản {d}: chỉ số Amihud {d}. Coin kém thanh khoản → LONG (tilt thanh khoản ngược).",
    "small": "Tilt coin nhỏ (tên nhầm lẫn trong mã): thực tế ưu tiên LONG coin có xếp hạng thanh khoản CAO (coin lớn), SHORT coin thanh khoản thấp.",
    "big": "Tilt coin lớn (tên nhầm lẫn trong mã): thực tế ưu tiên LONG coin có xếp hạng thanh khoản THẤP (coin nhỏ).",
    "lvol": "Biến động thấp {d}: trừ độ biến động {d}. Coin ít biến động → LONG, coin biến động mạnh → SHORT.",
    "rev": "Đảo chiều {d}: trừ lợi suất {d}. Coin vừa giảm → LONG.",
}

PARAM_DOC = {
    "factors": "Các nhân tố được xếp hạng phần trăm trong vũ trụ rồi lấy trung bình (điểm tổng hợp).",
    "K": "Vũ trụ: top K coin theo khối lượng USDT trung bình 30 ngày, có ít nhất 90 ngày lịch sử.",
    "q": "Tỷ lệ mỗi chân: LONG nhóm q cao điểm nhất, SHORT nhóm q thấp điểm nhất.",
    "rebal": "Chu kỳ đánh giá lại (ngày). Quyết định tại đóng nến 20:00 UTC (00:00), khớp tại giá mở nến kế.",
    "buffer": "Hysteresis: vị thế cũ được giữ chừng nào còn nằm trong nhóm q+buffer, giảm vòng quay và phí.",
    "smooth_days": "Làm mượt điểm tổng hợp bằng trung bình trượt (ngày) để giảm nhiễu.",
    "tier_neutral": "Chia vũ trụ thành 3 bậc thanh khoản; LONG/SHORT trong từng bậc nên không lệch về coin lớn hay nhỏ.",
    "mode": "ls = long/short cân bằng tiền (tổng danh nghĩa LONG ≈ SHORT tại kỳ tái cân bằng), KHÔNG cân bằng beta.",
    "tv": "Mục tiêu biến động danh mục (năm hóa). Quy mô vị thế = mục tiêu / biến động back-cast 60 ngày của chính danh mục giả định; đòn bẩy tối đa 2×.",
    "wt": "Trọng số trong chân: eq = đều; ivol = nghịch biến động.",
    "L": "Cửa sổ nhân tố (ngày).",
    "zwin": "Cửa sổ z-score (ngày).",
    "thr": "Ngưỡng z-score để vào lệnh.",
    "asset": "Tài sản giao dịch.",
}


def _split_tok(tok: str) -> tuple[str, str]:
    name = tok.rstrip("0123456789.")
    d = tok[len(name):]
    return name, (f"{d} ngày" if d and name not in ("small", "big") else "")


def explain_factor(tok: str) -> str:
    name, d = _split_tok(tok)
    return FACTOR_DOC.get(name, tok).format(d=d)


def mechanism(spec: dict) -> list[str]:
    p = spec["params"]
    if spec["family"] == "mkt_flow":
        return [
            "Định thời BTC/ETH theo dòng lệnh taker tổng hợp của toàn bộ vũ trụ thanh khoản.",
            f"Tính z-score (cửa sổ {p['zwin']} ngày) của tỷ lệ taker-mua trung bình {p['L']} ngày; "
            f"khi z > {p['thr']} thì giữ {p['asset']} (LONG), ngược lại đứng ngoài.",
            "Không stop-loss: chỉ vào/ra theo tín hiệu dòng lệnh, quy mô theo mục tiêu biến động.",
        ]
    toks = p["factors"].split("+")
    out = [
        f"Mỗi {p['rebal']} ngày, lúc đóng nến 00:00 UTC, xếp hạng top {p['K']} coin thanh khoản bằng điểm tổng hợp của {len(toks)} nhân tố "
        f"(hạng phần trăm trung bình). LONG {int(p['q'] * 100)}% điểm cao nhất, SHORT {int(p['q'] * 100)}% thấp nhất; "
        + ("mỗi chân chiếm nửa tổng vị thế; trong chân, trọng số TỈ LỆ NGHỊCH với biến động 30 ngày (coin ít biến động nhận tỷ trọng lớn hơn nhiều, "
         "nên vị thế có thể tập trung vào vài coin; đã thấy một vị thế đơn ≈ 44% vốn)." if p.get("wt") == "ivol"
         else "mỗi chân chiếm nửa tổng vị thế, chia đều giữa các coin."),
        "Nhân tố:",
    ]
    out += [f"  • {t}: {explain_factor(t)}" for t in toks]
    if p.get("tier_neutral"):
        out.append("Trung hòa thanh khoản: vũ trụ chia 3 bậc, LONG/SHORT trong từng bậc.")
    if p.get("buffer"):
        out.append(f"Hysteresis {p['buffer']}: giữ vị thế cũ chừng nào còn trong nhóm q+{p['buffer']}.")
    if p.get("smooth_days"):
        out.append(f"Điểm được làm mượt {p['smooth_days']} ngày.")
    out.append(
        f"Quy mô: mục tiêu biến động {int(p['tv'] * 100)}%/năm, đòn bẩy tối đa 2×, tổng danh nghĩa ≤ 3× vốn. "
        "Khớp tại giá mở nến kế sau quyết định; phí 5 bps + trượt giá 3/8/15 bps theo bậc thanh khoản; funding thực 00/08/16 UTC."
    )
    out.append("KHÔNG có stop-loss, trailing hay giảm vị thế theo lỗ; vị thế chỉ đổi khi tới kỳ đánh giá lại.")
    return out


def params_table(spec: dict) -> list[dict]:
    rows = []
    for k, v in spec["params"].items():
        rows.append({"name": k, "value": v if not isinstance(v, bool) else ("có" if v else "không"),
                     "meaning": PARAM_DOC.get(k, "")})
    return rows


def _split_block(m: dict) -> dict:
    keys = ("cagr", "maxdd", "calmar", "maxdd_intra", "calmar_intra", "total_return", "sharpe",
            "gross_avg", "turnover_per_year", "pos_years", "month_win", "years")
    out = {k: m[k] for k in keys if k in m}
    out["yearly"] = {str(y): v for y, v in m["yearly"].items()}
    return out


def alpha_rationale(spec: dict) -> list[str]:
    """Economic hypotheses for why the ranking might earn money, each with its risk.
    None of these has been tested causally (no factor ablation yet)."""
    p = spec["params"]
    out = ["Các điểm dưới đây là GIẢ THUYẾT kinh tế chưa kiểm chứng nhân quả (chưa chạy ablation từng nhân tố). Không có gì bảo đảm lợi nhuận."]
    if spec["family"] == "mkt_flow":
        out.append("Giả thuyết: dòng lệnh taker tổng hợp của thị trường altcoin dẫn trước giá BTC/ETH. Rủi ro: tín hiệu ồn, kết quả test của cấu hình này âm; khi đứng ngoài thì không sinh lời.")
        return out

    facs = p.get("factors", "")
    if "taker" in facs or "tchg" in facs:
        out.append("Taker-flow: giả thuyết là áp lực mua/bán chủ động còn kéo dài vài ngày vì thông tin và dòng tiền lan chậm ở altcoin. Rủi ro: cũng có thể chỉ là dấu vết của phiên pump/dump sắp đảo chiều, và tín hiệu có thể mất khi nhiều người cùng khai thác.")
    if "fund" in facs or "fz" in facs:
        out.append("Funding: giả thuyết là funding cao phản ánh vị thế long đông, nên short nhóm đó có thể nhận phí funding và hưởng lợi khi vị thế bị xả. Rủi ro: funding cao thường đi cùng xu hướng tăng mạnh, nên chân short có thể lỗ lớn (squeeze), và khoản funding nhận được nhỏ so với biến động giá.")
    if "mom" in facs:
        out.append("Động lượng giá: giả thuyết là hành vi bầy đàn làm coin đang tăng tiếp tục tăng ngắn hạn. Rủi ro: ở các vòng đầu, động lượng giá đứng riêng không vượt qua validation (suy giảm 2024–2025).")
    if "resid" in facs:
        out.append("Động lượng phần dư: giả thuyết là phần lợi suất không giải thích bởi BTC (ước lượng beta 60 ngày) chứa thông tin riêng của coin. Rủi ro: beta ước lượng nhiễu, phần dư vẫn có thể phản ánh nhiễu.")
    if "vsurge" in facs or "lot" in facs:
        out.append("Cú sốc khối lượng / lottery: giả thuyết là khối lượng bùng nổ hoặc phiên pump 1 ngày dự báo hành vi sau đó. Rủi ro: nhân tố phụ, chưa rõ đóng góp độc lập.")
    if "liq" in facs or "small" in facs or "big" in facs or "illiq" in facs:
        out.append("Nhân tố thanh khoản/quy mô: có tilt về coin lớn hoặc nhỏ. Rủi ro: nhân tố này đảo dấu giữa train và validation, nên dễ phụ thuộc chế độ thị trường.")

    if p.get("tier_neutral"):
        out.append("Trung hòa theo bậc thanh khoản: LONG/SHORT trong từng bậc nên không lệch về coin lớn hay nhỏ, nhưng vẫn có thể lỗ nếu cả thị trường altcoin chuyển động cùng chiều.")

    if p.get("mode", "") == "ls":
        out.append("Cấu trúc: cân bằng tiền (dollar-neutral) tại kỳ tái cân bằng, tức tổng danh nghĩa LONG ≈ tổng SHORT. Đây KHÔNG phải trung hòa beta: phía LONG và SHORT có beta với BTC khác nhau, vị thế lệch dần giữa hai kỳ tái cân bằng, nên vẫn có thể lỗ khi thị trường biến động mạnh hoặc altcoin tăng/giảm đồng loạt. Không có stop-loss nên chân SHORT của một coin tăng đột biến gây lỗ trực tiếp.")
    return out



def build_profiles(post_lock_start: str = "2026-09-01 00:00") -> dict:
    lab = Lab()
    fin = pd.read_csv(OUT_DIR / "final_results.csv").set_index("id")
    rob = pd.read_csv(OUT_DIR / "robustness.csv").set_index("id")
    order = json.loads((OUT_DIR / "locked_order.json").read_text())
    origin = {}
    for d in sorted(ROUNDS_DIR.iterdir()):
        vp = d / "val_results.parquet"
        if vp.exists():
            for sid in pd.read_parquet(vp)["id"]:
                origin.setdefault(sid, d.name)

    live = None
    try:
        from .binance import PublicClient
        from .book import shadow_state, shared_context
        from .feed import SharedFeed
        from .store import DATA_DIR

        feed = SharedFeed(DATA_DIR, PublicClient())
        if feed.path.exists():
            feed.load()
            panel, _ = feed.panel()
            ctx, cost = shared_context(panel)
            start_ms = int(pd.Timestamp(post_lock_start, tz="UTC").timestamp() * 1000)
            live = (panel, ctx, cost, int(np.searchsorted(feed.index, start_ms)), shadow_state)
    except Exception:  # noqa: BLE001 - optional enrichment
        live = None

    btc_close = pd.Series(lab.panel.close[:, lab.ctx.btc], index=lab.panel.index).resample("1D").last()
    btc_daily = btc_close.pct_change()

    out = {}
    for s in load_lock()["specs"]:
        sid = s["id"]
        spec = {"family": s["family"], "params": s["params"]}
        blocks, curves, last = {}, [], 1.0
        bounds = {}
        for split in ("train", "val", "test"):
            m, res = lab.run(spec, split)
            blocks[split] = _split_block(m)
            eq = res.equity * last
            idx = res.index.as_unit("ms").asi8.astype(np.int64)
            step = 30
            curves += [[int(idx[i]), float(eq[i])] for i in range(0, len(eq), step)]
            last = float(eq[-1])
            bounds[split] = int(idx[0])
        
        # Tính metrics từng năm chi tiết trên đường lợi suất nối liền
        dr = pd.concat([lab.daily(spec, "train"), lab.daily(spec, "val"), lab.daily(spec, "test")])
        yearly_metrics = []
        for year, grp in dr.groupby(dr.index.year):
            eq_y = (1 + grp).cumprod()
            ret_y = float(eq_y.iloc[-1] - 1.0) if len(eq_y) > 0 else 0.0
            dd_y = float((1 - eq_y / eq_y.cummax()).max()) if len(eq_y) > 0 else 0.0
            calmar_y = float(ret_y / dd_y) if dd_y > 1e-9 else 0.0
            yearly_metrics.append({"year": year, "ret": ret_y, "maxdd": dd_y, "calmar": calmar_y})

        # empirical exposure to BTC in the backtest (daily returns): shows what "dollar-neutral" really gave
        btc_beta = {}
        for split in ("train", "val", "test"):
            d = lab.daily(spec, split)
            b = btc_daily.reindex(d.index)
            ok = b.notna() & d.notna()
            var = float(b[ok].var())
            btc_beta[split] = {
                "beta": float(np.cov(d[ok], b[ok])[0, 1] / var) if var > 0 else 0.0,
                "corr": float(np.corrcoef(d[ok], b[ok])[0, 1]) if ok.sum() > 5 else 0.0,
            }

        curves.append([int(idx[-1]), last])
        W, reb = lab.weights(spec)
        w = np.abs(np.nan_to_num(W[np.flatnonzero(reb)]))
        w = w[w.sum(axis=1) > 0]
        prof = {
            "id": sid,
            "family": s["family"],
            "title": describe_spec(spec),
            "origin_round": origin.get(sid, "?"),
            "lock_rank": order.index(sid) + 1 if sid in order else None,
            "mechanism": mechanism(spec),
            "rationale": alpha_rationale(spec),
            "params": params_table(spec),
            "yearly_stats": yearly_metrics,
            "btc_beta": btc_beta,
            "backtest": blocks,
            "stress": {"val_calmar": float(fin.loc[sid, "val_stress_calmar"]),
                       "test_calmar": float(fin.loc[sid, "test_stress_calmar"]),
                       "test_total_return_2x_cost": float(fin.loc[sid, "test_stress_total_return"])},
            "robustness": {"test_delay1_calmar": float(rob.loc[sid, "test_delay1_calmar"]),
                           "test_delay3_calmar": float(rob.loc[sid, "test_delay3_calmar"]),
                           "val_delay1_calmar": float(rob.loc[sid, "val_delay1_calmar"]),
                           "val_delay3_calmar": float(rob.loc[sid, "val_delay3_calmar"])},
            "max_single_weight_median": float(np.median(w.max(axis=1))) if len(w) else 0.0,
            "curve": curves,
            "split_starts": bounds,
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "status_note": "Kết quả thăm dò: validation đã bị dùng thích nghi (xem docs/NOSTOP_RESEARCH_PROTOCOL).",
        }
        if live is not None:
            panel, ctx, cost, i0, shadow_state = live
            st = shadow_state(panel, ctx, cost, spec, i0, 10000.0)
            prof["post_lock"] = {"start": post_lock_start, "return": st["return"], "max_dd": st["max_dd"],
                                 "days": st["days"]}
        out[sid] = prof
    return out
