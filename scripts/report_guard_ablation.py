"""Show all factorial backtest contrasts and residual open-inventory risk."""

import json
from collections import defaultdict
from html import escape

import numpy as np
import pandas as pd
from compare_account_risk import ROOT,write
from search_guard_ablation import OUT,PRIOR
from short_guard_ablation import COMPONENTS

NAMES={1:"Tăng 24h ≤10%",2:"Lợi suất 6h ≤0",4:"Funding 24h ≥−0,1%",8:"ATR1h/giá ≤5%"}


def mask_name(mask):return "Không lọc" if mask==0 else " + ".join(name for bit,name in NAMES.items() if mask&bit)


def label(spec):return mask_name(spec["guard"]["mask"])+f" · ký quỹ {spec['notional']/5:g} USDT"


def money(x):return "Không hoàn tất" if x is None else f"{x:.2f}"


def tr(values):return "<tr>"+"".join("<td>"+escape(str(v))+"</td>" for v in values)+"</tr>"


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));audit=json.loads((OUT/"verification.json").read_text(encoding="utf-8"))
    lookup={(r["mask"],r["notional"],r["window"],r["cost"]):r for r in s["results"]}
    effects=[];effect_html=[]
    for window in s["protocol"]["windows"]:
        for n in [25,100]:
            for cost in ["base","stress"]:
                for bit,name in COMPONENTS:
                    pairs=[]
                    for mask in range(16):
                        if mask&bit:continue
                        off,on=lookup[(mask,n,window,cost)],lookup[(mask|bit,n,window,cost)]
                        pairs.append(dict(off_mask=mask,on_mask=mask|bit,
                            equity_difference=None if off["ending_equity"] is None or on["ending_equity"] is None else on["ending_equity"]-off["ending_equity"],
                            drawdown_difference=on["max_drawdown"]-off["max_drawdown"]))
                    complete=[p["equity_difference"] for p in pairs if p["equity_difference"] is not None]
                    full=lookup[(15,n,window,cost)];leave=lookup[(15^bit,n,window,cost)]
                    solo=lookup[(bit,n,window,cost)];none=lookup[(0,n,window,cost)]
                    diff=lambda a,b:None if a["ending_equity"] is None or b["ending_equity"] is None else a["ending_equity"]-b["ending_equity"]
                    e=dict(component=bit,name=name,notional=n,window=window,cost=cost,pairs=pairs,
                           complete_pairs=len(complete),mean_equity_difference=float(np.mean(complete)) if complete else None,
                           min_equity_difference=min(complete) if complete else None,max_equity_difference=max(complete) if complete else None,
                           mean_drawdown_difference=float(np.mean([p["drawdown_difference"] for p in pairs])),
                           full_minus_leave_one_out=diff(full,leave),singleton_minus_none=diff(solo,none))
                    effects.append(e)
                    if window=="full":effect_html.append(tr([NAMES[bit],n/5,cost,money(e["singleton_minus_none"]),money(e["full_minus_leave_one_out"]),money(e["mean_equity_difference"]),f"{e['mean_drawdown_difference']*100:+.2f}",f"{len(complete)}/8"]))
    write(OUT/"factorial_effects.json",effects)
    aggregate=[];table=[];mdrows=[]
    for spec in s["specs"]:
        rows=[r for r in s["results"] if r["strategy_id"]==spec["id"]]
        full={r["cost"]:r for r in rows if r["window"]=="full"};rolling=[r for r in rows if r["window"]!="full"]
        values=[r["ending_equity"] for r in rolling if r["ending_equity"] is not None]
        a=dict(id=spec["id"],mask=spec["guard"]["mask"],notional=spec["notional"],positive_rolling=sum(v>500 for v in values),rolling_count=len(rolling),
               incomplete=len(rolling)-len(values),rolling_min=min(values) if values else None,rolling_max=max(values) if values else None,
               worst_drawdown=max(r["max_drawdown"] for r in rows),full={c:r["ending_equity"] for c,r in full.items()})
        aggregate.append(a)
        fields=[label(spec),money(a["full"]["base"]),money(a["full"]["stress"]),f"{money(a['rolling_min'])}–{money(a['rolling_max'])}",f"{a['positive_rolling']}/14",a["incomplete"],f"{a['worst_drawdown']*100:.2f}%"]
        table.append(tr(fields));mdrows.append("| "+" | ".join(str(x) for x in fields)+" |")
    write(OUT/"rolling_summary.json",aggregate)
    contributions=[];series=[]
    for row in s["results"]:
        if row["window"]!="full":continue
        raw=json.loads((OUT/"runs"/f"{row['id']}.json").read_text(encoding="utf-8"));bycoin=defaultdict(float)
        for j in raw["journal"]:
            if "net" in j:bycoin[j["symbol"]]+=j["net"]
        for pos in raw["open_positions"]:bycoin[pos["symbol"]]+=pos["unrealized"]-pos["entry_fee"]+pos["funding"]
        if row["pnl"] is not None:assert abs(sum(bycoin.values())-row["pnl"])<1e-6
        contributions.append(dict(id=row["id"],coin_pnl=dict(sorted(bycoin.items())),pnl=row["pnl"],complete=row["ending_equity"] is not None))
        f=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(f)-1}
        for _,g in f.groupby((f["at"]-f["at"].iloc[0])//21600000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(v["at"]),round(v.equity,6)] for _,v in f.loc[sorted(ix)].iterrows()],
                           first_pause=int(f.loc[f.paused,"at"].iloc[0]) if f.paused.any() else None))
    write(OUT/"coin_contributions.json",contributions)
    data=dict(full=series,results=s["results"]);write(OUT/"dashboard_data.json",data)
    style=(PRIOR/"dashboard.html").read_text(encoding="utf-8").split("<style>",1)[1].split("</style>",1)[0]
    (OUT/"dashboard.js").write_text((PRIOR/"dashboard.js").read_text(encoding="utf-8"),encoding="utf-8")
    summary_rows=[]
    for mask in [0,1,2,4,8,14,13,11,7,15]:
        a=next(a for a in aggregate if a["mask"]==mask and a["notional"]==25)
        summary_rows.append(tr([mask_name(mask),money(a["full"]["base"]),money(a["full"]["stress"]),f"{a['positive_rolling']}/14",f"{a['worst_drawdown']*100:.2f}%"]))
    observations=json.loads((OUT/"observations.json").read_text(encoding="utf-8"));missing=sum(r["pass_mask"] is None for r in observations)
    html=r'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Tách tác dụng từng bộ lọc</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / KIỂM TRA TỪNG ĐIỀU KIỆN · LƯỢT 08</div><h1>Điều kiện nào thực sự giúp tài khoản?</h1><p class="muted">09/2025–05/2026 UTC · 500 USDT · x5 · ba phần thuận xu hướng · trailing 3 ATR / hồi 1% · tối đa 5 vị thế</p>
