"""Report causal entry research without hiding the repeatedly used history."""

import json
from html import escape

import pandas as pd
from compare_account_risk import ROOT,sha,write
from search_guarded_entries import OUT

NAMES={"seller_pressure":"Lực bán + phá đáy","overextension_reversal":"Tăng quá xa rồi quay đầu 4h"}
GUARDS={"none":"không lọc","nonnegative_carry":"funding đã trả ≥0","anti_squeeze":"lọc tăng nóng / funding / ATR","trend_confirmation":"xu hướng alt + BTC"}
TIMINGS={"immediate":"Vào ngay","delay60":"Chờ 60 phút","rejection0.5":"Hồi 0,5 ATR rồi giảm lại","breakdown0.5":"Giảm tiếp 0,5 ATR"}


def money(v):return "Không hoàn tất" if v is None else f"{v:.2f}"


def label(s):
    e=s["entry"]
    return f"{NAMES[e['source']['family']]} · {TIMINGS[e['timing']['id']]} · {GUARDS[e['guard']]} · ký quỹ {s['notional']/5:g} · "+("không SL" if s["management"]=="hold" else "SL4% + 72h")


def tr(fields):return "<tr>"+"".join("<td>"+escape(str(v))+"</td>" for v in fields)+"</tr>"


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));audit=json.loads((OUT/"verification.json").read_text(encoding="utf-8"))
    full=[]
    for r in s["results"]:
        if r["window"]!="full":continue
        f=pd.read_parquet(OUT/"runs"/f"{r['id']}_equity.parquet");indices={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//21600000):indices.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        full.append(dict(r,points=[[int(v["at"]),round(v.equity,6)] for _,v in f.loc[sorted(indices)].iterrows()],
                         first_pause=int(f.loc[f.paused,"at"].iloc[0]) if f.paused.any() else None))
    data=dict(full=full,results=s["results"]);write(OUT/"dashboard_data.json",data)
    table=[];mdrows=[];aggregate=[]
    for spec in s["portfolio_specs"]:
        rows=[r for r in s["results"] if r["strategy_id"]==spec["id"]]
        whole={r["cost"]:r for r in rows if r["window"]=="full"};rolling=[r for r in rows if r["window"]!="full"]
        values=[r["ending_equity"] for r in rolling if r["ending_equity"] is not None]
        a=dict(id=spec["id"],label=label(spec),positive_rolling=sum(v>500 for v in values),rolling_count=len(rolling),
               incomplete=len(rolling)-len(values),rolling_min=min(values),rolling_max=max(values),
               worst_drawdown=max(r["max_drawdown"] for r in rows),full={c:r["ending_equity"] for c,r in whole.items()})
        aggregate.append(a)
        fields=[label(spec),money(a["full"]["base"]),money(a["full"]["stress"]),f"{a['rolling_min']:.2f}–{a['rolling_max']:.2f}",f"{a['positive_rolling']}/14",f"{a['worst_drawdown']*100:.2f}%"]
        table.append(tr(fields));mdrows.append("| "+" | ".join(fields)+" |")
    write(OUT/"rolling_summary.json",aggregate)
    screenrows=[]
    for row in s["validation"]+s["holdout"]:
        control=next(r for r in s["controls"] if r["spec"]["source"]["id"]==row["spec"]["source"]["id"] and r["window"]==row["window"])
        for r,name in [(row,"Đã lọc"),(control,"Đối chứng")]:
            fields=[NAMES[r["spec"]["source"]["family"]],name,"12/2025–02/2026" if r["window"]=="validation" else "03–05/2026",r["counts"]["complete"]]
            for cost in ["base","stress"]:
                v=r["cases"][cost];fields.extend([f"{v['mean_net_return']*100:+.3f}%",f"[{v['ci95'][0]*100:+.3f}; {v['ci95'][1]*100:+.3f}]%"])
            screenrows.append(tr(fields))
    timingrows=[]
    for family in NAMES:
        for timing in TIMINGS:
            pool=[r for r in s["development"] if r["spec"]["source"]["family"]==family and r["spec"]["timing"]["id"]==timing and r["eligible"]]
            if not pool:timingrows.append(tr([NAMES[family],TIMINGS[timing],"Không đủ mẫu","—","—","—"]));continue
            best=max(pool,key=lambda r:(r["worst_lower"],r["worst_mean"]))
            timingrows.append(tr([NAMES[family],TIMINGS[timing],GUARDS[best["spec"]["guard"]]+f" / {best['spec']['hours']}h",best["counts"]["complete"],f"{best['worst_mean']*100:+.3f}%",f"{best['worst_lower']*100:+.3f}%"]))
    reference=ROOT/"artifacts/capital_holding_20260925/dashboard.html"
    previous=reference.read_text(encoding="utf-8")
    style=previous.split("<style>",1)[1].split("</style>",1)[0]
    # Reuse the reviewed UI renderer; it reads rows, points and these same DOM IDs.
    renderer="const num="+previous.split(";const num=",1)[1].split("</script>",1)[0]
    (OUT/"dashboard.js").write_text(renderer,encoding="utf-8")
    html=r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Điểm vào và bộ lọc</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / ĐIỂM VÀO · LƯỢT 07</div><h1>Lọc trước khi vào giúp cải thiện một ứng viên</h1><p class="muted">01/09/2025–01/06/2026, không gồm ngày cuối · UTC · vốn 500 USDT · Short, x5, tối đa 5 vị thế · ba phần, TP trailing</p>
