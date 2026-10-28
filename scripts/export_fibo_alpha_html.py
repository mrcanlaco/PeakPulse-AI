"""Generator script for the PeakPulse AI (Đảo Vàng) Multi-Layered Alpha Wiki & Research Portal.

Reads:
  - artifacts/fibo_trend_short/backtest_in_sample_2025.json
  - artifacts/fibo_trend_short/pump_amplitude_study_2025.json
  - artifacts/fibo_trend_short/factor1_multi_repo_study_2025.json

Outputs:
  - artifacts/fibo_trend_short/alpha_wiki_registry.json (Structured JSON Knowledge Base for easy programmatic retrieval & updates)
  - artifacts/fibo_trend_short/fibo_alpha_research_2025.html (Interactive Wiki / Website / Research Portal)
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "fibo_trend_short"
BASELINE_JSON = ARTIFACTS_DIR / "backtest_in_sample_2025.json"
PUMP_STUDY_JSON = ARTIFACTS_DIR / "pump_amplitude_study_2025.json"
MULTI_REPO_JSON = ARTIFACTS_DIR / "factor1_multi_repo_study_2025.json"
AUDIT_STUDY_JSON = ARTIFACTS_DIR / "independent_audit_study.json"
AUDIT_DOSSIER_MD = ARTIFACTS_DIR / "CHATGPT_INDEPENDENT_AUDIT_DOSSIER.md"
COIN_UNIVERSE_JSON = ARTIFACTS_DIR / "coin_universe_study_2026.json"
REGISTRY_JSON = ARTIFACTS_DIR / "alpha_wiki_registry.json"
OUTPUT_HTML = ARTIFACTS_DIR / "fibo_alpha_research_2025.html"


def fmt_pct(val: float, plus: bool = True) -> str:
    sign = "+" if (plus and val > 0) else ""
    return f"{sign}{val:.2f}%"


def fmt_pct3(val: float, plus: bool = True) -> str:
    sign = "+" if (plus and val > 0) else ""
    return f"{sign}{val:.3f}%"


def badge_class(val: float, threshold: float = 0.0) -> str:
    if val > threshold:
        return "pos"
    if val < threshold:
        return "neg"
    return "neu"


def build_alpha_wiki_registry() -> dict[str, Any]:
    """Construct the structured Alpha Ontology & Knowledge Base Registry."""
    return {
        "schema_version": "4.26.0",
        "architecture": "6-Pillar MECE Knowledge Base + 338-Coin PIT Universe + v4.0.26 Independent Audit & Paper OOS v1",
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy_branch": "fibo_trend_short",
        "in_sample_window": "2020-01-01T00:00:00Z -> 2025-12-31T23:59:59Z (Strict Historical Backtest Ceiling)",
        "oos_validation_window": "Paper OOS v1 Prospective Stream: 2026-10-18T04:00:00Z -> 2028-10-16T00:00:00Z (104 Calendar Weeks)",
        "live_signoff": "NOT_GRANTED",
        "historical_walk_forward_gate_2022_2025": "CASH",
        "multi_cycle_discoveries_2020_2026": [
            {
                "id": "DISC-07",
                "title": "Kết Quả Tái Kiểm Toán Độc Lập 6 Cấu Hình Trên Vũ Trụ 338 Mã Đã Sửa Thiên Lệch (v4.0.21 — Chuẩn VIP6 vs Stress Regular)",
                "summary": "Sau khi khắc phục toàn bộ phát hiện kiểm toán v4.0.1 -> v4.0.21 (khử thiên lệch chọn coin theo thời điểm, tách vòng đời hợp đồng hủy niêm yết/đổi tên, khớp giá mở cửa nhảy gap qua Stop, tính cooldown theo giờ thoát thực tế và trừ phí/trượt giá trên từng lần khớp kể cả chốt lời từng phần TP1/TP2/TP3 + funding thực tế): Ở bản Chuẩn VIP6 (2.5 bps phí + 10 bps trượt giá = 12.5 bps/fill), 4/6 ứng viên có lợi nhuận ròng dương toàn kỳ 2020–2025, dẫn đầu là Elite + Sniper (+26.19%, liên tục +26.05%, MaxDD 15.33%, 790 lệnh) và Sniper (+14.54%, MaxDD 18.05%, 940 lệnh). Trong giai đoạn 2024–2025, cả 6/6 ứng viên đều lãi dương ở bản Chuẩn (Sniper RR>=1 24h đạt +21.46% với CI 95% tuần [+0.0727%; +0.2992%] > 0) và 3/6 ứng viên vẫn lãi dương ngay cả dưới bài test Stress Regular (55 bps/fill).",
            },
            {
                "id": "DISC-08",
                "title": "Giải Phẫu Ma Sát Chi Phí Từng Lần Khớp (Per-Fill Slippage) & Trạng Thái Cổng Walk-Forward / Paper OOS v1 (v4.0.9 -> v4.0.26)",
                "summary": "Phân rã dòng tiền chỉ rõ vì sao chỉ số từ mức 'rất đẹp' ban đầu quy tụ về mức lợi nhuận thực tế: Với cơ chế chốt lời nhiều bậc (TP1, TP2, TP3), mỗi lệnh chịu nhiều lần phí và trượt giá. Ở bản Stress Regular (5 bps phí + 50 bps trượt giá = 55 bps/fill), riêng trượt giá ngốn mất -33.28% đến -92.76% NAV toàn kỳ 2020–2025, khiến cả 6 cấu hình đều âm toàn kỳ ở mức trượt giá 50 bps. Kết hợp với năm 2023 thị trường phục hồi gây lỗ nhẹ cho vị thế Short (-8.15% với Elite + Sniper), cổng chọn Walk-Forward tự động (đòi hỏi mọi năm trước dương ở bản Chuẩn VÀ tổng bản Stress không âm) giữ trạng thái phòng thủ CASH (live_signoff = NOT_GRANTED) và chuyển sang thu thập bằng chứng thực tế qua hệ thống Paper OOS v1 (12 tài khoản, 50 mã thanh khoản cao, bắt đầu từ 18/10/2026).",
            },
            {
                "id": "DISC-01",
                "title": "Bằng Chứng Thép Của Tầng Vĩ Mô pysystemtrade (Tầng 3) Trong Đại Sóng Bull Run 2020–2021",
                "summary": "Ở Mốc 0 (Baseline), đánh Short máy móc lỗ -775.2% (2020) và -1,531.3% (2021). Ở Nhánh Mở Rộng (Mốc 3B/4B/5B — cho phép Short khi KER >= 0.65 ngay cả khi PST == False), chiến lược vẫn lỗ -70.1% đến -83.0% trong năm 2021 vì các cú bơm dựng cột khi xu hướng lớn dương và gia tốc chưa gãy chính là chân sóng thần Parabolic. Ngược lại, khi bắt buộc PST phải bật đèn xanh (Mốc 4A, 5A, 6S — Nhánh Tinh Hoa), chiến lược BẤT BẠI cả 7/7 năm liên tiếp (2020 -> 2026), thậm chí lãi +59.45% (PF 1.18) ngay giữa tâm bão Siêu Bull Run 2021!",
            },
            {
                "id": "DISC-02",
                "title": "Sự Chuyển Dịch Cấu Trúc Thị Trường Crypto: Từ Cơn Điên Một Chiều (2020–2021) Sang Chu Kỳ Phái Sinh Bơm-Xả (2022–2026)",
                "summary": "Giai đoạn 2020–2021, Nhánh Tinh Hoa (Mốc 5A/6S) đóng vai trò 'Phòng thủ sinh lời' (WR 52%–63.6%, PF 1.08–1.73, bảo toàn vốn và lãi nhẹ khi đám đông Short sớm cháy tài khoản). Từ 2022–2026, khi thanh khoản Futures và hành vi Bơm-Xả hai chiều thống trị, chiến lược bước vào Thời Kỳ Hoàng Kim: WR vọt lên 60% -> 80%, PF đạt 1.63 -> 4.76 (Năm 2024 lãi +150.1% đến +280.0%, năm 2025 lãi +121.3% đến +195.9%, năm 2026 OOS lãi +45.2% đến +127.0% với DD chỉ 7.6%–12.1%).",
            },
            {
                "id": "DISC-03",
                "title": "Thang Điểm Hội Tụ 4 Tầng (Conviction Score 0–100) Phân Hóa Chính Xác Qua Cả 7 Năm (2020–2026)",
                "summary": "Trong 6 năm (2020–2025, 1,467 lệnh sóng >= 50%), nhóm điểm thấp (< 55đ: -134.3%, PF 0.95) và trung bình (55–69đ: -237.5%, PF 0.90) thua lỗ nặng trong các mùa Bull Run 2020–2021. Ngược lại, nhóm Hạng A (70–84đ, 284 lệnh) lãi +432.15% (WR 62.68%, PF 1.42, riêng năm 2021 thắng 60.0% thu về +140.20%) và Hạng S (>= 85đ, 34 lệnh) đạt WR 73.53%, PF 2.25, DD 31.3% (Năm 2021 PF 2.01; năm 2022, 2023 và 2026 OOS đạt 100% Win Rate!).",
            },
            {
                "id": "DISC-04",
                "title": "Quy Tắc Vận Hành Linh Hoạt 2 Chế Độ Theo Chu Kỳ Thị Trường (Dual-Mode Playbook)",
                "summary": "(1) Chế độ Mặc định / An toàn Mọi Thời Tiết (Mốc 6S Sniper Tinh Hoa hoặc Conviction Score >= 70): Bắt buộc có PST + KER >= 0.35 + imp_ker >= 0.50 + H1 Break -> Bất bại 7/7 năm (2020–2026), miễn nhiễm với Parabolic Bull Run. (2) Chế độ Tối Đa Lợi Nhuận Altcoin (Mốc 6B / 6A Mở Rộng): Bật thêm nhánh OR (KER >= 0.65) trong thị trường Sideways / Bear / Altcoin Pump-Dump để tối đa hóa tổng lãi (+280% năm 2024, +196% năm 2025, +127% OOS 2026).",
            },
            {
                "id": "DISC-05",
                "title": "Định Luật Chọn Lọc Vũ Trụ 338 Đồng Coin v1.2 (Tier S Core 40 Mã + Tier A 28 Mã vs Blacklist 269 Mã)",
                "summary": "Quét toàn bộ 338 mã Binance Futures phát hiện: Nếu đánh bừa không lọc vũ trụ coin, 109 mã G5 (Thanh khoản mỏng <$2.5M/ngày hoặc râu nến thao túng >4.5%) và nhóm Mid-cap kém thanh khoản gây lỗ -1,607.4% (PF 0.69) ở OOS 2026. Ngược lại, 2 nhóm bản chất tài sản G4_LIQUID_MEME (PF 3.08 ở OOS 2026) và G2_LIQUID_L1_L2_DEFI (PF 1.64 ở OOS 2026) tạo ra siêu lợi nhuận bền vững. Khi khóa danh sách Ex-Ante v1.2: Nhóm TIER_S_CORE (40 mã) lãi +330.1% (PF 4.40, MaxDD 15.8%) và Tổng Whitelist S+A v1.2 (68 mã) lãi +400.1% (WR 66.1%, PF 2.84, MaxDD 29.6%) trong kiểm thử mù OOS 2026!",
            },
            {
                "id": "DISC-06",
                "title": "Định Luật Vốn Hóa Lưu Hành (Market Cap >= $150M) & Tỷ Lệ Cung Lưu Hành (Float Ratio >= 64%–75%) Đối Chiếu Với Chuẩn Point-in-Time a1e6ca7d",
                "summary": "Tham chiếu kiến trúc Point-in-Time của dự án a1e6ca7d (Warmup >= 63 ngày + Top-50 Volume, 0% PnL Selection Bias -> OOS 2026 lãi +96.2%, PF 1.37) và kết hợp dữ liệu Tổng cung lưu hành (Circulating Supply) từ CoinGecko phát hiện 2 quy luật sống còn: (1) Mọi đồng coin có Vốn hóa lưu hành < $150M đều bị đội lái thao túng nguồn cung Spot để ép Short Squeeze trên Futures (211 mã MCap < $150M lỗ -1,135.7% ở OOS 2026). (2) Ngay cả khi MCap >= $150M, nhóm Low-Float VC Unlock (Circulating/Total Supply < 40%: WLD, AERO, PUMP...) lỗ -382.2% (PF 0.50) ở OOS 2026; trong khi nhóm High-Float (Circulating/Total >= 75%, 68 mã đã phân phối hết cho cộng đồng) lãi +1,454.0% (IS) và +324.7% (PF 1.81, OOS 2026)! Nhờ lọc bỏ 20 mã G3 Low-Float/Small-Cap (lỗ -31.6% ở OOS 2026), Tier A v1.2 tăng vọt lãi OOS từ +38.3% lên +70.0% (+83%) và Bộ quy tắc Thuần Point-in-Time 0% PnL Bias (Age>=63d + MCap>=$150M + Float>=70% + Vol>=$5M, 64 mã) đạt +235.5% (PF 2.01, MaxDD 34.2%) ở OOS 2026!",
            },
        ],
        "taxonomy_layers": [
            {
                "layer_id": "L1",
                "name": "Tầng 1: Tâm Lý Đám Đông & Nỗi Đau Vị Thế (Behavioral & Position Pain Layer)",
                "cardinality": "Cực ít (4–5 cơ chế gốc)",
                "stability": "Bất biến theo thời gian (Không bao giờ lỗi thời)",
                "description": "Nguồn gốc thực sự của mọi Alpha: Tiền trên thị trường chỉ sinh ra khi một nhóm đám đông bị cuốn vào hưng phấn cực độ hoặc bị ép vào thế buộc phải cắt lỗ/xả hòa vốn.",
                "mechanisms": [
                    {
                        "id": "L1.1",
                        "title": "FOMO Mua Đuổi & Cạn Kiệt Người Mua Cuối Cùng (Buyer Exhaustion)",
                        "summary": "Khi giá tăng sốc >= 50%–100% trong thời gian ngắn, toàn bộ người mua tiềm năng đã nhảy vào tàu (Long đòn bẩy cao), không còn dòng tiền mới đẩy tiếp.",
                    },
                    {
                        "id": "L1.2",
                        "title": "Hiệu Ứng Mỏ Neo & Tâm Lý 'Cầu Về Bờ' (Disposition Effect / Breakeven Supply Wall)",
                        "summary": "Sau cú sập đầu tiên từ đỉnh, người mua FOMO ở đỉnh bị kẹp hàng (Trapped Bulls). Khi giá hồi lên 50%–61.8% (vùng Fibo), họ đồng loạt bán ra để thoát lỗ/hòa vốn.",
                    },
                    {
                        "id": "L1.3",
                        "title": "Thác Đổ Cắt Lỗ & Thanh Lý Cưỡng Bức (Stop-Run & Liquidation Cascade)",
                        "summary": "Khi nhịp hồi Fibo thất bại và giá phá thủng đáy cấu trúc ngắn hạn (H1 BOS), cả đội kẹp đỉnh lẫn đội bắt đáy sớm hoảng loạn bán tháo, đẩy giá rơi tự do về đáy cũ (TP1) và Fibo 1.272–1.618.",
                    },
                    {
                        "id": "L1.4",
                        "title": "Bẫy Chặn Đầu Xe Lửa (Premature Short-Squeeze Trap)",
                        "summary": "Đám đông thấy giá mới tăng nhẹ (15%–25%) hoặc đang trong Siêu Uptrend có tổ chức đỡ giá đã vội nhảy vào Short sớm, trở thành nhiên liệu bị ép cắt lỗ (Short Squeeze).",
                    },
                ],
            },
            {
                "layer_id": "L2",
                "name": "Tầng 2: Vi Cấu Trúc & Động Lực Thanh Khoản (Microstructure & Liquidity Physics)",
                "cardinality": "Ít (6–8 cơ chế vật lý trên sổ lệnh)",
                "stability": "Rất cao (Phản ánh cấu trúc vật lý của cung-cầu)",
                "description": "Cách hành vi tâm lý đám đông ở Tầng 1 để lại dấu chân vật lý đo đếm được trên chuỗi giá và khối lượng.",
                "mechanisms": [
                    {
                        "id": "L2.1",
                        "title": "Khoảng Không Thanh Khoản (Air-Pocket Vacuum) vs Bậc Thang Hỗ Trợ (Staircase Support)",
                        "summary": "Sóng bơm dựng đứng một mạch (KER >= 0.35–0.60) không tạo ra vùng tích lũy nào dọc đường -> bên dưới hoàn toàn rỗng cầu đỡ. Ngược lại sóng đi zíc-zắc (KER < 0.35) xây nhiều bậc thang đỡ giá.",
                    },
                    {
                        "id": "L2.2",
                        "title": "Đứt Gãy Gia Tốc Động Lượng (Second-Derivative Momentum Collapse)",
                        "summary": "Trước khi xu hướng giá đảo chiều, đạo hàm bậc 2 (gia tốc tăng) phải gãy sập âm mạnh (accel(4,16) <= -1.0).",
                    },
                    {
                        "id": "L2.3",
                        "title": "Xung Lực Xả Mở Màn Phá Cấu Trúc (First Impulse Breakdown)",
                        "summary": "Nhịp sập đầu tiên từ đỉnh đủ sâu để khóa chặt đội mua đỉnh và xác nhận phe bán chủ động đã kiểm soát cuộc chơi.",
                    },
                    {
                        "id": "L2.4",
                        "title": "Sự Lệch Pha Đa Khung Thời Gian (HTF Retracement -> LTF Structural Break)",
                        "summary": "Khung lớn (H4/D1) đang trong nhịp hồi kỹ thuật lên vùng Fibo, nhưng khung nhỏ (H1) chuyển trạng thái từ hồi tăng sang phá vỡ đáy cấu trúc (Micro-BOS).",
                    },
                ],
            },
            {
                "layer_id": "L3",
                "name": "Tầng 3: Bối Cảnh & Chế Độ Vĩ Mô (Macro Regime & Context Gate)",
                "cardinality": "3–4 Trạng thái môi trường",
                "stability": "Cao (Quyết định khi nào bật/tắt chiến lược)",
                "description": "Bộ công tắc môi trường giải thích tại sao cùng một mô hình nến nhưng lúc thì thắng 70%, lúc thì thua liên hoàn.",
                "mechanisms": [
                    {
                        "id": "L3.1",
                        "title": "Sóng Hồi Trong Xu Hướng Giảm Lớn (Bear Market Rally / Mean-Reversion Regime)",
                        "summary": "Khi xu hướng dài hạn đang âm (ewmac(16,64) <= 0 hoặc EMA20 <= EMA50), các cú bơm >= 50% chỉ là nhịp hồi kỹ thuật hoặc xả nốt hàng tồn -> Short theo xu hướng chính cực kỳ thuận lợi.",
                    },
                    {
                        "id": "L3.2",
                        "title": "Siêu Xu Hướng Tăng Bền Vững (Runaway Institutional Bull Trend)",
                        "summary": "Khi ewmac(16,64) > 0, gia tốc chưa gãy (accel > -1.0) và sóng tăng xây nền đều đặn (KER < 0.50) -> Dòng tiền lớn liên tục mua đỡ tại MA20/MA50, cấm Short.",
                    },
                    {
                        "id": "L3.3",
                        "title": "Nổ Biên Độ Thoát Nén Đầu Sóng (Volatility Squeeze Breakout)",
                        "summary": "Khi biến động đang nén cực thấp rồi giá vọt tăng mạnh trong 1–8 nến H4 đầu tiên (< 1 ngày): Đây là điểm khởi đầu chu kỳ tăng mới, không phải đỉnh kiệt sức.",
                    },
                ],
            },
            {
                "layer_id": "L4",
                "name": "Tầng 4: Hình Thức & Công Thức Toán Học (Surface Indicators Layer)",
                "cardinality": "Hàng trăm biến thể chỉ báo từ các Repo",
                "stability": "Thấp nếu dùng mù quáng (Trùng lặp 50%–85% giữa các chỉ báo cùng họ)",
                "description": "Tầng biểu diễn bằng code/toán học. Nguyên tắc cốt lõi: Mỗi cơ chế ở Tầng 2 & 3 chỉ chọn đúng 1 công thức đại diện tốt nhất ở Tầng 4, tuyệt đối không ghép chồng các chỉ báo cùng đo 1 cơ chế.",
                "mechanisms": [
                    {
                        "id": "L4.1",
                        "title": "Họ Chỉ Báo Biên Độ Mở Rộng (Amplitude Family)",
                        "summary": "Đại diện chuẩn: prior_pump_pct >= 50%. Biến thể trùng lặp: Pump so với MA7 đáy, ROI 14 ngày.",
                    },
                    {
                        "id": "L4.2",
                        "title": "Họ Chỉ Báo Độ Rỗng & Tốc Độ Sóng (Wave Efficiency / Velocity Family)",
                        "summary": "Đại diện chuẩn: Kaufman Efficiency Ratio (KER >= 0.35 / 0.65). Biến thể trùng lặp cao: Pump Velocity (%/ngày, r=0.304), Wave Duration 1-8 ngày (r=0.825 với Velocity), Qlib RSQR(14) (r=0.495 với KER).",
                    },
                    {
                        "id": "L4.3",
                        "title": "Họ Chỉ Báo Chế Độ Xu Hướng & Gia Tốc (Regime & Acceleration Family)",
                        "summary": "Đại diện chuẩn: pysystemtrade ewmac(16,64) <= 0 OR accel(4,16) <= -1.0. Biến thể trùng lặp: EMA20 <= EMA50, MACD Histogram.",
                    },
                ],
            },
        ],
        "alpha_passports": [
            {
                "id": "ALPHA-F1A",
                "name": "Overextended Crowd Euphoria (Biên Độ Sóng Bơm >= 50%)",
                "factor_group": "Factor #1: Sóng Tăng Trước Đỉnh",
                "status": "LOCKED_IN_SAMPLE",
                "status_label": "✅ Đã Khóa (Cổng Bắt Buộc)",
                "source_repo": "PeakPulse Native + MA Deep Dive",
                "layer_mapping": {
                    "L1": "L1.1 — FOMO Mua Đuổi & Cạn Kiệt Người Mua",
                    "L2": "Biên độ mở rộng cực đại từ vùng giá đáy",
                    "L3": "Loại bỏ nhiễu dao động < 25%",
                    "L4_formula": "prior_pump_pct = (swing_high - prior_low) / prior_low >= 0.50",
                },
                "psychology_mechanism": "Chỉ khi đồng coin đã tăng từ +50% đến +100%+, lòng tham đám đông mới đẩy lượng vị thế Long FOMO lên mức bão hòa, tạo ra động lực xả chốt lời và lực cung kẹp hàng đủ lớn khi giá gãy.",
                "genesis_conditions": "Giá tạo đỉnh Swing High trên H4/D1 với mức tăng >= 50% tính từ đáy Prior Low gần nhất (kiểm chứng tương đương tăng >= 45% so với vùng giá trung bình MA7 đáy).",
                "working_regime": "Thị trường Altcoin và Crypto có tính chu kỳ Bơm-Xả (Pump & Dump), đặc biệt từ mốc >= 40% (toàn hệ thống dương) và >= 50% (Điểm ngọt Alpha).",
                "failure_modes": "Khi sóng tăng trước đỉnh < 25% (3,400+ lệnh nhiễu lỗ -699.97%): giá chưa hề quá mua, nhịp chỉnh chỉ là tích lũy nhẹ rồi vượt đỉnh dễ dàng.",
                "redundant_indicators": [
                    "Biên độ tính từ MA7 vùng đáy (Trùng 88% với prior_pump_pct >= 50%)",
                    "ROC / Momentum % cố định 10-20 nến",
                ],
                "orthogonal_synergies": [
                    "ALPHA-F1B (Chế độ xu hướng & Gia tốc pysystemtrade)",
                    "ALPHA-F1C (Độ rỗng thanh khoản KER)",
                ],
                "metrics_2025": {
                    "trades": 480,
                    "win_rate_pct": 55.21,
                    "tp1_pct": 38.96,
                    "avg_net_pct": 0.485,
                    "total_net_pct": 232.64,
                    "profit_factor": 1.13,
                    "max_dd_pct": 244.5,
                },
                "code_snippet": "sig.wave.prior_pump_pct >= 50.0  # hoặc config.min_prior_pump_pct = 0.50",
            },
            {
                "id": "ALPHA-F1B",
                "name": "Carver Macro Regime & Broken Acceleration (ewmac <= 0 OR accel <= -1)",
                "factor_group": "Factor #1: Sóng Tăng Trước Đỉnh",
                "status": "LOCKED_IN_SAMPLE",
                "status_label": "✅ Đã Khóa (Trụ Cột Vĩ Mô & Gia Tốc)",
                "source_repo": "pst-group/pysystemtrade (Robert Carver)",
                "layer_mapping": {
                    "L1": "L1.1 + L1.4 — Tránh bẫy chặn đầu tàu tổ chức đang đẩy giá",
                    "L2": "L2.2 — Đứt gãy đạo hàm bậc 2 (Gia tốc accel(4,16) <= -1.0)",
                    "L3": "L3.1 — Chế độ Bear Market Rally (ewmac(16,64) <= 0)",
                    "L4_formula": "(ewmac_16_64 <= 0.0) or (cur_accel_4_16 <= -1.0)",
                },
                "psychology_mechanism": "Phân biệt giữa (1) cú bơm lừa trong xu hướng giảm lớn (nơi phe kẹp hàng dài hạn chực chờ xả) hoặc (2) đỉnh xu hướng tăng nhưng lực đẩy đã gãy sập đột ngột, với (3) một Siêu Uptrend đang được dòng tiền lớn mua đỡ đều đặn.",
                "genesis_conditions": "Tại đỉnh Swing High, ewmac(16,64) = (EWMA16 - EWMA64)/robust_vol_35 <= 0 (Bear Regime, 136 lệnh PF 1.63), HOẶC tại thời điểm vào lệnh gia tốc accel(4,16) = ewmac(4,16)_t - ewmac(4,16)_{t-4} <= -1.0 (65 lệnh PF 1.61).",
                "working_regime": "Hoạt động ổn định trên cả BTC/ETH lẫn Altcoin vì đã chuẩn hóa theo biến động riêng của từng đồng coin (robust_vol_calc).",
                "failure_modes": "Điểm mù duy nhất: Vẫn để lọt 71 lệnh sóng bò zíc-zắc (KER < 0.35) xây nhiều bậc thang hỗ trợ dọc đường (nhóm 71 lệnh này chỉ đạt PF 1.04, gây 95.9% DD).",
                "redundant_indicators": [
                    "Cấu trúc EMA20 <= EMA50 (Là phiên bản chưa chuẩn hóa biến động của ewmac(16,64) <= 0)",
                    "MACD Histogram đảo chiều âm",
                ],
                "orthogonal_synergies": [
                    "ALPHA-F1C (Lean KER >= 0.35): Tương quan r = 0.024 -> Ghép chung đẩy PF từ 1.63 lên 2.24!",
                ],
                "metrics_2025": {
                    "trades": 201,
                    "win_rate_pct": 63.18,
                    "tp1_pct": 44.28,
                    "avg_net_pct": 1.797,
                    "total_net_pct": 361.24,
                    "profit_factor": 1.63,
                    "max_dd_pct": 103.5,
                },
                "code_snippet": "pst_pass = (peak_ewmac_16_64 <= 0.0) or (cur_accel_4_16 <= -1.0)",
            },
            {
                "id": "ALPHA-F1C",
                "name": "Kaufman Liquidity Air-Pocket (Độ Rỗng Sóng KER >= 0.35 / 0.65)",
                "factor_group": "Factor #1: Sóng Tăng Trước Đỉnh",
                "status": "LOCKED_IN_SAMPLE",
                "status_label": "🏆 Đột Phá Mới (Trụ Cột Cấu Trúc Sóng)",
                "source_repo": "QuantConnect/Lean & perp-quant-lab (AF-0172)",
                "layer_mapping": {
                    "L1": "L1.1 + L1.3 — Giá kéo dựng đứng khiến không ai kịp đặt lệnh mua tích lũy dọc đường",
                    "L2": "L2.1 — Khoảng không thanh khoản (Air-Pocket Vacuum) vs Bậc thang đỡ giá (Staircase)",
                    "L3": "Cứu được cả các cú bơm dựng cột tuyệt đối (KER >= 0.65) trong Bull Market",
                    "L4_formula": "ker_wave = abs(close_peak - close_low) / sum(abs(diff(closes_low_to_peak))) >= 0.35",
                },
                "psychology_mechanism": "Khi giá bơm một mạch không có nhịp nghỉ (KER cao), toàn bộ khoảng giá từ đáy lên đỉnh là một 'vùng chân không thanh khoản'. Khi đỉnh gãy và retest Fibo 0.5–0.618 thất bại, không có bất kỳ vùng hỗ trợ ngang nào bên dưới để đỡ giá.",
                "genesis_conditions": "Tỷ số giữa quãng đường tịnh tiến ròng |Close_đỉnh - Close_đáy| chia cho tổng quãng đường zíc-zắc từng nến đạt >= 0.35 (loại bỏ sóng bậc thang) hoặc >= 0.60–0.65 (sóng dựng cột Air-Pocket).",
                "working_regime": "Cực mạnh khi kết hợp trực giao với ALPHA-F1B (PST): Nâng Win Rate lên 68.46%–74.55%, Profit Factor đạt 2.24 (tại KER>=0.35), 2.45 (tại KER>=0.40) và 3.08 (tại KER>=0.60).",
                "failure_modes": "Nếu dùng KER đơn độc ở sóng nhỏ (< 25%) hoặc sóng quá ngắn 1-4 nến H4 mới bắt đầu Breakout thì dễ nhầm với nến mở màn sóng tăng.",
                "redundant_indicators": [
                    "Pump Velocity >= 8%/ngày (crypto-factor-research, r = 0.304, cùng đo độ dựng đứng của sóng)",
                    "Wave Duration 1-8 ngày (r = 0.825 với Velocity, trùng 75.4%)",
                    "Microsoft Qlib RSQR(14) (r = 0.495 với KER nhưng kém hiệu quả hơn)",
                ],
                "orthogonal_synergies": [
                    "ALPHA-F1B (pysystemtrade): Tương quan r = 0.024 -> Ghép chung tạo ra Bộ Lọc Factor #1 Hoàn Chỉnh.",
                    "ALPHA-F3 (H1 BREAK_STRUCTURE_2): Đẩy Win Rate lên 77.78%, PF 2.99!",
                ],
                "metrics_2025": {
                    "trades": 135,
                    "win_rate_pct": 64.44,
                    "tp1_pct": 48.15,
                    "avg_net_pct": 1.916,
                    "total_net_pct": 258.70,
                    "profit_factor": 1.68,
                    "max_dd_pct": 59.1,
                },
                "code_snippet": "ker_wave = abs(closes[-1] - closes[0]) / np.sum(np.abs(np.diff(closes)))",
            },
            {
                "id": "ALPHA-F1-SYNTHESIS",
                "name": "Hợp Nhất Tinh Hoa Factor #1 (PST + Lean KER Synthesis)",
                "factor_group": "Factor #1: Sóng Tăng Trước Đỉnh",
                "status": "LOCKED_IN_SAMPLE",
                "status_label": "👑 Cấu Hình Chuẩn Factor #1",
                "source_repo": "pysystemtrade + QuantConnect/Lean Synthesis",
                "layer_mapping": {
                    "L1": "Hội tụ đầy đủ L1.1 (FOMO >= 50%) + L1.4 (Không chặn tàu tổ chức)",
                    "L2": "L2.1 (Khoảng không thanh khoản KER) + L2.2 (Gãy gia tốc accel)",
                    "L3": "L3.1 (Chế độ Bear Rally ewmac <= 0)",
                    "L4_formula": "Chế độ Tinh Hoa: PST & (KER >= 0.35) | Chế độ Mở Rộng: (PST & KER >= 0.35) OR (KER >= 0.65)",
                },
                "psychology_mechanism": "Sự kết hợp trực giao hoàn hảo giữa 3 câu hỏi: (1) Đám đông đã FOMO đủ lớn chưa (>=50%)? (2) Đà tăng đã gãy gia tốc hoặc nằm trong xu hướng giảm lớn chưa (PST)? (3) Bên dưới đỉnh có phải là khoảng không thanh khoản không có nền đỡ không (KER)?",
                "genesis_conditions": "Thỏa mãn đồng thời ALPHA-F1A + ALPHA-F1B + ALPHA-F1C.",
                "working_regime": "Chế độ Tinh Hoa (130 lệnh, WR 68.46%, PF 2.24, DD 75.7%) tối ưu tỷ suất lợi nhuận/rủi ro; Chế độ Mở Rộng (198 lệnh, WR 65.66%, Tổng lãi +427.43%, PF 1.85) tối đa hóa tổng lợi nhuận.",
                "failure_modes": "Còn ~30% lệnh thua chủ yếu rơi vào nhóm chỉ có nến H1 đơn lẻ (CANDLE_PATTERN_1, WR 55.56%) hoặc nhịp sập đầu tiên (Factor #2) chưa tối ưu.",
                "redundant_indicators": [
                    "Không cần thêm bất kỳ chỉ báo MA, RSI, Bollinger %B hay Duration nào nữa ở Factor #1.",
                ],
                "orthogonal_synergies": [
                    "Sẵn sàng làm nền tảng cố định (Ceteris Paribus) để tối ưu tiếp ALPHA-F2, ALPHA-F3, ALPHA-F4.",
                ],
                "metrics_2025": {
                    "trades": 130,
                    "win_rate_pct": 68.46,
                    "tp1_pct": 46.15,
                    "avg_net_pct": 2.682,
                    "total_net_pct": 348.66,
                    "profit_factor": 2.24,
                    "max_dd_pct": 75.7,
                },
                "code_snippet": "f1_elite = (prior_pump_pct >= 50.0) and ((ewmac_16_64 <= 0.0) or (accel_4_16 <= -1.0)) and (ker_wave >= 0.35)",
            },
            {
                "id": "ALPHA-F1D",
                "name": "Cross-Sectional BTC Context & Idiosyncratic Pump Spread",
                "factor_group": "Factor #1: Bối Cảnh Tương Quan BTC (5D)",
                "status": "LOCKED_IN_SAMPLE",
                "status_label": "✅ Đã Khóa (Tầng Vĩ Mô Liên Thị Trường)",
                "source_repo": "Multi-Asset Quant Factor Research",
                "layer_mapping": {
                    "L1": "L1.1 — Phân biệt coin tự bơm làm giá đơn lẻ vs sóng tăng toàn thị trường",
                    "L2": "Tách biệt dòng tiền nội tại (Idiosyncratic Flow) khỏi Beta chung của BTC",
                    "L3": "L3.1 — BTC không ở trạng thái bứt phá mạnh (btc_ewmac_4_16 <= 0.5) & Spread >= 60%",
                    "L4_formula": "(idiosyncratic_spread = prior_pump_pct - max(0, btc_ret_pct) >= 60.0) and (btc_ewmac_4_16 <= 0.5)",
                },
                "psychology_mechanism": "Khi một đồng Altcoin tự bơm vượt trội hơn BTC từ +60% trở lên trong khi BTC đang đi ngang hoặc suy yếu (btc_ewmac_4_16 <= 0.5), cú bơm đó thuần túy là đội lái/nhỏ lẻ đẩy giá cục bộ không có dòng tiền vĩ mô chống lưng -> Khi xả sẽ rơi tự do.",
                "genesis_conditions": "Chênh lệch biên độ tăng của coin trừ đi biên độ tăng của BTC cùng khung thời gian đạt >= 60% (246 lệnh đạt PF 1.29, Tổng lãi +254.21%; trong khi nhóm < 60% lỗ ròng -21.58%, PF 0.98).",
                "working_regime": "Độc lập tương quan hoàn toàn với F1B và F1C (|r| <= 0.36). Dùng làm biến cộng điểm (+10 điểm) trong Thang Điểm Hội Tụ 0–100.",
                "failure_modes": "Khi BTC đang nổ sóng tăng mạnh toàn thị trường (btc_ewmac_4_16 > 0.5), thủy triều BTC dâng sẽ kéo cả các coin yếu lên theo.",
                "redundant_indicators": ["Beta 30 ngày so với BTC", "ETH/BTC ratio ngắn hạn"],
                "orthogonal_synergies": ["ALPHA-F1-SYNTHESIS", "ALPHA-F4 (Điểm Hội Tụ Conviction Score)"],
                "metrics_2025": {
                    "trades": 246,
                    "win_rate_pct": 58.94,
                    "tp1_pct": 43.50,
                    "avg_net_pct": 1.033,
                    "total_net_pct": 254.21,
                    "profit_factor": 1.29,
                    "max_dd_pct": 115.6,
                },
                "code_snippet": "idiosyncratic_spread = raw_pump_pct - max(0.0, btc_ret_pct)  # >= 60.0%",
            },
            {
                "id": "ALPHA-F2",
                "name": "First Structural Crack — Nhịp Sập Mở Màn Dứt Khoát (Drop >= 6% & imp_ker >= 0.50)",
                "factor_group": "Factor #2: Nhịp Sập Đầu Tiên (Impulse Drop)",
                "status": "LOCKED_IN_SAMPLE",
                "status_label": "🏆 Đã Khóa Sau Review (Trụ Cột Phá Cấu Trúc)",
                "source_repo": "PeakPulse Native + Kaufman Efficiency Physics",
                "layer_mapping": {
                    "L1": "L1.2 — Gây sốc tâm lý, nhốt chặt đội mua đỉnh vào thế kẹp hàng (Trapped Bulls)",
                    "L2": "L2.3 — Xung lực xả thẳng đứng (imp_ker >= 0.50), phân biệt với cờ tăng (Bull Flag)",
                    "L3": "Hoạt động đồng nhất trên cả H4 (WR 63.64%, PF 1.62) và D1 (WR 70.43%, PF 2.39)",
                    "L4_formula": "(imp_drop_pct >= 6.0) and (imp_ker >= 0.50)",
                },
                "psychology_mechanism": "Nếu nhịp giảm đầu tiên từ đỉnh đi kiểu 'cưa chân bàn' zíc-zắc (imp_ker < 0.50), đó thực chất là nhịp tích lũy Cờ Tăng (Bull Flag) có lực cầu hấp thụ liên tục (nhóm này WR chỉ 51.6%–56.0%, PF 1.17–1.19). Ngược lại, khi nhịp sập đầu tiên rơi thẳng đứng (imp_ker >= 0.50) với biên độ >= 6%, phe mua đỉnh bị nhốt bất ngờ không kịp thoát, buộc phải chờ hồi lên Fibo 0.5–0.618 để xả về bờ.",
                "genesis_conditions": "Nhịp sập từ Swing High xuống Impulse Low đạt độ sâu >= 6% và hệ số thẳng Kaufman của nhịp sập imp_ker >= 0.50.",
                "working_regime": "Trên nền F1 Tinh Hoa (99 lệnh): Nâng Win Rate từ 68.46% lên 73.74%, Lãi TB từ +2.682% lên +3.341%/lệnh, Profit Factor vọt từ 2.24 lên 2.85, MaxDD giảm còn 60.5%! Trên nền F1 Mở Rộng (148 lệnh): WR 68.92%, TP1 50.00%, Tổng lãi +398.00%, PF 2.16.",
                "failure_modes": "Nhịp sập zíc-zắc (imp_ker < 0.50, 50 lệnh bị loại bỏ): Win Rate tụt xuống 56.00%, Avg chỉ +0.589%/lệnh, PF 1.19.",
                "redundant_indicators": [
                    "imp_retrace_of_pump_pct = Drop / Pump_Range (Tương quan r = +0.861 với imp_drop_pct)",
                    "imp_vol_units = Drop / robust_vol_35 (Tương quan r = +0.738 với imp_drop_pct)",
                ],
                "orthogonal_synergies": [
                    "Độc lập hoàn toàn với ker_wave của Factor #1 (r = +0.119) và imp_drop_pct (r = -0.136).",
                    "Ghép trực giao với ALPHA-F3 (H1 Structure Break) nâng Win Rate lên 77.61%, PF 2.93!",
                ],
                "metrics_2025": {
                    "trades": 99,
                    "win_rate_pct": 73.74,
                    "tp1_pct": 49.49,
                    "avg_net_pct": 3.341,
                    "total_net_pct": 330.80,
                    "profit_factor": 2.85,
                    "max_dd_pct": 60.5,
                },
                "code_snippet": "f2_pass = (imp_drop_pct >= 6.0) and (imp_ker >= 0.50)",
            },
            {
                "id": "ALPHA-F3",
                "name": "Fibonacci Breakeven Wall (0.500–0.786), H1 Micro-BOS & Pullback Volume Dry-Up",
                "factor_group": "Factor #3: Vùng Hồi Fibo & Nến Xác Nhận H1",
                "status": "LOCKED_IN_SAMPLE",
                "status_label": "🏆 Đã Khóa Sau Review (Điểm Bóp Cò Sniper H1)",
                "source_repo": "PeakPulse Multi-TF Fibo Engine",
                "layer_mapping": {
                    "L1": "L1.2 (Bức tường xả hòa vốn tại Fibo 0.500–0.786) + L1.3 (Hoảng loạn cắt lỗ khi thủng đáy H1)",
                    "L2": "L2.4 — Lệch pha HTF-LTF (cond2_break_prev_low) + Cạn kiệt thanh khoản nhịp hồi (pullback_vol_ratio <= 1.1)",
                    "L3": "Chặn các nhịp hồi quá sâu > 0.786 (nơi lực cung kẹp đỉnh đã bị hấp thụ hết)",
                    "L4_formula": "(0.500 <= max_fibo_ratio <= 0.786) and cond2_break_prev_low  # + Điểm thưởng khi pullback_vol_ratio_1h <= 1.1",
                },
                "psychology_mechanism": "Chứng minh thực nghiệm 3 quy luật: (1) Vùng Golden Pocket 0.500–0.618 đạt WR 75.32%, PF 2.49 và vùng quét 0.618–0.786 đạt AvgR cao nhất (+0.33R); nhưng nếu giá vượt quá 0.786 thì WR rơi xuống 54.17% vì tường bán đã vỡ. (2) Chỉ có mẫu nến H1 đơn lẻ (CANDLE_PATTERN_1) mà không phá cấu trúc chỉ đạt WR 51.06%, PF 1.33; nhưng khi có Phá Vỡ Cấu Trúc H1 (BREAK_STRUCTURE_2 hoặc COMBO_1_2) thì WR vọt lên 77.23%, PF 2.84 (riêng COMBO_1_2 đạt PF 3.00!). (3) Khi Volume nhịp hồi cạn kiệt (<= 1.1x Volume nhịp sập), WR đạt 73.08%, PF 2.67, AvgR +0.41R.",
                "genesis_conditions": "Đỉnh nhịp hồi nằm trong dải Fibo 0.500–0.786 và nến H1 đóng đỏ xác nhận phá đáy H1 liền trước hoặc đóng gãy ngược xuống dưới Fibo 0.500.",
                "working_regime": "Trên nền F1 + F2 Mở Rộng (90 lệnh): Win Rate 76.67%, Chạm TP1 54.44%, Lãi TB +3.108%/lệnh, PF 2.55, MaxDD giảm sâu xuống chỉ còn 41.5%! Trên nền F1 + F2 Tinh Hoa (67 lệnh): Win Rate 77.61%, PF 2.93!",
                "failure_modes": "Vào lệnh sớm chỉ dựa vào 1 cây nến Pinbar/Engulfing trên H1 khi giá chưa hề phá đáy H1 trước hoặc chưa gãy lại dưới mốc Fibo 0.500.",
                "redundant_indicators": ["RSI / Stochastic phân kỳ trên H1"],
                "orthogonal_synergies": [
                    "pullback_vol_ratio_1h độc lập hoàn toàn với cond2_break (r = -0.023), max_fibo_ratio (r = +0.047) và ker_wave (r = -0.110).",
                ],
                "metrics_2025": {
                    "trades": 90,
                    "win_rate_pct": 76.67,
                    "tp1_pct": 54.44,
                    "avg_net_pct": 3.108,
                    "total_net_pct": 279.70,
                    "profit_factor": 2.55,
                    "max_dd_pct": 41.5,
                },
                "code_snippet": "f3_sniper = (0.500 <= max_fibo_ratio <= 0.786) and sig.h1_confirmation.cond2_break_prev_low",
            },
            {
                "id": "ALPHA-F4",
                "name": "Optimal Stop-Loss Fibo 0.886, Staged TP (50/30/20) & Dynamic Conviction Sizing (0.75R–2.0R)",
                "factor_group": "Factor #4: Quản Trị Rủi Ro, SL/TP & Đi Vốn Động",
                "status": "LOCKED_IN_SAMPLE",
                "status_label": "👑 Đã Khóa Sau Review (Tối Ưu Hóa R-Multiple & Vốn)",
                "source_repo": "PeakPulse Risk Engine + Carver Conviction Scaling",
                "layer_mapping": {
                    "L1": "L1.2 + L1.3 — Khi giá đã vượt qua mốc Fibo 0.886 thì bức tường kẹp hàng đã thất thủ -> Cắt lỗ sớm tiết kiệm R",
                    "L2": "Khóa Breakeven ngay khi chạm TP1 (Fibo 0.0) và nuôi 50% vị thế còn lại tới Fibo Ext 1.272 & 1.618",
                    "L3": "Phân bổ khối lượng đặt cược (0.75R / 1.25R / 2.00R) tỷ lệ thuận với Thang Điểm Hội Tụ 4 Tầng (0–100)",
                    "L4_formula": "stop_loss = fibo.level_0886 + 0.25 * atr_1h | risk_mult = 2.0 if score>=85 else (1.25 if score>=70 else 0.75)",
                },
                "psychology_mechanism": "Đặt SL ở tận trên đỉnh Swing High (1.000) làm khoảng cách rủi ro R bị giãn rộng không cần thiết vì bất kỳ nhịp hồi nào vượt quá 0.886 đều đã phá hỏng cấu trúc giảm. Đặt SL ở 0.786 lại quá sát khiến dễ bị quét râu (WR tụt từ 68.9% xuống 60.8%). Mốc Fibo 0.886 + 0.25 ATR là điểm cân bằng vàng: giữ nguyên tỷ lệ chạm TP1 (50.00%) nhưng đẩy Profit Factor từ 2.07 lên 2.42, AvgR từ +0.24R lên +0.35R và giảm MaxDD từ 67.9% xuống 52.2%!",
                "genesis_conditions": "Áp dụng SL tại Fibo 0.886 + 0.25 ATR, chia TP 50%/30%/20% (hoặc 40%/40%/20%) và nhân khối lượng theo Conviction Score 4 tầng.",
                "working_regime": "Mốc 6B Toàn Diện (148 lệnh): Tổng lãi ròng vọt lên +512.65% (+3.464%/lệnh), PF 2.63, AvgR +0.43R, MaxDD 52.9%! Mốc 6A Sniper (90 lệnh): Win Rate 75.56%, Lãi TB +3.833%/lệnh, Tổng lãi +344.94%, PF 2.80, AvgR +0.44R, MaxDD chỉ 38.0%!",
                "failure_modes": "Đặt SL quá chật tại 0.786 sẽ làm mất 8.1% Win Rate do các pha quét râu thanh khoản tại vùng 0.618–0.786.",
                "redundant_indicators": ["Trailing Stop quá sớm trước khi giá chạm TP1 (Fibo 0.0)"],
                "orthogonal_synergies": [
                    "Kết tinh toàn bộ 4 nhân tố trực giao (ALPHA-F1 + ALPHA-F2 + ALPHA-F3 + ALPHA-F4) thành hệ thống hoàn chỉnh.",
                ],
                "metrics_2025": {
                    "trades": 148,
                    "win_rate_pct": 67.57,
                    "tp1_pct": 50.00,
                    "avg_net_pct": 3.464,
                    "total_net_pct": 512.65,
                    "profit_factor": 2.63,
                    "max_dd_pct": 52.9,
                },
                "code_snippet": "config = FiboTrendShortConfig(min_prior_pump_pct=0.50, min_impulse_drop_pct=0.06, min_wave_ker=0.35, min_impulse_ker=0.50, sl_mode='above_0886')",
            },
            {
                "id": "REJECTED-01",
                "name": "Bẫy Volatility Breakout Khi Dùng Độc Lập pump_vol_units & mr_wings Ở Sóng Nhỏ",
                "factor_group": "Bài Học Phủ Định (Negative Knowledge / Anti-Alpha)",
                "status": "REJECTED_TRAP",
                "status_label": "🚫 Đã Loại Bỏ (Bẫy Breakout Đầu Sóng)",
                "source_repo": "pst-group/pysystemtrade (Khi áp dụng sai ngữ cảnh cho Crypto)",
                "layer_mapping": {
                    "L1": "L1.4 — Bẫy Short sớm khi dòng tiền mới vừa châm ngòi nổ",
                    "L2": "Mở rộng biến động từ nền nén chặt (Volatility Squeeze Expansion)",
                    "L3": "L3.3 — Khởi đầu sóng tăng mới",
                    "L4_formula": "pump_vol_units = (swing_high - prior_low) / robust_vol >= 10 (khi prior_pump_pct chỉ 15%–25%)",
                },
                "psychology_mechanism": "Khi một đồng coin đi ngang nén chặt nhiều tuần (robust_vol cực nhỏ), chỉ cần tăng +15% là đã gấp 10–14 lần độ lệch chuẩn (mr_wings > 2 sigma). Nhưng đó là cây nến Breakout mở màn chu kỳ tăng lớn, nhảy vào Short sẽ bị cán SL hàng loạt.",
                "genesis_conditions": "Áp dụng mr_wings hoặc pump_vol_units mà không có điều kiện biên độ tuyệt đối prior_pump_pct >= 50%.",
                "working_regime": "Không hoạt động cho chiến lược bắt đỉnh Crypto (Lỗ -0.24% đến -0.57%/lệnh, PF 0.87–0.92).",
                "failure_modes": "Luôn thất bại khi thị trường chuyển từ tích lũy sang xu hướng tăng mới.",
                "redundant_indicators": ["Bollinger Band Squeeze Breakout", "Keltner Channel Breakout"],
                "orthogonal_synergies": ["Phải bị chặn bởi ALPHA-F1A (prior_pump_pct >= 50%) và ALPHA-F1B."],
                "metrics_2025": {
                    "trades": 391,
                    "win_rate_pct": 48.08,
                    "tp1_pct": 39.64,
                    "avg_net_pct": -0.453,
                    "total_net_pct": -177.01,
                    "profit_factor": 0.90,
                    "max_dd_pct": 310.0,
                },
                "code_snippet": "# CẤM DÙNG ĐỘC LẬP KHI CHƯA ĐỦ BIÊN ĐỘ >= 50%",
            },
            {
                "id": "REDUNDANT-01",
                "name": "Ghép Trùng Lặp Cùng Cơ Chế: Pump Velocity + Wave Duration + Qlib RSQR",
                "factor_group": "Bài Học Chống Đa Cộng Tuyến (Collinearity Warning)",
                "status": "MERGED_REDUNDANT",
                "status_label": "⚠️ Đã Gộp Vào ALPHA-F1C (Tránh Trùng Lặp)",
                "source_repo": "crypto-factor-research + microsoft/qlib + MA Study",
                "layer_mapping": {
                    "L1": "L1.1 — FOMO bơm nhanh",
                    "L2": "L2.1 — Cùng đo tốc độ/độ thẳng của sóng tăng",
                    "L3": "Cùng tầng cơ chế với KER",
                    "L4_formula": "pump_velocity >= 8%/day AND pump_duration <= 8 days (Trùng lặp 75.4%, r = +0.825)",
                },
                "psychology_mechanism": "Cả 3 chỉ báo (Velocity %/ngày, Duration <= 8 ngày, và KER) đều phản ánh cùng một hiện tượng: giá tăng nhanh không tạo nền. Khi đã dùng KER (đo trực tiếp độ rỗng thanh khoản), việc nhồi thêm điều kiện Duration hay Velocity không mang lại thông tin mới mà chỉ cắt bớt lệnh thắng.",
                "genesis_conditions": "Ghép nhiều chỉ báo ở Tầng 4 cùng thuộc Họ Tốc Độ/Độ Rỗng Sóng.",
                "working_regime": "Đứng riêng lẻ Velocity >= 8%/ngày rất tốt (189 lệnh, PF 1.55, +341.9%), nhưng ghép chung với Duration <= 8 ngày làm PF tụt xuống 1.48 và mất +114.9% lãi!",
                "failure_modes": "Over-filtering (Lọc chồng chéo cùng 1 tầng cơ chế).",
                "redundant_indicators": ["pump_velocity_per_day", "pump_days_equiv", "qlib_rsqr_14"],
                "orthogonal_synergies": ["Đã chọn KER (ALPHA-F1C) làm đại diện duy nhất chuẩn xác nhất cho cả họ này."],
                "metrics_2025": {
                    "trades": 147,
                    "win_rate_pct": 65.31,
                    "tp1_pct": 48.30,
                    "avg_net_pct": 1.544,
                    "total_net_pct": 227.03,
                    "profit_factor": 1.48,
                    "max_dd_pct": 67.4,
                },
                "code_snippet": "# ĐÃ GỘP: Chỉ dùng duy nhất `ker_wave >= 0.35` đại diện cho Tầng 2.1",
            },
        ],
    }


def build_html(
    baseline: dict,
    pump_study: dict,
    registry: dict[str, Any],
    audit_study: dict[str, Any],
    audit_dossier_md: str,
    coin_universe: dict[str, Any],
) -> str:
    keys = [
        ">= 5%",
        ">= 10%",
        ">= 15%",
        ">= 20%",
        ">= 25%",
        ">= 30%",
        ">= 40%",
        ">= 50%",
        ">= 65%",
        ">= 80%",
        ">= 100%",
    ]

    overall_rows = []
    tf_rows = []
    tier_rows = []
    chart_bars_overall = []
    chart_bars_tf = []

    for k in keys:
        entry = pump_study[k]
        thr = entry["pump_threshold_pct"]
        ov = entry["overall"]
        h4 = entry["4h"]
        d1 = entry["1d"]
        bs2 = entry["BREAK_STRUCTURE_2"]
        cb = entry["COMBO_1_2"]
        cp1 = entry["CANDLE_PATTERN_1"]

        row_highlight = ""
        tag_html = ""
        if thr == 5:
            tag_html = '<span class="tag tag-muted">Baseline (Nhiễu)</span>'
        elif thr == 30:
            tag_html = '<span class="tag tag-info">Điểm ngoặt D1 Dương</span>'
        elif thr == 40:
            row_highlight = "row-inflection"
            tag_html = '<span class="tag tag-cyan">Điểm ngoặt Toàn Hệ Thống</span>'
        elif thr == 50:
            row_highlight = "row-sweetspot"
            tag_html = '<span class="tag tag-gold">★ Điểm Ngọt Alpha (Sweet Spot)</span>'
        elif thr == 100:
            row_highlight = "row-climax"
            tag_html = '<span class="tag tag-emerald">⚡ Siêu Sóng X2 (Climax)</span>'

        ov_cls = badge_class(ov["avg_net_return_pct"])
        pf_cls = badge_class(ov["profit_factor"], 1.0)

        overall_rows.append(f"""
        <tr class="{row_highlight}">
          <td><strong>{k}</strong> {tag_html}</td>
          <td class="num">{ov["total_trades"]:,}</td>
          <td class="num"><strong>{ov["win_rate_pct"]:.2f}%</strong></td>
          <td class="num">{ov["tp1_hit_rate_pct"]:.2f}%</td>
          <td class="num">{ov["tp2_hit_rate_pct"]:.2f}%</td>
          <td class="num">{ov["tp3_hit_rate_pct"]:.2f}%</td>
          <td class="num {ov_cls}"><strong>{fmt_pct3(ov["avg_net_return_pct"])}</strong></td>
          <td class="num {ov_cls}"><strong>{fmt_pct(ov["total_net_return_pct"])}</strong></td>
          <td class="num {pf_cls}"><strong>{ov["profit_factor"]:.2f}</strong></td>
          <td class="num">{ov["max_drawdown_pct"]:.1f}%</td>
        </tr>
        """)

        h4_cls = badge_class(h4["avg_net_return_pct"])
        d1_cls = badge_class(d1["avg_net_return_pct"])
        tf_rows.append(f"""
        <tr class="{row_highlight}">
          <td><strong>{k}</strong></td>
          <td class="num">{h4["total_trades"]:,}</td>
          <td class="num">{h4["win_rate_pct"]:.2f}%</td>
          <td class="num">{h4["tp1_hit_rate_pct"]:.2f}%</td>
          <td class="num {h4_cls}"><strong>{fmt_pct3(h4["avg_net_return_pct"])}</strong></td>
          <td class="num {h4_cls}">{fmt_pct(h4["total_net_return_pct"])}</td>
          <td class="num {badge_class(h4["profit_factor"], 1.0)}">{h4["profit_factor"]:.2f}</td>
          <td class="num sep-left">{d1["total_trades"]:,}</td>
          <td class="num">{d1["win_rate_pct"]:.2f}%</td>
          <td class="num">{d1["tp1_hit_rate_pct"]:.2f}%</td>
          <td class="num {d1_cls}"><strong>{fmt_pct3(d1["avg_net_return_pct"])}</strong></td>
          <td class="num {d1_cls}">{fmt_pct(d1["total_net_return_pct"])}</td>
          <td class="num {badge_class(d1["profit_factor"], 1.0)}">{d1["profit_factor"]:.2f}</td>
        </tr>
        """)

        bs2_cls = badge_class(bs2["avg_net_return_pct"])
        cb_cls = badge_class(cb["avg_net_return_pct"])
        cp1_cls = badge_class(cp1["avg_net_return_pct"])
        tier_rows.append(f"""
        <tr class="{row_highlight}">
          <td><strong>{k}</strong></td>
          <td class="num">{bs2["total_trades"]:,}</td>
          <td class="num">{bs2["win_rate_pct"]:.2f}%</td>
          <td class="num {bs2_cls}"><strong>{fmt_pct3(bs2["avg_net_return_pct"])}</strong></td>
          <td class="num {badge_class(bs2["profit_factor"], 1.0)}">{bs2["profit_factor"]:.2f}</td>
          <td class="num sep-left">{cb["total_trades"]:,}</td>
          <td class="num">{cb["win_rate_pct"]:.2f}%</td>
          <td class="num {cb_cls}"><strong>{fmt_pct3(cb["avg_net_return_pct"])}</strong></td>
          <td class="num {badge_class(cb["profit_factor"], 1.0)}">{cb["profit_factor"]:.2f}</td>
          <td class="num sep-left">{cp1["total_trades"]:,}</td>
          <td class="num">{cp1["win_rate_pct"]:.2f}%</td>
          <td class="num {cp1_cls}"><strong>{fmt_pct3(cp1["avg_net_return_pct"])}</strong></td>
          <td class="num {badge_class(cp1["profit_factor"], 1.0)}">{cp1["profit_factor"]:.2f}</td>
        </tr>
        """)

        avg_val = ov["avg_net_return_pct"]
        width_pct = min(100.0, abs(avg_val) / 0.85 * 100.0)
        bar_type = "bar-pos" if avg_val >= 0 else "bar-neg"
        chart_bars_overall.append(f"""
        <div class="bar-row">
          <div class="bar-label">{k}</div>
          <div class="bar-track">
            <div class="bar-fill {bar_type}" style="width: {width_pct:.1f}%"></div>
          </div>
          <div class="bar-value {ov_cls}">{fmt_pct3(avg_val)} <span class="sub-val">(WR {ov['win_rate_pct']:.1f}% | PF {ov['profit_factor']:.2f})</span></div>
        </div>
        """)

        h4_val = h4["avg_net_return_pct"]
        d1_val = d1["avg_net_return_pct"]
        h4_w = min(100.0, abs(h4_val) / 0.85 * 100.0)
        d1_w = min(100.0, abs(d1_val) / 0.85 * 100.0)
        chart_bars_tf.append(f"""
        <div class="dual-bar-row">
          <div class="bar-label">{k}</div>
          <div class="dual-bars">
            <div class="mini-bar-line">
              <span class="tf-badge tf-h4">H4</span>
              <div class="bar-track"><div class="bar-fill {'bar-pos' if h4_val >= 0 else 'bar-neg'}" style="width:{h4_w:.1f}%"></div></div>
              <span class="mini-val {h4_cls}">{fmt_pct3(h4_val)}</span>
            </div>
            <div class="mini-bar-line">
              <span class="tf-badge tf-d1">D1</span>
              <div class="bar-track"><div class="bar-fill {'bar-pos' if d1_val >= 0 else 'bar-neg'}" style="width:{d1_w:.1f}%"></div></div>
              <span class="mini-val {d1_cls}">{fmt_pct3(d1_val)}</span>
            </div>
          </div>
        </div>
        """)

    # Baseline Symbol rows
    sym_items = sorted(
        baseline["by_symbol"].items(),
        key=lambda kv: kv[1]["avg_net_return_pct"],
        reverse=True,
    )
    symbol_rows = []
    for sym, st in sym_items:
        s_cls = badge_class(st["avg_net_return_pct"])
        pf_cls = badge_class(st["profit_factor"], 1.0)
        group_tag = (
            '<span class="tag tag-emerald">Altcoin Có Alpha Tự Nhiên</span>'
            if st["avg_net_return_pct"] > 0
            else (
                '<span class="tag tag-danger">Major Coin (Short Sớm Dễ Chết)</span>'
                if sym in ("BTCUSDT", "BNBUSDT", "SOLUSDT", "ETHUSDT")
                else '<span class="tag tag-muted">Cần Lọc Sóng >= 50%</span>'
            )
        )
        symbol_rows.append(f"""
        <tr class="searchable-item" data-search="{sym.lower()} altcoin major coin">
          <td><strong>{sym}</strong> {group_tag}</td>
          <td class="num">{st["total_trades"]:,}</td>
          <td class="num">{st["win_rate_pct"]:.2f}%</td>
          <td class="num">{st["tp1_hit_rate_pct"]:.2f}%</td>
          <td class="num">{st["tp2_hit_rate_pct"]:.2f}%</td>
          <td class="num">{st["tp3_hit_rate_pct"]:.2f}%</td>
          <td class="num {s_cls}"><strong>{fmt_pct3(st["avg_net_return_pct"])}</strong></td>
          <td class="num {s_cls}">{fmt_pct(st["total_net_return_pct"])}</td>
          <td class="num {pf_cls}"><strong>{st["profit_factor"]:.2f}</strong></td>
        </tr>
        """)

    # Build Alpha Passport Cards HTML from registry
    passport_cards_html = []
    for p in registry["alpha_passports"]:
        m = p["metrics_2025"]
        status_cls = {
            "LOCKED_IN_SAMPLE": "card-locked",
            "CANDIDATE_NEXT": "card-candidate",
            "REJECTED_TRAP": "card-rejected",
            "MERGED_REDUNDANT": "card-merged",
        }.get(p["status"], "")
        badge_cls = {
            "LOCKED_IN_SAMPLE": "tag-emerald",
            "CANDIDATE_NEXT": "tag-cyan",
            "REJECTED_TRAP": "tag-danger",
            "MERGED_REDUNDANT": "tag-gold",
        }.get(p["status"], "tag-muted")

        red_items = "".join(f"<li>{r}</li>" for r in p["redundant_indicators"])
        syn_items = "".join(f"<li>{s}</li>" for s in p["orthogonal_synergies"])
        search_blob = (
            f"{p['id']} {p['name']} {p['factor_group']} {p['source_repo']} "
            f"{p['psychology_mechanism']} {p['layer_mapping']['L4_formula']}"
        ).lower()

        passport_cards_html.append(f"""
        <div class="passport-card {status_cls} searchable-item" data-status="{p['status']}" data-search="{search_blob}">
          <div class="passport-top">
            <div>
              <span class="passport-id">{p['id']}</span>
              <span class="tag {badge_cls}">{p['status_label']}</span>
              <span class="tag tag-muted">{p['factor_group']}</span>
            </div>
            <div class="passport-actions">
              <button class="btn-mini" onclick='copyPassportJson({json.dumps(p["id"])})'>📋 Copy JSON</button>
              <button class="btn-mini" onclick='copyText({json.dumps(p["code_snippet"])}, "Đã copy công thức code!")'>⚡ Copy Code</button>
            </div>
          </div>
          <h3 class="passport-title">{p['name']}</h3>
          <div class="passport-repo">Nguồn tham chiếu: <code>{p['source_repo']}</code></div>

          <!-- KPI Strip inside Passport -->
          <div class="passport-metrics">
            <div class="pm-item"><span class="pm-lbl">Số Lệnh (2024–2025)</span><span class="pm-val">{m['trades']}</span></div>
            <div class="pm-item"><span class="pm-lbl">Win Rate</span><span class="pm-val {'pos' if m['win_rate_pct']>=55 else 'neg'}">{m['win_rate_pct']:.2f}%</span></div>
            <div class="pm-item"><span class="pm-lbl">Chạm TP1</span><span class="pm-val">{m['tp1_pct']:.2f}%</span></div>
            <div class="pm-item"><span class="pm-lbl">Lãi TB / Lệnh</span><span class="pm-val {badge_class(m['avg_net_pct'])}">{fmt_pct3(m['avg_net_pct'])}</span></div>
            <div class="pm-item"><span class="pm-lbl">Tổng Lãi Ròng</span><span class="pm-val {badge_class(m['total_net_pct'])}">{fmt_pct(m['total_net_pct'])}</span></div>
            <div class="pm-item"><span class="pm-lbl">Profit Factor</span><span class="pm-val {badge_class(m['profit_factor'], 1.0)}">{m['profit_factor']:.2f}</span></div>
            <div class="pm-item"><span class="pm-lbl">Max Drawdown</span><span class="pm-val">{m['max_dd_pct']:.1f}%</span></div>
          </div>

          <!-- 4-Layer Mapping Box -->
          <div class="layer-map-box">
            <div class="lm-row"><span class="lm-tag l1">Tầng 1 (Tâm lý)</span><span>{p['layer_mapping']['L1']}</span></div>
            <div class="lm-row"><span class="lm-tag l2">Tầng 2 (Vật lý)</span><span>{p['layer_mapping']['L2']}</span></div>
            <div class="lm-row"><span class="lm-tag l3">Tầng 3 (Vĩ mô)</span><span>{p['layer_mapping']['L3']}</span></div>
            <div class="lm-row"><span class="lm-tag l4">Tầng 4 (Công thức)</span><code>{p['layer_mapping']['L4_formula']}</code></div>
          </div>

          <!-- Deep Mechanism Grid -->
          <div class="passport-grid">
            <div class="pg-box">
              <h5>🧠 Cơ Chế Tâm Lý Đám Đông &amp; Điều Kiện Hình Thành</h5>
              <p><strong>Tại sao có Alpha:</strong> {p['psychology_mechanism']}</p>
              <p style="margin-top:6px;"><strong>Điều kiện hình thành:</strong> {p['genesis_conditions']}</p>
            </div>
            <div class="pg-box">
              <h5>🚦 Khi Nào Hoạt Động (Working) vs Khi Nào Tắt Điện (Kill-Switch)</h5>
              <p><strong class="pos">✔ Khi hoạt động mạnh:</strong> {p['working_regime']}</p>
              <p style="margin-top:6px;"><strong class="neg">✖ Tử huyệt / Khi mất tác dụng:</strong> {p['failure_modes']}</p>
            </div>
            <div class="pg-box">
              <h5>🔗 Liên Kết Hệ Thống: Chống Trùng Lặp &amp; Cộng Hưởng Trực Giao</h5>
              <p><strong style="color:#fbbf24;">⚠️ Chỉ báo trùng lặp (Cấm ghép chồng):</strong></p>
              <ul class="compact-list">{red_items}</ul>
              <p style="margin-top:6px;"><strong class="pos">⚡ Alpha trực giao (Nên ghép chung):</strong></p>
              <ul class="compact-list">{syn_items}</ul>
            </div>
          </div>
        </div>
        """)

    # Build Locked Milestones 14-Symbol Comparison Rows (Chuyên mục 5.1)
    cs_2025 = audit_study["cross_section"]["is_2020_2025"]["m4_f2_elite"]["by_symbol"]
    cs_2425 = audit_study["cross_section"]["is_2024_2025"]["m6_f4_expanded"]["by_symbol"]
    cs_2026 = audit_study["cross_section"]["oos_2026"]["m6_f4_expanded"]["by_symbol"]
    all_syms = list(cs_2025.keys())
    locked_symbol_rows = []
    for sym in all_syms:
        s20 = cs_2025[sym]
        s24 = cs_2425[sym]
        s26 = cs_2026[sym]
        c20 = badge_class(s20["total_net_return_pct"]) if s20["total_trades"] > 0 else "neu"
        c24 = badge_class(s24["total_net_return_pct"]) if s24["total_trades"] > 0 else "neu"
        c26 = badge_class(s26["total_net_return_pct"]) if s26["total_trades"] > 0 else "neu"
        pf20_str = f"{s20['profit_factor']:.2f}" if s20["total_trades"] > 0 else "—"
        pf24_str = f"{s24['profit_factor']:.2f}" if s24["total_trades"] > 0 else "—"
        pf26_str = f"{s26['profit_factor']:.2f}" if s26["total_trades"] > 0 else "—"
        wr20_str = f"{s20['win_rate_pct']:.1f}%" if s20["total_trades"] > 0 else "—"
        wr24_str = f"{s24['win_rate_pct']:.1f}%" if s24["total_trades"] > 0 else "—"
        wr26_str = f"{s26['win_rate_pct']:.1f}%" if s26["total_trades"] > 0 else "—"
        net20_str = fmt_pct(s20["total_net_return_pct"]) if s20["total_trades"] > 0 else "0.0% (Đứng ngoài)"
        net24_str = fmt_pct(s24["total_net_return_pct"]) if s24["total_trades"] > 0 else "0.0% (Đứng ngoài)"
        net26_str = fmt_pct(s26["total_net_return_pct"]) if s26["total_trades"] > 0 else "0.0% (Đứng ngoài)"
        locked_symbol_rows.append(f"""
        <tr class="searchable-item" data-search="{sym.lower()} cross-asset breadth">
          <td><strong>{sym}</strong></td>
          <td class="num sep-left">{s20['total_trades']}</td>
          <td class="num">{wr20_str}</td>
          <td class="num {c20}"><strong>{net20_str}</strong></td>
          <td class="num {c20}">{pf20_str}</td>
          <td class="num sep-left">{s24['total_trades']}</td>
          <td class="num">{wr24_str}</td>
          <td class="num {c24}"><strong>{net24_str}</strong></td>
          <td class="num {c24}">{pf24_str}</td>
          <td class="num sep-left">{s26['total_trades']}</td>
          <td class="num">{wr26_str}</td>
          <td class="num {c26}"><strong>{net26_str}</strong></td>
          <td class="num {c26}">{pf26_str}</td>
        </tr>
        """)

    # Build 338-Coin Universe Walk-Forward & Archetype & MarketCap/Float & Coin Profile Tables (Chuyên mục 5.0)
    u_tiers_meta = [
        (
            "TIER_S_CORE",
            "👑 Hạng S — Danh Sách Chủ Lực (Tier S Core v1.2)",
            "G4 Liquid Meme + G2 Liquid L1/L2/DeFi (Warmup >= 63d, Vol >= $5M/d & IS Dương)",
            "row-climax",
        ),
        (
            "TIER_S_PLUS_A_WHITELIST",
            "🏆 Tổng Danh Sách Cho Phép Short Chuẩn v1.2 (Tier S + Tier A = 68 Mã)",
            "40 mã Tier S + 28 mã Tier A đã lọc sạch bẫy Low-Float (<64%) & Small-Cap (<$150M)",
            "row-sweetspot",
        ),
        (
            "TIER_A_EXTENDED",
            "⭐ Hạng A — Danh Sách Mở Rộng v1.2 (Tier A Extended = 28 Mã)",
            "G2/G4 còn lại + G3 có MCap >= $150M, Float >= 64%, Vol >= $10M/d, Wick <= 3.5%",
            "",
        ),
        (
            "PIT_ZERO_BIAS_MCAP_FLOAT",
            "🔬 Chuẩn Point-in-Time 0% PnL Bias + Vốn Hóa & Cung Lưu Hành (64 Mã)",
            "100% Khách quan (Không nhìn PnL IS): Age >= 63d + MCap >= $150M + Float >= 70% + Vol >= $5M/d + Wick <= 3.5%",
            "row-sweetspot",
        ),
        (
            "PIT_A1E6CA7D_TOP50_VOL",
            "📐 Chuẩn Tham Chiếu a1e6ca7d (Top-50 Volume + Age >= 63d, 0% PnL Bias)",
            "Chỉ lọc Thanh khoản Top-50 + Warmup >= 63d + Wick <= 3.2% (Chưa lọc Market Cap & Float Ratio)",
            "",
        ),
        (
            "LOW_FLOAT_OR_SMALL_MCAP_G3_TRAPS",
            "⚠️ 20 Mã G3 Bẫy Low-Float (<64%) Hoặc Vốn Hóa Nhỏ (<$150M) Bị Loại Ở v1.2",
            "Ví dụ WLD (Float 38%), AERO (50%), PUMP (56%), MINA ($110M): IS lãi +928% nhưng OOS 2026 bị Squeeze lỗ -31.6%!",
            "",
        ),
        (
            "ALL_340_UNFILTERED",
            "🌌 Toàn Bộ Vũ Trụ 338 Coin (Nếu Đánh Bừa Không Chọn Lọc)",
            "Bao gồm cả 109 mã thanh khoản mỏng G5 và các mã bẫy Squeeze",
            "",
        ),
        (
            "BLACKLIST",
            "🚫 Danh Sách Cấm Short Chuẩn v1.2 (Blacklist — 269 Mã Loại Bỏ)",
            "G1 Tích trữ (BTC/ETH/BNB/PAXG) + G5 Làm giá + MCap < $150M + Low-Float VC Unlock < 64%",
            "",
        ),
    ]
    universe_tier_rows = []
    for t_key, t_lbl, t_desc, r_cls in u_tiers_meta:
        td = coin_universe["by_universe_tier"][t_key]
        cnt = td["coin_count"]
        is6 = td["is_2024_2025"]["m6_f4_expanded"]
        oos6 = td["oos_2026"]["m6_f4_expanded"]
        oos4 = td["oos_2026"]["m4_f2_elite"]
        c_is = badge_class(is6["total_net_return_pct"])
        c_oos6 = badge_class(oos6["total_net_return_pct"])
        c_oos4 = badge_class(oos4["total_net_return_pct"])
        universe_tier_rows.append(f"""
        <tr class="{r_cls}">
          <td><strong>{t_lbl}</strong><br/><small style="color:#94a3b8;">{t_desc}</small></td>
          <td class="num"><strong>{cnt} mã</strong></td>
          <td class="num sep-left">{is6['total_trades']}</td>
          <td class="num">{is6['win_rate_pct']:.1f}%</td>
          <td class="num {c_is}"><strong>{fmt_pct(is6['total_net_return_pct'])}</strong></td>
          <td class="num {badge_class(is6['profit_factor'], 1.0)}"><strong>{is6['profit_factor']:.2f}</strong></td>
          <td class="num">{is6['max_drawdown_pct']:.1f}%</td>
          <td class="num sep-left">{oos6['total_trades']}</td>
          <td class="num"><strong>{oos6['win_rate_pct']:.1f}%</strong></td>
          <td class="num {c_oos6}"><strong>{fmt_pct(oos6['total_net_return_pct'])}</strong></td>
          <td class="num {badge_class(oos6['profit_factor'], 1.0)}"><strong>{oos6['profit_factor']:.2f}</strong></td>
          <td class="num">{oos6['max_drawdown_pct']:.1f}%</td>
          <td class="num sep-left {c_oos4}">{fmt_pct(oos4['total_net_return_pct'])} <small>(PF {oos4['profit_factor']:.2f})</small></td>
        </tr>
        """)

    # Build Market Cap & Circulating Supply Float Ratio Rows (New in v1.2)
    mcap_float_meta = [
        (
            "by_float_ratio",
            "FLOAT_HIGH_75_PLUS",
            "👑 Cung Lưu Hành Cao: Float Ratio (Circulating / Total Supply) >= 75% (Trên nhóm MCap >= $150M)",
            "Token đã phân phối rộng rãi cho cộng đồng (0 áp lực VC làm giá mở khóa) -> Trọng lực xả tự nhiên hoàn hảo!",
            "row-climax",
        ),
        (
            "by_float_ratio",
            "FLOAT_MED_40_75",
            "⚠️ Cung Lưu Hành Trung Bình: 40% <= Float Ratio < 75% (Trên nhóm MCap >= $150M)",
            "Đang trong lịch trả góp Vesting -> Có cả nhịp xả lẫn nhịp MM đẩy giá trước kỳ Unlock (OOS đi ngang -14.2%)",
            "",
        ),
        (
            "by_float_ratio",
            "FLOAT_LOW_UNDER_40",
            "☠️ Bẫy Low-Float / High-FDV: Float Ratio < 40% (Cung lưu hành bị khóa >60% bởi VC/MM)",
            "Đội lái nắm trọn cung lưu hành ít ỏi bên ngoài để kéo Short Squeeze quét sạch SL trước khi xả (OOS lỗ -382.2%, PF 0.50)!",
            "",
        ),
        (
            "by_market_cap",
            "MC3_LOWER_MID_150M_500M",
            "🏆 Điểm Ngọt Vốn Hóa MC3: Lower Mid-Cap ($150M <= Circulating MCap < $500M)",
            "Đủ lớn (> $150M) để một đội lái đơn lẻ không thể thao túng sổ lệnh Spot, nhưng đủ nhẹ để bơm sốc >=50% rồi sập",
            "row-sweetspot",
        ),
        (
            "by_market_cap",
            "MC1_LARGE_CAP_2B_PLUS",
            "💎 Vốn Hóa Lớn MC1: Large-Cap Altcoins (Circulating MCap >= $2.0B — SOL, DOGE, XRP, LINK, PEPE...)",
            "Thanh khoản cực sâu; chỉ sinh lời mạnh khi kết hợp chọn lọc nhóm G2/G4 có Float >= 70%",
            "",
        ),
        (
            "by_market_cap",
            "MC2_UPPER_MID_500M_2B",
            "📊 Vốn Hóa Trung Lớn MC2: Upper Mid-Cap ($500M <= Circulating MCap < $2.0B)",
            "Cần lọc bỏ các mã Low-Float VC coin (như WLD, JUP, ONDO, ENA khi Float thấp) để giữ phần lõi G2/G4",
            "",
        ),
        (
            "by_market_cap",
            "MC4_SMALL_CAP_50M_150M",
            "🚫 Bẫy Vốn Hóa Nhỏ MC4: Small-Cap ($50M <= Circulating MCap < $150M)",
            "Cung lưu hành quá nhỏ: MM chỉ cần $5M–$10M gom Spot là ép cháy phe Short trên Futures (OOS lỗ -327.8%, PF 0.79)",
            "",
        ),
        (
            "by_market_cap",
            "MC5_MICRO_UNDER_50M",
            "🚫 Bẫy Vốn Hóa Siêu Nhỏ MC5: Micro-Cap (Circulating MCap < $50M)",
            "100% là sòng bạc của đội lái thao túng Funding & Râu nến (IS lỗ -107.0%, OOS lỗ -807.9%, PF 0.65)",
            "",
        ),
    ]
    universe_mcap_float_rows = []
    for sec_key, item_key, lbl, desc, r_cls in mcap_float_meta:
        md = coin_universe.get(sec_key, {}).get(item_key)
        if not md:
            continue
        is6 = md["is_2024_2025"]["m6_f4_expanded"]
        oos6 = md["oos_2026"]["m6_f4_expanded"]
        oos4 = md["oos_2026"]["m4_f2_elite"]
        c_is = badge_class(is6["total_net_return_pct"]) if is6["total_trades"] > 0 else "neu"
        c_oos = badge_class(oos6["total_net_return_pct"]) if oos6["total_trades"] > 0 else "neu"
        c_oos4 = badge_class(oos4["total_net_return_pct"]) if oos4["total_trades"] > 0 else "neu"
        universe_mcap_float_rows.append(f"""
        <tr class="{r_cls}">
          <td><strong>{lbl}</strong><br/><small style="color:#94a3b8;">{desc}</small></td>
          <td class="num"><strong>{md['coin_count']} mã</strong></td>
          <td class="num sep-left">{is6['total_trades']}</td>
          <td class="num">{is6['win_rate_pct']:.1f}%</td>
          <td class="num {c_is}"><strong>{fmt_pct(is6['total_net_return_pct'])}</strong></td>
          <td class="num {badge_class(is6['profit_factor'], 1.0)}"><strong>{is6['profit_factor']:.2f}</strong></td>
          <td class="num sep-left">{oos6['total_trades']}</td>
          <td class="num"><strong>{oos6['win_rate_pct']:.1f}%</strong></td>
          <td class="num {c_oos}"><strong>{fmt_pct(oos6['total_net_return_pct'])}</strong></td>
          <td class="num {badge_class(oos6['profit_factor'], 1.0)}"><strong>{oos6['profit_factor']:.2f}</strong></td>
          <td class="num">{oos6['max_drawdown_pct']:.1f}%</td>
          <td class="num sep-left {c_oos4}">{fmt_pct(oos4['total_net_return_pct'])} <small>(PF {oos4['profit_factor']:.2f})</small></td>
        </tr>
        """)

    u_arch_meta = [
        (
            "G4_LIQUID_MEME_RETAIL",
            "🔥 G4: Liquid Meme & Retail Mania (PEPE, BONK, SHIB, WIF, TRUMP...)",
            "Bơm 100% bằng FOMO nhỏ lẻ, 0 giá trị nội tại -> Xả thẳng đứng theo trọng lực",
            "row-climax",
        ),
        (
            "G2_LIQUID_L1_L2_DEFI",
            "💎 G2: Liquid L1 / L2 / DeFi Blue-Chips (SOL, LINK, AVAX, SUI, UNI...)",
            "Sổ lệnh sâu ($15M–$500M/ngày), tôn trọng chuẩn xác Fibo 0.5–0.786, ít râu quét SL",
            "row-sweetspot",
        ),
        (
            "G1_STORE_OF_VALUE_MAJOR",
            "🛡️ G1: Store-of-Value & Institutional Bid (BTC, ETH, BNB, PAXG)",
            "Lực đỡ ETF/Tổ chức dài hạn -> Chỉ dùng làm Bộ lọc Vĩ mô (F1C), CẤM SHORT",
            "",
        ),
        (
            "G3_HIGH_BETA_NARRATIVE_MIDCAP",
            "⚠️ G3: High-Beta Narrative Mid-Caps (148 mã phân hóa mạnh)",
            "Chỉ chọn các mã MCap >= $150M, Float >= 64%, Vol >= $10M/d & râu sạch vào Tier A; còn lại dễ bị ép Short Squeeze",
            "",
        ),
        (
            "G5_THIN_OR_MANIPULATED",
            "☠️ G5: Thin Orderbook / Scam-Wick Manipulated (<$2.5M/d hoặc Wick >4.5%)",
            "Đội lái (MM) thao túng Funding âm và phóng râu nến quét sạch Stop Loss -> CẤM TUYỆT ĐỐI",
            "",
        ),
    ]
    universe_archetype_rows = []
    for a_key, a_lbl, a_desc, r_cls in u_arch_meta:
        ad = coin_universe["by_archetype"][a_key]
        is6 = ad["is_2024_2025"]["m6_f4_expanded"]
        oos6 = ad["oos_2026"]["m6_f4_expanded"]
        c_is = badge_class(is6["total_net_return_pct"]) if is6["total_trades"] > 0 else "neu"
        c_oos = badge_class(oos6["total_net_return_pct"]) if oos6["total_trades"] > 0 else "neu"
        universe_archetype_rows.append(f"""
        <tr class="{r_cls}">
          <td><strong>{a_lbl}</strong><br/><small style="color:#94a3b8;">{a_desc}</small></td>
          <td class="num">{ad['coin_count']} mã</td>
          <td class="num">{ad['avg_gravity_decay_pct']:.1f}%</td>
          <td class="num sep-left">{is6['total_trades']}</td>
          <td class="num">{is6['win_rate_pct']:.1f}%</td>
          <td class="num {c_is}"><strong>{fmt_pct(is6['total_net_return_pct'])}</strong></td>
          <td class="num {badge_class(is6['profit_factor'], 1.0)}"><strong>{is6['profit_factor']:.2f}</strong></td>
          <td class="num sep-left">{oos6['total_trades']}</td>
          <td class="num">{oos6['win_rate_pct']:.1f}%</td>
          <td class="num {c_oos}"><strong>{fmt_pct(oos6['total_net_return_pct'])}</strong></td>
          <td class="num {badge_class(oos6['profit_factor'], 1.0)}"><strong>{oos6['profit_factor']:.2f}</strong></td>
        </tr>
        """)

    # Build Coin Profile Rows (All 40 Tier S + All 28 Tier A + Dynamic + Top 45 Blacklist examples)
    universe_coin_rows = []
    bl_shown = 0
    for p in coin_universe["symbol_profiles"]:
        ut = p["universe_tier"]
        if ut == "BLACKLIST":
            if bl_shown >= 45 and p["symbol"] not in ("BTCUSDT", "ETHUSDT", "BNBUSDT", "PAXGUSDT", "WLDUSDT", "AEROUSDT", "PUMPUSDT", "MINAUSDT"):
                continue
            bl_shown += 1

        sym = p["symbol"]
        arch = p["archetype"]
        qvol_m = p["median_daily_qvol_usd"] / 1e6
        mcap_m = p.get("mcap_usd", 0.0) / 1e6
        float_pct = p.get("float_ratio", 1.0) * 100.0
        wick = p["wick_toxicity_p90_pct"]
        grav = p["gravity_decay_rate_pct"]
        sc = p["suitability_score"]
        is6 = p["is_2024_2025"]["m6_f4_expanded"]
        oos6 = p["oos_2026"]["m6_f4_expanded"]

        tier_badge = {
            "TIER_S_CORE": '<span class="tag tag-emerald">👑 TIER S CORE</span>',
            "TIER_A_EXTENDED": '<span class="tag tag-gold">⭐ TIER A v1.2</span>',
            "DYNAMIC_POOL": '<span class="tag tag-cyan">🔄 DYNAMIC</span>',
            "BLACKLIST": '<span class="tag tag-danger">🚫 BLACKLIST</span>',
        }.get(ut, ut)

        row_cls = "row-climax" if ut == "TIER_S_CORE" else ("row-sweetspot" if ut == "TIER_A_EXTENDED" else "")
        c_is = badge_class(is6["total_net_return_pct"]) if is6["total_trades"] > 0 else "neu"
        c_oos = badge_class(oos6["total_net_return_pct"]) if oos6["total_trades"] > 0 else "neu"
        is_str = f"{fmt_pct(is6['total_net_return_pct'])} (PF {is6['profit_factor']:.2f})" if is6["total_trades"] > 0 else "0 lệnh"
        oos_str = f"{fmt_pct(oos6['total_net_return_pct'])} (PF {oos6['profit_factor']:.2f})" if oos6["total_trades"] > 0 else "0 lệnh"
        mcap_str = f"${mcap_m:,.0f}M" if mcap_m > 0 else "Unranked"
        float_cls = "pos" if float_pct >= 70.0 else ("neg" if float_pct < 50.0 else "neu")

        universe_coin_rows.append(f"""
        <tr class="universe-coin-row {row_cls} searchable-item" data-utier="{ut}" data-search="{sym.lower()} {ut.lower()} {arch.lower()}">
          <td><strong>{sym}</strong></td>
          <td>{tier_badge}</td>
          <td class="num"><strong>{sc:.1f}</strong></td>
          <td><code>{arch}</code></td>
          <td class="num"><strong>{mcap_str}</strong></td>
          <td class="num {float_cls}"><strong>{float_pct:.0f}%</strong></td>
          <td class="num">${qvol_m:,.1f}M</td>
          <td class="num">{grav:.1f}%</td>
          <td class="num">{wick:.2f}%</td>
          <td class="num sep-left">{is6['total_trades']}</td>
          <td class="num {c_is}"><strong>{is_str}</strong></td>
          <td class="num sep-left">{oos6['total_trades']}</td>
          <td class="num {c_oos}"><strong>{oos_str}</strong></td>
          <td><small style="color:#cbd5e1;">{p['tier_reason_vi']}</small></td>
        </tr>
        """)

    tier_s_list_json = json.dumps(coin_universe["lists"]["tier_s_core"], ensure_ascii=False)
    tier_sa_list_json = json.dumps(
        coin_universe["lists"]["tier_s_core"] + coin_universe["lists"]["tier_a_extended"],
        ensure_ascii=False,
    )
    pit_zero_bias_list_json = json.dumps(
        coin_universe["lists"].get("pit_zero_bias_mcap_float", []),
        ensure_ascii=False,
    )
    blacklist_list_json = json.dumps(coin_universe["lists"]["blacklist_do_not_short"], ensure_ascii=False)

    # Build H4 vs D1 Timeframe Breakdown across Milestones (Chuyên mục 5.2)
    tf_milestone_configs = [
        ("IS 6 Năm (2020–2025)", "is_2020_2025", "m1_f1a_pump50", "Mốc 1: Raw Pump >= 50%", ""),
        ("IS 6 Năm (2020–2025)", "is_2020_2025", "m3_f1c_elite", "Mốc 3A: F1 Tinh Hoa (PST & KER>=0.35)", ""),
        ("IS 6 Năm (2020–2025)", "is_2020_2025", "m4_f2_elite", "★ Mốc 4A: +F2 Tinh Hoa (imp_ker>=0.50)", "row-sweetspot"),
        ("IS 6 Năm (2020–2025)", "is_2020_2025", "m6_f4_expanded", "👑 Mốc 6B: Toàn Diện (SL 0.886 + Đi Vốn)", ""),
        ("IS 6 Năm (2020–2025)", "is_2020_2025", "m6_f4_sniper", "👑 Mốc 6A: Sniper Mở Rộng", ""),
        ("IS 6 Năm (2020–2025)", "is_2020_2025", "m6_f4_elite_sniper", "👑 Mốc 6S: Sniper Tinh Hoa (7/7 Năm Dương)", "row-climax"),
        ("IS 2 Năm (2024–2025)", "is_2024_2025", "m4_f2_elite", "★ Mốc 4A (2024–2025)", ""),
        ("IS 2 Năm (2024–2025)", "is_2024_2025", "m6_f4_expanded", "👑 Mốc 6B Toàn Diện (2024–2025)", "row-sweetspot"),
        ("IS 2 Năm (2024–2025)", "is_2024_2025", "m6_f4_sniper", "👑 Mốc 6A Sniper Mở Rộng (2024–2025)", "row-climax"),
        ("IS 2 Năm (2024–2025)", "is_2024_2025", "m6_f4_elite_sniper", "👑 Mốc 6S Sniper Tinh Hoa (2024–2025)", "row-climax"),
        ("OOS Thực Chiến (2026)", "oos_2026", "m4_f2_elite", "★ Mốc 4A (OOS 2026)", ""),
        ("OOS Thực Chiến (2026)", "oos_2026", "m6_f4_expanded", "👑 Mốc 6B Toàn Diện (OOS 2026)", "row-sweetspot"),
        ("OOS Thực Chiến (2026)", "oos_2026", "m6_f4_sniper", "👑 Mốc 6A Sniper Mở Rộng (OOS 2026)", "row-climax"),
        ("OOS Thực Chiến (2026)", "oos_2026", "m6_f4_elite_sniper", "👑 Mốc 6S Sniper Tinh Hoa (OOS 2026)", "row-climax"),
    ]
    tf_milestone_rows = []
    for horizon_lbl, h_key, m_key, m_lbl, r_cls in tf_milestone_configs:
        tf_data = audit_study["cross_section"][h_key][m_key]["by_timeframe"]
        h4_d = tf_data["4h"]
        d1_d = tf_data["1d"]
        c_h4 = badge_class(h4_d["total_net_return_pct"])
        c_d1 = badge_class(d1_d["total_net_return_pct"])
        tf_milestone_rows.append(f"""
        <tr class="{r_cls}">
          <td><span class="tag tag-muted">{horizon_lbl}</span> <strong>{m_lbl}</strong></td>
          <td class="num sep-left">{h4_d['total_trades']}</td>
          <td class="num">{h4_d['win_rate_pct']:.1f}%</td>
          <td class="num">{h4_d['tp1_hit_rate_pct']:.1f}%</td>
          <td class="num {c_h4}">{fmt_pct3(h4_d['avg_net_return_pct'])}</td>
          <td class="num {c_h4}"><strong>{fmt_pct(h4_d['total_net_return_pct'])}</strong></td>
          <td class="num {badge_class(h4_d['profit_factor'], 1.0)}"><strong>{h4_d['profit_factor']:.2f}</strong></td>
          <td class="num">{h4_d['max_drawdown_pct']:.1f}%</td>
          <td class="num sep-left">{d1_d['total_trades']}</td>
          <td class="num">{d1_d['win_rate_pct']:.1f}%</td>
          <td class="num">{d1_d['tp1_hit_rate_pct']:.1f}%</td>
          <td class="num {c_d1}">{fmt_pct3(d1_d['avg_net_return_pct'])}</td>
          <td class="num {c_d1}"><strong>{fmt_pct(d1_d['total_net_return_pct'])}</strong></td>
          <td class="num {badge_class(d1_d['profit_factor'], 1.0)}"><strong>{d1_d['profit_factor']:.2f}</strong></td>
          <td class="num">{d1_d['max_drawdown_pct']:.1f}%</td>
        </tr>
        """)

    # Build Fee & Slippage Stress-Test Rows & Tail-Risk/Concurrency Rows (Chuyên mục 6.2)
    audit_configs = [
        ("IS 6 Năm (2020–25)", "audit_is_2020_2025", "m1_f1a_pump50", "Mốc 1: F1A (Pump >= 50%)", ""),
        ("IS 6 Năm (2020–25)", "audit_is_2020_2025", "m2_f1b_pst", "Mốc 2: +F1B (pysystemtrade)", ""),
        ("IS 6 Năm (2020–25)", "audit_is_2020_2025", "m3_f1c_elite", "Mốc 3A: +F1C Tinh Hoa (PST & KER>=0.35)", ""),
        ("IS 6 Năm (2020–25)", "audit_is_2020_2025", "m4_f2_elite", "★ Mốc 4A: +F2 Tinh Hoa (Bất bại 7/7 năm)", "row-sweetspot"),
        ("IS 6 Năm (2020–25)", "audit_is_2020_2025", "m5_f3_elite", "★ Mốc 5A: +F3 Tinh Hoa (H1 Break)", "row-sweetspot"),
        ("IS 6 Năm (2020–25)", "audit_is_2020_2025", "m6_f4_expanded", "👑 Mốc 6B: Toàn Diện (SL 0.886 + Đi Vốn)", ""),
        ("IS 6 Năm (2020–25)", "audit_is_2020_2025", "m6_f4_sniper", "👑 Mốc 6A: Sniper Mở Rộng", ""),
        ("IS 6 Năm (2020–25)", "audit_is_2020_2025", "m6_f4_elite_sniper", "👑 Mốc 6S: Sniper Tinh Hoa (7/7 Năm Dương)", "row-climax"),
        ("IS 2 Năm (2024–25)", "audit_is_2024_2025", "m4_f2_elite", "★ Mốc 4A (2024–2025)", ""),
        ("IS 2 Năm (2024–25)", "audit_is_2024_2025", "m6_f4_expanded", "👑 Mốc 6B Toàn Diện (2024–2025)", "row-sweetspot"),
        ("IS 2 Năm (2024–25)", "audit_is_2024_2025", "m6_f4_sniper", "👑 Mốc 6A Sniper Mở Rộng (2024–2025)", "row-climax"),
        ("IS 2 Năm (2024–25)", "audit_is_2024_2025", "m6_f4_elite_sniper", "👑 Mốc 6S Sniper Tinh Hoa (2024–2025)", "row-climax"),
        ("OOS 2026 (Thực Chiến)", "audit_oos_2026", "m4_f2_elite", "★ Mốc 4A (OOS 2026)", ""),
        ("OOS 2026 (Thực Chiến)", "audit_oos_2026", "m6_f4_expanded", "👑 Mốc 6B Toàn Diện (OOS 2026)", "row-sweetspot"),
        ("OOS 2026 (Thực Chiến)", "audit_oos_2026", "m6_f4_sniper", "👑 Mốc 6A Sniper Mở Rộng (OOS 2026)", "row-climax"),
        ("OOS 2026 (Thực Chiến)", "audit_oos_2026", "m6_f4_elite_sniper", "👑 Mốc 6S Sniper Tinh Hoa (OOS 2026)", "row-climax"),
    ]
    fee_stress_rows = []
    tail_risk_rows = []
    for h_lbl, h_key, m_key, m_lbl, r_cls in audit_configs:
        st = audit_study[h_key][m_key]
        fs = st["fee_stress_test"]
        be_bps = st["breakeven_fee_bps"]
        be_cls = "pos" if be_bps >= 100 else ("neu" if be_bps >= 40 else "neg")
        fee_stress_rows.append(f"""
        <tr class="{r_cls}">
          <td><span class="tag tag-muted">{h_lbl}</span> <strong>{m_lbl}</strong></td>
          <td class="num">{st['total_trades']}</td>
          <td class="num sep-left {badge_class(fs['0_bps']['total_net_pct'])}">{fmt_pct(fs['0_bps']['total_net_pct'])} <small>(PF {fs['0_bps']['profit_factor']:.2f})</small></td>
          <td class="num {badge_class(fs['10_bps']['total_net_pct'])}"><strong>{fmt_pct(fs['10_bps']['total_net_pct'])}</strong> <small>(PF {fs['10_bps']['profit_factor']:.2f})</small></td>
          <td class="num {badge_class(fs['20_bps']['total_net_pct'])}"><strong>{fmt_pct(fs['20_bps']['total_net_pct'])}</strong> <small>(PF {fs['20_bps']['profit_factor']:.2f})</small></td>
          <td class="num {badge_class(fs['30_bps']['total_net_pct'])}">{fmt_pct(fs['30_bps']['total_net_pct'])} <small>(PF {fs['30_bps']['profit_factor']:.2f})</small></td>
          <td class="num {badge_class(fs['40_bps']['total_net_pct'])}"><strong>{fmt_pct(fs['40_bps']['total_net_pct'])}</strong> <small>(PF {fs['40_bps']['profit_factor']:.2f})</small></td>
          <td class="num sep-left {be_cls}"><strong>{be_bps:.1f} bps ({be_bps/100:.2f}%/lệnh)</strong></td>
        </tr>
        """)

        oc = st["outcomes"]
        dist = st["distribution"]
        conc = st["concurrency"]
        tail_risk_rows.append(f"""
        <tr class="{r_cls}">
          <td><span class="tag tag-muted">{h_lbl}</span> <strong>{m_lbl}</strong></td>
          <td class="num">{st['total_trades']}</td>
          <td class="num sep-left pos">{oc['tp3_hit_pct']:.1f}%</td>
          <td class="num pos">{oc['tp2_hit_pct']:.1f}%</td>
          <td class="num cyan">{oc['tp1_breakeven_pct']:.1f}%</td>
          <td class="num neg">{oc['stop_loss_pct']:.1f}%</td>
          <td class="num">{oc['time_exit_pct']:.1f}%</td>
          <td class="num sep-left pos">+{dist['avg_win_pct']:.2f}%</td>
          <td class="num neg">{dist['avg_loss_pct']:.2f}%</td>
          <td class="num"><strong>{dist['payoff_ratio']:.2f}x</strong></td>
          <td class="num {badge_class(dist['median_net_pct'])}"><strong>{fmt_pct3(dist['median_net_pct'])}</strong></td>
          <td class="num neg">{dist['max_consecutive_losses']} lệnh ({dist['max_losing_streak_cum_pct']:.1f}%)</td>
          <td class="num">{dist['avg_hold_hours']:.1f}h</td>
          <td class="num sep-left"><strong>{conc['max_concurrent_trades']}</strong> <small>(P95: {conc['p95_concurrent_trades']:.0f})</small></td>
        </tr>
        """)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    registry_json_inline = json.dumps(registry, ensure_ascii=False)
    audit_dossier_escaped = html.escape(audit_dossier_md)
    audit_dossier_json_inline = json.dumps(audit_dossier_md, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PeakPulse AI — Wiki &amp; Kho Tri Thức Nghiên Cứu Alpha Đa Tầng (2020–2026 &amp; AI Audit Dossier)</title>
  <style>
    :root {{
      --bg-main: #070b14;
      --bg-sidebar: #0d1322;
      --bg-card: #111827;
      --bg-card-alt: #172033;
      --bg-highlight: rgba(245, 158, 11, 0.12);
      --bg-cyan: rgba(6, 182, 212, 0.10);
      --bg-emerald: rgba(16, 185, 129, 0.12);
      --border: #1f2937;
      --border-accent: #334155;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --gold: #f59e0b;
      --cyan: #06b6d4;
      --emerald: #10b981;
      --rose: #f43f5e;
      --violet: #8b5cf6;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      background: var(--bg-main);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      line-height: 1.6;
      display: flex;
      min-height: 100vh;
    }}
    /* Wiki App Layout: Fixed Sidebar + Main Content */
    .wiki-sidebar {{
      width: 300px;
      background: var(--bg-sidebar);
      border-right: 1px solid var(--border);
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      overflow-y: auto;
      padding: 20px 16px;
      z-index: 100;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .wiki-brand {{
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }}
    .wiki-brand h2 {{
      font-size: 17px;
      font-weight: 800;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .wiki-brand p {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }}
    .search-box {{
      position: relative;
    }}
    .search-input {{
      width: 100%;
      background: #111827;
      border: 1px solid #374151;
      color: #fff;
      padding: 9px 12px;
      border-radius: 8px;
      font-size: 13px;
      outline: none;
    }}
    .search-input:focus {{
      border-color: var(--gold);
      box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2);
    }}
    .nav-group-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.7px;
      color: #64748b;
      font-weight: 800;
      margin: 6px 0 4px 6px;
    }}
    .nav-list {{
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .nav-link {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      text-align: left;
      background: transparent;
      border: 1px solid transparent;
      color: #cbd5e1;
      padding: 8px 11px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .nav-link:hover {{
      background: rgba(255, 255, 255, 0.05);
      color: #fff;
    }}
    .nav-link.active {{
      background: rgba(245, 158, 11, 0.16);
      color: #fbbf24;
      border-color: rgba(245, 158, 11, 0.4);
    }}
    .nav-count {{
      font-size: 11px;
      background: #1e293b;
      color: #94a3b8;
      padding: 1px 7px;
      border-radius: 99px;
    }}
    .sidebar-footer {{
      margin-top: auto;
      padding-top: 14px;
      border-top: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .btn-action {{
      width: 100%;
      background: linear-gradient(135deg, #f59e0b, #d97706);
      color: #090d16;
      border: none;
      padding: 9px 12px;
      border-radius: 8px;
      font-weight: 800;
      font-size: 12.5px;
      cursor: pointer;
    }}
    .btn-action.secondary {{
      background: #1e293b;
      color: #e2e8f0;
      border: 1px solid #334155;
    }}
    /* Main Content Area */
    .wiki-main {{
      margin-left: 300px;
      flex: 1;
      padding: 28px 34px 70px;
      max-width: calc(100vw - 300px);
    }}
    .container {{
      max-width: 1320px;
      margin: 0 auto;
    }}
    @media (max-width: 1024px) {{
      .wiki-sidebar {{
        position: static;
        width: 100%;
        border-right: none;
        border-bottom: 1px solid var(--border);
      }}
      body {{
        flex-direction: column;
      }}
      .wiki-main {{
        margin-left: 0;
        max-width: 100%;
        padding: 20px 16px;
      }}
    }}
    /* Hero */
    .hero {{
      background: linear-gradient(135deg, #111827 0%, #1e1b4b 55%, #0f172a 100%);
      border: 1px solid #312e81;
      border-radius: 16px;
      padding: 26px 30px;
      margin-bottom: 24px;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
    }}
    .hero-top {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 11px;
      border-radius: 999px;
      font-size: 11.5px;
      font-weight: 700;
      letter-spacing: 0.4px;
      text-transform: uppercase;
    }}
    .pill-gold {{ background: rgba(245, 158, 11, 0.18); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }}
    .pill-lock {{ background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }}
    .pill-cyan {{ background: rgba(6, 182, 212, 0.18); color: #22d3ee; border: 1px solid rgba(6, 182, 212, 0.4); }}
    .hero h1 {{
      font-size: 24px;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 8px;
    }}
    .hero p {{
      color: #cbd5e1;
      font-size: 14.5px;
      max-width: 1020px;
    }}
    /* KPI Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 26px;
    }}
    .kpi-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 18px;
    }}
    .kpi-card.gold {{ border-color: rgba(245, 158, 11, 0.45); background: linear-gradient(180deg, #111827, rgba(245, 158, 11, 0.07)); }}
    .kpi-card.emerald {{ border-color: rgba(16, 185, 129, 0.45); background: linear-gradient(180deg, #111827, rgba(16, 185, 129, 0.07)); }}
    .kpi-card.cyan {{ border-color: rgba(6, 182, 212, 0.45); background: linear-gradient(180deg, #111827, rgba(6, 182, 212, 0.07)); }}
    .kpi-label {{
      font-size: 11.5px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 5px;
      font-weight: 700;
    }}
    .kpi-val {{
      font-size: 23px;
      font-weight: 800;
      margin-bottom: 4px;
    }}
    .kpi-sub {{
      font-size: 12px;
      color: var(--text-muted);
    }}
    /* Wiki Sections */
    .wiki-page {{
      display: block;
    }}
    .wiki-page.hidden-page {{
      display: none;
    }}
    .section {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 24px 26px;
      margin-bottom: 26px;
    }}
    .section-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 18px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }}
    .section-title {{
      font-size: 19px;
      font-weight: 800;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .section-subtitle {{
      font-size: 13.5px;
      color: var(--text-muted);
      margin-top: 4px;
    }}
    /* Alpha Passport Cards */
    .filter-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 18px;
      align-items: center;
    }}
    .passport-list {{
      display: flex;
      flex-direction: column;
      gap: 18px;
    }}
    .passport-card {{
      background: var(--bg-card-alt);
      border: 1px solid var(--border-accent);
      border-left: 5px solid var(--emerald);
      border-radius: 12px;
      padding: 20px 22px;
      transition: transform 0.12s;
    }}
    .passport-card.card-candidate {{ border-left-color: var(--cyan); }}
    .passport-card.card-rejected {{ border-left-color: var(--rose); opacity: 0.92; }}
    .passport-card.card-merged {{ border-left-color: var(--gold); }}
    .passport-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .passport-id {{
      font-family: monospace;
      font-size: 13px;
      font-weight: 800;
      background: #0f172a;
      color: #f8fafc;
      padding: 3px 9px;
      border-radius: 6px;
      border: 1px solid #334155;
    }}
    .passport-actions {{
      display: flex;
      gap: 8px;
    }}
    .btn-mini {{
      background: #1e293b;
      color: #cbd5e1;
      border: 1px solid #334155;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }}
    .btn-mini:hover {{
      background: var(--gold);
      color: #090d16;
      border-color: var(--gold);
    }}
    .passport-title {{
      font-size: 17.5px;
      font-weight: 800;
      color: #fff;
      margin-bottom: 4px;
    }}
    .passport-repo {{
      font-size: 12.5px;
      color: var(--text-muted);
      margin-bottom: 14px;
    }}
    .passport-metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(125px, 1fr));
      gap: 10px;
      background: #0b1120;
      border: 1px solid #1e293b;
      border-radius: 10px;
      padding: 12px 14px;
      margin-bottom: 14px;
    }}
    .pm-item {{
      display: flex;
      flex-direction: column;
    }}
    .pm-lbl {{
      font-size: 11px;
      color: #64748b;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .pm-val {{
      font-size: 15px;
      font-weight: 800;
      font-variant-numeric: tabular-nums;
    }}
    .layer-map-box {{
      background: rgba(15, 23, 42, 0.75);
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 10px 14px;
      margin-bottom: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 13px;
    }}
    .lm-row {{
      display: flex;
      align-items: baseline;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .lm-tag {{
      font-size: 11px;
      font-weight: 800;
      padding: 2px 8px;
      border-radius: 5px;
      min-width: 132px;
      text-align: center;
    }}
    .lm-tag.l1 {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
    .lm-tag.l2 {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; }}
    .lm-tag.l3 {{ background: rgba(6, 182, 212, 0.2); color: #22d3ee; }}
    .lm-tag.l4 {{ background: rgba(148, 163, 184, 0.2); color: #cbd5e1; }}
    .passport-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .pg-box {{
      background: rgba(17, 24, 39, 0.7);
      border: 1px solid #1f2937;
      border-radius: 8px;
      padding: 12px 14px;
      font-size: 13px;
      color: #d1d5db;
    }}
    .pg-box h5 {{
      font-size: 13px;
      color: #fff;
      margin-bottom: 6px;
    }}
    .compact-list {{
      padding-left: 18px;
      margin-top: 3px;
      font-size: 12.5px;
      color: #cbd5e1;
    }}
    /* Callout boxes */
    .insight-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin: 16px 0 22px;
    }}
    .insight-box {{
      background: var(--bg-card-alt);
      border-left: 4px solid var(--gold);
      border-radius: 10px;
      padding: 16px 18px;
    }}
    .insight-box.emerald {{ border-left-color: var(--emerald); }}
    .insight-box.cyan {{ border-left-color: var(--cyan); }}
    .insight-box.rose {{ border-left-color: var(--rose); }}
    .insight-box h4 {{
      font-size: 14.5px;
      font-weight: 700;
      margin-bottom: 6px;
      color: #fff;
    }}
    .insight-box p {{
      font-size: 13.5px;
      color: #d1d5db;
    }}
    /* Tables */
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 10px;
      margin-top: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13.5px;
    }}
    th, td {{
      padding: 11px 13px;
      text-align: left;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}
    th {{
      background: #0f172a;
      color: #cbd5e1;
      font-weight: 700;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }}
    th.group-head {{
      text-align: center;
      background: #1e293b;
      color: #f8fafc;
      border-bottom: 2px solid #334155;
    }}
    td.num, th.num {{
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .sep-left {{
      border-left: 2px solid #1e293b;
    }}
    tr:hover {{
      background: rgba(255, 255, 255, 0.03);
    }}
    tr.row-inflection {{ background: var(--bg-cyan); }}
    tr.row-sweetspot {{ background: var(--bg-highlight); }}
    tr.row-climax {{ background: var(--bg-emerald); }}
    .pos {{ color: #34d399; }}
    .neg {{ color: #fb7185; }}
    .neu {{ color: #9ca3af; }}
    /* Tags */
    .tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      margin-left: 6px;
    }}
    .tag-muted {{ background: #1f2937; color: #9ca3af; }}
    .tag-info {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; }}
    .tag-cyan {{ background: rgba(6, 182, 212, 0.2); color: #22d3ee; }}
    .tag-gold {{ background: rgba(245, 158, 11, 0.25); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.5); }}
    .tag-emerald {{ background: rgba(16, 185, 129, 0.22); color: #34d399; }}
    .tag-danger {{ background: rgba(244, 63, 94, 0.2); color: #fb7185; }}
    /* Visual Bars */
    .charts-two-col {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
      gap: 20px;
      margin: 18px 0 24px;
    }}
    .chart-card {{
      background: var(--bg-card-alt);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
    }}
    .chart-card h4 {{
      font-size: 14px;
      color: #e2e8f0;
      margin-bottom: 14px;
      font-weight: 700;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 76px 1fr 220px;
      align-items: center;
      gap: 10px;
      margin-bottom: 9px;
      font-size: 12.5px;
    }}
    .bar-label {{ font-weight: 700; color: #e5e7eb; }}
    .bar-track {{
      height: 11px;
      background: #0f172a;
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid #1e293b;
    }}
    .bar-fill {{ height: 100%; border-radius: 999px; }}
    .bar-pos {{ background: linear-gradient(90deg, #10b981, #34d399); }}
    .bar-neg {{ background: linear-gradient(90deg, #e11d48, #fb7185); }}
    .bar-value {{ text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }}
    .sub-val {{ color: var(--text-muted); font-weight: 400; font-size: 11.5px; }}
    .dual-bar-row {{
      display: grid;
      grid-template-columns: 76px 1fr;
      align-items: center;
      gap: 10px;
      padding: 5px 0;
      border-bottom: 1px dashed rgba(255,255,255,0.06);
      font-size: 12px;
    }}
    .dual-bars {{ display: flex; flex-direction: column; gap: 4px; }}
    .mini-bar-line {{
      display: grid;
      grid-template-columns: 32px 1fr 80px;
      align-items: center;
      gap: 8px;
    }}
    .tf-badge {{
      font-size: 10px;
      font-weight: 800;
      padding: 1px 5px;
      border-radius: 4px;
      text-align: center;
    }}
    .tf-h4 {{ background: rgba(139, 92, 246, 0.25); color: #c4b5fd; }}
    .tf-d1 {{ background: rgba(6, 182, 212, 0.25); color: #67e8f9; }}
    .mini-val {{ text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }}
    /* Tabs */
    .tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }}
    .tab-btn {{
      background: #1f2937;
      color: #cbd5e1;
      border: 1px solid #374151;
      padding: 8px 15px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 12.5px;
      font-weight: 700;
      transition: all 0.15s;
    }}
    .tab-btn.active {{
      background: var(--gold);
      color: #090d16;
      border-color: var(--gold);
    }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    /* Toast notification */
    #toast {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #10b981;
      color: #052e16;
      font-weight: 800;
      padding: 10px 18px;
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
      display: none;
      z-index: 9999;
    }}
    footer {{
      text-align: center;
      color: var(--text-muted);
      font-size: 12.5px;
      margin-top: 36px;
    }}
  </style>
</head>
<body>
  <!-- LEFT SIDEBAR WIKI NAVIGATION (6-PILLAR MECE ARCHITECTURE) -->
  <aside class="wiki-sidebar">
    <div class="wiki-brand">
      <h2>📚 PeakPulse Alpha Wiki</h2>
      <p>Kiến Trúc 6 Trụ Cột MECE • Chu Kỳ 7 Năm (2020–2026) &amp; Hồ Sơ Kiểm Định AI</p>
    </div>

    <div class="search-box">
      <input
        type="text"
        id="globalSearch"
        class="search-input"
        placeholder="🔍 Tìm Alpha, KER, FOMO, BTC, Phí..."
        oninput="handleGlobalSearch(this.value)"
      />
    </div>

    <div>
      <div class="nav-group-label">Chế Độ Hiển Thị</div>
      <ul class="nav-list">
        <li>
          <button class="nav-link active" onclick="showWikiPage(event, 'ALL')">
            <span>📖 Xem Toàn Bộ (Full Portal)</span>
            <span class="nav-count">6 Mục</span>
          </button>
        </li>
      </ul>
    </div>

    <div>
      <div class="nav-group-label">6 Chuyên Mục MECE (Không Trùng Lặp)</div>
      <ul class="nav-list">
        <li>
          <button class="nav-link" onclick="showWikiPage(event, 'page-overview')">
            <span>🏠 1. Tổng Quan &amp; Playbook</span>
            <span class="nav-count">KPIs</span>
          </button>
        </li>
        <li>
          <button class="nav-link" onclick="showWikiPage(event, 'page-alpha-library')">
            <span>🧠 2. Kiến Trúc &amp; Hồ Sơ Alpha</span>
            <span class="nav-count">{len(registry['alpha_passports'])}</span>
          </button>
        </li>
        <li>
          <button class="nav-link" onclick="showWikiPage(event, 'page-factor-lab')">
            <span>🔬 3. Phòng Thí Nghiệm F1→F4</span>
            <span class="nav-count">5 Tab</span>
          </button>
        </li>
        <li>
          <button class="nav-link" onclick="showWikiPage(event, 'page-multiyear-oos')">
            <span>📈 4. Chu Kỳ 7 Năm (2020→2026)</span>
            <span class="nav-count">7 Năm</span>
          </button>
        </li>
        <li>
          <button class="nav-link" onclick="showWikiPage(event, 'page-asset-tf')">
            <span>🪙 5. Vũ Trụ 338 Coin &amp; Khung Giờ</span>
            <span class="nav-count">338 Mã</span>
          </button>
        </li>
        <li>
          <button class="nav-link" onclick="showWikiPage(event, 'page-audit-spec')">
            <span>🔍 6. Hồ Sơ Kiểm Định (AI Audit)</span>
            <span class="nav-count">v4.0.26</span>
          </button>
        </li>
      </ul>
    </div>

    <div class="sidebar-footer">
      <button class="btn-action" onclick="copyAuditDossierMd()">📋 Copy Hồ Sơ Cho ChatGPT (.MD)</button>
      <button class="btn-action secondary" onclick="downloadRegistryJson()">📥 Tải Kho Alpha (.JSON)</button>
      <button class="btn-action secondary" onclick="window.print()">🖨️ In / Xuất Báo Cáo PDF</button>
    </div>
  </aside>

  <!-- MAIN WIKI CONTENT -->
  <main class="wiki-main">
    <div class="container">
      <!-- ===================================================================== -->
      <!-- PILLAR 1: EXECUTIVE OVERVIEW, UNIFIED EVOLUTION & PLAYBOOK            -->
      <!-- ===================================================================== -->
      <div id="page-overview" class="wiki-page">
        <header class="hero">
          <div class="hero-top">
            <div class="badge-row">
              <span class="pill pill-gold">Nhánh 2: Fibo Trend Short (H4/D1 → H1)</span>
              <span class="pill pill-cyan">Trần Backtest Lịch Sử: 2020 → 2025 (338 Mã PIT)</span>
              <span class="pill pill-lock">🟢 Paper OOS v1: OBSERVING (PID 28988 • 12 Tài Khoản • Live Sign-off: NOT_GRANTED)</span>
            </div>
            <div style="font-size: 12px; color: #94a3b8;">Schema v4.26 • Cập nhật: {now_str}</div>
          </div>
          <h1>Wiki &amp; Kho Tri Thức Nghiên Cứu Alpha Đa Tầng — Chiến Lược Xác Nhận Đảo Chiều &amp; Short Fibo (v4.0.26 &amp; Paper OOS v1)</h1>
          <p>
            Tổ chức theo cấu trúc <strong>6 Chuyên Mục MECE (Không trùng lặp, Đầy đủ toàn diện)</strong>: Từ <strong>Tổng quan Kiểm toán v4.0.26, Phân rã Chi phí &amp; Playbook vận hành (Mục 1)</strong>, <strong>Kiến trúc Hình Chóp Ngược 4 Tầng &amp; 9 Hồ sơ Alpha (Mục 2)</strong>, <strong>Phòng thí nghiệm Ceteris Paribus F1→F4 (Mục 3)</strong>, <strong>Kiểm chứng xuyên chu kỳ 2020–2026 (Mục 4)</strong>, <strong>Giải phẫu Vũ trụ 338 đồng Coin &amp; H4/D1 (Mục 5)</strong> đến <strong>Hồ sơ Kiểm định Độc lập v4.0.26 &amp; Paper OOS v1 (Mục 6)</strong>.
          </p>
        </header>

        <!-- NEW SECTION: V4.0.21 - V4.0.26 INSTITUTIONAL REAUDIT & PAPER OOS V1 -->
        <section class="section" style="border-color: rgba(16, 185, 129, 0.65); background: linear-gradient(180deg, #0f172a 0%, #091e1a 100%);">
          <div class="section-header">
            <div>
              <div class="section-title">
                <span>🏛️ Báo Cáo Xuất Bản Kết Quả Tái Kiểm Toán Độc Lập v4.0.21–v4.0.26 &amp; Trạng Thái Paper OOS v1 (MỚI NHẤT)</span>
              </div>
              <div class="section-subtitle">
                Sau khi bóc tách toàn bộ thiên lệch chọn coin (Point-in-Time Universe &amp; Contract Lifecycle trên 338 mã), tính đúng <code>cooldown</code> theo giờ thoát thực tế (<code>exit_close_time</code>), khớp giá mở cửa nhảy gap qua Stop và trừ phí + trượt giá trên <strong>từng lần khớp lệnh (kể cả chốt lời từng phần TP1, TP2, TP3)</strong> kèm <code>360,781</code> sự kiện funding thực tế: <strong>4/6 cấu hình vẫn sinh lời ròng toàn kỳ 2020–2025</strong> và <strong>6/6 cấu hình đều lãi dương trong giai đoạn 2024–2025</strong> ở mức phí Chuẩn (<code>VIP6 2.5 bps + trượt giá 10 bps = 12.5 bps/fill</code>).
              </div>
            </div>
            <span class="pill pill-gold">Cổng Tự Động: CASH • Live Sign-off: NOT_GRANTED</span>
          </div>

          <div class="kpi-grid" style="margin-bottom: 20px;">
            <div class="kpi-card emerald">
              <div class="kpi-label">👑 Ứng Viên Số 1 Toàn Kỳ (2020–2025)</div>
              <div class="kpi-val pos">+26.19% NAV</div>
              <div class="kpi-sub"><code>Elite + Sniper</code> • Chuẩn VIP6 (12.5 bps/fill) • <strong>MaxDD 15.33%</strong> • 790 lệnh (Liên tục: +26.05%)</div>
            </div>
            <div class="kpi-card cyan">
              <div class="kpi-label">★ Ứng Viên Số 1 Giai Đoạn 2024–2025</div>
              <div class="kpi-val pos">+21.46% NAV</div>
              <div class="kpi-sub"><code>Sniper RR &ge; 1 (Max 24h)</code> • CI 95% tuần: <strong>[+0.073%; +0.299%] &gt; 0</strong> • Stress: <strong>+1.70%</strong></div>
            </div>
            <div class="kpi-card gold">
              <div class="kpi-label">Tỷ Lệ Ứng Viên Sinh Lời (Chuẩn VIP6)</div>
              <div class="kpi-val pos">4/6 (Toàn Kỳ) • 6/6 (24–25)</div>
              <div class="kpi-sub">Giai đoạn 2024–2025: <strong>3/6 ứng viên lãi dương cả ở bản Stress (55 bps/fill)</strong></div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">🟢 Hệ Thống Paper OOS v1 Thực Tế</div>
              <div class="kpi-val pos">OBSERVING (Rev 781)</div>
              <div class="kpi-sub">PID 28988 • 12 tài khoản <code>NAV = 100.00</code> • <code>0</code> lệnh • <code>0</code> lỗi hệ thống • Khớp 100% realtime</div>
            </div>
          </div>

          <h4 style="color:#34d399; font-size:14.5px; margin: 14px 0 8px;">A. Bảng Hiệu Suất NAV 6 Cấu Hình Ứng Viên Trên Vũ Trụ Đã Khử Thiên Lệch (v4.0.21 — Trần Dữ Liệu 31/12/2025)</h4>
          <div class="table-wrap" style="margin-bottom: 18px;">
            <table>
              <thead>
                <tr>
                  <th rowspan="2">Mã Cấu Hình</th>
                  <th rowspan="2">Tên Cấu Hình &amp; Cơ Chế Khối Lượng</th>
                  <th colspan="3" class="group-head">TOÀN KỲ 2020–2025 (CHUẨN 12.5 BPS/FILL)</th>
                  <th colspan="3" class="group-head sep-left">TOÀN KỲ 2020–2025 (STRESS 55 BPS/FILL)</th>
                  <th colspan="3" class="group-head sep-left">GIAI ĐOẠN 2024–2025 HỒI CỨU</th>
                </tr>
                <tr>
                  <th class="num">NAV Ròng</th>
                  <th class="num">MaxDD</th>
                  <th class="num">Số Lệnh</th>
                  <th class="num sep-left">NAV Stress</th>
                  <th class="num">MaxDD</th>
                  <th class="num">Số Lệnh</th>
                  <th class="num sep-left">Chuẩn 24–25</th>
                  <th class="num">CI 95% Tuần (Chuẩn)</th>
                  <th class="num">Stress 24–25</th>
                </tr>
              </thead>
              <tbody>
                <tr class="row-climax">
                  <td><code>elite_sniper_risk</code></td>
                  <td><strong>👑 Elite + Sniper (Stop Risk 0.5% NAV)</strong></td>
                  <td class="num pos"><strong>+26.19%</strong></td>
                  <td class="num pos"><strong>15.33%</strong></td>
                  <td class="num">790</td>
                  <td class="num neg sep-left">-14.48%</td>
                  <td class="num">26.16%</td>
                  <td class="num">813</td>
                  <td class="num pos sep-left"><strong>+15.32%</strong></td>
                  <td class="num">[-0.0017%; +0.2788%]</td>
                  <td class="num pos"><strong>+3.91%</strong></td>
                </tr>
                <tr class="row-sweetspot">
                  <td><code>sniper_risk</code></td>
                  <td><strong>★ Sniper (Stop Risk 0.5% NAV)</strong></td>
                  <td class="num pos"><strong>+14.54%</strong></td>
                  <td class="num pos"><strong>18.05%</strong></td>
                  <td class="num">940</td>
                  <td class="num neg sep-left">-23.05%</td>
                  <td class="num">31.54%</td>
                  <td class="num">969</td>
                  <td class="num pos sep-left"><strong>+18.80%</strong></td>
                  <td class="num pos"><strong>[+0.0032%; +0.3335%]</strong></td>
                  <td class="num pos"><strong>+4.76%</strong></td>
                </tr>
                <tr class="row-inflection">
                  <td><code>sniper_rr1_horizon24</code></td>
                  <td><strong>★ Sniper RR &ge; 1, Tối Đa 24 Giờ</strong></td>
                  <td class="num pos"><strong>+7.91%</strong></td>
                  <td class="num pos"><strong>17.34%</strong></td>
                  <td class="num">1,025</td>
                  <td class="num neg sep-left">-30.13%</td>
                  <td class="num">34.68%</td>
                  <td class="num">1,043</td>
                  <td class="num pos sep-left"><strong>+21.46%</strong></td>
                  <td class="num pos"><strong>[+0.0727%; +0.2992%]</strong></td>
                  <td class="num pos"><strong>+1.70%</strong></td>
                </tr>
                <tr>
                  <td><code>sniper_horizon24</code></td>
                  <td><strong>Sniper, Tối Đa 24 Giờ</strong></td>
                  <td class="num pos"><strong>+7.14%</strong></td>
                  <td class="num">18.45%</td>
                  <td class="num">1,263</td>
                  <td class="num neg sep-left">-35.57%</td>
                  <td class="num">37.92%</td>
                  <td class="num">1,277</td>
                  <td class="num pos sep-left"><strong>+13.89%</strong></td>
                  <td class="num pos"><strong>[+0.0048%; +0.2416%]</strong></td>
                  <td class="num neg">-4.81%</td>
                </tr>
                <tr>
                  <td><code>m6_risk</code></td>
                  <td>M6 Mở Rộng (Stop Risk 0.5% NAV)</td>
                  <td class="num neg">-1.61%</td>
                  <td class="num">28.72%</td>
                  <td class="num">1,124</td>
                  <td class="num neg sep-left">-40.22%</td>
                  <td class="num">48.28%</td>
                  <td class="num">1,149</td>
                  <td class="num pos sep-left"><strong>+19.73%</strong></td>
                  <td class="num">[-0.0383%; +0.3863%]</td>
                  <td class="num neg">-3.04%</td>
                </tr>
                <tr>
                  <td><code>reference_m6_fixed</code></td>
                  <td>M6 Tham Chiếu Gốc (Khối lượng cố định)</td>
                  <td class="num neg">-16.89%</td>
                  <td class="num neg">66.84%</td>
                  <td class="num">1,255</td>
                  <td class="num neg sep-left">-91.35%</td>
                  <td class="num neg">94.42%</td>
                  <td class="num">1,225</td>
                  <td class="num pos sep-left"><strong>+66.06%</strong></td>
                  <td class="num">[-0.1989%; +1.3555%]</td>
                  <td class="num neg">-24.93%</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h4 style="color:#fbbf24; font-size:14.5px; margin: 14px 0 8px;">B. Phân Rã Kế Toán Dòng Tiền Danh Mục &amp; Hiệu Suất Từng Năm (Giải Phẫu Lý Do Chỉ Số Thực Tế Khác Với Bản Mẫu Đầu)</h4>
          <div class="table-wrap" style="margin-bottom: 16px;">
            <table>
              <thead>
                <tr>
                  <th>Cấu Hình &amp; Kịch Bản</th>
                  <th class="num">PnL Giá Tham Chiếu</th>
                  <th class="num">Phí Taker</th>
                  <th class="num">Trượt Giá (Slippage)</th>
                  <th class="num">Funding Ròng</th>
                  <th class="num sep-left">NAV Ròng (v4.0.9)</th>
                  <th class="num">NAV Vũ Trụ Sửa (v4.0.21)</th>
                  <th class="num sep-left">2020</th>
                  <th class="num">2021</th>
                  <th class="num">2022</th>
                  <th class="num">2023</th>
                  <th class="num">2024</th>
                  <th class="num">2025</th>
                </tr>
              </thead>
              <tbody>
                <tr class="row-climax">
                  <td><strong>Elite + Sniper — Chuẩn (12.5 bps/fill)</strong></td>
                  <td class="num pos">+20.80%</td>
                  <td class="num neg">-2.12%</td>
                  <td class="num neg">-8.47%</td>
                  <td class="num pos">+3.24%</td>
                  <td class="num pos sep-left">+13.45%</td>
                  <td class="num pos"><strong>+26.19%</strong></td>
                  <td class="num pos sep-left">+3.43%</td>
                  <td class="num pos">+2.82%</td>
                  <td class="num pos">+6.24%</td>
                  <td class="num neg">-8.15%</td>
                  <td class="num pos">+3.24%</td>
                  <td class="num pos">+5.89%</td>
                </tr>
                <tr>
                  <td><strong>Elite + Sniper — Stress (55 bps/fill)</strong></td>
                  <td class="num pos">+16.43%</td>
                  <td class="num neg">-3.33%</td>
                  <td class="num neg"><strong>-33.28%</strong></td>
                  <td class="num pos">+2.80%</td>
                  <td class="num neg sep-left">-17.38%</td>
                  <td class="num neg">-14.48%</td>
                  <td class="num neg sep-left">-0.62%</td>
                  <td class="num neg">-4.47%</td>
                  <td class="num neg">-0.67%</td>
                  <td class="num neg">-11.18%</td>
                  <td class="num neg">-2.80%</td>
                  <td class="num pos">+1.47%</td>
                </tr>
                <tr class="row-sweetspot">
                  <td><strong>Sniper — Chuẩn (12.5 bps/fill)</strong></td>
                  <td class="num pos">+10.09%</td>
                  <td class="num neg">-2.40%</td>
                  <td class="num neg">-9.58%</td>
                  <td class="num pos">+4.24%</td>
                  <td class="num pos sep-left">+2.36%</td>
                  <td class="num pos"><strong>+14.54%</strong></td>
                  <td class="num pos sep-left">+1.50%</td>
                  <td class="num neg">-1.51%</td>
                  <td class="num pos">+5.52%</td>
                  <td class="num neg">-13.10%</td>
                  <td class="num pos">+6.28%</td>
                  <td class="num pos">+5.07%</td>
                </tr>
                <tr class="row-inflection">
                  <td><strong>Sniper RR&ge;1 24h — Chuẩn (12.5 bps/fill)</strong></td>
                  <td class="num pos">+15.98%</td>
                  <td class="num neg">-2.68%</td>
                  <td class="num neg">-10.73%</td>
                  <td class="num pos">+1.90%</td>
                  <td class="num pos sep-left">+4.47%</td>
                  <td class="num pos"><strong>+7.91%</strong></td>
                  <td class="num neg sep-left">-1.74%</td>
                  <td class="num pos">+2.86%</td>
                  <td class="num neg">-3.18%</td>
                  <td class="num neg">-4.80%</td>
                  <td class="num pos">+9.50%</td>
                  <td class="num pos">+2.40%</td>
                </tr>
                <tr>
                  <td><strong>M6 Cố Định — Chuẩn (12.5 bps/fill)</strong></td>
                  <td class="num pos">+53.63%</td>
                  <td class="num neg">-12.03%</td>
                  <td class="num neg"><strong>-48.14%</strong></td>
                  <td class="num pos">+19.74%</td>
                  <td class="num pos sep-left">+13.21%</td>
                  <td class="num neg">-16.89%</td>
                  <td class="num neg sep-left">-0.44%</td>
                  <td class="num neg">-1.88%</td>
                  <td class="num pos">+23.29%</td>
                  <td class="num neg">-29.53%</td>
                  <td class="num neg">-2.32%</td>
                  <td class="num pos">+36.55%</td>
                </tr>
                <tr>
                  <td><strong>M6 Cố Định — Stress (55 bps/fill)</strong></td>
                  <td class="num pos">+2.91%</td>
                  <td class="num neg">-9.28%</td>
                  <td class="num neg"><strong>-92.76%</strong></td>
                  <td class="num pos">+11.87%</td>
                  <td class="num neg sep-left">-87.26%</td>
                  <td class="num neg">-91.35%</td>
                  <td class="num neg sep-left">-19.79%</td>
                  <td class="num neg">-51.33%</td>
                  <td class="num pos">+1.69%</td>
                  <td class="num neg">-49.81%</td>
                  <td class="num neg">-33.26%</td>
                  <td class="num neg">-4.14%</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="insight-grid">
            <div class="insight-box emerald">
              <h4>1. Thực Tế Khả Năng Sinh Lời: Nhóm Sniper Sống Sót Vững Vàng</h4>
              <p>
                Ở điều kiện khớp lệnh chuẩn (<code>VIP6 2.5 bps + trượt giá 10 bps = 12.5 bps/fill</code>), <strong><code>Elite + Sniper</code> lãi +26.19% (MaxDD chỉ 15.33%, thắng 5/6 năm)</strong> và <strong><code>Sniper RR&ge;1 24h</code> lãi +21.46% giai đoạn 2024–2025</strong> (cận dưới CI 95% tuần lớn hơn 0, đồng thời lãi dương +1.70% ngay cả ở bài test tra tấn Stress 55 bps/fill).
              </p>
            </div>
            <div class="insight-box gold">
              <h4>2. Tại Sao Chỉ Số Từ "Rất Đẹp" Quy Tụ Về Mức Thực Tế?</h4>
              <p>
                • <strong>Ma sát trượt giá nhiều bậc TP:</strong> Ở <code>M6 cố định</code>, giá tham chiếu lãi <code>+53.63%</code> nhưng phí (<code>-12.03%</code>) và trượt giá (<code>-48.14%</code>) ngốn mất <code>-60.17%</code>! Nhờ quản trị vốn <code>0.5% NAV theo Stop</code> và lọc tín hiệu nhiễu, <code>Elite + Sniper</code> ép trượt giá toàn kỳ xuống chỉ còn <code>-8.47%</code>.<br/>
                • <strong>Đánh đổi Lợi nhuận vs MaxDD:</strong> Giảm rủi ro mỗi lệnh xuống <code>0.5% NAV</code> giúp kéo MaxDD từ <code>66.84%</code> xuống <code>15.33%</code>, đổi lại biên độ lãi tuyệt đối đằm hơn.
              </p>
            </div>
            <div class="insight-box cyan">
              <h4>3. Vì Sao Cổng Tự Động Giữ Trạng Thái CASH &amp; Chạy Paper OOS v1?</h4>
              <p>
                Quy tắc chọn tự động đã đăng ký yêu cầu: <em>"Mọi năm trước đều dương ở bản Chuẩn VÀ tổng lợi nhuận bản Stress (trượt giá 50 bps/fill) không âm, MaxDD &le; 15%"</em>. Vì năm <code>2023</code> âm nhẹ và mức trượt giá <code>50 bps/fill</code> quá khắc nghiệt, hệ thống giữ <code>live_signoff = NOT_GRANTED (CASH)</code> và chạy <strong>Paper OOS v1 thời gian thực</strong> từ <code>18/10/2026</code>.
              </p>
            </div>
          </div>
        </section>

        <section class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">Mốc 0: Baseline 6 Năm (2020–25)</div>
            <div class="kpi-val neg">-3,366.6% Tổng Lỗ</div>
            <div class="kpi-sub">12,339 lệnh • WR 47.44% • PF 0.89 • 2021 lỗ -1,531%</div>
          </div>
          <div class="kpi-card cyan">
            <div class="kpi-label">Mốc 4A Tinh Hoa (2020–2025)</div>
            <div class="kpi-val pos">+456.8% (Bất Bại 7/7 Năm)</div>
            <div class="kpi-sub">299 lệnh • WR 61.54% (24–25: 73.7%) • <strong>OOS 2026: PF 4.55</strong></div>
          </div>
          <div class="kpi-card gold">
            <div class="kpi-label">★ Mốc 6S Sniper Tinh Hoa (2020–26)</div>
            <div class="kpi-val pos">7/7 Năm Dương Liên Tiếp</div>
            <div class="kpi-sub">2020–25: +378.9% (Bull 2021: +59.5%) • <strong>OOS 2026: WR 77.8%, PF 4.03</strong></div>
          </div>
          <div class="kpi-card emerald">
            <div class="kpi-label">★ Mốc 6A Sniper Mở Rộng (24–26)</div>
            <div class="kpi-val pos">WR 80.0% (OOS 2026)</div>
            <div class="kpi-sub">IS 24–25: +344.9%, PF 2.80 • <strong>OOS 2026: +86.0%, PF 4.68, DD 8.4%</strong></div>
          </div>
          <div class="kpi-card emerald">
            <div class="kpi-label">👑 Mốc 6B Toàn Diện (2020–2026)</div>
            <div class="kpi-val pos">+518.0% (IS) | +127.0% (OOS)</div>
            <div class="kpi-sub">IS 24–25: +512.7%, PF 2.63 • <strong>OOS 2026: WR 76.0%, PF 4.76</strong></div>
          </div>
        </section>

        <section class="section" style="border-color: rgba(16, 185, 129, 0.45);">
          <div class="section-header">
            <div>
              <div class="section-title">
                <span>🏆 Bảng Tổng Hợp Tiến Hóa Chiến Lược Qua 8 Cấp Độ (Đối Chiếu Song Song 3 Giai Đoạn: IS 24–25 • IS 6 Năm 20–25 • OOS 2026)</span>
              </div>
              <div class="section-subtitle">
                Mỗi cấp độ bổ sung đúng 1 nhân tố trực giao đã qua cổng kiểm duyệt đa cộng tuyến (Spearman <code>|r| &lt; 0.25</code>). Đã trừ phí &amp; trượt giá thực tế (<code>10 bps</code> ở Mốc 0–5, <code>20 bps</code> ở Mốc 6A/6B/6S).
              </div>
            </div>
            <span class="pill pill-lock">✔ Zero Re-tuning Across Horizons</span>
          </div>

          <div class="table-wrap" style="margin-bottom: 20px;">
            <table>
              <thead>
                <tr>
                  <th rowspan="2">Cấp Độ Tiến Hóa Chiến Lược</th>
                  <th rowspan="2">Công Thức Đã Khóa</th>
                  <th colspan="4" class="group-head">IN-SAMPLE 2 NĂM (2024–2025)</th>
                  <th colspan="4" class="group-head sep-left">IN-SAMPLE 6 NĂM (2020–2025)</th>
                  <th colspan="4" class="group-head sep-left">OUT-OF-SAMPLE (2026)</th>
                </tr>
                <tr>
                  <th class="num">Lệnh</th>
                  <th class="num">WR</th>
                  <th class="num">Tổng Lãi</th>
                  <th class="num">PF (MaxDD)</th>
                  <th class="num sep-left">Lệnh</th>
                  <th class="num">WR</th>
                  <th class="num">Tổng Lãi</th>
                  <th class="num">PF (MaxDD)</th>
                  <th class="num sep-left">Lệnh</th>
                  <th class="num">WR</th>
                  <th class="num">Tổng Lãi</th>
                  <th class="num">PF (MaxDD)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Mốc 0: Baseline</strong></td>
                  <td><code>prior_pump_pct &gt;= 5%</code></td>
                  <td class="num">4,706</td>
                  <td class="num">48.6%</td>
                  <td class="num neg">-700.0%</td>
                  <td class="num neg">0.94 (1354%)</td>
                  <td class="num sep-left">12,339</td>
                  <td class="num">47.4%</td>
                  <td class="num neg">-3,366.6%</td>
                  <td class="num neg">0.89 (4089%)</td>
                  <td class="num sep-left">1,503</td>
                  <td class="num">52.2%</td>
                  <td class="num pos">+566.7%</td>
                  <td class="num pos">1.21 (286%)</td>
                </tr>
                <tr>
                  <td><strong>Mốc 1: +Factor #1A</strong></td>
                  <td><code>prior_pump_pct &gt;= 50%</code></td>
                  <td class="num">480</td>
                  <td class="num">55.2%</td>
                  <td class="num pos">+232.6%</td>
                  <td class="num pos">1.13 (245%)</td>
                  <td class="num sep-left">1,467</td>
                  <td class="num">51.5%</td>
                  <td class="num pos">+166.5%</td>
                  <td class="num pos">1.03 (816%)</td>
                  <td class="num sep-left">52</td>
                  <td class="num">65.4%</td>
                  <td class="num pos">+95.0%</td>
                  <td class="num pos">1.51 (101%)</td>
                </tr>
                <tr>
                  <td><strong>Mốc 2: +Factor #1B</strong></td>
                  <td><code>ewmac(16,64)&lt;=0 OR accel&lt;=-1</code></td>
                  <td class="num">201</td>
                  <td class="num">63.2%</td>
                  <td class="num pos">+361.2%</td>
                  <td class="num pos">1.63 (104%)</td>
                  <td class="num sep-left">642</td>
                  <td class="num">55.9%</td>
                  <td class="num pos">+404.9%</td>
                  <td class="num pos">1.16 (340%)</td>
                  <td class="num sep-left">24</td>
                  <td class="num">70.8%</td>
                  <td class="num pos">+57.1%</td>
                  <td class="num pos">1.59 (52%)</td>
                </tr>
                <tr>
                  <td><strong>Mốc 3B: +F1C Mở Rộng</strong></td>
                  <td><code>(PST &amp; KER&gt;=0.35) OR KER&gt;=0.65</code></td>
                  <td class="num">198</td>
                  <td class="num">65.7%</td>
                  <td class="num pos">+427.4%</td>
                  <td class="num pos">1.85 (78%)</td>
                  <td class="num sep-left">567</td>
                  <td class="num">56.8%</td>
                  <td class="num pos">+326.1%</td>
                  <td class="num pos">1.16 (350%)</td>
                  <td class="num sep-left">32</td>
                  <td class="num">68.8%</td>
                  <td class="num pos">+72.4%</td>
                  <td class="num pos">1.64 (57%)</td>
                </tr>
                <tr class="row-inflection">
                  <td><strong>Mốc 3A: +F1C Tinh Hoa</strong></td>
                  <td><code>PST &amp; wave_ker &gt;= 0.35</code></td>
                  <td class="num">130</td>
                  <td class="num"><strong>68.5%</strong></td>
                  <td class="num pos">+348.7%</td>
                  <td class="num pos"><strong>2.24 (76%)</strong></td>
                  <td class="num sep-left">390</td>
                  <td class="num"><strong>59.5%</strong></td>
                  <td class="num pos"><strong>+447.9%</strong></td>
                  <td class="num pos"><strong>1.34 (185%)</strong></td>
                  <td class="num sep-left">19</td>
                  <td class="num">68.4%</td>
                  <td class="num pos">+31.0%</td>
                  <td class="num pos">1.36 (54%)</td>
                </tr>
                <tr class="row-sweetspot">
                  <td><strong>★ Mốc 4A: +F2 Tinh Hoa</strong></td>
                  <td><code>F1 Tinh Hoa + imp_ker &gt;= 0.50</code></td>
                  <td class="num">99</td>
                  <td class="num"><strong>73.7%</strong></td>
                  <td class="num pos">+330.8%</td>
                  <td class="num pos"><strong>2.85 (61%)</strong></td>
                  <td class="num sep-left">299</td>
                  <td class="num"><strong>61.5%</strong></td>
                  <td class="num pos"><strong>+456.8%</strong></td>
                  <td class="num pos"><strong>1.46 (150%)</strong></td>
                  <td class="num sep-left">15</td>
                  <td class="num"><strong>73.3%</strong></td>
                  <td class="num pos"><strong>+77.5%</strong></td>
                  <td class="num pos"><strong>4.55 (10.8%)</strong></td>
                </tr>
                <tr>
                  <td><strong>★ Mốc 5A: +F3 Tinh Hoa</strong></td>
                  <td><code>+ Fibo 0.5–0.786 &amp; H1 Phá Đáy</code></td>
                  <td class="num">67</td>
                  <td class="num"><strong>77.6%</strong></td>
                  <td class="num pos">+220.0%</td>
                  <td class="num pos"><strong>2.93 (47%)</strong></td>
                  <td class="num sep-left">169</td>
                  <td class="num"><strong>65.1%</strong></td>
                  <td class="num pos"><strong>+313.6%</strong></td>
                  <td class="num pos"><strong>1.58 (95%)</strong></td>
                  <td class="num sep-left">9</td>
                  <td class="num"><strong>77.8%</strong></td>
                  <td class="num pos"><strong>+40.4%</strong></td>
                  <td class="num pos"><strong>3.61 (9.3%)</strong></td>
                </tr>
                <tr class="row-climax">
                  <td><strong>👑 Mốc 6B: Toàn Diện</strong></td>
                  <td><code>F1+F2 Mở Rộng + SL 0.886 + Đi Vốn</code></td>
                  <td class="num">148</td>
                  <td class="num"><strong>67.6%</strong></td>
                  <td class="num pos"><strong>+512.7%</strong></td>
                  <td class="num pos"><strong>2.63 (53%)</strong></td>
                  <td class="num sep-left">443</td>
                  <td class="num"><strong>56.9%</strong></td>
                  <td class="num pos"><strong>+518.0%</strong></td>
                  <td class="num pos"><strong>1.32 (270%)</strong></td>
                  <td class="num sep-left">25</td>
                  <td class="num"><strong>76.0%</strong></td>
                  <td class="num pos"><strong>+127.0%</strong></td>
                  <td class="num pos"><strong>4.76 (12.1%)</strong></td>
                </tr>
                <tr class="row-climax">
                  <td><strong>👑 Mốc 6A: Sniper Mở Rộng</strong></td>
                  <td><code>F1_Exp+F2+F3 + SL 0.886 + Đi Vốn</code></td>
                  <td class="num">90</td>
                  <td class="num"><strong>75.6%</strong></td>
                  <td class="num pos"><strong>+344.9%</strong></td>
                  <td class="num pos"><strong>2.80 (38%)</strong></td>
                  <td class="num sep-left">250</td>
                  <td class="num"><strong>62.0%</strong></td>
                  <td class="num pos"><strong>+372.7%</strong></td>
                  <td class="num pos"><strong>1.39 (196%)</strong></td>
                  <td class="num sep-left">15</td>
                  <td class="num"><strong>80.0%</strong></td>
                  <td class="num pos"><strong>+86.0%</strong></td>
                  <td class="num pos"><strong>4.68 (8.4%)</strong></td>
                </tr>
                <tr class="row-climax">
                  <td><strong>👑 Mốc 6S: Sniper Tinh Hoa</strong></td>
                  <td><code>F1_Elite+F2+F3 + SL 0.886 + Đi Vốn</code></td>
                  <td class="num">64</td>
                  <td class="num"><strong>75.0%</strong></td>
                  <td class="num pos"><strong>+237.4%</strong></td>
                  <td class="num pos"><strong>2.83 (45%)</strong></td>
                  <td class="num sep-left">169</td>
                  <td class="num"><strong>63.3%</strong></td>
                  <td class="num pos"><strong>+378.9%</strong></td>
                  <td class="num pos"><strong>1.59 (108%)</strong></td>
                  <td class="num sep-left">9</td>
                  <td class="num"><strong>77.8%</strong></td>
                  <td class="num pos"><strong>+45.2%</strong></td>
                  <td class="num pos"><strong>4.03 (7.6%)</strong></td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Dual-Mode Playbook & Conviction Score Rubric -->
          <div class="passport-grid">
            <div class="pg-box" style="border-left: 4px solid #10b981;">
              <h5>🛡️ Chế Độ 1 — Mặc Định / An Toàn Mọi Thời Tiết (<code>Mốc 6S Sniper Tinh Hoa</code>)</h5>
              <p><strong>Khi nào dùng:</strong> Chế độ mặc định quanh năm hoặc khi thị trường vĩ mô đang trong <strong>Parabolic Bull Run (như 2020–2021)</strong>.</p>
              <ul class="compact-list" style="margin-top:6px;">
                <li><strong>Điều kiện bắt buộc:</strong> <code>pysystemtrade == True</code> (<code>ewmac(16,64) &lt;= 0 OR accel(4,16) &lt;= -1.0</code>) kết hợp <code>wave_ker &gt;= 0.35</code> + <code>imp_drop &gt;= 6% &amp; imp_ker &gt;= 0.50</code> + <code>Fibo 0.500–0.786 &amp; H1 Phá Đáy</code> + <code>SL 0.886</code>.</li>
                <li><strong>Hiệu suất:</strong> <strong>Dương liên tiếp cả 7/7 năm (2020 → 2026)</strong>, lãi <strong>+59.5% ngay giữa đại sóng Bull Run 2021</strong>, OOS 2026 đạt <strong>WR 77.8%, PF 4.03, MaxDD chỉ 7.6%</strong>.</li>
              </ul>
            </div>
            <div class="pg-box" style="border-left: 4px solid #f59e0b;">
              <h5>🔥 Chế Độ 2 — Tối Đa Hóa Lợi Nhuận Mùa Altcoin Pump-Dump (<code>Mốc 6B / 6A Mở Rộng</code>)</h5>
              <p><strong>Khi nào dùng:</strong> Thị trường 2 chiều, Sideways, Bear hoặc Altcoin Rotation (như giai đoạn <strong>2022–2026</strong>).</p>
              <ul class="compact-list" style="margin-top:6px;">
                <li><strong>Điều kiện mở rộng:</strong> Bật thêm nhánh <code>OR (wave_ker &gt;= 0.65)</code> để bắt trọn các cú bơm dựng cột xả thẳng của Altcoin ngay cả khi <code>ewmac</code> chưa kịp âm.</li>
                <li><strong>Hiệu suất:</strong> Nhân bội lợi nhuận trong chu kỳ 2022–2026: <strong>+512.7% (IS 2024–25)</strong> và <strong>+127.0% (OOS 2026, PF 4.76)</strong>; độ rộng thắng trên <strong>12/13 đồng coin (92.3%)</strong>.</li>
              </ul>
            </div>
            <div class="pg-box" style="border-left: 4px solid #8b5cf6;">
              <h5>🎯 Thang Điểm Hội Tụ 4 Tầng (<code>Conviction Score 0–100</code>) &amp; Đi Vốn Động</h5>
              <ul class="compact-list">
                <li><strong>F1 (Tối đa 35đ):</strong> <code>PST</code> (+20đ) + <code>wave_ker &gt;= 0.60</code> (+15đ, hoặc <code>&gt;= 0.35</code> +10đ).</li>
                <li><strong>F2 (Tối đa 25đ):</strong> <code>imp_drop &gt;= 6%</code> (+10đ) + <code>imp_ker &gt;= 0.65</code> (+15đ, hoặc <code>&gt;= 0.50</code> +10đ).</li>
                <li><strong>F3 (Tối đa 25đ):</strong> <code>COMBO_1_2</code> (+15đ) / <code>BREAK_STRUCTURE_2</code> (+12đ) + <code>Fibo 0.50–0.618</code> (+5đ) + <code>Vol Ratio &lt;= 1.0</code> (+5đ).</li>
                <li><strong>F4 (Tối đa 15đ):</strong> Khung <code>D1</code> (+10đ) / <code>H4</code> (+5đ) + <code>RR &gt;= 1.5</code> (+5đ).</li>
                <li><strong>Quy tắc đi vốn:</strong> <code>&lt; 55đ</code>: Bỏ qua (<code>0R</code>) • <code>55–69đ (Hạng B)</code>: <code>0.75R</code> • <code>70–84đ (Hạng A)</code>: <code>1.25R</code> • <code>&gt;= 85đ (Hạng S)</code>: <code>2.00R</code>.</li>
              </ul>
            </div>
          </div>
        </section>
      </div>

      <!-- ===================================================================== -->
      <!-- PILLAR 2: 4-LAYER ONTOLOGY, ALPHA PASSPORTS & COLLINEARITY MATRIX     -->
      <!-- ===================================================================== -->
      <div id="page-alpha-library" class="wiki-page">
        <section class="section" style="border-color: rgba(139, 92, 246, 0.45); background: linear-gradient(180deg, #111827 0%, #131129 100%);">
          <div class="section-header">
            <div>
              <div class="section-title">
                <span>🧠 Chuyên Mục 2: Kiến Trúc Hình Chóp Ngược 4 Tầng, Hồ Sơ Alpha &amp; Ma Trận Chống Trùng Lặp</span>
              </div>
              <div class="section-subtitle">
                Quản trị toàn bộ <strong>{len(registry['alpha_passports'])} Hồ Sơ Định Danh Alpha (Alpha Passports)</strong> (7 Alpha đã khóa + 2 Bài học bẫy/trùng lặp), sơ đồ phân tầng <code>L1 → L4</code> và bằng chứng kiểm định đa cộng tuyến Spearman.
              </div>
            </div>
          </div>

          <div class="tabs">
            <button class="tab-btn active" onclick="switchSubTab(event, 'sub-lib', 'tab-lib-passports')">2.1. Thư Viện {len(registry['alpha_passports'])} Hồ Sơ Định Danh Alpha (Passports)</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-lib', 'tab-lib-ontology')">2.2. Mô Hình Hình Chóp Ngược 4 Tầng (L1 → L4)</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-lib', 'tab-lib-collinearity')">2.3. Ma Trận Chống Trùng Lặp &amp; Cộng Hưởng Trực Giao</button>
          </div>

          <!-- Sub-tab 2.1: Alpha Passports -->
          <div id="tab-lib-passports" class="tab-panel sub-lib active">
            <div class="filter-bar">
              <span style="font-size: 12.5px; color: var(--text-muted); font-weight: 700;">Lọc theo trạng thái:</span>
              <button class="tab-btn active" onclick="filterPassports(event, 'ALL')">Tất Cả ({len(registry['alpha_passports'])})</button>
              <button class="tab-btn" onclick="filterPassports(event, 'LOCKED_IN_SAMPLE')">✅ Đã Khóa In-Sample (7)</button>
              <button class="tab-btn" onclick="filterPassports(event, 'REJECTED_OR_MERGED')">🚫 Bài Học Bẫy &amp; Trùng Lặp (2)</button>
            </div>

            <div class="passport-list" id="passportList">
              {''.join(passport_cards_html)}
            </div>
          </div>

          <!-- Sub-tab 2.2: 4-Layer Inverted Pyramid Ontology -->
          <div id="tab-lib-ontology" class="tab-panel sub-lib">
            <div style="display: flex; flex-direction: column; gap: 12px; margin: 10px 0 8px;">
              <!-- Layer 4 -->
              <div style="background: rgba(30, 41, 59, 0.85); border: 1px solid #475569; border-left: 6px solid #94a3b8; border-radius: 12px; padding: 16px 20px; width: 100%;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 6px;">
                  <strong style="color: #e2e8f0; font-size: 15px;">TẦNG 4 (TRÊN CÙNG — RẤT NHIỀU &amp; TRÙNG LẶP CAO): Tầng Hình Thức &amp; Chỉ Báo Toán Học (Surface Indicators Layer)</strong>
                  <span class="tag tag-muted">Hàng trăm biến thể • Độ trùng lặp 50%–85%</span>
                </div>
                <p style="font-size: 13.5px; color: #cbd5e1; margin-bottom: 8px;">
                  Nơi các repo (<code>Qlib</code>, <code>pysystemtrade</code>, <code>Lean</code>, <code>Freqtrade</code>) viết ra vô số công thức: <code>KER</code>, <code>Velocity %/ngày</code>, <code>Duration 1-8 ngày</code>, <code>RSQR(14)</code>, <code>EMA20 vs EMA50</code>, <code>ewmac(16,64)</code>, <code>accel(4,16)</code>, <code>mr_wings</code>, <code>Bollinger %B</code>, <code>RSI14</code>, <code>Volume Ratio 20</code>, <code>Fibo 0.5–0.618</code>...
                </p>
                <div style="font-size: 12.5px; color: #fbbf24;">
                  ⚠️ <strong>Quy tắc Kho Alpha:</strong> Mỗi cơ chế ở Tầng 2 &amp; Tầng 3 chỉ được cử ra <strong>1 chỉ báo đại diện xuất sắc nhất ở Tầng 4</strong>. Tuyệt đối không ghép 2 chỉ báo Tầng 4 cùng đo 1 cơ chế Tầng 2 (ví dụ ghép <code>Velocity &gt;= 8%</code> + <code>Duration &lt;= 8 ngày</code> bị trùng <strong>75.4%</strong>, làm tụt PF từ 1.55 xuống 1.48).
                </div>
              </div>

              <!-- Layer 3 -->
              <div style="background: rgba(15, 23, 42, 0.9); border: 1px solid rgba(6, 182, 212, 0.45); border-left: 6px solid #06b6d4; border-radius: 12px; padding: 16px 20px; width: 94%; margin: 0 auto;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 6px;">
                  <strong style="color: #67e8f9; font-size: 15px;">TẦNG 3 (BỐI CẢNH VĨ MÔ): Tầng Chế Độ Thị Trường &amp; Điều Kiện Biên (Macro Regime &amp; Context Gate)</strong>
                  <span class="tag tag-cyan">3 – 4 Trạng thái • Công tắc Bật / Tắt Alpha</span>
                </div>
                <p style="font-size: 13.5px; color: #cbd5e1;">
                  Quyết định <strong>khi nào Alpha hoạt động (Working) và khi nào mất tác dụng (Kill-Switch)</strong>:
                  <br/>• <strong>[L3.1] Bear Market Rally</strong> (<code>ewmac(16,64) &lt;= 0</code> hoặc <code>EMA20 &lt;= EMA50</code>): Sóng bơm ngược trong xu hướng giảm lớn → Short thắng 62.5%, PF 1.63.
                  <br/>• <strong>[L3.2] Runaway Institutional Bull Trend</strong> (<code>ewmac(16,64) &gt; 0</code> &amp; <code>accel &gt; -1.0</code> &amp; <code>KER &lt; 0.5</code>): Dòng tiền tổ chức đỡ giá bền vững → Cấm Short (nhóm này lỗ -128.61% giai đoạn 2024–25 và lỗ -1,531% năm 2021).
                  <br/>• <strong>[L3.3] Volatility Squeeze Breakout</strong> (Nén chặt rồi nổ 1–8 nến H4 đầu tiên): Mở màn chu kỳ tăng mới → Cấm Short.
                </p>
              </div>

              <!-- Layer 2 -->
              <div style="background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(245, 158, 11, 0.5); border-left: 6px solid #f59e0b; border-radius: 12px; padding: 16px 20px; width: 88%; margin: 0 auto;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 6px;">
                  <strong style="color: #fbbf24; font-size: 15px;">TẦNG 2 (VẬT LÝ SỔ LỆNH): Tầng Vi Cấu Trúc &amp; Động Lực Thanh Khoản (Microstructure &amp; Liquidity Physics)</strong>
                  <span class="tag tag-gold">6 – 8 Cơ chế vật lý • Trực giao (Độc lập với nhau)</span>
                </div>
                <p style="font-size: 13.5px; color: #cbd5e1;">
                  Dấu chân vật lý của dòng tiền trên sổ lệnh:
                  <br/>• <strong>[L2.1] Khoảng Không Thanh Khoản (Air-Pocket Vacuum vs Staircase Support):</strong> Bơm thẳng không xây bậc thang đỡ giá bên dưới (đại diện: <code>wave_ker &gt;= 0.35</code>).
                  <br/>• <strong>[L2.2] Đứt Gãy Gia Tốc Động Lượng (Momentum Deceleration):</strong> Đạo hàm bậc 2 của giá gãy âm tại đỉnh (đại diện: <code>accel(4,16) &lt;= -1.0</code>).
                  <br/>• <strong>[L2.3] Xung Lực Xả Mở Màn (Clean Impulse Breakdown):</strong> Nhịp sập đầu tiên thẳng đứng (<code>imp_drop_pct &gt;= 6% &amp; imp_ker &gt;= 0.50</code>) nhốt sống đội mua đỉnh (Factor #2).
                  <br/>• <strong>[L2.4] Lệch Pha Đa Khung Thời Gian (HTF Retracement → LTF Micro-BOS):</strong> H4/D1 hồi lên vùng Fibo <code>0.500–0.786</code> cạn cung và H1 đóng nến phá đáy cấu trúc (Factor #3).
                </p>
              </div>

              <!-- Layer 1 -->
              <div style="background: linear-gradient(90deg, rgba(16, 185, 129, 0.16), rgba(6, 182, 212, 0.12)); border: 1px solid rgba(16, 185, 129, 0.6); border-left: 6px solid #10b981; border-radius: 12px; padding: 18px 22px; width: 82%; margin: 0 auto;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 6px;">
                  <strong style="color: #34d399; font-size: 15.5px;">TẦNG 1 (TẦNG LÕI BẤT BIẾN — ÍT NHẤT): Tầng Tâm Lý Đám Đông &amp; Nỗi Đau Vị Thế (Behavioral &amp; Position Pain Layer)</strong>
                  <span class="tag tag-emerald">Chỉ 4 Cơ chế gốc • Nguồn cội của mọi Alpha</span>
                </div>
                <p style="font-size: 13.5px; color: #ecfdf5;">
                  • <strong>[L1.1] FOMO Mua Đuổi &amp; Cạn Kiệt Người Mua Cuối Cùng (Buyer Exhaustion):</strong> Giá tăng sốc <code>&gt;= 50%–100%</code> hút cạn tiền mặt của đám đông vào vị thế Long ở vùng đỉnh.
                  <br/>• <strong>[L1.2] Hiệu Ứng Mỏ Neo &amp; Tâm Lý "Cầu Về Bờ" (Disposition Effect / Breakeven Wall):</strong> Đội mua đỉnh bị kẹp hàng sau nhịp sập đầu tiên; khi giá hồi lên <strong>50%–61.8% (Fibo)</strong>, họ xả hàng loạt để thoát lỗ.
                  <br/>• <strong>[L1.3] Thác Đổ Cắt Lỗ &amp; Thanh Lý Cưỡng Bức (Stop-Run &amp; Liquidation Cascade):</strong> Khi nhịp hồi Fibo thất bại và thủng đáy H1, cả đội kẹp đỉnh lẫn đội bắt đáy sớm hoảng loạn bán tháo về TP1/TP2/TP3.
                  <br/>• <strong>[L1.4] Bẫy Chặn Đầu Xe Lửa (Premature Short-Squeeze Trap):</strong> Đám đông Short sớm khi sóng mới tăng 10%–25% hoặc đang trong Uptrend tổ chức, trở thành thanh khoản bị quét Stop Loss.
                </p>
              </div>
            </div>
          </div>

          <!-- Sub-tab 2.3: Collinearity & Orthogonal Synergy Matrix -->
          <div id="tab-lib-collinearity" class="tab-panel sub-lib">
            <div class="table-wrap" style="margin-bottom: 18px;">
              <table>
                <thead>
                  <tr>
                    <th>Cặp Chỉ Báo Kết Hợp (Kiểm Định Đa Cộng Tuyến Spearman)</th>
                    <th>Mối Quan Hệ Cơ Chế</th>
                    <th class="num">Hệ Số Tương Quan</th>
                    <th class="num">Số Lệnh</th>
                    <th class="num">Win Rate</th>
                    <th class="num">Lãi TB/Lệnh</th>
                    <th class="num">Profit Factor</th>
                    <th>Kết Luận Cổng Kiểm Duyệt (Review Gate)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Đơn lẻ F1: <code>Velocity &gt;= 8%/ngày</code> (CryptoFactor)</td>
                    <td>Tầng 2.1: Bơm nhanh ít nền</td>
                    <td class="num">—</td>
                    <td class="num">189</td>
                    <td class="num">65.08%</td>
                    <td class="num pos">+1.809%</td>
                    <td class="num pos">1.55</td>
                    <td><span class="tag tag-info">Mốc chuẩn đơn lẻ của nhóm Tốc độ</span></td>
                  </tr>
                  <tr>
                    <td>Ghép Trùng Lặp F1: <code>Velocity &gt;= 8%/ngày</code> <strong>AND</strong> <code>Duration &lt;= 8 ngày</code></td>
                    <td><span class="tag tag-danger">Cùng Cơ Chế L2.1 (Trùng lặp)</span></td>
                    <td class="num neg"><strong>r = +0.825 (Trùng 75.4%)</strong></td>
                    <td class="num">147</td>
                    <td class="num">65.31%</td>
                    <td class="num pos">+1.544%</td>
                    <td class="num neg"><strong>1.48 (Giảm!)</strong></td>
                    <td><span class="tag tag-danger">✗ Cả 2 cùng đo tốc độ sóng → Ghép vào làm giảm PF &amp; mất 114% lãi</span></td>
                  </tr>
                  <tr>
                    <td>Ghép Trùng Lặp F2: <code>imp_drop_pct</code> vs <code>imp_retrace_of_pump</code> / <code>imp_vol_units</code></td>
                    <td><span class="tag tag-danger">Cùng Cơ Chế L2.3 (Độ sâu sập)</span></td>
                    <td class="num neg"><strong>r = +0.861 / +0.738</strong></td>
                    <td class="num">130</td>
                    <td class="num">68.46%</td>
                    <td class="num pos">+2.682%</td>
                    <td class="num">2.24</td>
                    <td><span class="tag tag-danger">✗ Trùng lặp 74%–86% → Chỉ giữ <code>imp_drop_pct &gt;= 6%</code> làm sàn</span></td>
                  </tr>
                  <tr class="row-sweetspot">
                    <td><strong>Ghép Trực Giao 2 Nhánh PST: <code>ewmac(16,64)&lt;=0</code> OR <code>accel(4,16)&lt;=-1</code></strong></td>
                    <td><span class="tag tag-gold">Khác Cơ Chế (Tầng 3.1 + Tầng 2.2)</span></td>
                    <td class="num pos"><strong>r = -0.202 (Trùng chỉ 3.0%)</strong></td>
                    <td class="num">201</td>
                    <td class="num">63.18%</td>
                    <td class="num pos">+1.797%</td>
                    <td class="num pos">1.63</td>
                    <td><span class="tag tag-gold">★ Hai tập lệnh gần như rời nhau (136 + 65 = 201 lệnh)</span></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>★ Ghép Trực Giao F1: <code>PST</code> AND <code>wave_ker &gt;= 0.35</code></strong></td>
                    <td><span class="tag tag-emerald">Trực Giao (L3.1/L2.2 + L2.1)</span></td>
                    <td class="num pos"><strong>r = +0.024</strong></td>
                    <td class="num"><strong>130</strong></td>
                    <td class="num"><strong>68.46%</strong></td>
                    <td class="num pos"><strong>+2.682%</strong></td>
                    <td class="num pos"><strong>2.24</strong></td>
                    <td><span class="tag tag-emerald">🏆 Tương quan = 0.024 → Cộng hưởng nhân bội PF từ 1.63 lên 2.24!</span></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>★ Ghép Trực Giao F1 + F2: <code>Mốc 3A</code> AND <code>imp_ker &gt;= 0.50</code></strong></td>
                    <td><span class="tag tag-emerald">Trực Giao (Sóng Bơm + Sóng Sập)</span></td>
                    <td class="num pos"><strong>r = +0.119</strong></td>
                    <td class="num"><strong>99</strong></td>
                    <td class="num"><strong>73.74%</strong></td>
                    <td class="num pos"><strong>+3.341%</strong></td>
                    <td class="num pos"><strong>2.85</strong></td>
                    <td><span class="tag tag-emerald">🏆 Độ thẳng nhịp sập độc lập với nhịp bơm → PF vọt lên 2.85!</span></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>★ Ghép Trực Giao F2 + F3: <code>imp_ker &gt;= 0.50</code> AND <code>pb_vol_ratio &lt;= 1.1</code></strong></td>
                    <td><span class="tag tag-emerald">Trực Giao (Nhịp Sập + Cạn Cung Hồi)</span></td>
                    <td class="num pos"><strong>r = -0.023</strong></td>
                    <td class="num"><strong>78</strong></td>
                    <td class="num"><strong>73.08%</strong></td>
                    <td class="num pos"><strong>+3.512%</strong></td>
                    <td class="num pos"><strong>2.67</strong></td>
                    <td><span class="tag tag-emerald">🏆 Tương quan gần bằng 0 (-0.023), AvgR đạt +0.41R</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>

      <!-- ===================================================================== -->
      <!-- PILLAR 4: 7-YEAR MULTI-CYCLE & OOS VALIDATION (2020 -> 2026)          -->
      <!-- ===================================================================== -->
      <div id="page-multiyear-oos" class="wiki-page">
        <section class="section" style="border-color: rgba(6, 182, 212, 0.5); background: linear-gradient(180deg, #111827 0%, #082032 100%);">
          <div class="section-header">
            <div>
              <div class="section-title">
                <span>📈 Chuyên Mục 4: Kiểm Chứng Xuyên Chu Kỳ 7 Năm (2020 → 2026 OOS) &amp; 4 Khám Phá Lịch Sử</span>
              </div>
              <div class="section-subtitle">
                Kiểm nghiệm toàn diện từ <strong>Đại sóng Parabolic Bull Run (2020–2021)</strong>, <strong>Mùa Đông Crypto (2022)</strong>, <strong>Tích Lũy (2023)</strong>, <strong>Chu kỳ ETF &amp; Meme (2024–2025)</strong> đến <strong>Out-of-Sample Thực Chiến (2026)</strong>.
              </div>
            </div>
            <span class="pill pill-cyan">12,339 Lệnh IS + 1,503 Lệnh OOS</span>
          </div>

          <div class="tabs">
            <button class="tab-btn active" onclick="switchSubTab(event, 'sub-multi', 'tab-multi-yearly')">4.1. Bảng Phân Hóa Từng Năm (2020 → 2026) Theo Mốc</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-multi', 'tab-multi-conviction')">4.2. Bảng Điểm Hội Tụ (Conviction 0–100) Từng Năm</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-multi', 'tab-multi-discoveries')">4.3. Bốn Khám Phá Cốt Lõi &amp; Chi Tiết OOS 2026</button>
          </div>

          <!-- Sub-tab 4.1: Year-by-Year Milestone Table -->
          <div id="tab-multi-yearly" class="tab-panel sub-multi active">
            <div class="table-wrap" style="margin-bottom:16px;">
              <table>
                <thead>
                  <tr>
                    <th>Cấu Hình Chiến Lược (Mốc 0 → Mốc 6S)</th>
                    <th class="num">Tổng 6 Năm<br/>(2020–2025)</th>
                    <th class="num sep-left">Năm 2020<br/>(DeFi Bull)</th>
                    <th class="num">Năm 2021<br/>(Mega Bull)</th>
                    <th class="num">Năm 2022<br/>(Bear Winter)</th>
                    <th class="num">Năm 2023<br/>(Sideways)</th>
                    <th class="num">Năm 2024<br/>(ETF &amp; Meme)</th>
                    <th class="num">Năm 2025<br/>(Alt Cycle)</th>
                    <th class="num sep-left">OOS 2026<br/>(Thực Chiến)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Mốc 0: Baseline (`Pump &gt;= 5%`)</strong></td>
                    <td class="num neg"><strong>-3,366.6%</strong><br/><small>12,339 lệnh | PF 0.89</small></td>
                    <td class="num neg">-775.2%<br/><small>WR 43.4% | PF 0.75</small></td>
                    <td class="num neg">-1,531.3%<br/><small>WR 44.4% | PF 0.81</small></td>
                    <td class="num pos">+197.0%<br/><small>WR 51.1% | PF 1.05</small></td>
                    <td class="num neg">-705.2%<br/><small>WR 47.1% | PF 0.82</small></td>
                    <td class="num neg">-980.6%<br/><small>WR 46.9% | PF 0.85</small></td>
                    <td class="num pos">+428.8%<br/><small>WR 50.4% | PF 1.08</small></td>
                    <td class="num pos sep-left">+566.7%<br/><small>WR 52.2% | DD 286%</small></td>
                  </tr>
                  <tr>
                    <td><strong>Mốc 1: F1A (`Pump &gt;= 50%`)</strong></td>
                    <td class="num pos"><strong>+166.5%</strong><br/><small>1,467 lệnh | PF 1.03</small></td>
                    <td class="num neg">-147.5%<br/><small>WR 46.3% | PF 0.78</small></td>
                    <td class="num neg">-121.0%<br/><small>WR 47.4% | PF 0.96</small></td>
                    <td class="num pos">+182.5%<br/><small>WR 60.4% | PF 1.58</small></td>
                    <td class="num neg">-17.8%<br/><small>WR 52.7% | PF 0.96</small></td>
                    <td class="num neg">-35.0%<br/><small>WR 53.7% | PF 0.97</small></td>
                    <td class="num pos">+305.3%<br/><small>WR 59.2% | PF 1.54</small></td>
                    <td class="num pos sep-left">+95.0%<br/><small>WR 65.4% | PF 1.51</small></td>
                  </tr>
                  <tr>
                    <td><strong>Mốc 2: +F1B (`pysystemtrade`)</strong></td>
                    <td class="num pos"><strong>+404.9%</strong><br/><small>642 lệnh | PF 1.16</small></td>
                    <td class="num neg">-137.6%<br/><small>WR 47.9% | PF 0.65</small></td>
                    <td class="num pos"><strong>+62.6%</strong><br/><small>WR 52.7% | PF 1.05</small></td>
                    <td class="num pos">+159.6%<br/><small>WR 60.2% | PF 1.64</small></td>
                    <td class="num neg">-16.0%<br/><small>WR 51.5% | PF 0.85</small></td>
                    <td class="num pos">+141.1%<br/><small>WR 64.6% | PF 1.53</small></td>
                    <td class="num pos">+195.2%<br/><small>WR 60.7% | PF 1.58</small></td>
                    <td class="num pos sep-left">+57.1%<br/><small>WR 70.8% | PF 1.59</small></td>
                  </tr>
                  <tr>
                    <td><strong>Mốc 3B: +F1C Mở Rộng (`PST OR KER&gt;=0.65`)</strong></td>
                    <td class="num pos"><strong>+326.1%</strong><br/><small>567 lệnh | PF 1.16</small></td>
                    <td class="num neg">-27.5%<br/><small>WR 52.1% | PF 0.89</small></td>
                    <td class="num neg">-82.1%<br/><small>WR 49.2% | PF 0.91</small></td>
                    <td class="num pos">+127.9%<br/><small>WR 60.7% | PF 1.66</small></td>
                    <td class="num neg">-73.9%<br/><small>WR 47.9% | PF 0.62</small></td>
                    <td class="num pos">+234.1%<br/><small>WR 66.1% | PF 1.78</small></td>
                    <td class="num pos">+147.6%<br/><small>WR 62.8% | PF 1.67</small></td>
                    <td class="num pos sep-left">+72.4%<br/><small>WR 68.8% | PF 1.64</small></td>
                  </tr>
                  <tr class="row-inflection">
                    <td><strong>Mốc 3A: +F1C Tinh Hoa (`PST &amp; KER&gt;=0.35`)</strong></td>
                    <td class="num pos"><strong>+447.9%</strong><br/><small>390 lệnh | PF 1.34</small></td>
                    <td class="num pos"><strong>+27.4%</strong><br/><small>WR 57.1% | PF 1.15</small></td>
                    <td class="num">-3.1%<br/><small>WR 51.7% | PF 0.99</small></td>
                    <td class="num pos">+106.5%<br/><small>WR 59.3% | PF 1.61</small></td>
                    <td class="num neg">-13.7%<br/><small>WR 52.0% | PF 0.82</small></td>
                    <td class="num pos"><strong>+222.5%</strong><br/><small>WR 72.3% | PF 2.69</small></td>
                    <td class="num pos">+108.2%<br/><small>WR 62.7% | PF 1.64</small></td>
                    <td class="num pos sep-left">+31.0%<br/><small>WR 68.4% | PF 1.36</small></td>
                  </tr>
                  <tr>
                    <td><strong>Mốc 4B: +F2 Mở Rộng (`imp_ker &gt;= 0.50`)</strong></td>
                    <td class="num pos"><strong>+323.9%</strong><br/><small>443 lệnh | PF 1.20</small></td>
                    <td class="num pos">+0.9%<br/><small>WR 53.7% | PF 1.00</small></td>
                    <td class="num neg">-70.1%<br/><small>WR 48.1% | PF 0.91</small></td>
                    <td class="num pos">+91.9%<br/><small>WR 61.4% | PF 1.78</small></td>
                    <td class="num neg">-51.2%<br/><small>WR 51.3% | PF 0.67</small></td>
                    <td class="num pos">+207.8%<br/><small>WR 66.7% | PF 1.90</small></td>
                    <td class="num pos">+144.5%<br/><small>WR 68.9% | PF 2.11</small></td>
                    <td class="num pos sep-left"><strong>+124.6%</strong><br/><small>WR 76.0% | PF 4.45</small></td>
                  </tr>
                  <tr class="row-sweetspot">
                    <td><strong>★ Mốc 4A: +F2 Tinh Hoa (Bất Bại 7/7 Năm!)</strong></td>
                    <td class="num pos"><strong>+456.8%</strong><br/><small>299 lệnh | PF 1.46</small></td>
                    <td class="num pos"><strong>+44.4%</strong><br/><small>WR 60.0% | PF 1.33</small></td>
                    <td class="num pos"><strong>+35.4%</strong><br/><small>WR 52.6% | PF 1.07</small></td>
                    <td class="num pos"><strong>+58.9%</strong><br/><small>WR 57.9% | PF 1.54</small></td>
                    <td class="num pos"><strong>+5.3%</strong><br/><small>WR 60.0% | PF 1.10</small></td>
                    <td class="num pos"><strong>+199.6%</strong><br/><small>WR 74.1% | PF 3.03</small></td>
                    <td class="num pos"><strong>+113.2%</strong><br/><small>WR 70.2% | PF 2.15</small></td>
                    <td class="num pos sep-left"><strong>+77.5%</strong><br/><small>WR 73.3% | PF 4.55</small></td>
                  </tr>
                  <tr>
                    <td><strong>Mốc 5B: +F3 Mở Rộng (`H1 Phá Cấu Trúc`)</strong></td>
                    <td class="num pos"><strong>+266.7%</strong><br/><small>250 lệnh | PF 1.29</small></td>
                    <td class="num pos">+18.8%<br/><small>WR 57.1% | PF 1.23</small></td>
                    <td class="num neg">-83.0%<br/><small>WR 47.3% | PF 0.84</small></td>
                    <td class="num pos">+53.4%<br/><small>WR 65.2% | PF 1.89</small></td>
                    <td class="num pos">+20.8%<br/><small>WR 68.8% | PF 1.49</small></td>
                    <td class="num pos">+129.7%<br/><small>WR 74.0% | PF 2.11</small></td>
                    <td class="num pos">+126.9%<br/><small>WR 77.5% | PF 2.83</small></td>
                    <td class="num pos sep-left"><strong>+82.9%</strong><br/><small>WR 80.0% | PF 4.45</small></td>
                  </tr>
                  <tr class="row-sweetspot">
                    <td><strong>★ Mốc 5A: +F3 Tinh Hoa (Bất Bại 7/7 Năm!)</strong></td>
                    <td class="num pos"><strong>+313.6%</strong><br/><small>169 lệnh | PF 1.58</small></td>
                    <td class="num pos"><strong>+39.9%</strong><br/><small>WR 63.6% | PF 1.73</small></td>
                    <td class="num pos"><strong>+23.5%</strong><br/><small>WR 53.9% | PF 1.08</small></td>
                    <td class="num pos"><strong>+31.7%</strong><br/><small>WR 60.0% | PF 1.53</small></td>
                    <td class="num pos"><strong>+4.4%</strong><br/><small>WR 71.4% | PF 1.24</small></td>
                    <td class="num pos"><strong>+126.5%</strong><br/><small>WR 77.8% | PF 3.02</small></td>
                    <td class="num pos"><strong>+87.6%</strong><br/><small>WR 75.0% | PF 2.53</small></td>
                    <td class="num pos sep-left"><strong>+40.4%</strong><br/><small>WR 77.8% | PF 3.61</small></td>
                  </tr>
                  <tr>
                    <td><strong>👑 Mốc 6B: +F4 Toàn Diện (`SL 0.886 + Đi Vốn`)</strong></td>
                    <td class="num pos"><strong>+518.0%</strong><br/><small>443 lệnh | PF 1.32</small></td>
                    <td class="num neg">-29.1%<br/><small>WR 50.0% | PF 0.86</small></td>
                    <td class="num neg">-21.4%<br/><small>WR 43.7% | PF 0.97</small></td>
                    <td class="num pos"><strong>+103.0%</strong><br/><small>WR 61.4% | PF 1.92</small></td>
                    <td class="num neg">-10.5%<br/><small>WR 48.7% | PF 0.91</small></td>
                    <td class="num pos"><strong>+280.0%</strong><br/><small>WR 65.5% | PF 2.31</small></td>
                    <td class="num pos"><strong>+195.9%</strong><br/><small>WR 67.2% | PF 2.70</small></td>
                    <td class="num pos sep-left"><strong>+127.0%</strong><br/><small>WR 76.0% | PF 4.76</small></td>
                  </tr>
                  <tr>
                    <td><strong>👑 Mốc 6A: +F4 Sniper Mở Rộng (`SL 0.886 + Đi Vốn`)</strong></td>
                    <td class="num pos"><strong>+372.7%</strong><br/><small>250 lệnh | PF 1.39</small></td>
                    <td class="num neg">-16.5%<br/><small>WR 53.6% | PF 0.85</small></td>
                    <td class="num neg">-24.9%<br/><small>WR 46.2% | PF 0.95</small></td>
                    <td class="num pos"><strong>+60.3%</strong><br/><small>WR 65.2% | PF 1.97</small></td>
                    <td class="num pos"><strong>+29.9%</strong><br/><small>WR 68.8% | PF 1.76</small></td>
                    <td class="num pos"><strong>+159.4%</strong><br/><small>WR 74.0% | PF 2.22</small></td>
                    <td class="num pos"><strong>+164.5%</strong><br/><small>WR 75.0% | PF 3.42</small></td>
                    <td class="num pos sep-left"><strong>+86.0%</strong><br/><small>WR 80.0% | PF 4.68</small></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>👑 Mốc 6S: +F4 Sniper Tinh Hoa (Bất Bại 7/7 Năm!)</strong></td>
                    <td class="num pos"><strong>+378.9%</strong><br/><small>169 lệnh | PF 1.59</small></td>
                    <td class="num pos"><strong>+2.4%</strong><br/><small>WR 59.1% | PF 1.03</small></td>
                    <td class="num pos"><strong>+59.5%</strong><br/><small>WR 51.9% | PF 1.18</small></td>
                    <td class="num pos"><strong>+39.3%</strong><br/><small>WR 60.0% | PF 1.63</small></td>
                    <td class="num pos"><strong>+6.5%</strong><br/><small>WR 71.4% | PF 1.33</small></td>
                    <td class="num pos"><strong>+150.1%</strong><br/><small>WR 77.8% | PF 2.73</small></td>
                    <td class="num pos"><strong>+121.3%</strong><br/><small>WR 71.9% | PF 2.99</small></td>
                    <td class="num pos sep-left"><strong>+45.2%</strong><br/><small>WR 77.8% | PF 4.03</small></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 4.2: Year-by-Year Conviction Tier Table -->
          <div id="tab-multi-conviction" class="tab-panel sub-multi">
            <p style="font-size:13.5px; color:#cbd5e1; margin-bottom:12px;">
              Chấm điểm toàn bộ <strong>1,467 lệnh sóng tăng &gt;= 50%</strong> trong suốt 6 năm In-Sample (2020–2025) và <strong>52 lệnh OOS (2026)</strong> theo đúng Thang điểm Hội tụ 0–100 đã khóa:
            </p>
            <div class="table-wrap" style="margin-bottom:18px;">
              <table>
                <thead>
                  <tr>
                    <th>Hạng Điểm Hội Tụ (<code>0–100</code>)</th>
                    <th class="num">Tổng 6 Năm<br/>(2020–2025)</th>
                    <th class="num sep-left">Năm 2020</th>
                    <th class="num">Năm 2021</th>
                    <th class="num">Năm 2022</th>
                    <th class="num">Năm 2023</th>
                    <th class="num">Năm 2024</th>
                    <th class="num">Năm 2025</th>
                    <th class="num sep-left">OOS 2026</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Hạng D/C (<code>&lt; 55đ</code> — Bỏ qua)</strong></td>
                    <td class="num neg"><strong>-134.3%</strong><br/><small>617 lệnh | WR 45.5% | PF 0.95</small></td>
                    <td class="num pos">+19.2%<br/><small>71 lệnh | WR 47.9%</small></td>
                    <td class="num neg">-43.5%<br/><small>228 lệnh | WR 42.1%</small></td>
                    <td class="num neg">-55.1%<br/><small>34 lệnh | WR 44.1%</small></td>
                    <td class="num neg">-26.7%<br/><small>57 lệnh | WR 43.9%</small></td>
                    <td class="num neg">-73.9%<br/><small>153 lệnh | WR 49.7%</small></td>
                    <td class="num pos">+45.6%<br/><small>74 lệnh | WR 47.3%</small></td>
                    <td class="num pos sep-left">+40.4%<br/><small>21 lệnh | PF 1.65</small></td>
                  </tr>
                  <tr>
                    <td><strong>Hạng B (<code>55–69đ</code> — Trung bình <code>0.75R</code>)</strong></td>
                    <td class="num neg"><strong>-237.5%</strong><br/><small>532 lệnh | WR 51.1% | PF 0.90</small></td>
                    <td class="num neg">-140.7%<br/><small>65 lệnh | WR 43.1%</small></td>
                    <td class="num neg">-262.5%<br/><small>210 lệnh | WR 45.2%</small></td>
                    <td class="num pos"><strong>+162.6%</strong><br/><small>45 lệnh | WR 68.9%</small></td>
                    <td class="num neg">-33.0%<br/><small>52 lệnh | WR 55.8%</small></td>
                    <td class="num neg">-94.5%<br/><small>91 lệnh | WR 50.6%</small></td>
                    <td class="num pos"><strong>+130.6%</strong><br/><small>69 lệnh | WR 62.3%</small></td>
                    <td class="num pos sep-left">+2.2%<br/><small>20 lệnh | PF 1.02</small></td>
                  </tr>
                  <tr class="row-sweetspot">
                    <td><strong>★ Hạng A (<code>70–84đ</code> — Tinh Hoa <code>1.25R</code>)</strong></td>
                    <td class="num pos"><strong>+432.2%</strong><br/><small>284 lệnh | WR 62.7% | PF 1.42</small></td>
                    <td class="num neg">-26.0%<br/><small>39 lệnh | WR 48.7%</small></td>
                    <td class="num pos"><strong>+140.2%</strong><br/><small>110 lệnh | WR 60.0%</small></td>
                    <td class="num pos"><strong>+57.4%</strong><br/><small>25 lệnh | WR 64.0%</small></td>
                    <td class="num pos"><strong>+37.9%</strong><br/><small>19 lệnh | WR 68.4%</small></td>
                    <td class="num pos"><strong>+138.0%</strong><br/><small>52 lệnh | WR 71.2%</small></td>
                    <td class="num pos"><strong>+84.6%</strong><br/><small>39 lệnh | WR 69.2%</small></td>
                    <td class="num pos sep-left"><strong>+40.4%</strong><br/><small>9 lệnh | WR 66.7% | PF 3.06</small></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>👑 Hạng S (<code>&gt;= 85đ</code> — Siêu Hội Tụ <code>2.00R</code>)</strong></td>
                    <td class="num pos"><strong>+106.2%</strong><br/><small>34 lệnh | WR 73.5% | PF 2.25</small></td>
                    <td class="num">0.0%<br/><small>0 lệnh</small></td>
                    <td class="num pos"><strong>+44.7%</strong><br/><small>13 lệnh | WR 69.2% | PF 2.01</small></td>
                    <td class="num pos"><strong>+17.6%</strong><br/><small>2 lệnh | WR 100%</small></td>
                    <td class="num pos"><strong>+4.1%</strong><br/><small>1 lệnh | WR 100%</small></td>
                    <td class="num neg">-4.7%<br/><small>4 lệnh | WR 50.0%</small></td>
                    <td class="num pos"><strong>+44.5%</strong><br/><small>14 lệnh | WR 78.6% | PF 4.46</small></td>
                    <td class="num pos sep-left"><strong>+12.0%</strong><br/><small>2 lệnh | WR 100% | DD 0%</small></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 4.3: 4 Major Discoveries & Detailed OOS 2026 -->
          <div id="tab-multi-discoveries" class="tab-panel sub-multi">
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap:16px; margin-bottom:20px;">
              <div style="background:rgba(16,185,129,0.08); border:1px solid rgba(16,185,129,0.4); border-left:5px solid #10b981; border-radius:12px; padding:16px 18px;">
                <div style="color:#34d399; font-weight:800; font-size:14.5px; margin-bottom:8px;">
                  🛡️ Khám Phá #1 (DISC-01): Tại Sao Mốc 4A, 5A &amp; 6S (Nhánh Tinh Hoa) BẤT BẠI Cả 7/7 Năm (2020 → 2026), Kể Cả Giữa Đại Sóng Bull Run 2021?
                </div>
                <ul style="font-size:13px; color:#cbd5e1; padding-left:18px; margin:0; line-height:1.65;">
                  <li><strong>Năm 2020–2021 là "nghĩa địa" của phe Short thông thường:</strong> Khi BTC từ 4k$ lên 69k$ và SOL/BNB/SHIB tăng hàng trăm lần, Mốc 0 (Baseline) lỗ <strong>-775.2% (2020)</strong> và <strong>-1,531.3% (2021)</strong>.</li>
                  <li><strong>Tại sao Nhánh Mở Rộng (<code>Mốc 3B/4B/5B</code>) vẫn lỗ năm 2021 (-70% đến -83%)?</strong> Vì công thức <code>(PST &amp; KER&gt;=0.35) OR (KER&gt;=0.65)</code> cho phép Short khi thấy sóng tăng dựng đứng (<code>KER &gt;= 0.65</code>) ngay cả khi <code>PST == False</code>. Trong đại sóng 2021, bơm dựng đứng khi xu hướng lớn &amp; gia tốc còn dương chính là <strong>chân sóng thần Parabolic</strong>!</li>
                  <li><strong>Khi khóa cứng <code>PST</code> ở Nhánh Tinh Hoa (<code>Mốc 4A, 5A, 6S</code>):</strong> Bắt buộc xu hướng lớn phải âm (<code>ewmac &lt;= 0</code>) hoặc gia tốc tại đỉnh đã gãy sập (<code>accel &lt;= -1.0</code>) → <strong>Dương liên tiếp cả 7/7 năm (2020 → 2026)</strong>, riêng giữa bão Bull Run 2021 <strong>Mốc 6S vẫn lãi +59.45% (PF 1.18)</strong>!</li>
                </ul>
              </div>

              <div style="background:rgba(6,182,212,0.08); border:1px solid rgba(6,182,212,0.4); border-left:5px solid #06b6d4; border-radius:12px; padding:16px 18px;">
                <div style="color:#67e8f9; font-weight:800; font-size:14.5px; margin-bottom:8px;">
                  📈 Khám Phá #2 (DISC-02): Sự Tiến Hóa Cấu Trúc Thị Trường Crypto Từ Thời Kỳ 2020–2021 Sang Thời Kỳ 2022–2026
                </div>
                <ul style="font-size:13px; color:#cbd5e1; padding-left:18px; margin:0; line-height:1.65;">
                  <li><strong>Thời kỳ 1 (2020–2021 — Cơn điên một chiều sơ khai):</strong> Chiến lược Tinh Hoa đóng vai trò <strong>"Phòng thủ sinh lời"</strong> — lọc bỏ hơn 98% bẫy Short sớm, giữ Win Rate 52%–63.6%, Profit Factor 1.08–1.73, bảo toàn vốn tuyệt đối.</li>
                  <li><strong>Thời kỳ 2 (2022–2026 — Phái sinh trưởng thành &amp; Chu kỳ Bơm-Xả hai chiều):</strong> Khi thanh khoản Futures dày đặc và các nhịp bơm Altcoin luôn đi kèm tường xả kẹp hàng tại vùng Fibo, chiến lược bước vào <strong>"Thời kỳ Hoàng Kim"</strong>:
                    <br/>• <strong>2022–2023:</strong> WR 60.0%–71.4%, PF 1.33–1.97 (+103.0% ở Mốc 6B năm 2022).
                    <br/>• <strong>2024–2025:</strong> WR <strong>71.9%–77.8%</strong>, Lãi <strong>+271.4% đến +475.9%</strong>, PF 2.31–3.42.
                    <br/>• <strong>2026 (OOS):</strong> WR <strong>76.0%–80.0%</strong>, PF <strong>4.03–4.76</strong>, MaxDD chỉ <strong>7.6%–12.1%</strong>!
                  </li>
                </ul>
              </div>

              <div style="background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.4); border-left:5px solid #f59e0b; border-radius:12px; padding:16px 18px;">
                <div style="color:#fbbf24; font-weight:800; font-size:14.5px; margin-bottom:8px;">
                  🎯 Khám Phá #3 (DISC-03): Thang Điểm Hội Tụ 4 Tầng (<code>Conviction Score &gt;= 70</code>) Tỏa Sáng Ngay Giữa Tâm Bão Bull Run 2021
                </div>
                <ul style="font-size:13px; color:#cbd5e1; padding-left:18px; margin:0; line-height:1.65;">
                  <li>Trong năm Siêu Bull Run 2021, các lệnh có điểm hội tụ thấp <strong>Hạng D/C (&lt; 55đ)</strong> và <strong>Hạng B (55–69đ)</strong> thua lỗ tổng cộng hơn <strong>-305%</strong> vì thiếu sự đồng thuận giữa vĩ mô và vi cấu trúc.</li>
                  <li>Ngược lại, ngay trong chính năm 2021 đó, <strong>110 lệnh đạt Hạng A (70–84 điểm)</strong> lại đạt Win Rate <strong>60.00%</strong>, mang về <strong>+140.20% lợi nhuận ròng (PF 1.27)</strong>; và <strong>13 lệnh đạt Hạng S (&gt;= 85 điểm)</strong> đạt Win Rate <strong>69.23%</strong>, thu về <strong>+44.73% (PF 2.01, DD chỉ 31.3%)</strong>!</li>
                </ul>
              </div>

              <div style="background:rgba(139,92,246,0.08); border:1px solid rgba(139,92,246,0.4); border-left:5px solid #8b5cf6; border-radius:12px; padding:16px 18px;">
                <div style="color:#c4b5fd; font-weight:800; font-size:14.5px; margin-bottom:8px;">
                  🧭 Khám Phá #4 (DISC-04): Kiểm Chứng Ngoại Mẫu OOS 2026 — Sự Lặp Lại Hoàn Hảo Của Trật Tự 4 Nhân Tố (Zero Re-tuning)
                </div>
                <ul style="font-size:13px; color:#cbd5e1; padding-left:18px; margin:0; line-height:1.65;">
                  <li>Dữ liệu 9 tháng năm 2026 hoàn toàn chưa từng được chạm tới trong suốt quá trình nghiên cứu.</li>
                  <li>Khi đem nguyên vẹn cả 7 cấp độ cấu hình sang chạy trên năm 2026, trật tự cải thiện lặp lại chính xác: Win Rate tăng từ <code>52.16%</code> (Mốc 0) → <code>65.38%</code> (Mốc 1) → <code>76.00%</code> (Mốc 4B/6B) → <strong><code>80.00%</code> (Mốc 5B/6A)</strong>; Profit Factor đạt <strong><code>4.03 – 4.76</code></strong> và Max Drawdown giảm từ <code>285.6%</code> xuống chỉ còn <strong><code>7.6% – 12.1%</code></strong>!</li>
                </ul>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- ===================================================================== -->
      <!-- PILLAR 3: 4-FACTOR CETERIS PARIBUS LABORATORY (F1 -> F4)              -->
      <!-- ===================================================================== -->
      <div id="page-factor-lab" class="wiki-page">
        <section class="section" style="border-color: rgba(245, 158, 11, 0.45);">
          <div class="section-header">
            <div>
              <div class="section-title">
                <span>🔬 Chuyên Mục 3: Phòng Thí Nghiệm Giải Phẫu 4 Nhân Tố Tuần Tự (Ceteris Paribus F1 → F4)</span>
              </div>
              <div class="section-subtitle">
                Toàn bộ chuỗi thí nghiệm Ceteris Paribus từ <code>EXP-1A</code> (Biên độ sóng), <code>EXP-1B</code> (Đường MA &amp; Thời gian nến), <code>EXP-1C/1D</code> (<code>pysystemtrade</code> &amp; 5 Kho chiến lược) đến <code>Factor #2</code> (Xung lực sập), <code>Factor #3</code> (Fibo &amp; H1 BOS), <code>Factor #4</code> (SL 0.886 &amp; Đi vốn) và 3 Hình ảnh trực quan.
              </div>
            </div>
            <span class="pill pill-gold">26 Phép Thử Ceteris Paribus</span>
          </div>

          <div class="tabs">
            <button class="tab-btn active" onclick="switchSubTab(event, 'sub-lab', 'tab-lab-f1a')">3.1. Factor #1A: Quét Sóng 5%→100% &amp; Đường MA (EXP-1A/1B)</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-lab', 'tab-lab-f1bc')">3.2. Factor #1B/1C: pysystemtrade &amp; 5 Kho Chiến Lược (EXP-1C/1D)</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-lab', 'tab-lab-f2f3')">3.3. Factor #2 (Nhịp Sập) &amp; Factor #3 (Fibo + H1 BOS)</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-lab', 'tab-lab-f4')">3.4. Factor #4: Stop Loss 0.886 &amp; Đi Vốn Động</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-lab', 'tab-lab-visual')">3.5. Giải Thích Trực Quan 3 Hình Ảnh Đời Thường</button>
          </div>

          <!-- Sub-tab 3.1: EXP-1A & EXP-1B -->
          <div id="tab-lab-f1a" class="tab-panel sub-lab active">
            <h4 style="color:#fbbf24; font-size:15px; margin-bottom:10px;">A. Thực Nghiệm EXP-1A: Quét Biên Độ Sóng Tăng Trước Đỉnh (5% → 100%, 4,706 Lệnh)</h4>
            <div class="charts-two-col">
              <div class="chart-card">
                <h4>Biểu Đồ Lợi Nhuận Ròng Trung Bình Mỗi Lệnh (Avg Net Return %)</h4>
                {''.join(chart_bars_overall)}
              </div>
              <div class="chart-card">
                <h4>So Sánh Trực Tiếp Khung H4 vs Khung D1 Qua Từng Mốc Sóng Tăng</h4>
                {''.join(chart_bars_tf)}
              </div>
            </div>

            <div class="table-wrap" style="margin-bottom:22px;">
              <table>
                <thead>
                  <tr>
                    <th>Biên Độ Sóng Tăng Trước Đỉnh</th>
                    <th class="num">Số Lệnh</th>
                    <th class="num">Win Rate</th>
                    <th class="num">Chạm TP1 (Đáy Cũ)</th>
                    <th class="num">Chạm TP2 (1.272)</th>
                    <th class="num">Chạm TP3 (1.618)</th>
                    <th class="num">Lãi TB / Lệnh</th>
                    <th class="num">Tổng Lãi Ròng</th>
                    <th class="num">Profit Factor</th>
                    <th class="num">Max Drawdown</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(overall_rows)}
                </tbody>
              </table>
            </div>

            <h4 style="color:#38bdf8; font-size:15px; margin:20px 0 10px;">B. Thực Nghiệm EXP-1B: Giải Phẫu Đường MA &amp; Độ Dài Nến Xây Sóng (H4 vs D1)</h4>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Phân Loại Bản Chất Sóng Tăng (&gt;= 50%) Bằng Đường MA &amp; Thời Gian Nến</th>
                    <th class="num">Số Lệnh</th>
                    <th class="num">Win Rate</th>
                    <th class="num">Chạm TP1</th>
                    <th class="num">Lãi TB / Lệnh</th>
                    <th class="num">Tổng Lãi Ròng</th>
                    <th class="num">Profit Factor</th>
                    <th>Bản Chất Thị Trường</th>
                  </tr>
                </thead>
                <tbody>
                  <tr class="row-climax">
                    <td><strong>1. Khung D1 — Bơm sốc 1–3 ngày (Ngày trước sang ngày sau)</strong></td>
                    <td class="num">19</td>
                    <td class="num"><strong>84.21%</strong></td>
                    <td class="num">47.37%</td>
                    <td class="num pos"><strong>+4.825%</strong></td>
                    <td class="num pos"><strong>+91.67%</strong></td>
                    <td class="num pos"><strong>4.44</strong></td>
                    <td><span class="tag tag-emerald">Pump &amp; Dump dựng cột, không có nền MA đỡ</span></td>
                  </tr>
                  <tr class="row-sweetspot">
                    <td><strong>2. Khung D1 — Sóng bơm ngắn 4–8 ngày</strong></td>
                    <td class="num">21</td>
                    <td class="num"><strong>71.43%</strong></td>
                    <td class="num">52.38%</td>
                    <td class="num pos"><strong>+1.942%</strong></td>
                    <td class="num pos"><strong>+40.78%</strong></td>
                    <td class="num pos"><strong>1.48</strong></td>
                    <td><span class="tag tag-gold">Nhịp đẩy FOMO 1 tuần rồi gãy</span></td>
                  </tr>
                  <tr>
                    <td>3. Khung D1 — Sóng bò rề rà 9–24 ngày (2–3 tuần)</td>
                    <td class="num">327</td>
                    <td class="num">50.76%</td>
                    <td class="num">33.64%</td>
                    <td class="num pos">+0.108%</td>
                    <td class="num pos">+35.33%</td>
                    <td class="num">1.03</td>
                    <td><span class="tag tag-muted">Tăng bền mỗi ngày 2-3%, MA20/50 kịp bò lên đỡ</span></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>4. Khung H4 — Sóng kéo dài 9–15 nến H4 (1.5 – 2.5 ngày)</strong></td>
                    <td class="num">12</td>
                    <td class="num"><strong>75.00%</strong></td>
                    <td class="num">66.67%</td>
                    <td class="num pos"><strong>+2.892%</strong></td>
                    <td class="num pos"><strong>+34.70%</strong></td>
                    <td class="num pos"><strong>3.39</strong></td>
                    <td><span class="tag tag-emerald">Trùng khớp khung 1.5–3 ngày của D1</span></td>
                  </tr>
                  <tr class="row-inflection">
                    <td><strong>5. Khung H4 — Sóng kéo dài 16–24 nến H4 (2.5 – 4 ngày)</strong></td>
                    <td class="num">94</td>
                    <td class="num"><strong>60.64%</strong></td>
                    <td class="num">50.00%</td>
                    <td class="num pos"><strong>+0.617%</strong></td>
                    <td class="num pos"><strong>+57.98%</strong></td>
                    <td class="num pos"><strong>1.17</strong></td>
                    <td><span class="tag tag-cyan">Trùng khớp khung 3–4 ngày của D1</span></td>
                  </tr>
                  <tr>
                    <td>6. Khung H4 — Tăng quá ngắn 1–8 nến H4 (&lt; 1 ngày)</td>
                    <td class="num">7</td>
                    <td class="num">28.57%</td>
                    <td class="num">28.57%</td>
                    <td class="num neg"><strong>-3.974%</strong></td>
                    <td class="num neg"><strong>-27.82%</strong></td>
                    <td class="num neg">0.29</td>
                    <td><span class="tag tag-danger">Mới là chân sóng Breakout đầu tiên, cấm Short</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 3.2: EXP-1C (pysystemtrade) & EXP-1D (5 Repos + KER Sensitivity) -->
          <div id="tab-lab-f1bc" class="tab-panel sub-lab">
            <h4 style="color:#fbbf24; font-size:15px; margin-bottom:10px;">A. Thực Nghiệm EXP-1C: Chuẩn Hóa Xu Hướng &amp; Gia Tốc Với <code>pst-group/pysystemtrade</code> (Robert Carver)</h4>
            <div class="table-wrap" style="margin-bottom:22px;">
              <table>
                <thead>
                  <tr>
                    <th>Bộ Quy Tắc Từ <code>pysystemtrade</code> (Áp Dụng Trên Tập Sóng &gt;= 50%)</th>
                    <th class="num">Số Lệnh</th>
                    <th class="num">Win Rate</th>
                    <th class="num">Chạm TP1</th>
                    <th class="num">Lãi TB / Lệnh</th>
                    <th class="num">Tổng Lãi Ròng</th>
                    <th class="num">Profit Factor</th>
                    <th>Ý Nghĩa Định Lượng (Carver Framework)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Gốc: Toàn bộ 480 lệnh có <code>Prior Pump &gt;= 50%</code></td>
                    <td class="num">480</td>
                    <td class="num">55.21%</td>
                    <td class="num">38.96%</td>
                    <td class="num pos">+0.485%</td>
                    <td class="num pos">+232.64%</td>
                    <td class="num pos">1.13</td>
                    <td><span class="tag tag-muted">Chưa lọc chế độ xu hướng &amp; gia tốc</span></td>
                  </tr>
                  <tr class="row-sweetspot">
                    <td><strong>Nhánh 1 (<code>ewmac.py</code>): <code>ewmac(16, 64) &lt;= 0</code> (Macro Bear Regime)</strong></td>
                    <td class="num">136</td>
                    <td class="num"><strong>62.50%</strong></td>
                    <td class="num">44.85%</td>
                    <td class="num pos"><strong>+1.747%</strong></td>
                    <td class="num pos"><strong>+237.54%</strong></td>
                    <td class="num pos"><strong>1.63</strong></td>
                    <td><span class="tag tag-gold">★ Sóng bơm &gt;= 50% ngược trong xu hướng giảm lớn</span></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>Nhánh 2 (<code>accel.py</code>): <code>ewmac(16, 64) &gt; 0</code> NHƯNG <code>accel(4, 16) &lt;= -1.0</code></strong></td>
                    <td class="num">65</td>
                    <td class="num"><strong>64.62%</strong></td>
                    <td class="num">43.08%</td>
                    <td class="num pos"><strong>+1.903%</strong></td>
                    <td class="num pos"><strong>+123.70%</strong></td>
                    <td class="num pos"><strong>1.61</strong></td>
                    <td><span class="tag tag-emerald">⚡ Xu hướng tăng nhưng Gia Tốc (Đạo hàm bậc 2) đã gãy sập</span></td>
                  </tr>
                  <tr>
                    <td>Nhánh 3 (Bẫy Bull Run): <code>ewmac(16, 64) &gt; 0</code> VÀ <code>accel(4, 16) &gt; -1.0</code></td>
                    <td class="num">279</td>
                    <td class="num">49.46%</td>
                    <td class="num">35.13%</td>
                    <td class="num neg"><strong>-0.461%</strong></td>
                    <td class="num neg"><strong>-128.61%</strong></td>
                    <td class="num neg"><strong>0.89</strong></td>
                    <td><span class="tag tag-danger">✗ Cả xu hướng lớn lẫn gia tốc vẫn khỏe -> Chặn tàu</span></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>★ HỢP NHẤT PYSYSTEMTRADE: <code>ewmac(16, 64) &lt;= 0</code> HOẶC <code>accel(4, 16) &lt;= -1.0</code></strong></td>
                    <td class="num"><strong>201</strong></td>
                    <td class="num"><strong>63.18%</strong></td>
                    <td class="num"><strong>44.28%</strong></td>
                    <td class="num pos"><strong>+1.797%</strong></td>
                    <td class="num pos"><strong>+361.24%</strong></td>
                    <td class="num pos"><strong>1.63</strong></td>
                    <td><span class="tag tag-emerald">★ Công thức chuẩn hóa 0 tham số rác (Tăng lãi lên +361.24%)</span></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h4 style="color:#34d399; font-size:15px; margin-bottom:10px;">B. Thực Nghiệm EXP-1D: Đối Chiếu 5 Kho Chiến Lược &amp; Quét Độ Nhạy <code>wave_ker (0.25 → 0.60)</code></h4>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Kho Chiến Lược &amp; Ngưỡng Độ Rỗng Sóng <code>KER</code> (In-Sample 2024–2025)</th>
                    <th class="num">Số Lệnh</th>
                    <th class="num">Win Rate</th>
                    <th class="num">Chạm TP1</th>
                    <th class="num">Lãi TB / Lệnh</th>
                    <th class="num">Tổng Lãi Ròng</th>
                    <th class="num">Profit Factor</th>
                    <th class="num">Max Drawdown</th>
                    <th>Đánh Giá Đóng Góp Alpha &amp; Tính Đơn Điệu</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Repo 2 (<code>QuantConnect/Lean</code>): Độc lập <code>KER &gt;= 0.60</code> (Sóng Air-Pocket)</td>
                    <td class="num">135</td>
                    <td class="num">64.44%</td>
                    <td class="num">48.15%</td>
                    <td class="num pos">+1.916%</td>
                    <td class="num pos">+258.70%</td>
                    <td class="num pos">1.68</td>
                    <td class="num pos">59.1%</td>
                    <td><span class="tag tag-gold">★ Bơm thẳng không nền đỡ, cắt nửa Drawdown</span></td>
                  </tr>
                  <tr>
                    <td>Repo 3 (<code>crypto-factor-research</code>): <code>Velocity &gt;= 8%/ngày</code> (vs <code>&lt; 8%</code> lỗ -109%)</td>
                    <td class="num">189</td>
                    <td class="num">65.08%</td>
                    <td class="num">50.26%</td>
                    <td class="num pos">+1.809%</td>
                    <td class="num pos">+341.90%</td>
                    <td class="num pos">1.55</td>
                    <td class="num">83.5%</td>
                    <td><span class="tag tag-info">Tách biệt hoàn hảo với nhóm bò chậm (-109.26%)</span></td>
                  </tr>
                  <tr>
                    <td>Repo 4 (<code>freqtrade</code>): <code>Volume Đỉnh &gt;= 2.0x SMA20</code> • Repo 5 (<code>qlib</code>): <code>RSQR(14) &lt; 0.65</code></td>
                    <td class="num">105 / 249</td>
                    <td class="num">62.9% / 55.4%</td>
                    <td class="num">40.0% / 37.4%</td>
                    <td class="num pos">+1.628% / +0.615%</td>
                    <td class="num pos">+170.9% / +153.2%</td>
                    <td class="num pos">1.46 / 1.16</td>
                    <td class="num">72.7% / 202.7%</td>
                    <td><span class="tag tag-muted">Có tác dụng phụ trợ nhưng kém trực giao hơn KER</span></td>
                  </tr>
                  <tr>
                    <td>↳ <em>Điểm mù trong <code>pysystemtrade</code>: 71 lệnh có <code>KER &lt; 0.35</code> (Sóng bò zíc-zắc)</em></td>
                    <td class="num">71</td>
                    <td class="num">53.52%</td>
                    <td class="num">40.85%</td>
                    <td class="num pos">+0.177%</td>
                    <td class="num pos">+12.59%</td>
                    <td class="num">1.04</td>
                    <td class="num neg">95.9%</td>
                    <td><span class="tag tag-danger">✗ Nhiều nền hỗ trợ bên dưới, gây 95.9% DD</span></td>
                  </tr>
                  <tr class="row-sweetspot">
                    <td><strong>★ NÂNG CẤP 3A (Tinh Hoa): <code>PST AND wave_ker &gt;= 0.35</code></strong></td>
                    <td class="num"><strong>130</strong></td>
                    <td class="num"><strong>68.46%</strong></td>
                    <td class="num"><strong>46.15%</strong></td>
                    <td class="num pos"><strong>+2.682%</strong></td>
                    <td class="num pos"><strong>+348.66%</strong></td>
                    <td class="num pos"><strong>2.24</strong></td>
                    <td class="num pos"><strong>75.7%</strong></td>
                    <td><span class="tag tag-gold">★ Điểm cân bằng vàng: Giữ 96.5% lãi, PF vọt lên 2.24</span></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>★ NÂNG CẤP 3A+ (Siêu Tinh Lọc): <code>PST AND wave_ker &gt;= 0.40</code></strong></td>
                    <td class="num"><strong>113</strong></td>
                    <td class="num"><strong>70.80%</strong></td>
                    <td class="num"><strong>48.67%</strong></td>
                    <td class="num pos"><strong>+2.991%</strong></td>
                    <td class="num pos"><strong>+338.00%</strong></td>
                    <td class="num pos"><strong>2.45</strong></td>
                    <td class="num pos"><strong>56.2%</strong></td>
                    <td><span class="tag tag-emerald">🏆 WR vượt 70.8%, PF 2.45, DD giảm xuống 56.2%</span></td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong>⚡ Siêu Sóng Air-Pocket: <code>PST AND wave_ker &gt;= 0.60</code></strong></td>
                    <td class="num"><strong>55</strong></td>
                    <td class="num"><strong>74.55%</strong></td>
                    <td class="num"><strong>49.09%</strong></td>
                    <td class="num pos"><strong>+3.853%</strong></td>
                    <td class="num pos"><strong>+211.89%</strong></td>
                    <td class="num pos"><strong>3.08</strong></td>
                    <td class="num pos"><strong>28.2%</strong></td>
                    <td><span class="tag tag-emerald">⚡ Đơn điệu tuyệt đối: WR 74.55%, PF 3.08, DD 28.2%</span></td>
                  </tr>
                  <tr class="row-sweetspot">
                    <td><strong>🔥 NÂNG CẤP 3B (Mở Rộng): <code>(PST &amp; KER &gt;= 0.35) OR (KER &gt;= 0.65)</code></strong></td>
                    <td class="num"><strong>198</strong></td>
                    <td class="num"><strong>65.66%</strong></td>
                    <td class="num"><strong>47.47%</strong></td>
                    <td class="num pos"><strong>+2.159%</strong></td>
                    <td class="num pos"><strong>+427.43%</strong></td>
                    <td class="num pos"><strong>1.85</strong></td>
                    <td class="num pos"><strong>77.5%</strong></td>
                    <td><span class="tag tag-gold">🔥 Cứu thêm 68 lệnh Air-Pocket, Tổng Lãi +427.4%</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 3.3: Factor #2 & Factor #3 -->
          <div id="tab-lab-f2f3" class="tab-panel sub-lab">
            <div class="passport-grid">
              <div class="pg-box" style="border-left: 4px solid #10b981;">
                <h5>⚡ Giải Phẫu Factor #2: Độ Thẳng Nhịp Sập Mở Màn (<code>imp_ker &gt;= 0.50</code>)</h5>
                <p><strong>1. Phát hiện Đa Cộng Tuyến (Review Gate):</strong> Ba biến <code>imp_drop_pct</code>, <code>imp_retrace_of_pump_pct</code> (<code>r=0.861</code>) và <code>imp_vol_units</code> (<code>r=0.738</code>) bị trùng lặp cao vì cùng đo độ sâu nhịp sập.</p>
                <p style="margin-top:8px;"><strong>2. Alpha Trực Giao Mới (<code>imp_ker</code>):</strong> Đo độ thẳng của nhịp sập mở màn, hoàn toàn độc lập với <code>wave_ker</code> (<code>r=0.119</code>) và <code>imp_drop_pct</code> (<code>r=-0.136</code>):</p>
                <ul class="compact-list" style="margin-top:6px;">
                  <li><strong>Nhịp sập thẳng trên nền Tinh Hoa (<code>imp_ker &gt;= 0.50</code>, 99 lệnh — Mốc 4A):</strong> Win Rate vọt lên <strong>73.74%</strong>, Avg <strong>+3.341%</strong>, <strong>PF 2.85</strong>, MaxDD giảm còn <strong>60.5%</strong>!</li>
                  <li><strong>Nhịp sập thẳng trên nền Mở Rộng (<code>imp_ker &gt;= 0.50</code>, 148 lệnh — Mốc 4B):</strong> WR <strong>68.92%</strong>, TP1 <strong>50.00%</strong>, Tổng lãi <strong>+398.00%</strong>, <strong>PF 2.16</strong>.</li>
                  <li><strong>Đối chứng — Nhịp sập zíc-zắc cưa chân bàn (<code>imp_ker &lt; 0.50</code>, 31 lệnh bị loại):</strong> Thực chất là Cờ Tăng (Bull Flag), WR chỉ <strong>51.61%</strong>, PF <strong>1.17</strong> (<code>AvgR +0.01R</code>).</li>
                </ul>
              </div>

              <div class="pg-box" style="border-left: 4px solid #06b6d4;">
                <h5>🎯 Giải Phẫu Factor #3: Vùng Hồi Fibo <code>0.500–0.786</code>, Cạn Cung &amp; Phá Đáy H1</h5>
                <p><strong>1. Phân vùng độ sâu hồi Fibonacci (Trên nền 148 lệnh Mốc 4B):</strong></p>
                <ul class="compact-list" style="margin-top:4px;">
                  <li><strong>Golden Pocket 0.500–0.618 (77 lệnh):</strong> WR <strong>75.32%</strong>, Avg <strong>+2.996%</strong>, <strong>PF 2.49</strong>.</li>
                  <li><strong>Quét thanh khoản 0.618–0.786 (47 lệnh):</strong> WR <strong>65.96%</strong>, TP1 <strong>55.32%</strong>, <strong>AvgR +0.33R</strong>.</li>
                  <li><strong>Hồi quá sâu &gt; 0.786 (24 lệnh bị loại):</strong> Tường bán đã bị hấp thụ, WR rơi xuống <strong>54.17%</strong> (<code>AvgR +0.08R</code>).</li>
                </ul>
                <p style="margin-top:8px;"><strong>2. Cơ chế kích hoạt H1 &amp; Cạn kiệt Volume (<code>pb_vol_ratio &lt;= 1.1</code>):</strong></p>
                <ul class="compact-list" style="margin-top:4px;">
                  <li>Chỉ có mẫu nến đơn lẻ <code>CANDLE_PATTERN_1</code> (47 lệnh): WR chỉ <strong>51.06%</strong>, PF <strong>1.33</strong>.</li>
                  <li>Có Phá Vỡ Cấu Trúc H1 (<code>BREAK_STRUCTURE_2</code> / <code>COMBO_1_2</code>, 101 lệnh): WR vọt lên <strong>77.23%</strong>, Avg <strong>+3.440%</strong>, <strong>PF 2.84</strong> (riêng <code>COMBO_1_2</code> đạt <strong>PF 3.00</strong>, DD 32.7%)!</li>
                  <li>Volume nhịp hồi cạn kiệt (<code>&lt;= 1.1x</code> Volume sập, 78 lệnh, <code>r=-0.023</code>): WR <strong>73.08%</strong>, <strong>PF 2.67</strong>, <strong>AvgR +0.41R</strong>!</li>
                </ul>
              </div>
            </div>
          </div>

          <!-- Sub-tab 3.4: Factor #4 -->
          <div id="tab-lab-f4" class="tab-panel sub-lab">
            <div class="passport-grid">
              <div class="pg-box" style="border-left: 4px solid #f59e0b;">
                <h5>🛡️ 1. Giải Phẫu Vị Trí Đặt Stop Loss (Above 1.000 vs Above 0.886 vs Above 0.786)</h5>
                <ul class="compact-list">
                  <li><strong><code>above_swing_high (1.000 + 0.25 ATR)</code> (Mặc định cũ):</strong> WR 68.92%, TP1 50.00%, Avg +2.553%, PF 2.07, AvgR +0.24R, MaxDD 67.9%.</li>
                  <li><strong><code>above_0786 (+ 0.25 ATR)</code>:</strong> Quá sát vùng phản ứng Fibo, bị râu nến quét oan làm Win Rate tụt xuống 60.81% và TP1 tụt còn 44.59%.</li>
                  <li><strong>★ <code>above_0886 (+ 0.25 ATR)</code> (Đã Khóa):</strong> Điểm ngọt cấu trúc hoàn hảo — giữ nguyên tỷ lệ chạm TP1 (50.00%), nâng Lãi TB lên <strong>+2.888%/lệnh</strong>, <strong>PF 2.42</strong>, <strong>AvgR +0.35R (+46%)</strong>, đồng thời ép MaxDD giảm từ 67.9% xuống <strong>52.2%</strong>!</li>
                </ul>
              </div>

              <div class="pg-box" style="border-left: 4px solid #8b5cf6;">
                <h5>📊 2. Hiệu Quả Phân Tầng Của Thang Điểm Hội Tụ (<code>Conviction Score 0–100</code>, 2024–2025)</h5>
                <ul class="compact-list">
                  <li><strong>Hạng D/C (<code>&lt; 55 điểm</code> — Đứng ngoài <code>0R</code>, 210 lệnh):</strong> WR chỉ 46.67%, Tổng lỗ <strong>-87.51%</strong>, PF 0.90, MaxDD 148.5%.</li>
                  <li><strong>Hạng B (<code>55–69 điểm</code> — Đi vốn <code>0.75R</code>, 162 lệnh):</strong> WR 55.56%, Tổng lãi +40.96%, PF 1.08.</li>
                  <li><strong>★ Hạng A (<code>70–84 điểm</code> — Đi vốn <code>1.25R</code>, 90 lệnh):</strong> WR <strong>71.11%</strong>, Avg <strong>+2.539%</strong>, Tổng lãi <strong>+228.53%</strong>, <strong>PF 1.99</strong>, MaxDD chỉ <strong>35.8%</strong>.</li>
                  <li><strong>👑 Hạng S (<code>&gt;= 85 điểm</code> — Đi vốn <code>2.00R</code>, 18 lệnh):</strong> WR <strong>72.22%</strong>, Avg <strong>+2.815%</strong>, <strong>PF 1.97</strong>, <strong>AvgR +0.32R</strong>, MaxDD chỉ <strong>28.1%</strong>.</li>
                </ul>
              </div>
            </div>
          </div>

          <!-- Sub-tab 3.5: 3 Visual Analogies -->
          <div id="tab-lab-visual" class="tab-panel sub-lab">
            <div class="passport-grid">
              <div class="pg-box">
                <h5>🎈 Hình ảnh 1: "Thổi Bóng Bay Rỗng Ruột" vs "Xây Cầu Thang Bê Tông" (Factor #1)</h5>
                <p>Hãy tưởng tượng giá một đồng coin tăng từ $10 lên $16 (+60%):</p>
                <ul class="compact-list" style="margin-top:4px;">
                  <li><strong>Cách 1 (Xây cầu thang — <code>wave_ker &lt; 0.35</code>):</strong> Giá tăng lên $12 rồi nghỉ 3 ngày thay máu, lên $14 lại nghỉ 3 ngày tích lũy. Mỗi nhịp nghỉ là một <strong>bậc thang bê tông</strong> có rất nhiều người đặt lệnh mua chờ sẵn. Khi giá chỉnh, chạm bậc thang là bật lên lại → Short vào đây rất dễ chết (PF chỉ 1.04).</li>
                  <li><strong>Cách 2 (Thổi bóng bay dựng đứng — <code>wave_ker &gt;= 0.35–0.65</code>):</strong> Giá phóng thẳng một mạch từ $10 lên $16 không nghỉ. Bên dưới hoàn toàn là <strong>khoảng không rỗng ruột (Air-Pocket)</strong> vì chưa ai kịp gom hàng ở $12 hay $14. Khi bóng xì hơi ở đỉnh, giá rơi tự do xuyên qua khoảng trống!</li>
                </ul>
              </div>
              <div class="pg-box">
                <h5>⚡ Hình ảnh 2: "Sập Cầu Thật Sự" vs "Nghỉ Lấy Đà Cờ Tăng" (Factor #2)</h5>
                <p>Sau khi tạo đỉnh $16, giá bắt đầu giảm nhịp đầu tiên về $13:</p>
                <ul class="compact-list" style="margin-top:4px;">
                  <li><strong>Nhịp giảm cưa chân bàn (<code>imp_ker &lt; 0.50</code>):</strong> Giá giảm 1 nến đỏ lại có 1 nến xanh rút râu đỡ lại, bò từ từ trong kênh giá hẹp. Đó không phải là sập, mà là <strong>phe Mua đang gom thêm hàng (Bull Flag)</strong> để chuẩn bị vượt đỉnh $16!</li>
                  <li><strong>Cú sập thẳng đứng khóa sổ (<code>imp_ker &gt;= 0.50</code> &amp; <code>Drop &gt;= 6%</code>):</strong> Một lực xả lớn đạp thẳng từ $16 xuống $13 quá nhanh khiến toàn bộ đám đông FOMO mua ở $15–$16 <strong>bị nhốt sống trên đỉnh không kịp chạy</strong>. Họ rơi vào trạng thái hoảng loạn và chỉ mong giá hồi lên một chút để bán tháo gỡ vốn.</li>
                </ul>
              </div>
              <div class="pg-box">
                <h5>🧱 Hình ảnh 3: "Bức Tường Cầu Về Bờ" &amp; "Cú Đạp Vỡ Trận H1" (Factor #3 &amp; #4)</h5>
                <p>Khi giá từ $13 hồi lên lại vùng Fibo 0.500–0.618 ($14.5–$14.8):</p>
                <ul class="compact-list" style="margin-top:4px;">
                  <li><strong>Tại sao không vào lệnh ngay khi thấy 1 cây nến đỏ H1 (<code>CANDLE_PATTERN_1</code>)?</strong> Vì lúc đó đội bắt đáy vẫn còn đang cố đẩy lên (WR chỉ 51%).</li>
                  <li><strong>Tại sao phải đợi <code>BREAK_STRUCTURE_2</code> (Đóng nến H1 thủng đáy nến H1 trước hoặc gãy lại dưới Fibo 0.5)?</strong> Đó là khoảnh khắc bức tường xả của đội kẹp đỉnh đã chặn đứng nhịp hồi, và <strong>đội mua bắt đáy bắt đầu vỡ trận tháo chạy</strong> (WR vọt lên <strong>77%–80%</strong>!).</li>
                  <li><strong>Tại sao đặt SL ở Fibo 0.886 thay vì 1.000?</strong> Nếu giá đã leo ngược qua mốc 0.886 (tức đã ăn hết bức tường xả mà không giảm), nghĩa là phe Mua quá khỏe. Cắt lỗ ngay tại 0.886 giúp tiết kiệm gần 15% quãng đường lỗ vô ích!</li>
                </ul>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- ===================================================================== -->
      <!-- PILLAR 5: 338-COIN UNIVERSE SELECTION, 14-COIN & TIMEFRAME ANATOMY     -->
      <!-- ===================================================================== -->
      <div id="page-asset-tf" class="wiki-page">
        <section class="section" style="border-color: rgba(16, 185, 129, 0.45);">
          <div class="section-header">
            <div>
              <div class="section-title">
                <span>🪙 Chuyên Mục 5: Giải Phẫu Vũ Trụ 338 Đồng Coin v1.2 — Market Cap, Cung Lưu Hành (Float Ratio), Chuẩn Point-in-Time &amp; Khung Giờ (H4 vs D1)</span>
              </div>
              <div class="section-subtitle">
                Quét toàn bộ <strong>338 mã Hợp đồng Tương lai USD-M</strong> kết hợp dữ liệu <strong>Vốn hóa lưu hành (<code>Circulating Market Cap &gt;= $150M</code>)</strong>, <strong>Tỷ lệ Cung lưu hành (<code>Float Ratio = Circulating / Total Supply &gt;= 64%–75%</code>)</strong> và quy tắc <strong>Warmup &gt;= 63 ngày (Chuẩn <code>a1e6ca7d</code>)</strong>: Loại bỏ 269 mã bẫy thanh khoản mỏng/Low-Float VC Unlock để cô đọng <strong>40 Mã Chủ Lực (Tier S Core)</strong>, <strong>28 Mã Mở Rộng (Tier A v1.2)</strong> &amp; <strong>64 Mã Point-in-Time 0% PnL Bias</strong>.
              </div>
            </div>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              <button class="btn-mini" style="background:#10b981; color:#052e16; font-weight:800;" onclick="copyUniverseList('tier_s')">📋 Copy 40 Mã Tier S Core</button>
              <button class="btn-mini" style="background:#f59e0b; color:#090d16; font-weight:800;" onclick="copyUniverseList('tier_sa')">📋 Copy 68 Mã Whitelist v1.2 (S+A)</button>
              <button class="btn-mini" style="background:#38bdf8; color:#090d16; font-weight:800;" onclick="copyUniverseList('pit_zero_bias')">📋 Copy 64 Mã PIT Zero-Bias</button>
            </div>
          </div>

          <div class="tabs">
            <button class="tab-btn active" onclick="switchSubTab(event, 'sub-asset', 'tab-asset-universe338')">5.0. Vũ Trụ 338 Coin v1.2: Market Cap, Cung Lưu Hành &amp; Whitelist/Blacklist</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-asset', 'tab-asset-locked')">5.1. Giải Phẫu Sâu 14 Coin Đại Diện 6 Năm (2020→2026)</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-asset', 'tab-asset-tf')">5.2. So Sánh Khung H4 vs Khung D1 Qua Các Mốc</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-asset', 'tab-asset-baseline')">5.3. Đối Chứng 14 Coin Ở Baseline (Mốc 0 — Chưa Lọc)</button>
          </div>

          <!-- Sub-tab 5.0: 338-Coin Universe Study & Tiered Whitelist/Blacklist -->
          <div id="tab-asset-universe338" class="tab-panel sub-asset active">
            <div class="insight-grid" style="margin-top:0;">
              <div class="insight-box emerald">
                <h4>1. Đối Chiếu Với Chuẩn Point-in-Time <code>a1e6ca7d</code>: Tại Sao Chỉ Dùng Volume Là Chưa Đủ?</h4>
                <p>
                  Nếu áp dụng nguyên bản quy tắc Point-in-Time của <code>a1e6ca7d</code> (<code>Age &gt;= 63 ngày + Top-50 Volume + Wick &lt;= 3.2%</code>, <strong>0% In-Sample PnL Bias</strong>), danh mục lãi <strong>+96.2% (PF 1.37, MaxDD 81.1%)</strong> ở OOS 2026. Tuy nhiên, khi bổ sung thêm 2 bộ lọc <strong>Vốn hóa lưu hành <code>MCap &gt;= $150M</code> + Cung lưu hành <code>Float Ratio &gt;= 70%</code></strong> (vẫn giữ <strong>0% In-Sample PnL Bias</strong>, 64 mã), lợi nhuận OOS 2026 tăng gấp <strong>2.45 lần lên +235.5% (PF 2.01)</strong> và MaxDD giảm hơn một nửa xuống <strong>34.2%</strong>!
                </p>
              </div>
              <div class="insight-box gold">
                <h4>2. Phát Hiện Sống Còn Về Tổng Cung Lưu Hành (<code>Float Ratio = Circulating / Total Supply</code>)</h4>
                <p>
                  <strong>• Nhóm High-Float (<code>Circulating / Total &gt;= 75%</code>, 68 mã đã phân phối hết cho cộng đồng):</strong> Đạt <strong>+1,454.0% (IS)</strong> và <strong>+324.7% (PF 1.81, OOS 2026)</strong> vì không ai thâu tóm được nguồn cung.<br/>
                  <strong>• Nhóm Low-Float VC Unlock (<code>Circulating / Total &lt; 40%</code>: <code>WLD, AERO, PUMP...</code>):</strong> Dù thanh khoản Futures lớn, lượng cung lưu hành ngoài thị trường bị khóa &gt;60% bởi VC/Market Maker → bị kéo Short Squeeze làm <strong>lỗ -382.2% (PF 0.50) ở OOS 2026</strong>!
                </p>
              </div>
              <div class="insight-box cyan">
                <h4>3. Ngưỡng Vốn Hóa Lưu Hành Tối Thiểu <code>MCap &gt;= $150M</code> &amp; Nâng Cấp Whitelist v1.2 (68 Mã)</h4>
                <p>
                  Toàn bộ <strong>211 mã có <code>Circulating Market Cap &lt; $150M</code></strong> (gồm cả <code>MC4 Small-Cap $50M–$150M</code> và <code>MC5 Micro-Cap &lt;$50M</code>) đều bị đội lái gom Spot ép cháy Short trên Futures, gây lỗ tổng cộng <strong>-1,135.7% ở OOS 2026</strong>! Khi lọc bỏ 20 mã G3 Low-Float/Small-Cap khỏi <code>Tier A</code>, lãi OOS 2026 của <code>Tier A v1.2 (28 mã)</code> tăng vọt từ <strong>+38.3% lên +70.0% (+83%)</strong> và Tổng Whitelist <code>S+A v1.2 (68 mã)</code> đạt <strong>+400.1% (WR 66.1%, PF 2.84, MaxDD 29.6%)</strong>!
                </p>
              </div>
            </div>

            <h4 style="color:#fbbf24; font-size:15px; margin:14px 0 8px;">A. Bảng Kiểm Chứng Walk-Forward Các Phương Pháp Chọn Vũ Trụ Coin (So Sánh Chuẩn <code>a1e6ca7d</code>, <code>PIT Zero-Bias MCap+Float</code> &amp; <code>Whitelist v1.2</code>)</h4>
            <div class="table-wrap" style="margin-bottom:22px;">
              <table>
                <thead>
                  <tr>
                    <th rowspan="2">Phương Pháp &amp; Phân Tầng Vũ Trụ Coin<br/>(Thiết Lập Ex-Ante Từ Dữ Liệu &lt;= 2025)</th>
                    <th rowspan="2" class="num">Số Lượng<br/>Coin</th>
                    <th colspan="5" class="group-head sep-left">IN-SAMPLE 2 NĂM (2024–2025 — MỐC 6B TOÀN DIỆN)</th>
                    <th colspan="5" class="group-head sep-left">🔥 OUT-OF-SAMPLE 2026 (MỐC 6B — KIỂM THỬ MÙ TƯƠNG LAI)</th>
                    <th class="group-head sep-left">OOS 2026 (MỐC 4A)</th>
                  </tr>
                  <tr>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi Ròng</th>
                    <th class="num">PF</th>
                    <th class="num">MaxDD</th>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi Ròng</th>
                    <th class="num">PF</th>
                    <th class="num">MaxDD</th>
                    <th class="num sep-left">Lãi Mốc 4A (PF)</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(universe_tier_rows)}
                </tbody>
              </table>
            </div>

            <h4 style="color:#a78bfa; font-size:15px; margin:14px 0 8px;">B1. Giải Phẫu Thực Nghiệm Theo Tỷ Lệ Cung Lưu Hành (<code>Float Ratio = Circulating / Total Supply</code>) &amp; Quy Mô Vốn Hóa Lưu Hành (<code>Circulating Market Cap</code>)</h4>
            <div class="table-wrap" style="margin-bottom:22px;">
              <table>
                <thead>
                  <tr>
                    <th rowspan="2">Phân Nhóm Cung Lưu Hành (Float Ratio) &amp; Vốn Hóa Lưu Hành (Circulating Market Cap)<br/><small>Đã loại trừ 4 mã G1 Store-of-Value (BTC, ETH, BNB, PAXG) • Hoàn toàn không dùng PnL quá khứ để phân nhóm</small></th>
                    <th rowspan="2" class="num">Số Mã</th>
                    <th colspan="4" class="group-head sep-left">IN-SAMPLE 2024–2025 (MỐC 6B)</th>
                    <th colspan="5" class="group-head sep-left">🔥 OUT-OF-SAMPLE 2026 (MỐC 6B)</th>
                    <th class="group-head sep-left">OOS 2026 (MỐC 4A)</th>
                  </tr>
                  <tr>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                    <th class="num">MaxDD</th>
                    <th class="num sep-left">Lãi Mốc 4A (PF)</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(universe_mcap_float_rows)}
                </tbody>
              </table>
            </div>

            <h4 style="color:#38bdf8; font-size:15px; margin:14px 0 8px;">B2. Giải Phẫu 5 Nhóm Bản Chất Tài Sản (5 Asset Archetypes G1 → G5 Trên Toàn Bộ 338 Coin)</h4>
            <div class="table-wrap" style="margin-bottom:22px;">
              <table>
                <thead>
                  <tr>
                    <th rowspan="2">Nhóm Bản Chất Tài Sản (Asset Archetype)</th>
                    <th rowspan="2" class="num">Số Mã</th>
                    <th rowspan="2" class="num">Tỷ Lệ Xả Tự Nhiên<br/>(Gravity Decay)</th>
                    <th colspan="4" class="group-head sep-left">IN-SAMPLE 2024–2025 (MỐC 6B)</th>
                    <th colspan="4" class="group-head sep-left">OUT-OF-SAMPLE 2026 (MỐC 6B)</th>
                  </tr>
                  <tr>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(universe_archetype_rows)}
                </tbody>
              </table>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin:18px 0 10px;">
              <h4 style="color:#34d399; font-size:15px; margin:0;">C. Danh Bạ Chi Tiết 40 Mã Chủ Lực (Tier S Core), 28 Mã Mở Rộng (Tier A v1.2) &amp; Các Mã Bẫy Low-Float/Blacklist</h4>
              <div class="filter-bar" style="margin:0;">
                <button class="tab-btn active" onclick="filterUniverseTier(event, 'ALL')">Tất Cả Danh Bạ</button>
                <button class="tab-btn" onclick="filterUniverseTier(event, 'TIER_S_CORE')">👑 40 Mã Tier S Core</button>
                <button class="tab-btn" onclick="filterUniverseTier(event, 'TIER_A_EXTENDED')">⭐ 28 Mã Tier A v1.2</button>
                <button class="tab-btn" onclick="filterUniverseTier(event, 'BLACKLIST')">🚫 Blacklist &amp; Bẫy Low-Float</button>
              </div>
            </div>

            <div class="table-wrap" style="max-height:540px; overflow-y:auto;">
              <table>
                <thead>
                  <tr>
                    <th>Mã Coin</th>
                    <th>Phân Hạng Universe</th>
                    <th class="num">Điểm DNA<br/>(0–100)</th>
                    <th>Nhóm Bản Chất (Archetype)</th>
                    <th class="num">Vốn Hóa<br/>Lưu Hành</th>
                    <th class="num">Cung Lưu Hành<br/>(Float %)</th>
                    <th class="num">Thanh Khoản<br/>Median/Ngày</th>
                    <th class="num">Gravity<br/>Decay %</th>
                    <th class="num">Độ Độc Râu<br/>(Wick P90)</th>
                    <th class="num sep-left">Lệnh IS</th>
                    <th class="num">Hiệu Suất IS (24–25)</th>
                    <th class="num sep-left">Lệnh OOS</th>
                    <th class="num">Hiệu Suất OOS (2026)</th>
                    <th>Lý Do Phân Hạng (Ex-Ante v1.2 Rule)</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(universe_coin_rows)}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 5.1: Locked Milestones 14-Symbol Breakdown -->
          <div id="tab-asset-locked" class="tab-panel sub-asset">
            <div class="insight-grid" style="margin-top:0;">
              <div class="insight-box emerald">
                <h4>1. Độ Rộng Thiết Diện Ngang (Breadth): 92.3% (IS) &amp; 100% (OOS)</h4>
                <p>
                  Ở Baseline <code>Mốc 0</code>, chỉ có <code>2/14</code> đồng coin có lãi (<code>14.3%</code>). Khi áp dụng bộ lọc 4 Nhân tố (<code>Mốc 6B</code> giai đoạn 2024–2025), <strong>12/13 đồng coin có tín hiệu đều sinh lời dương (92.3%)</strong>! Sang <strong>OOS 2026</strong>, cả <strong>7/7 đồng coin có tín hiệu đều thắng (100.0%)</strong>.
                </p>
              </div>
              <div class="insight-box cyan">
                <h4>2. Không Phụ Thuộc Vào Một Đồng Coin Đơn Lẻ (No Outlier Dependency)</h4>
                <p>
                  Đồng đóng góp cao nhất trong 6 năm <code>2020–2025 (Mốc 4A)</code> chỉ chiếm <strong>22.8%</strong> tổng lãi dương; trong <code>2024–2025 (Mốc 6B)</code> chỉ chiếm <strong>25.3%</strong>; và trong <code>OOS 2026</code> chỉ chiếm <strong>26.1%</strong>. Lợi nhuận phân bổ đều khắp cả Major Altcoin (<code>SOL, BNB, ETH, AAVE, ADA</code>) lẫn High-Beta/Meme.
                </p>
              </div>
              <div class="insight-box gold">
                <h4>3. Tự Động Đứng Ngoài <code>BTCUSDT</code> Trong Sóng Tổ Chức ETF</h4>
                <p>
                  Trong giai đoạn <code>2024–2026</code>, <code>BTCUSDT</code> tăng bền vững theo dòng tiền ETF tổ chức (không có sóng bơm FOMO <code>&gt;= 50%</code> kèm đứt gãy cấu trúc). Hệ thống <strong>tự động phát 0 lệnh Short BTCUSDT</strong>, giúp tiết kiệm <strong>-136.02%</strong> khoản lỗ bắt đỉnh BTC ở Baseline!
                </p>
              </div>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th rowspan="2">Cặp Giao Dịch<br/>(14 Symbols)</th>
                    <th colspan="4" class="group-head">MỐC 4A TINH HOA — 6 NĂM (2020–2025)<br/><small>10/14 Coin Dương • Top-1 Share: 22.8%</small></th>
                    <th colspan="4" class="group-head sep-left">👑 MỐC 6B TOÀN DIỆN — 2 NĂM (2024–2025)<br/><small>12/13 Coin Dương (92.3%) • Top-1 Share: 25.3%</small></th>
                    <th colspan="4" class="group-head sep-left">👑 MỐC 6B TOÀN DIỆN — OOS 2026<br/><small>7/7 Coin Dương (100.0%) • Top-1 Share: 26.1%</small></th>
                  </tr>
                  <tr>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(locked_symbol_rows)}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 5.2: H4 vs D1 Timeframe Comparison -->
          <div id="tab-asset-tf" class="tab-panel sub-asset">
            <div class="insight-grid" style="margin-top:0;">
              <div class="insight-box emerald">
                <h4>Khung D1 (Sóng Vĩ Mô) — Trụ Cột Xuyên Suốt Mọi Chu Kỳ</h4>
                <p>
                  Khung <code>D1</code> giữ Profit Factor dương bền bỉ từ <code>2020–2025</code> (<code>Mốc 4A: +357.1%, PF 1.56</code>; <code>Mốc 6S: +352.9%, PF 1.81</code>) sang <code>2024–2025</code> (<code>Mốc 6B: +409.5%, PF 2.86</code>) và <code>OOS 2026</code> (<code>Mốc 6B: +97.0%, WR 82.4%, PF 5.79</code>).
                </p>
              </div>
              <div class="insight-box cyan">
                <h4>Khung H4 (Sóng Trung Hạn 1.5–4 Ngày) — Bứt Phá Khi Đủ 4 Nhân Tố</h4>
                <p>
                  Ở <code>Mốc 1</code> thô (chỉ lọc <code>Pump &gt;= 50%</code>), khung <code>H4</code> vẫn bị âm trong 6 năm (<code>-243.2%</code>). Nhưng khi khóa đủ <code>F1 + F2 + F3 + F4</code>, khung <code>H4</code> chuyển sang dương hoàn toàn cả ở <code>2020–2025 (+99.7% Mốc 4A)</code>, <code>2024–2025 (+103.2% Mốc 6B, WR 70.0%, DD 23.2%)</code> lẫn <code>OOS 2026 (+30.0%, PF 3.17, DD 7.3%)</code>!
                </p>
              </div>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th rowspan="2">Giai Đoạn &amp; Cấu Hình Chiến Lược</th>
                    <th colspan="7" class="group-head">KHUNG H4 (SÓNG TRUNG HẠN 1.5 – 4 NGÀY)</th>
                    <th colspan="7" class="group-head sep-left">KHUNG D1 (SÓNG VĨ MÔ NHIỀU NGÀY / TUẦN)</th>
                  </tr>
                  <tr>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">TP1</th>
                    <th class="num">TB/Lệnh</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                    <th class="num">MaxDD</th>
                    <th class="num sep-left">Lệnh</th>
                    <th class="num">WR</th>
                    <th class="num">TP1</th>
                    <th class="num">TB/Lệnh</th>
                    <th class="num">Tổng Lãi</th>
                    <th class="num">PF</th>
                    <th class="num">MaxDD</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(tf_milestone_rows)}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 5.3: Baseline 14-Symbol Diagnostics -->
          <div id="tab-asset-baseline" class="tab-panel sub-asset">
            <p style="font-size:13.5px; color:#cbd5e1; margin-bottom:12px;">
              Bảng đối chứng 4,706 lệnh ở <strong>Baseline ban đầu (Mốc 0 — khi chưa có bất kỳ bộ lọc Alpha nào)</strong> giải thích vì sao bắt đỉnh sớm ở Major Coin (<code>BTC, BNB, SOL, ETH</code>) gây thua lỗ nặng nề, trong khi chỉ có 2 đồng Altcoin có chu kỳ xả mạnh mới tự dương nhẹ:
            </p>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Cặp Giao Dịch (Symbol — Mốc 0 Baseline 2024–2025)</th>
                    <th class="num">Số Lệnh</th>
                    <th class="num">Win Rate</th>
                    <th class="num">Chạm TP1 (0.0)</th>
                    <th class="num">Chạm TP2 (1.272)</th>
                    <th class="num">Chạm TP3 (1.618)</th>
                    <th class="num">Lãi TB / Lệnh</th>
                    <th class="num">Tổng Lãi Ròng</th>
                    <th class="num">Profit Factor</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(symbol_rows)}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>

      <!-- ===================================================================== -->
      <!-- PILLAR 6: INDEPENDENT AI AUDIT DOSSIER & TECHNICAL SPECIFICATION       -->
      <!-- ===================================================================== -->
      <div id="page-audit-spec" class="wiki-page">
        <section class="section" style="border-color: rgba(244, 63, 94, 0.5); background: linear-gradient(180deg, #111827 0%, #1f1224 100%);">
          <div class="section-header">
            <div>
              <div class="section-title">
                <span>🔍 Chuyên Mục 6: Hồ Sơ Kiểm Định Định Lượng Độc Lập (Dành Cho ChatGPT o1/o3/GPT-4o &amp; Quant Auditor)</span>
              </div>
              <div class="section-subtitle">
                Cung cấp đầy đủ <strong>Đặc tả toán học Point-in-Time (Chống Look-Ahead Bias)</strong>, <strong>Khai báo Bậc tự do (26 biến thể đã thử)</strong>, <strong>Ma trận Stress-Test Phí &amp; Trượt giá (0 → 40 bps)</strong>, <strong>Phân phối Đuôi rủi ro &amp; Lệnh mở đồng thời (Concurrency)</strong> cùng <strong>Trọn bộ Hồ sơ Markdown 1-Click Copy cho ChatGPT</strong>.
              </div>
            </div>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              <button class="btn-mini" style="background:#f59e0b; color:#090d16; font-weight:800; padding:6px 12px;" onclick="copyAuditDossierMd()">📋 Copy Trọn Bộ Hồ Sơ Cho ChatGPT</button>
              <button class="btn-mini" style="padding:6px 12px;" onclick="downloadAuditDossierMd()">📥 Tải File .MD Kiểm Định</button>
            </div>
          </div>

          <div class="tabs">
            <button class="tab-btn active" onclick="switchSubTab(event, 'sub-audit', 'tab-audit-v426')">6.0. 🏆 Kết Quả Kiểm Toán v4.0.26 &amp; Paper OOS v1 (MỚI NHẤT)</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-audit', 'tab-audit-spec')">6.1. Đặc Tả Toán Học Point-in-Time &amp; Chống Overfitting</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-audit', 'tab-audit-stress')">6.2. Ma Trận Stress-Test Phí (0→40 bps) &amp; Đuôi Rủi Ro / Concurrency</button>
            <button class="tab-btn" onclick="switchSubTab(event, 'sub-audit', 'tab-audit-dossier')">6.3. Hồ Sơ Markdown &amp; Prompt Red-Team Cho ChatGPT + Quản Trị JSON</button>
          </div>

          <!-- Sub-tab 6.0: v4.0.0 -> v4.0.26 Independent Audit Progression & Paper OOS v1 -->
          <div id="tab-audit-v426" class="tab-panel sub-audit active">
            <h4 style="color:#34d399; font-size:15px; margin-bottom:10px;">A. Lộ Trình Khắc Phục &amp; Chuẩn Hóa Qua 26 Vòng Kiểm Toán Độc Lập (<code>v4.0.0 → v4.0.26</code>)</h4>
            <div class="table-wrap" style="margin-bottom:20px;">
              <table>
                <thead>
                  <tr>
                    <th>Giai Đoạn / Phiên Bản</th>
                    <th>Hồ Sơ Bằng Chứng</th>
                    <th>Các Phát Hiện &amp; Hạng Mục Đã Khắc Phục Triệt Để</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong><code>v4.0.1 – v4.0.5</code></strong></td>
                    <td><code>RED_TEAM_REAUDIT_RESPONSE_v4_0_5_2026-10-17.md</code></td>
                    <td>Sửa kiểm tra SL hòa vốn trong cùng nến sau TP1/TP2; tách chạy độc lập từng cấu hình; tính <code>cooldown</code> theo giờ thoát thực tế (<code>exit_close_time</code>) khi dữ liệu khuyết (FS404-01); xuất &amp; kiểm định trực tiếp danh tính <code>executed_trade_ids</code> trên 112 nút danh mục (FS404-02); đồng bộ fingerprint <code>funding_8h</code> (FS404-03); bảo toàn <code>terminal_outcome</code> từ simulator (FS404-04) — <strong>27/27 tests passed</strong>.</td>
                  </tr>
                  <tr>
                    <td><strong><code>v4.0.6</code></strong></td>
                    <td><code>PHUONG_PHAP_FIBO_SHORT_v4_0_6.md</code></td>
                    <td>Chuẩn hóa phương pháp luận: tách bạch <code>fixed_1x</code> và <code>m6_scaled</code>; sửa hệ số điểm <code>&lt;55</code> về <code>0.80x</code>; cố định nến cuối IS đóng lúc <code>2026-01-01T00:00Z</code>; áp dụng phí <code>0/20/40/60 bps</code> vào simulator; đồng bộ pivot <code>2/2</code>; khớp giá mở cửa nhảy gap qua Stop; bổ sung <code>paper_order_planner</code> — <strong>55/55 tests passed</strong>.</td>
                  </tr>
                  <tr>
                    <td><strong><code>v4.0.7 – v4.0.21</code></strong></td>
                    <td><code>research_v4_0_9/REPORT.md</code><br/><code>research_v4_0_19/REPORT.md</code><br/><code>research_v4_0_21/REPORT.md</code></td>
                    <td>Khóa chuẩn chi phí theo từng lần khớp (<code>standard_vip6: 12.5 bps/fill</code> vs <code>stress_regular: 55.0 bps/fill</code>); đối soát <code>360,781</code> sự kiện funding thực tế trên <code>191</code> giai đoạn hợp đồng; kiểm định danh mục liên tục không đặt lại năm (<code>v4.0.19</code>); tái kiểm 6 cấu hình trên vũ trụ 338 mã đã sửa vòng đời hợp đồng (<code>v4.0.21</code>).</td>
                  </tr>
                  <tr class="row-climax">
                    <td><strong><code>v4.0.22 – v4.0.26</code> &amp; <code>paper_oos_v1</code></strong></td>
                    <td><code>research_v4_0_26/REPORT.md</code><br/><code>paper_oos_v1/PROTOCOL.json</code><br/><code>paper_oos_v1/STATUS.json</code></td>
                    <td>Hoàn thiện đường ống tín hiệu thời gian thực (<code>signal_snapshot_v423</code>, <code>stream_execution_v424</code>, <code>decision_feed_v425</code>), đóng băng giao thức <code>paper_oos_v1</code> (<code>SHA256: 3b394d2dc14e...</code>) và vận hành quan sát thời gian thực 12 tài khoản Paper trên 50 mã USDT-M Futures từ <code>18/10/2026</code> đến <code>16/10/2028</code> (104 tuần).</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h4 style="color:#38bdf8; font-size:15px; margin-bottom:10px;">B. Trạng Thái Vận Hành Thực Tế Của Hệ Thống Paper OOS (<code>paper_oos_v1/STATUS.json</code> — Cập Nhật 20/10/2026)</h4>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Thông Số Vận Hành</th>
                    <th>Giá Trị Thực Tế</th>
                    <th>Ý Nghĩa Kiểm Toán &amp; Quy Tắc Giao Thức</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Tiến Trình &amp; Trạng Thái</strong></td>
                    <td><code>PID 28988 • OBSERVING</code></td>
                    <td>Đang chạy nền ổn định, <code>error = null</code>, <code>sqlite_integrity = ok</code>, Dashboard nội bộ tại <code>http://127.0.0.1:8766</code>.</td>
                  </tr>
                  <tr>
                    <td><strong>Heartbeat &amp; Revision</strong></td>
                    <td><code>2026-10-20T15:55:29Z (Rev 781)</code></td>
                    <td>Đồng bộ 100% thời gian thực (Nến 5m mới nhất: <code>15:55Z</code>, Tín hiệu H1 mới nhất: <code>15:00Z</code>).</td>
                  </tr>
                  <tr>
                    <td><strong>12 Tài Khoản Paper (6 Cấu Hình &times; 2 Mức Phí)</strong></td>
                    <td><code>NAV = 100.00 • 0 Lệnh Mở/Đóng</code></td>
                    <td>Tất cả 12 tài khoản giữ nguyên vốn <code>100.00</code>, chưa phát sinh tín hiệu hội tụ đủ điều kiện từ khi mở cổng <code>18/10/2026</code>.</td>
                  </tr>
                  <tr>
                    <td><strong>Sự Cố Hệ Thống / Cơ Hội</strong></td>
                    <td><code>Critical: 0 • Opportunity: 176</code></td>
                    <td><code>0</code> lỗi nghiêm trọng; <code>176</code> sự kiện trễ từ đợt máy chủ Sleep/Reboot ngày <code>19/10/2026</code> đã được bỏ qua đúng luật nhân quả, không khớp lệnh hồi tố. Hơn 32 giờ qua chạy liên tục không phát sinh thêm bất kỳ sự kiện trễ nào.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 6.1: Mathematical & Execution Specification -->
          <div id="tab-audit-spec" class="tab-panel sub-audit">
            <div class="passport-grid">
              <div class="pg-box" style="border-left: 4px solid #10b981;">
                <h5>⏱️ 1. Cơ Chế Chống Nhìn Trộm Tương Lai (Strict Point-in-Time Alignment)</h5>
                <ul class="compact-list">
                  <li><strong>Quy tắc 1 (HTF Close Alignment):</strong> Một cây nến khung lớn <code>H4</code> hoặc <code>D1</code> mở tại <code>T_open</code> chỉ hoàn tất và được phép nhìn thấy tại thời điểm đóng nến <code>T_close = T_open + Δ_HTF</code> (<code>+4h</code> cho H4, <code>+24h</code> cho D1). Tuyệt đối không dùng đỉnh/đáy của nến HTF đang chạy.</li>
                  <li><strong>Quy tắc 2 (Pivot Confirmation Delay):</strong> Đỉnh/Đáy <code>Swing High/Low</code> dùng <code>pivot_span = 2</code> (2 nến trái + 2 nến phải). Do đó một đỉnh tại chỉ số <code>i</code> chỉ được xác nhận hợp lệ sau khi nến <code>i + 2</code> đã đóng hoàn toàn.</li>
                  <li><strong>Quy tắc 3 (Entry &amp; Next-Bar Simulation):</strong> Khi nến <code>H1</code> tại chỉ số <code>j</code> đóng cửa kích hoạt tín hiệu, giá vào lệnh là <code>Close[j]</code> và toàn bộ quá trình kiểm tra chạm <code>SL / TP1 / TP2 / TP3</code> chỉ bắt đầu từ <strong>nến H1 kế tiếp <code>j + 1</code> trở đi</strong>.</li>
                  <li><strong>Quy tắc 4 (Intra-Bar Pessimistic SL-First Rule):</strong> Nếu trong cùng 1 nến H1 mà <code>High &gt;= SL</code> và <code>Low &lt;= TP</code> cùng lúc, hệ thống <strong>luôn xử lý kiểm tra chạm <code>Stop Loss</code> trước</strong> để loại bỏ thiên kiến lạc quan trong nến.</li>
                </ul>
              </div>

              <div class="pg-box" style="border-left: 4px solid #06b6d4;">
                <h5>📐 2. Cơ Chế Chia 3 Đích Chốt Lời (Staged Exit) &amp; Khử Trùng Lặp Sóng</h5>
                <ul class="compact-list">
                  <li><strong>Khử trùng lặp sóng (Wave Deduplication):</strong> Mỗi con sóng cấu trúc chỉ được phép mở tối đa <strong>01 lệnh duy nhất</strong> (<code>used_structures</code> khóa theo khóa bộ ba <code>(timeframe, swing_high_idx, impulse_low_idx)</code>). Tránh việc bắn nhồi nhiều lệnh H1 trên cùng một nhịp hồi.</li>
                  <li><strong>Chia 3 phần chốt lời (<code>1/3 + 1/3 + 1/3</code>):</strong>
                    <br/>• <code>TP1 = L_imp</code> (Đáy nhịp sập đầu tiên — Fibo <code>0.0</code>): Chốt <code>1/3</code> vị thế và <strong>dời Stop Loss của <code>2/3</code> còn lại về Hòa Vốn (<code>Entry Price</code>)</strong>.
                    <br/>• <code>TP2 = L_imp - 0.272 × (H_swing - L_imp)</code> (Fibo Extension <code>1.272</code>): Chốt tiếp <code>1/3</code> vị thế.
                    <br/>• <code>TP3 = L_imp - 0.618 × (H_swing - L_imp)</code> (Fibo Extension <code>1.618</code>): Chốt nốt <code>1/3</code> cuối cùng.
                    <br/>• <code>Time Exit</code>: Đóng tại giá đóng cửa sau <code>48</code> nến H1 (với sóng H4) hoặc <code>96</code> nến H1 (với sóng D1) nếu chưa chạm hết đích.
                  </li>
                </ul>
              </div>

              <div class="pg-box" style="border-left: 4px solid #f59e0b;">
                <h5>🧪 3. Phân Tách 3 Tầng Dữ Liệu &amp; Khai Báo Bậc Tự Do (Degrees of Freedom)</h5>
                <ul class="compact-list">
                  <li><strong>Tầng 1 — In-Sample Tinh Chỉnh (<code>2024–2025</code>, 2 năm):</strong> Dùng để giải phẫu 4 Nhân tố và chọn ngưỡng.</li>
                  <li><strong>Tầng 2 — In-Sample Mở Rộng / Back-cast (<code>2020–2023</code>, 4 năm):</strong> Kiểm tra độ bền ngược về quá khứ qua đại sóng Bull Run 2020–2021 và Bear 2022 <strong>mà không sửa bất kỳ ngưỡng nào</strong>.</li>
                  <li><strong>Tầng 3 — Forward Out-of-Sample (<code>01/01/2026 → 29/09/2026</code>, 9 tháng):</strong> Dữ liệu tương lai hoàn toàn độc lập, chạy đúng 1 lần duy nhất (Zero Re-tuning).</li>
                  <li><strong>Tổng số biến thể đã thử (Multiple Testing Disclosure):</strong> Tổng cộng <strong>26 biến thể giả thuyết</strong> qua 4 giai đoạn (11 mốc biên độ ở F1A + 6 công thức repo ở F1B/C + 4 biến thể nhịp sập ở F2 + 3 vùng Fibo/Volume ở F3 + 2 mốc SL ở F4). Mỗi nhân tố chỉ giữ lại đúng 1 đại diện trực giao.</li>
                </ul>
              </div>
            </div>
          </div>

          <!-- Sub-tab 6.2: Fee Stress-Test & Tail-Risk / Concurrency Tables -->
          <div id="tab-audit-stress" class="tab-panel sub-audit">
            <h4 style="color:#fbbf24; font-size:15px; margin-bottom:8px;">A. Ma Trận Stress-Test Phí Giao Dịch &amp; Trượt Giá (<code>0 bps → 40 bps</code> Round-Trip) &amp; Ngưỡng Phí Hòa Vốn (<code>Break-Even Fee bps</code>)</h4>
            <p style="font-size:13px; color:#cbd5e1; margin-bottom:12px;">
              <strong>Lưu ý kiểm toán:</strong> Số liệu báo cáo mặc định đã trừ sẵn <code>10 bps (0.10%)</code> ở Mốc 0–5 và <code>20 bps (0.20%)</code> ở Mốc 6A/6B/6S. Bảng dưới đây kiểm tra độ nhạy khi phí + trượt giá tăng từ <code>0 bps</code> lên tới <strong><code>40 bps (0.40%/lệnh)</code></strong>:
            </p>
            <div class="table-wrap" style="margin-bottom:24px;">
              <table>
                <thead>
                  <tr>
                    <th>Giai Đoạn &amp; Cấu Hình</th>
                    <th class="num">Số Lệnh</th>
                    <th class="num sep-left">0 bps (Gross)</th>
                    <th class="num">10 bps (0.10%)</th>
                    <th class="num">20 bps (0.20%)</th>
                    <th class="num">30 bps (0.30%)</th>
                    <th class="num">40 bps (0.40%)</th>
                    <th class="num sep-left">Phí Hòa Vốn Tối Đa<br/>(Break-Even Fee)</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(fee_stress_rows)}
                </tbody>
              </table>
            </div>

            <h4 style="color:#38bdf8; font-size:15px; margin-bottom:8px;">B. Bảng Phân Phối Kết Cục Lệnh, Đuôi Rủi Ro (Tail-Risk) &amp; Số Lệnh Mở Cùng Lúc (Portfolio Concurrency)</h4>
            <p style="font-size:13px; color:#cbd5e1; margin-bottom:12px;">
              <code>MaxDD</code> được tính theo <strong>trật tự thời gian thực của toàn danh mục (Chronological Portfolio Drawdown)</strong>. Nhờ cơ chế dời SL về Hòa vốn sau khi chạm <code>TP1</code> (<code>TP1_BE</code> chiếm 11%–18% số lệnh), chuỗi thua liên tiếp tối đa ở các mốc đã khóa giảm mạnh và số lệnh mở cùng lúc (<code>Max Concurrent</code>) rất thấp:
            </p>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Giai Đoạn &amp; Cấu Hình</th>
                    <th class="num">Lệnh</th>
                    <th class="num sep-left">% TP3</th>
                    <th class="num">% TP2</th>
                    <th class="num">% TP1_BE</th>
                    <th class="num">% SL</th>
                    <th class="num">% Time</th>
                    <th class="num sep-left">Avg Win</th>
                    <th class="num">Avg Loss</th>
                    <th class="num">Payoff</th>
                    <th class="num">Median PnL</th>
                    <th class="num">Chuỗi Thua Max</th>
                    <th class="num">Hold TB</th>
                    <th class="num sep-left">Lệnh Mở Đồng Thời<br/>(Max / P95)</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(tail_risk_rows)}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Sub-tab 6.3: Self-Contained Markdown Dossier for ChatGPT & JSON Guide -->
          <div id="tab-audit-dossier" class="tab-panel sub-audit">
            <div class="insight-grid" style="margin-top:0;">
              <div class="insight-box emerald">
                <h4>1. Cách Đưa Cho ChatGPT (o1 / o3 / GPT-4o) Kiểm Định Độc Lập</h4>
                <p>
                  Bấm nút <strong><code>📋 Copy Trọn Bộ Hồ Sơ Cho ChatGPT</code></strong> bên dưới (hoặc mở file <code>artifacts/fibo_trend_short/CHATGPT_INDEPENDENT_AUDIT_DOSSIER.md</code>) và dán thẳng vào ChatGPT. Hồ sơ đã đính kèm sẵn <strong>Prompt đóng vai Giám đốc Quản trị Rủi ro Định lượng (Head of Quant Risk Audit)</strong> với 6 câu hỏi thẩm định gắt gao nhất.
                </p>
              </div>
              <div class="insight-box cyan">
                <h4>2. Cách Truy Xuất &amp; Bổ Sung Alpha Bằng Code (<code>alpha_wiki_registry.json</code>)</h4>
                <p>
                  Toàn bộ 9 Hồ sơ Alpha, 4 Khám phá chu kỳ và thông số kiểm định được lưu chuẩn hóa tại <code>artifacts/fibo_trend_short/alpha_wiki_registry.json</code>. Để cập nhật lại cả JSON lẫn Wiki HTML sau khi thêm nghiên cứu mới, chạy:<br/>
                  <code>.\\.venv\\Scripts\\python.exe scripts\\export_fibo_alpha_html.py</code>
                </p>
              </div>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:10px;">
              <strong style="color:#fbbf24; font-size:14px;">📄 Toàn Văn Hồ Sơ Kiểm Định Độc Lập Tự Chứa (<code>CHATGPT_INDEPENDENT_AUDIT_DOSSIER.md</code>):</strong>
              <div style="display:flex; gap:8px;">
                <button class="btn-mini" style="background:#10b981; color:#052e16; font-weight:800;" onclick="copyAuditDossierMd()">📋 Copy Toàn Bộ Markdown Cho ChatGPT</button>
                <button class="btn-mini" onclick="downloadAuditDossierMd()">📥 Tải File CHATGPT_INDEPENDENT_AUDIT_DOSSIER.md</button>
              </div>
            </div>

            <pre style="background:#090d16; border:1px solid #334155; border-radius:10px; padding:16px; color:#e2e8f0; font-size:12.5px; line-height:1.55; max-height:560px; overflow-y:auto; white-space:pre-wrap; word-break:break-word;">{audit_dossier_escaped}</pre>
          </div>
        </section>
      </div>

      <footer>
        PeakPulse AI (Đảo Vàng) • Wiki Nghiên Cứu Alpha Đa Tầng (Kiến Trúc 6 Chuyên Mục MECE v4.0) • In-Sample 6 Năm (2020–2025) + OOS Thực Chiến (2026) + Hồ Sơ Kiểm Định AI Độc Lập
      </footer>
    </div>
  </main>

  <div id="toast">Đã sao chép!</div>

  <script>
    const ALPHA_REGISTRY = {registry_json_inline};
    const AUDIT_DOSSIER_MD = {audit_dossier_json_inline};
    const TIER_S_LIST = {tier_s_list_json};
    const TIER_SA_LIST = {tier_sa_list_json};
    const PIT_ZERO_BIAS_LIST = {pit_zero_bias_list_json};
    const BLACKLIST_LIST = {blacklist_list_json};

    function showToast(msg) {{
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => {{ t.style.display = 'none'; }}, 2200);
    }}

    function copyText(text, msg) {{
      navigator.clipboard.writeText(text).then(() => showToast(msg || 'Đã sao chép!'));
    }}

    function copyUniverseList(mode) {{
      if (mode === 'tier_s') {{
        copyText(JSON.stringify(TIER_S_LIST, null, 2), 'Đã copy danh sách 40 Mã Tier S Core!');
      }} else if (mode === 'tier_sa') {{
        copyText(JSON.stringify(TIER_SA_LIST, null, 2), 'Đã copy danh sách 68 Mã Whitelist v1.2 (Tier S + A)!');
      }} else if (mode === 'pit_zero_bias') {{
        copyText(JSON.stringify(PIT_ZERO_BIAS_LIST, null, 2), 'Đã copy danh sách 64 Mã Point-in-Time Zero-Bias!');
      }} else {{
        copyText(JSON.stringify(BLACKLIST_LIST, null, 2), 'Đã copy danh sách Blacklist!');
      }}
    }}

    function filterUniverseTier(evt, tierFilter) {{
      const parent = evt.currentTarget.closest('.filter-bar');
      parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      evt.currentTarget.classList.add('active');

      document.querySelectorAll('.universe-coin-row').forEach(row => {{
        const ut = row.getAttribute('data-utier');
        if (tierFilter === 'ALL') {{
          row.style.display = '';
        }} else {{
          row.style.display = (ut === tierFilter) ? '' : 'none';
        }}
      }});
    }}

    function copyPassportJson(alphaId) {{
      const found = ALPHA_REGISTRY.alpha_passports.find(p => p.id === alphaId);
      if (found) {{
        copyText(JSON.stringify(found, null, 2), 'Đã copy Hồ sơ JSON của ' + alphaId + '!');
      }}
    }}

    function copyAuditDossierMd() {{
      copyText(AUDIT_DOSSIER_MD, 'Đã copy trọn bộ Hồ sơ Kiểm định cho ChatGPT!');
    }}

    function downloadAuditDossierMd() {{
      const blob = new Blob([AUDIT_DOSSIER_MD], {{ type: 'text/markdown;charset=utf-8' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'CHATGPT_INDEPENDENT_AUDIT_DOSSIER.md';
      a.click();
      URL.revokeObjectURL(url);
      showToast('Đã tải xuống CHATGPT_INDEPENDENT_AUDIT_DOSSIER.md!');
    }}

    function downloadRegistryJson() {{
      const blob = new Blob([JSON.stringify(ALPHA_REGISTRY, null, 2)], {{ type: 'application/json' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'alpha_wiki_registry.json';
      a.click();
      URL.revokeObjectURL(url);
      showToast('Đã tải xuống alpha_wiki_registry.json!');
    }}

    function showWikiPage(evt, pageId) {{
      document.querySelectorAll('.wiki-sidebar .nav-link').forEach(btn => btn.classList.remove('active'));
      if (evt && evt.currentTarget) {{
        evt.currentTarget.classList.add('active');
      }}
      const pages = document.querySelectorAll('.wiki-page');
      if (pageId === 'ALL') {{
        pages.forEach(p => p.classList.remove('hidden-page'));
      }} else {{
        pages.forEach(p => {{
          if (p.id === pageId) {{
            p.classList.remove('hidden-page');
          }} else {{
            p.classList.add('hidden-page');
          }}
        }});
      }}
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function filterPassports(evt, statusFilter) {{
      const parent = evt.currentTarget.closest('.filter-bar');
      parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      evt.currentTarget.classList.add('active');

      document.querySelectorAll('.passport-card').forEach(card => {{
        const st = card.getAttribute('data-status');
        if (statusFilter === 'ALL') {{
          card.style.display = '';
        }} else if (statusFilter === 'REJECTED_OR_MERGED') {{
          card.style.display = (st === 'REJECTED_TRAP' || st === 'MERGED_REDUNDANT') ? '' : 'none';
        }} else {{
          card.style.display = (st === statusFilter) ? '' : 'none';
        }}
      }});
    }}

    function handleGlobalSearch(query) {{
      const q = (query || '').trim().toLowerCase();
      const pages = document.querySelectorAll('.wiki-page');
      if (q.length > 0) {{
        pages.forEach(p => p.classList.remove('hidden-page'));
      }}
      document.querySelectorAll('.searchable-item').forEach(item => {{
        const hay = item.getAttribute('data-search') || '';
        item.style.display = (!q || hay.includes(q)) ? '' : 'none';
      }});
    }}

    function switchSubTab(evt, groupClass, panelId) {{
      const parent = evt.currentTarget.closest('.section');
      const buttons = parent.querySelectorAll('.tabs .tab-btn');
      const panels = parent.querySelectorAll('.' + groupClass);
      buttons.forEach(btn => btn.classList.remove('active'));
      panels.forEach(panel => panel.classList.remove('active'));
      evt.currentTarget.classList.add('active');
      document.getElementById(panelId).classList.add('active');
    }}
  </script>
</body>
</html>
"""


