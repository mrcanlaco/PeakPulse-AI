"""Queue-priority research with unchanged signal population and matched controls."""
import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write
from search_signal_priority import OUT

LABELS=dict(zscore="Độ lệch giá gốc",impulse_atr="Động lượng / ATR",low_vol="Biến động thấp",liquidity="Thanh khoản cao",
            funding24="Funding đã biết",weak6="Yếu trong 6h",body_atr="Thân nến / ATR")


def main():
    s=json.loads((OUT/"summary.json").read_text());v=json.loads((OUT/"verification.json").read_text());f=json.loads((OUT/"findings.json").read_text(encoding="utf-8"))
    assert len(s["results"])==v["journals_audited"]==336
    look={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]};rob={(r["strategy_id"],r["cost"]):r for r in s["robustness"]}
    name=lambda sp:LABELS[sp["ranking"]]+f" · {sp['cap']} chỗ Short"
    num=lambda x:"Không hoàn tất" if x is None else f"{x:.2f}"
    tr=lambda xs:"<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in xs)+"</tr>"
    rows=[];picked=[];series=[];locked={r["strategy_id"] for r in s["selected"] if r["strategy_id"]}
    for sp in s["specs"]:
        rs=lambda w:[look[(sp["id"],w,c)] for c in ["base","stress"]]
        robs=[rob[(sp["id"],c)] for c in ["base","stress"]]
        row=[name(sp),*[' / '.join(num(r["ending_equity"]) for r in rs(w)) for w in ["development","later","year"]],
            ' / '.join(f"{r['max_drawdown']*100:.2f}%" for r in rs("year")),
            ' / '.join(str(r["profitable"])+"/10" for r in robs),
            ' / '.join(num(r["worst_ending"]) for r in robs)]
        rows.append(row)
        if sp["id"] in locked or sp["baseline"]:picked.append(row)
    for row in s["results"]:
        curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(curve)-1}
        for _,g in curve.groupby((curve["at"]-curve["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(p["at"]),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    old=(ROOT/"artifacts/side_capacity_20260925/dashboard.html").read_text(encoding="utf-8")
    style=old.split("<style>",1)[1].split("</style>",1)[0];script=old.split("<script>",1)[1].split("</script>",1)[0]
    script="const spans="+json.dumps(s["protocol"]["windows"])+script[script.index(",labels="):]
    options="".join(f'<option value="{sp["id"]}"'+(' selected' if sp["id"]=="impulse_atr_cap5" else '')+'>'+escape(name(sp))+'</option>' for sp in s["specs"])
    periods="".join(f'<option value="{w}"'+(' selected' if w=="later" else '')+'>'+escape(
        {"year":"Cả năm 09/2025–08/2026","development":"Giai đoạn chọn 09/2025–05/2026","later":"3 tháng từ 06/2026"}.get(w,
        "3 tháng từ "+pd.Timestamp(span[0],unit="ms",tz="UTC").strftime("%m/%Y")))+'</option>' for w,span in s["protocol"]["windows"].items())
    header="<tr><th>Ưu tiên</th><th>Tài sản giai đoạn chọn</th><th>Tài sản 06–08</th><th>Tài sản cả năm</th><th>DD cả năm</th><th>Cửa sổ 3 tháng có lời</th><th>Tài sản cửa sổ tệ nhất*</th></tr>"
    audit=(f"{v['journals_audited']} sổ đối soát, {v['baseline_paths_exact']} đối chứng khớp toàn bộ lượt cũ, {v['replayed_paths_exact']} đường chạy lại khớp. "
        f"Tính lại độc lập đặc trưng của {v['independent_event_features']} sự kiện, {v['causal_prefixes']} phép so sánh khi cắt dữ liệu tương lai; "
        f"đối soát {v['directional_fills_checked']:,} lần khớp, {v['funding_quantities_checked']:,} khoản funding và tái dựng {v['equity_states_reconstructed']:,} mốc tài sản. "
        f"{v['unit_tests_passed']} kiểm thử đạt. Các phép đếm chồng lấn giữa cấu hình, không phải số mẫu thị trường độc lập.")
    reordered="".join(tr([LABELS[k],n]) for k,n in v["reordered_timestamps"].items())
    target=f"{s['target_met_rows']}/336 đường đạt tăng 50% ở từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Ưu tiên tín hiệu Short</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / THỨ TỰ TÍN HIỆU CÙNG THỜI ĐIỂM · LƯỢT 22</div><h1>__TITLE__</h1><p class="muted">500 USDT · Cross x5 · tổng danh nghĩa 25 USDT/vị thế · cùng 497 sự kiện Short</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div>
<div class="cards"><div class="card">Cách xếp hạng<strong>7</strong></div><div class="card">Giới hạn vị thế<strong>3 / 5</strong></div><div class="card">Cấu hình / đường chạy<strong>14 / 336</strong></div><div class="card">Kiểm thử đạt<strong>95</strong></div></div>
<section class="panel"><h2>Lựa chọn khóa trước giai đoạn tháng 6–8</h2><p>Chọn một cách ưu tiên cho mỗi giới hạn vị thế, chỉ dùng 09/2025–05/2026: cả hai mức chi phí có lời, DD dưới 20%, ít nhất 20 vị thế đóng và đường đầy đủ. Xếp theo tháng tệ nhất rồi tài sản cuối. Bảng gồm các lựa chọn và hai đối chứng cũ. Cặp số: cơ sở / chi phí cao. Mỗi cửa sổ khởi chạy riêng 500 USDT, gồm lãi/lỗ còn mở.</p><div class="scroll"><table><thead>__HEADER__</thead><tbody>__PICKED__</tbody></table></div><p>__DIAGNOSIS__</p></section>
<section class="panel"><h2>Tài sản và lợi suất từng tháng</h2><div class="filters"><label>Cách ưu tiên<select id="strategy">__OPTIONS__</select></label><label>Cửa sổ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress" selected>Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm các vị thế còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Toàn bộ 14 cấu hình</h2><p>10 cửa sổ ba tháng khởi chạy từ 09/2025 đến 06/2026 chồng lấn nhau, không phải 10 mẫu độc lập. Giữ cả những cửa sổ thua lỗ trong báo cáo; đây là lịch sử đã nghiên cứu nhiều lần, không phải kiểm định tương lai mới.</p><div class="scroll"><table><thead>__HEADER__</thead><tbody>__ROWS__</tbody></table></div><p>*Chỉ tính đường hoàn tất khi lấy tài sản tệ nhất; mẫu số có lời luôn giữ 10.</p></section>
<section class="panel"><h2>Thay đổi chính xác những gì?</h2><p>497 tín hiệu nằm ở 273 thời điểm. Có 83 thời điểm nhiều tín hiệu cùng xuất hiện, gồm 307 sự kiện; tối đa 17 ứng viên cùng lúc. Mọi cấu hình giữ nguyên coin, thời điểm, ATR, mã tín hiệu và hướng. Chỉ đổi thứ tự xử lý trong cùng thời điểm; không kéo tín hiệu ở tương lai về trước, không bỏ các coin đột biến.</p><div class="scroll"><table><thead><tr><th>Cách ưu tiên</th><th>Số thời điểm đổi thứ tự so với gốc</th></tr></thead><tbody>__REORDERED__</tbody></table></div><p>Độ lệch giá: điểm z-score gốc. Động lượng/ATR: trị tuyệt đối lợi suất 24h chia ATR/giá. Biến động thấp: ATR/giá nhỏ hơn được ưu tiên. Thanh khoản: tổng khối lượng quy đổi 24h cao hơn. Funding: tổng tỷ lệ đã thanh toán trong 24h, chỉ dùng thông tin có trước tín hiệu ít nhất 60 giây; làm tròn 12 chữ số thập phân để tránh nhiễu cộng số thực khi phá hòa. Yếu 6h: lợi suất 6h thấp hơn. Thân nến/ATR: độ giảm từ mở đến đóng nến 4h chia ATR.</p><p>Tiếp tục vào ba phần khi giá thuận 0,25 ATR; hết hạn thêm sau 6h. Trailing kích hoạt 3 ATR, hồi 1%, quan sát nến đóng 5 phút, khớp mở nến tiếp theo cộng trượt bất lợi. Không SL, không đóng theo thời gian. Dừng mở mới ở DD20%, giữ vị thế và tính funding/lỗ mở. Không tăng danh nghĩa.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Mục tiêu 50% từng tháng chưa đạt. Phí/trượt cơ sở 0,05%/0,20%, cao 0,10%/0,50% mỗi lần khớp. Mỗi mức chạy lại tài khoản nên có thể thay đổi vị thế; đường chi phí cao không luôn thấp hơn. Bộ lọc sàn hiện tại, maintenance proxy 1%, thiếu sổ lệnh/bậc ký quỹ lịch sử và thiên lệch tập coin vẫn giới hạn kết luận. Chưa bật live; cấu hình tài khoản thật giữ nguyên.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">336 kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,value in dict(STYLE=style,TITLE=escape(f["title"]),TARGET=escape(target),FINDING=escape(f["finding"]),DIAGNOSIS=escape(f["diagnosis"]),
        HEADER=header,PICKED="".join(tr(r) for r in picked),OPTIONS=options,PERIODS=periods,ROWS="".join(tr(r) for r in rows),
        REORDERED=reordered,AUDIT=escape(audit),SCRIPT=script).items():html=html.replace("__"+k+"__",value)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+f["title"],"",target,"",f["finding"],"",f["diagnosis"],"",
        "Cặp số: cơ sở / chi phí cao. Mỗi cửa sổ bắt đầu riêng500USDT; cửa sổ chồng lấn và lịch sử đã dùng lặp.","",
        "| Ưu tiên |Giai đoạn chọn|06–08|Cả năm|DD cả năm|Cửa sổ có lời|Cửa sổ tệ nhất|","|---|---:|---:|---:|---:|---:|---:|",
        *["| "+" | ".join(r)+" |" for r in rows],"",audit,"",
        "Không tăng khối lượng, không bỏ sự kiện lỗ, không thay thời điểm tín hiệu. Currentfilters,MMR1%proxy,5msampling,assumedslippage,universebias. Không bật live.","",
        "[Dashboard](dashboard.html) · [Quy tắc](protocol.json) · [Đối soát](verification.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=336,target_passes=s["target_met_rows"],
        evidence=f["finding"],next_steps=f["next_steps"],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