<div class="notice"><b>Chưa đạt 50% mỗi tháng.</b><p>Nhóm tăng quá xa rồi quay đầu, thêm bộ lọc tăng nóng/funding/ATR, có lời ở 14/14 trường hợp khởi chạy ba tháng–chi phí. Với ký quỹ 5 USDT, cả chín tháng kết thúc ở 533,23–540,07 USDT, sụt giảm lớn nhất 3,66%. Đây là kết quả khám phá trên lịch sử đã sử dụng nhiều lần, chưa phải bằng chứng độc lập.</p><p>Đường chín tháng vẫn có tháng lỗ tới 1,77%, cuối kỳ còn năm vị thế mở; vị thế lâu nhất đã giữ 127 ngày. Bộ lọc chưa giải quyết được thời gian vốn bị mắc kẹt.</p><span class="pill">Lịch sử chồng lấn · Không bật live</span></div>
<div class="cards"><div class="card">Tổ hợp sàng lọc<strong>96</strong></div><div class="card">Đường tài khoản<strong>256</strong></div><div class="card">Đạt mục tiêu tháng<strong>0</strong></div><div class="card">Kiểm thử đạt<strong>103</strong></div></div>
<section class="panel"><h2>Đã thử những điểm vào nào?</h2><p>Vào ngay; chờ đúng 60 phút; chờ giảm tiếp 0,5 ATR; hoặc chờ hồi 0,5 ATR rồi giảm lại 0,25 ATR từ đỉnh theo dõi. Hai cách theo giá hết hạn sau 6 giờ. Mỗi cách kết hợp bốn bộ lọc, trên hai nguồn tín hiệu và ba thời gian đo sự kiện 4/24/72h.</p><p>Tại lúc kích hoạt, thử không lọc; tổng funding đã thanh toán 24h không âm; lọc tăng nóng/funding/ATR; hoặc xác nhận xu hướng giảm của altcoin và BTC. Không dùng funding tương lai, không xóa tên coin gây lỗ. Bộ lọc không đạt thì bỏ sự kiện, không tự chờ tới lúc thuận lợi.</p><p><b>Quy tắc lọc ứng viên cải thiện:</b> lợi suất 24h ≤10%, lợi suất 6h ≤0, tổng funding đã trả 24h ≥−0,1%, ATR14 nến 1h / giá ≤5%. Tất cả từ nến đã đóng gần nhất. Trailing vẫn dùng ATR đóng băng của tín hiệu gốc; bộ lọc ATR1h không thay nó.</p>
<div class="scroll"><table><thead><tr><th>Nguồn</th><th>Điểm vào</th><th>Bộ lọc / thời gian đo tốt nhất kỳ chọn</th><th>Sự kiện</th><th>TB sau chi phí xấu hơn</th><th>Cận dưới 95% xấu hơn</th></tr></thead><tbody>__TIMINGS__</tbody></table></div><p class="muted">Bảng này chỉ dùng kỳ 09–11/2025 để chọn, chưa phải lợi nhuận tài khoản. 72/96 tổ hợp đủ ngưỡng 50 sự kiện; không tổ hợp nào có cận dưới 95% dương ở cả hai mức chi phí. Các khoảng tin cậy chưa hiệu chỉnh thử nhiều giả thuyết.</p></section>
<section class="panel"><h2>Tài sản, lợi suất tháng và đổi ngày bắt đầu</h2><label>Phương án<select id="strategy">__OPTIONS__</select></label><p>Ký quỹ 5/20 USDT tương ứng tổng danh nghĩa 25/100 USDT cho cả ba phần. Mức 20 USDT và biến thể SL/đóng sau 72h chỉ dùng để nghiên cứu.</p>
<div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản chín tháng đã định giá vị thế mở"></svg><div id="chartStatus"></div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div>
<h3>Vốn và thời gian giữ lệnh</h3><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Ký quỹ cam kết TB</th><th>Đủ 5 vị thế</th><th>Khóa mở mới</th><th>Danh nghĩa vào / vốn</th><th>Trung vị giữ lệnh đóng</th><th>Lệnh mở lâu nhất</th></tr></thead><tbody id="utilization"></tbody></table></div>
<h3>Bảy tài khoản khởi chạy riêng</h3><p>Mỗi ngày bắt đầu chạy ba tháng với 500 USDT, thử hai mức chi phí. Các kỳ chồng lấn; 14/14 có lời không có nghĩa 14 mẫu độc lập hoặc từng tháng đều có lời.</p><div class="scroll"><table><thead><tr><th>Tháng bắt đầu</th><th>Chi phí</th><th>Tài sản cuối kỳ</th><th>Sụt giảm từ đỉnh</th><th>Đã vào</th><th>Còn mở</th><th>Trạng thái</th></tr></thead><tbody id="rolling"></tbody></table></div><p id="stopDetails"></p></section>
<section class="panel"><h2>Đối chiếu toàn bộ tài khoản</h2><div class="scroll"><table><thead><tr><th>Phương án</th><th>9 tháng cơ sở</th><th>9 tháng cao</th><th>Khoảng cuối kỳ 3 tháng</th><th>Kỳ 3 tháng có lời</th><th>DD lớn nhất mọi kỳ</th></tr></thead><tbody>__TABLE__</tbody></table></div><p>Mọi con số đã tính phí, funding và lãi/lỗ vị thế còn mở. Không tự tăng vốn theo lợi nhuận. Hai phần sau chỉ thêm khi giá đi thuận 0,5 ATR, hết hạn sau 6h; không tăng vị thế để gỡ lỗ.</p></section>
<section class="panel"><h2>Lợi thế tín hiệu chưa được xác nhận</h2><p>Chọn một tổ hợp mỗi nguồn từ 09–11/2025, khóa trước khi đánh giá 12/2025–02/2026 và 03–05/2026. Hai tổ hợp được chọn đều là vào ngay có lọc. Lợi suất sự kiện 4 giờ dưới đây vẫn âm sau chi phí, dù một số danh mục trailing giữ lâu có lời. Hai phép đo khác cách thoát và không được dùng thay thế nhau.</p><div class="scroll"><table><thead><tr><th>Nguồn</th><th>Nhóm</th><th>Kỳ</th><th>Mẫu</th><th>TB cơ sở</th><th>CI95 cơ sở</th><th>TB cao</th><th>CI95 cao</th></tr></thead><tbody>__SCREENS__</tbody></table></div></section>
<section class="panel"><h2>Đối soát và phạm vi kết luận</h2><p>103 kiểm thử đạt; kiểm tra cắt dữ liệu tương lai cho 32 bộ điểm vào và 30 bộ đặc trưng; 256 sổ tài khoản, phí/funding/ngân sách và tháng đối soát. 128 đường đối chứng khớp chính xác lượt trước, bốn đường ứng viên mới tái lập chính xác.</p><p>Cơ sở: phí 0,05%, trượt giá 0,20% mỗi lần khớp thị trường; chi phí cao: 0,10% / 0,50%. Trailing kích hoạt 3 ATR rồi hồi 1%, lấy mẫu 5 phút. SL nghiên cứu bằng 4% danh nghĩa, tỷ lệ phần đã khớp; thời hạn 72h có thể chốt lỗ. DD20% khóa mở mới, không đóng vị thế cũ và không phải trần lỗ.</p><p class="muted">Lịch sử đã được nghiên cứu lặp lại; danh sách kho có thể thiếu coin hủy niêm yết. Dùng bộ lọc sàn hiện tại, maintenance 1% thay bậc lịch sử, chưa có khớp lệnh theo orderbook. Bộ lọc không bảo đảm tránh squeeze. Ký quỹ cam kết không phải giới hạn lỗ Cross. Cần tách từng điều kiện lọc và kiểm tra dữ liệu độc lập; chưa đủ điều kiện chạy thật. Cấu hình live giữ nguyên.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">256 tài khoản</a> · <a href="development.json">96 phép sàng lọc</a> · <a href="rolling_summary.json">So sánh ngày bắt đầu</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa trước</a></p></section></main><script>const data=__JSON__;</script><script src="dashboard.js"></script></body></html>'''
    chosen="overextension_reversal_immediate_anti_squeeze_n25_hold"
    options="".join(f'<option value="{escape(p["id"])}"'+(' selected' if p["id"]==chosen else '')+'>'+escape(label(p))+"</option>" for p in s["portfolio_specs"])
    for key,value in dict(STYLE=style,TIMINGS="".join(timingrows),OPTIONS=options,TABLE="".join(table),SCREENS="".join(screenrows),JSON=json.dumps(data,ensure_ascii=False,separators=(",",":"),allow_nan=False).replace("</","<\\/")).items():html=html.replace("__"+key+"__",value)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# Điểm vào và bộ lọc — lượt 07","",
        "96 tổ hợp sàng lọc, 256 mô phỏng tài khoản. Chưa có cấu hình đạt ít nhất 50% trong từng tháng. Hai ứng viên đều là vào ngay có lọc; chờ 60 phút, chờ giảm tiếp hoặc hồi rồi giảm lại không được chọn theo kỳ phát triển.","",
        "Tăng quá xa rồi quay đầu 4h + bộ lọc tăng nóng/funding/ATR: ký quỹ 5 USDT, x5, ba phần, trailing không SL; cuối chín tháng 533,23–540,07 USDT. Có lời ở 14/14 trường hợp ba tháng–chi phí, DD lớn nhất 3,66%. Bản chưa lọc: 521,96–525,50, 12/14 có lời, DD lớn nhất 11,96% qua các kỳ bắt đầu.","",
        "Bộ lọc tại điểm vào: ret24h≤10%, ret6h≤0, funding thực đã trả trong 24h≥−0,1%, 0<ATR14 khung1h/giá≤5%. Chỉ nến đã đóng, funding trễ ít nhất 60 giây, không loại tên coin theo kết quả. Đây là ngưỡng nghiên cứu, không phải bảo đảm chống squeeze.","",
        "Mức ký quỹ 20 USDT cùng ứng viên: cuối chín tháng 650,99–677,14, DD lớn nhất 16,52%; cả 14 kỳ ba tháng dương. Kỳ khởi chạy 03/2026 chỉ đạt 520,73–524,16 sau ba tháng. Tăng vốn không giải quyết mục tiêu 50% mỗi tháng.","",
        "Các kỳ chồng lấn và lịch sử đã nghiên cứu lặp lại, chưa phải 14 mẫu độc lập. Không tổ hợp nào có cận dưới CI95 dương ở cả hai chi phí trong kỳ sàng lọc. Lợi suất sự kiện 4h của ứng viên vẫn âm trong kỳ đánh giá cuối; cách thoát này khác danh mục trailing giữ lâu.","",
        "Ứng viên 5 USDT vẫn có tháng lỗ tới 1,77%; cuối chín tháng còn năm vị thế mở, lâu nhất 127 ngày. Các khoản này đã được định giá vào tài sản cuối kỳ, nhưng rủi ro giữ lâu chưa được giải quyết.","",
        "| Phương án | 9 tháng cơ sở | 9 tháng cao | Khoảng 3 tháng | Có lời | DD lớn nhất mọi kỳ |","|---|---:|---:|---:|---:|---:|",*mdrows,"",
        f"{audit['unit_tests_passed']} kiểm thử; {audit['journals_audited']} sổ đối soát; {audit['entry_prefix_checks']} bộ điểm vào/{audit['feature_prefix_checks']} bộ đặc trưng kiểm tra nhân quả; {audit['prior_baseline_paths_exact']} đối chứng cũ và {audit['new_paths_exact']} đường mới tái lập chính xác.","",
        s["protocol"]["limitations"],"",
        "Tiếp theo: tách từng thành phần bộ lọc để xem yếu tố nào tạo cải thiện; khóa ứng viên và thử dữ liệu độc lập. Chưa thay cấu hình live.","",
        "[Dashboard](dashboard.html) · [256 kết quả](comparison.csv) · [Đối soát](verification.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,screens=96,account_paths=256,target_passes=0,
          new_evidence="Anti-squeeze entry guard on4h overextension improves rolling-start robustness to14/14 profitable overlapping3month/cost cases at25/100notional; every-month50% goal still unmet. Event4h means remain negative after costs.",
          next_steps=["Ablate each guard component with frozen source/entry/exit to identify causal contribution and instability.",
                      "Freeze candidate and assess independent later history with no new tuning; retain costs and open losses.",
                      "Historical margin tiers/orderbook and delisting coverage still required before financially verified claims."],
          live_config_unchanged=True,ui_renderer_source_sha256=sha(reference)))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