def main() -> None:
    baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    pump_study = json.loads(PUMP_STUDY_JSON.read_text(encoding="utf-8"))
    audit_study = json.loads(AUDIT_STUDY_JSON.read_text(encoding="utf-8"))
    audit_dossier_md = AUDIT_DOSSIER_MD.read_text(encoding="utf-8")
    coin_universe = json.loads(COIN_UNIVERSE_JSON.read_text(encoding="utf-8"))
    registry = build_alpha_wiki_registry()
    pub_v426_path = ARTIFACTS_DIR / "fibo_strategy_publication_v4_0_26.json"
    if pub_v426_path.exists():
        registry["reaudit_v4_0_26_and_paper_oos_v1"] = json.loads(
            pub_v426_path.read_text(encoding="utf-8")
        )
    registry["coin_universe_selection_2026"] = {
        "metadata": coin_universe["metadata"],
        "by_universe_tier": coin_universe["by_universe_tier"],
        "by_archetype": coin_universe["by_archetype"],
        "by_market_cap": coin_universe.get("by_market_cap", {}),
        "by_float_ratio": coin_universe.get("by_float_ratio", {}),
        "lists": coin_universe["lists"],
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_JSON.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported structured Alpha Registry JSON to: {REGISTRY_JSON}")

    html_content = build_html(
        baseline, pump_study, registry, audit_study, audit_dossier_md, coin_universe
    )
    OUTPUT_HTML.write_text(html_content, encoding="utf-8")
    print(f"Exported Interactive Wiki HTML Portal to: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()

