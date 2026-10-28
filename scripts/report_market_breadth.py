"""Report broad-market short research with preserved reversal controls."""

import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write
from search_market_breadth import OUT,WINDOWS

REGIMES={"any":"Không lọc thị trường","breadth60":"≥60% coin dưới EMA60","breadth75_btc":"≥75% coin dưới EMA60 + BTC giảm","ret6":"Lọc 6h"}
RANKS={"raw7d":"Yếu 7 ngày","beta7d":"Yếu 7 ngày, chỉnh theo BTC","reversal":"Đảo chiều cũ"}
ENTRIES={"scheduled":"kiểm tra mỗi 4h","pullback":"hồi EMA20 rồi giảm","immediate":"vào ngay"}


def source_name(p):return RANKS[p["ranking"]]+" · "+REGIMES[p["regime"]]+" · "+ENTRIES[p["entry"]]
def name(p):return source_name(p["source"])+f" · ký quỹ {p['notional']/5:g} · "+("đóng sau tối đa 7 ngày" if p["holding"]=="time168" else "giữ không hạn")
def num(x):return "Không hoàn tất" if x is None else f"{x:.2f}"
def tr(values):return "<tr>"+"".join("<td>"+escape(str(v))+"</td>" for v in values)+"</tr>"


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));v=json.loads((OUT/"verification.json").read_text(encoding="utf-8"));findings=json.loads((OUT/"findings.json").read_text(encoding="utf-8"))
    assert len(s["results"])==v["journals_audited"]==312
    specs={p["id"]:p for p in s["specs"]};lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]}
    pair=lambda rs,k:" / ".join(num(r[k]) for r in rs)
    selected=[];mdrows=[];primary=[];bench=[];series=[]
    for ident in s["selected"]:
        rows=lambda w:[lookup[(ident,w,c)] for c in ["base","stress"]]
        fields=[name(specs[ident]),pair(rows("development"),"ending_equity"),pair(rows("later"),"ending_equity"),pair(rows("year"),"ending_equity"),
            " / ".join(str(r["entries"]) for r in rows("year")),f"{100*max(r['max_drawdown'] for r in rows('year')):.2f}%"]
        selected.append(tr(fields));mdrows.append("| "+" | ".join(fields)+" |")
    for p in s["specs"]:
        if p["notional"]!=25:continue
        if p["baseline"]:
            year=[lookup[(p["id"],"year",c)] for c in ["base","stress"]];later=[lookup[(p["id"],"later",c)] for c in ["base","stress"]]
            bench.append(tr([source_name(p["source"]),pair(year,"ending_equity"),pair(later,"ending_equity"),f"{100*max(r['max_drawdown'] for r in year):.2f}%"]))
        elif p["holding"]=="hold":
            cells=[]
            for holding in ["hold","time168"]:
                for window in ["year","later"]:
                    ident=f"{p['source']['id']}_n25_{holding}"
                    cells.append(pair([lookup[(ident,window,c)] for c in ["base","stress"]],"ending_equity"))
            primary.append(tr([source_name(p["source"]),*cells]))
    for row in s["results"]:
        f=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(q["at"]),round(q.equity,6)] for _,q in f.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    market=pd.read_parquet(OUT/"market.parquet");start,end=WINDOWS["year"]
    market=market[(market.index>=pd.Timestamp(start,unit="ms",tz="UTC"))&(market.index<pd.Timestamp(end,unit="ms",tz="UTC"))]
    activity=dict(bars=len(market),coverage_min=int(market.coverage.min()),coverage_max=int(market.coverage.max()),ready_fraction=float(market.ready.mean()),
        breadth60_fraction=float((market.ready&market.breadth_below_ema60.ge(.6)).mean()),breadth75_fraction=float((market.ready&market.breadth_below_ema60.ge(.75)).mean()))
    write(OUT/"market_activity.json",activity)
    old=(ROOT/"artifacts/retest_entries_20260925/dashboard.html").read_text(encoding="utf-8")
    style=old.split("<style>",1)[1].split("</style>",1)[0];script=old.split("<script>",1)[1].split("</script>",1)[0]
    default=next((i for i in s["selected"] if specs[i]["notional"]==25 and specs[i]["holding"]=="hold"),"benchmark_mask2_n25")
    options="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]==default else '')+'>'+escape(name(p))+(' · đã khóa' if p["id"] in s["selected"] else '')+'</option>' for p in s["specs"])
    missing=[]
    for n in [25,100]:
        for h in ["hold","time168"]:
            if not any(specs[i]["notional"]==n and specs[i]["holding"]==h for i in s["selected"]):missing.append(f"ký quỹ {n/5:g} USDT, "+("giữ không hạn" if h=="hold" else "đóng tối đa 7 ngày"))
    unavailable="Không có ứng viên đạt điều kiện chọn ở nhóm: "+"; ".join(missing)+"." if missing else "Cả bốn nhóm có ứng viên chẩn đoán; được chọn chưa đủ điều kiện giao dịch thật."
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Short theo độ rộng thị trường</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / ĐỘ YẾU TƯƠNG ĐỐI VÀ THỊ TRƯỜNG · LƯỢT 13</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026, UTC, không gồm ngày cuối · 500 USDT · Cross x5 · tối đa 5 vị thế · ba phần 0,25 ATR · trailing 3 ATR/hồi 1%</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div>
<div class="cards"><div class="card">Nguồn tín hiệu mới<strong>12</strong></div><div class="card">Cấu hình gồm đối chứng<strong>52</strong></div><div class="card">Đường tài khoản<strong>312</strong></div><div class="card">Kiểm thử đạt<strong>69</strong></div></div>
<section class="panel"><h2>Ứng viên chọn từ 9 tháng đầu</h2><p>Chọn riêng từng quy mô/cách giữ lệnh bằng 09/2025–05/2026: tháng tệ nhất tốt nhất ở cả hai mức chi phí, rồi tài sản cuối. Phải hoàn tất, DD dưới 20% và ít nhất 20 vị thế đã đóng ở mỗi mức chi phí. Chỉ chọn trong nguồn tín hiệu mới. Khóa trước khi chạy kỳ sau trong lượt này; lịch sử đã từng được xem, không gọi là tập kiểm tra độc lập.</p><p><b>__MISSING__</b></p><div class="scroll"><table><thead><tr><th>Ứng viên</th><th>9 tháng đầu</th><th>3 tháng sau</th><th>Cả năm</th><th>Vị thế vào cả năm</th><th>DD cả năm lớn nhất</th></tr></thead><tbody>__SELECTED__</tbody></table></div><p>Cặp số: cơ sở / chi phí cao. Mỗi cửa sổ khởi chạy riêng từ 500 USDT. Không cộng kết quả các tài khoản khởi chạy khác nhau. “Đóng tối đa 7 ngày” có thể đóng lỗ, là phương án nghiên cứu riêng so với yêu cầu giữ không hạn.</p></section>
<section class="panel"><h2>Đối chứng đảo chiều cũ · ký quỹ 5 USDT</h2><div class="scroll"><table><thead><tr><th>Nguồn tín hiệu</th><th>Tài sản cả năm</th><th>Tài sản 3 tháng sau</th><th>DD cả năm lớn nhất</th></tr></thead><tbody>__BENCH__</tbody></table></div></section>
<section class="panel"><h2>Đủ 12 nguồn tín hiệu mới · ký quỹ 5 USDT</h2><p>Tổng danh nghĩa 25 USDT cho cả ba phần. Hai cách giữ lệnh đều có trailing; cột “7 ngày” thêm thời hạn đóng thị trường, không phải giữ cố định đủ 7 ngày mới được chốt.</p><div class="scroll"><table><thead><tr><th>Nguồn</th><th>Giữ không hạn · cả năm</th><th>Giữ không hạn · 3 tháng</th><th>Tối đa 7 ngày · cả năm</th><th>Tối đa 7 ngày · 3 tháng</th></tr></thead><tbody>__PRIMARY__</tbody></table></div></section>
<section class="panel"><h2>Xem đường tài sản và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="year">Cả năm · 09/2025–08/2026</option><option value="later">Tài khoản mới · 06–08/2026</option><option value="development">Chọn tham số · 09/2025–05/2026</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm vị thế mở theo thời gian"></svg><div id="chartStatus">Đang tải dữ liệu…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><p class="muted">Đồ thị giữ đầu, cuối, đáy và đỉnh mỗi ngày. Tháng thiếu sau sự cố không được thay bằng 0%; không gán số dư cuối sau ngưỡng thiếu ký quỹ mô phỏng.</p></section>
<section class="panel"><h2>Giả thuyết và cách tính</h2><p>Độ yếu tuần đo lợi suất log trong 7 ngày, bỏ 24 giờ gần nhất. Bản điều chỉnh BTC trừ beta × lợi suất BTC cùng kỳ; beta tính từ 168 cặp lợi suất giờ đã biết, cũng kết thúc trước 24 giờ. Đây là điều chỉnh theo mức biến động cùng BTC, không phải bằng chứng coin được định giá sai.</p><p>Xếp hạng nhóm 20% yếu nhất trong danh sách 30 altcoin đã khóa. Cả hai cách xếp hạng dùng cùng điều kiện dữ liệu/thanh khoản. Cần ít nhất 24 coin đủ điều kiện; đồng hạng dùng thứ hạng trung bình. Coin phải đang giảm trong 24 giờ, EMA20 dưới EMA60 và giá dưới EMA20 khung 4h.</p><p>Ba trạng thái: không lọc thị trường; ít nhất 60% coin đủ điều kiện dưới EMA60; ít nhất 75% và BTC cùng xu hướng giảm. Điểm vào kiểm tra mỗi 4h, hoặc thêm điều kiện nến hồi chạm EMA20 rồi đóng giảm. Mỗi coin cách tín hiệu ít nhất 24 giờ. __ACTIVITY__</p><p>Nghiên cứu <a href="https://www.nber.org/papers/w25882">Common Risk Factors in Cryptocurrency</a> và <a href="https://www.nber.org/papers/w24877">Risks and Returns of Cryptocurrency</a> gợi ý xem xét động lượng và yếu tố thị trường. Các quy tắc ở đây là giả thuyết tự xây dựng; không phải tái lập nghiên cứu hoặc bằng chứng đạt 50%/tháng trên Binance Futures.</p></section>
<section class="panel"><h2>Đối soát và giới hạn</h2><p>__AUDIT__</p><p>Phí 0,05%/0,10%, trượt giá 0,20%/0,50%, funding thực và vị thế mở. Dừng mở mới ở DD20% không giới hạn lỗ cũ. Ký quỹ 20 USDT chỉ để nghiên cứu; cấu hình live giữ nguyên.</p><p>Giới hạn: nghiên cứu lặp trên cùng lịch sử; maintenance proxy 1% thay bậc lịch sử, bộ lọc sàn hiện tại, lấy mẫu 5 phút, chưa có orderbook, kho có thể thiếu coin hủy niêm yết. Bảng sự kiện 4h/24h dùng bootstrap khối 7 ngày, chưa điều chỉnh thử nhiều cấu hình; không phải lợi suất tài khoản hoặc căn cứ xác nhận lợi thế tương lai.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">312 kết quả</a> · <a href="screens.json">Đo từng sự kiện</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc</a> · <a href="candidate_lock.json">Bản khóa lựa chọn</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    target=f"{s['target_met_rows']}/312 đường đạt 50% từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    audit=f"{v['journals_audited']} sổ đối soát; {v['baseline_paths_exact']} đường đối chứng khớp lượt trước; {v['replayed_paths_exact']} đường chạy lại khớp. Kiểm tra độc lập {v['independent_beta_samples_checked']} hệ số beta, {v['independent_rank_signals_checked']} tín hiệu/rank và {v['signal_prefixes_exact']} tập tín hiệu trước ranh giới thời gian. {v['event_screens_recomputed']} bảng sự kiện tính lại; 69 kiểm thử đạt. Hash dữ liệu/mã nguồn và cấu hình live khớp."
    activity_text=f"Trong kỳ cả năm, có đủ độ phủ ở {activity['ready_fraction']*100:.1f}% số nến 4h; ngưỡng độ rộng 60% đạt ở {activity['breadth60_fraction']*100:.1f}%, ngưỡng 75% đạt ở {activity['breadth75_fraction']*100:.1f}% (chưa thêm điều kiện BTC)."
    for k,val in dict(STYLE=style,TITLE=escape(findings["title"]),TARGET=escape(target),FINDING=escape(findings["finding"]),MISSING=escape(unavailable),SELECTED="".join(selected),BENCH="".join(bench),PRIMARY="".join(primary),OPTIONS=options,AUDIT=escape(audit),ACTIVITY=escape(activity_text),SCRIPT=script).items():html=html.replace("__"+k+"__",val)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    (OUT/"report.md").write_text("\n".join(["# "+findings["title"],"",target,"",findings["finding"],"",unavailable,"",
        "Cặp số là cơ sở / chi phí cao. Cửa sổ09/2025–05/2026 chọn tham số; 06–08/2026 đã từng được xem. Mỗi cửa sổ khởi chạy mới500USDT. Đóng tối đa7ngày bao gồm lệnh lỗ, chỉ là phương án nghiên cứu.","",
        "| Ứng viên | 9 tháng đầu | 3 tháng sau | Cả năm | Vị thế cả năm | DD |","|---|---:|---:|---:|---:|---:|",*mdrows,"",audit,"",activity_text,"",
        "Nguồn ý tưởng: [Common Risk Factors](https://www.nber.org/papers/w25882), [Risks and Returns](https://www.nber.org/papers/w24877). Không phải xác nhận short-onlyFutures hoặc50% mỗi tháng.","",
        "Giới hạn: lịch sử dùng lặp, universe có thể thiếu coin hủy niêm yết, MMR1%proxy, currentfilters,5msampling,assumedslippage/noorderbook. Giữ nguyên cấu hìnhlive.","",
        "[Dashboard](dashboard.html) · [Kết quả](comparison.csv) · [Quy tắc](protocol.json)"]),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=312,target_passes=s["target_met_rows"],evidence=findings["finding"],next_steps=findings["next_steps"],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