<div class="notice"><b>__TARGET__ / 512 mô phỏng đạt ít nhất 50% trong từng tháng.</b><p>Đã chạy toàn bộ 16 cách bật/tắt bốn điều kiện, ở ký quỹ 5 và 20 USDT. Giữ nguyên tín hiệu tăng quá xa rồi quay đầu 4h, cách vào và thoát; không chỉnh ngưỡng theo kết quả, không loại tên coin gây lỗ.</p><span class="pill">Nghiên cứu trên lịch sử đã dùng · Live giữ nguyên</span></div>
<div class="cards"><div class="card">Tập điều kiện<strong>16</strong></div><div class="card">Tài khoản mô phỏng<strong>512</strong></div><div class="card">Đối chứng cũ tái lập<strong>64</strong></div><div class="card">Kiểm thử đạt<strong>111</strong></div></div>
<section class="panel"><h2>Điều kiện 6 giờ tạo phần lớn cải thiện</h2><p>Chỉ thêm lợi suất 6h ≤0 vào tín hiệu đảo chiều 4h: ở ký quỹ 5 USDT, cuối chín tháng đạt 541,24–547,14, so với 521,96–525,50 khi không lọc và 533,23–540,07 khi dùng đủ bốn điều kiện. Cả 14 trường hợp ba tháng–chi phí đều có lời.</p><p>Điều này yêu cầu xu hướng ngắn hơn cũng đã ngừng tăng trước khi Short. Đây là cách diễn giải quy tắc; mô phỏng chưa chứng minh quan hệ nhân quả thị trường. Các điều kiện ATR, funding và tăng 24h không tạo cải thiện bổ sung nhất quán.</p><p>Ứng viên vẫn còn năm vị thế cuối kỳ, lâu nhất 127 ngày; tháng xấu nhất ở ký quỹ 5 USDT lỗ khoảng 1,75%. Ký quỹ 20 USDT kết thúc 662,92–677,76 trong chín tháng, vẫn không đạt 50% mỗi tháng. Không tự nâng ứng viên lên giao dịch thật.</p></section>
<section class="panel"><h2>Bỏ từng điều kiện và thử riêng từng điều kiện</h2><p>Ở mức ký quỹ 5 USDT. Mỗi khoảng kết quả là hai mức phí/trượt giá; sụt giảm lớn nhất lấy trên cả đường chín tháng và bảy tài khoản khởi chạy riêng ba tháng.</p><div class="scroll"><table><thead><tr><th>Điều kiện giữ lại</th><th>9 tháng cơ sở</th><th>9 tháng cao</th><th>Kỳ 3 tháng có lời</th><th>DD lớn nhất mọi kỳ</th></tr></thead><tbody>__KEYTABLE__</tbody></table></div><p>14 trường hợp ba tháng là bảy kỳ chồng lấn × hai chi phí, không phải 14 mẫu độc lập. Tài khoản ba tháng dương không đồng nghĩa từng tháng dương. Vị thế còn mở luôn được định giá, không loại khỏi kết quả.</p></section>
<section class="panel"><h2>Đóng góp khi bật một điều kiện</h2><p>“Dùng riêng” = điều kiện đó trừ không lọc. “Thêm vào ba điều kiện khác” = đủ bốn trừ bỏ điều kiện đó. “Trung bình 8 cặp” đo chênh lệch khi bật/tắt nó trong mọi tổ hợp ba điều kiện còn lại. Đơn vị lợi nhuận: USDT; chênh lệch DD: điểm phần trăm, âm là giảm sụt giảm.</p><div class="scroll"><table><thead><tr><th>Điều kiện</th><th>Ký quỹ/vị thế</th><th>Chi phí</th><th>Dùng riêng</th><th>Thêm vào ba điều kiện khác</th><th>TB 8 cặp</th><th>Chênh lệch DD TB</th><th>Cặp hoàn tất</th></tr></thead><tbody>__EFFECTS__</tbody></table></div><p class="muted">Đây là chênh lệch xác định trong mô phỏng, không phải ước lượng tác động nhân quả trên thị trường. Bộ lọc thay đổi thứ tự khớp và việc chiếm chỗ; hiệu quả không cộng tuyến tính. Không suy diễn ý nghĩa thống kê từ tám cặp phụ thuộc nhau.</p></section>
<section class="panel"><h2>Tài sản và kết quả theo tháng</h2><label>Tổ hợp và quy mô<select id="strategy">__OPTIONS__</select></label><div class="legend"><span><i style="background:#62d6c2"></i>Chi phí cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản đã tính cả vị thế mở"></svg><div id="chartStatus"></div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div><h3>Vốn cam kết và thời gian giữ</h3><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Ký quỹ TB</th><th>Đủ 5 vị thế</th><th>Khóa mở mới</th><th>Danh nghĩa vào / vốn</th><th>Trung vị giữ lệnh đóng</th><th>Lệnh mở lâu nhất</th></tr></thead><tbody id="utilization"></tbody></table></div><h3>Bảy tài khoản khởi chạy riêng 500 USDT</h3><div class="scroll"><table><thead><tr><th>Tháng bắt đầu</th><th>Chi phí</th><th>Tài sản cuối kỳ</th><th>DD</th><th>Đã vào</th><th>Còn mở</th><th>Trạng thái</th></tr></thead><tbody id="rolling"></tbody></table></div><p id="stopDetails"></p></section>
<section class="panel"><h2>Đầy đủ 32 cấu hình</h2><div class="scroll"><table><thead><tr><th>Cấu hình</th><th>9 tháng cơ sở</th><th>9 tháng cao</th><th>Khoảng cuối kỳ 3 tháng hoàn tất</th><th>Kỳ có lời</th><th>Không hoàn tất</th><th>DD lớn nhất</th></tr></thead><tbody>__TABLE__</tbody></table></div></section>
<section class="panel"><h2>Dữ liệu và kiểm chứng</h2><p>Bốn ngưỡng giữ nguyên: lợi suất 24h ≤10%; lợi suất 6h ≤0; funding thực đã trả trong 24h ≥−0,1%; 0&lt;ATR14 nến 1h/giá≤5%. Chỉ dùng nến đã đóng gần nhất dưới một giờ tuổi, funding trễ ít nhất 60 giây. __MISSING__ sự kiện thiếu dữ liệu điều kiện. Bản không lọc giữ nguyên tín hiệu gốc; các bản có lọc dùng chung điều kiện đủ dữ liệu.</p><p>111 kiểm thử đạt; 16 tập tín hiệu kiểm tra cắt tương lai và dựng lại độc lập bốn bất đẳng thức; 512 sổ tài khoản, phí, funding, ngân sách và kết quả tháng đối soát. 64 đường không lọc/đủ bốn điều kiện khớp chính xác lượt trước; tám đường dùng riêng từng điều kiện tái lập chính xác.</p><p>Cơ sở: phí 0,05% và trượt giá 0,20% mỗi lần khớp thị trường; mức cao: 0,10% và 0,50%. Tổng danh nghĩa 25/100 USDT chia cả ba phần; mức lớn chỉ để nghiên cứu. Không SL/đóng theo thời gian. DD20% khóa mở mới, tiếp tục giữ và định giá lệnh cũ; không giới hạn lỗ ở20%.</p><p class="muted">Lịch sử đã khảo sát nhiều lần, còn nguy cơ thiếu coin hủy niêm yết; bộ lọc sàn hiện tại, maintenance1% thay bậc lịch sử, lấy mẫu5 phút và chưa có orderbook. Bộ lọc không bảo đảm chống squeeze. Ký quỹ không phải mức lỗ tối đa Cross. Kết quả này chưa đủ điều kiện chuyển sang tiền thật.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">512 đường tài khoản</a> · <a href="factorial_effects.json">Chênh lệch từng điều kiện</a> · <a href="coin_contributions.json">Lãi/lỗ theo coin, gồm vị thế mở</a> · <a href="screens.json">Sự kiện 4/24/72h</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc</a></p></section></main><script>const data=__JSON__;</script><script src="dashboard.js"></script></body></html>'''
    options="".join(f'<option value="{escape(p["id"])}"'+(' selected' if p["id"]=="mask02_n25" else '')+'>'+escape(label(p))+"</option>" for p in s["specs"])
    vals=dict(STYLE=style,TARGET=str(s["target_met_rows"]),KEYTABLE="".join(summary_rows),EFFECTS="".join(effect_html),OPTIONS=options,TABLE="".join(table),MISSING=str(missing),JSON=json.dumps(data,ensure_ascii=False,separators=(",",":"),allow_nan=False).replace("</","<\\/"))
    for k,v in vals.items():html=html.replace("__"+k+"__",v)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# Tách tác dụng từng điều kiện — lượt08","",f"16 tập điều kiện ×2 quy mô ×8 cửa sổ ×2 chi phí =512 đường tài khoản. {s['target_met_rows']} đường đạt50% trong từng tháng. Không chọn lại ngưỡng theo kết quả.","",
        "Điều kiện ret6h≤0 tạo phần lớn cải thiện. Dùng riêng ở ký quỹ5USDT: chín tháng500→541,24–547,14; 14/14 trường hợp ba tháng–chi phí có lời. Không lọc:521,96–525,50; đủ4điều kiện:533,23–540,07. Các kỳ chồng lấn, không độc lập; lịch sử đã xem nhiều lần.","",
        "Vẫn có tháng lỗ tới1,75%; cuối kỳ còn5vị thế, lâu nhất127ngày. Ở ký quỹ20USDT cùng điều kiện, cuối kỳ662,92–677,76 nhưng tháng xấu nhất lỗ khoảng5,49%. Đây không phải chiến lược đạt mục tiêu hoặc đủ điều kiện live.","",
        "Bốn điều kiện: tăng24h≤10%, ret6h≤0, funding thực24h≥−0,1%, ATR1h/giá≤5%. Tín hiệu4h, vào ngay ba phần và trailing3ATR/1% giữ nguyên. Vốn500,x5,cap5; notional25/100 là tổng cả ba phần.","",
        "| Tập điều kiện/quy mô | 9 tháng cơ sở | 9 tháng cao | Khoảng3 tháng hoàn tất | Kỳ có lời | Không hoàn tất | DD lớn nhất |","|---|---:|---:|---:|---:|---:|---:|",*mdrows,"",
        "## Đóng góp của mỗi điều kiện ở đường chín tháng, ký quỹ5USDT","",
        "| Điều kiện | Chi phí | Dùng riêng trừ không lọc | Đủ4 trừ bỏ điều kiện | TB8 cặp | Chênh lệch DD TB (điểm%) |","|---|---|---:|---:|---:|---:|"]
    for e in effects:
        if e["window"]=="full" and e["notional"]==25:md.append(f"| {NAMES[e['component']]} | {e['cost']} | {money(e['singleton_minus_none'])} | {money(e['full_minus_leave_one_out'])} | {money(e['mean_equity_difference'])} | {e['mean_drawdown_difference']*100:+.2f} |")
    md.extend(["","Chênh lệch mô phỏng không chứng minh tác động nhân quả thị trường. Tám cặp phụ thuộc nhau; giữ vốn/chỗ có thể làm thay đổi danh sách khớp. Các kỳ ba tháng chồng lấn, không phải mẫu độc lập. Tài sản bao gồm vị thế mở, không giả định thanh lý hoặc bỏ lệnh lỗ.","",
        f"{audit['unit_tests_passed']} kiểm thử; {audit['journals_audited']} sổ đối soát; {audit['prior_baseline_paths_exact']} đối chứng cũ, {audit['new_paths_exact']} đường mới tái lập; 16 bộ tín hiệu kiểm tra nhân quả và dựng lại độc lập. Cấu hình live giữ nguyên.","",s["protocol"]["limitations"],"",
        "[Dashboard](dashboard.html) · [Chênh lệch từng điều kiện](factorial_effects.json) · [Lãi/lỗ theo coin](coin_contributions.json) · [Đối soát](verification.json)"])
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=512,target_passes=s["target_met_rows"],
        contribution="Factorial16subset study separates frozen guard components and portfolio interactions; all512 paths audited,64 exact controls,8 independent reruns.",
        next_steps=["Use factorial evidence to identify robust component, do not select favorable dates or exclude losing coins.",
                    "Freeze candidate and test same universe on later independently acquired data before further tuning.",
                    "Assess remaining long-held inventory and profit turnover against50%eachmonth without linear scaling."],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
