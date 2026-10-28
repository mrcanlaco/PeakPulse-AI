"""Trend-entry research: frozen selection, monthly equity and all alternatives."""
import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT, write
from search_directional_trend import OUT


def name(s):
    if s["baseline"]:
        return {"short":"Đối chứng: đảo chiều Short","long":"Đối chứng: đảo chiều Long","both":"Đối chứng: đảo chiều cả hai"}[s["mode"]]
    src=s["source"]
    return (("Phá biên" if src["family"]=="breakout" else "Hồi EMA")+" · "+
        {"long":"Long","both_trend":"Long/Short xu hướng","hybrid":"Long xu hướng + Short đảo chiều"}[s["mode"]]+" · "+
        ("BTC + độ rộng 60%" if src["regime"]=="breadth60_btc" else "không lọc thị trường")+
        f" · ký quỹ {s['notional']/5:g} · "+("giữ không hạn" if s["holding"]=="hold" else "đóng sau 168h"))


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));v=json.loads((OUT/"verification.json").read_text())
    f=json.loads((OUT/"findings.json").read_text(encoding="utf-8"))
    assert len(s["results"])==v["journals_audited"]==306
    num=lambda x:"Không hoàn tất" if x is None else f"{x:.2f}"
    tr=lambda xs:"<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in xs)+"</tr>"
    lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]}
    specs={p["id"]:p for p in s["specs"]};locked={p["strategy_id"] for p in s["selected"] if p["strategy_id"]}
    selected=[];rows=[];series=[]
    for sp in s["specs"]:
        rs=lambda w:[lookup[(sp["id"],w,c)] for c in ["base","stress"]]
        values=[name(sp),*[' / '.join(num(r["ending_equity"]) for r in rs(w)) for w in ["development","later","year"]],
            ' / '.join(f"{r['max_drawdown']*100:.2f}%" for r in rs("later")),
            ' / '.join(f"{r['side_entries'].get('LONG',0)}L + {r['side_entries'].get('SHORT',0)}S" for r in rs("later"))]
        rows.append(values)
        if sp["id"] in locked or sp["id"]=="control_short":selected.append(values)
    for r in s["results"]:
        curve=pd.read_parquet(OUT/"runs"/f"{r['id']}_equity.parquet");ix={0,len(curve)-1}
        for _,g in curve.groupby((curve["at"]-curve["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(r,points=[[int(p["at"]),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    old=(ROOT/"artifacts/directional_reversal_20260925/dashboard.html").read_text(encoding="utf-8")
    style=old.split("<style>",1)[1].split("</style>",1)[0];script=old.split("<script>",1)[1].split("</script>",1)[0]
    options="".join(f'<option value="{p["id"]}"'+(' selected' if p["id"]=="breakout_any_both_trend_n25_hold" else '')+'>'+escape(name(p))+'</option>' for p in s["specs"])
    target=f"{s['target_met_rows']}/306 đường đạt tăng 50% ở từng tháng; {s['incomplete_paths']} đường không hoàn tất."
    audit=(f"{v['journals_audited']} sổ được đối soát; {v['baseline_paths_exact']} đối chứng khớp lượt trước; {v['replayed_paths_exact']} đường chạy lại khớp. "
        f"Kiểm tra {v['independent_unique_signals']:,} mã sự kiện khác nhau, {v['market_states_checked']:,} trạng thái thị trường, "
        f"{v['causal_prefixes']} so sánh khi cắt dữ liệu tương lai; tái dựng {v['equity_states_reconstructed']:,} mốc tài sản, "
        f"{v['funding_quantities_checked']:,} khoản funding và {v['directional_fills_checked']:,} lần khớp. {v['unit_tests_passed']} kiểm thử đạt. "
        "Những phép đếm này chồng lấn giữa cấu hình, không phải số mẫu thị trường độc lập.")
    header="<tr><th>Cấu hình</th><th>Tài sản giai đoạn chọn</th><th>Tài sản 06–08/2026</th><th>Tài sản cả năm</th><th>DD 3 tháng</th><th>Vị thế vào 3 tháng</th></tr>"
    stops="".join(tr([r["id"],pd.Timestamp(r["stop_event"]["at"],unit="ms",tz="UTC").isoformat() if r["stop_event"] else "—",str(r["errors"])]) for r in v["incomplete_paths"])
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Long/Short theo xu hướng</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / XU HƯỚNG VÀ CHỌN HƯỚNG THỊ TRƯỜNG · LƯỢT 20</div><h1>__TITLE__</h1><p class="muted">01/09/2025–01/09/2026 UTC · cùng 30 altcoin · tài khoản chung 500 USDT · Cross x5 · tối đa 5 vị thế</p>
<div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div><div class="cards"><div class="card">Điểm vào mới<strong>Phá biên / hồi EMA</strong></div><div class="card">Cấu hình mới / đối chứng<strong>48 / 3</strong></div><div class="card">Đường tài khoản<strong>306</strong></div><div class="card">Kiểm thử đạt<strong>88</strong></div></div>
<section class="panel"><h2>Ứng viên khóa trước giai đoạn 06–08</h2><p>Chọn bằng dữ liệu 09/2025–05/2026: cả hai mức chi phí phải có lời, DD dưới 20%, ít nhất 20 vị thế đóng và đường tài khoản đầy đủ. Xếp theo lợi suất tháng tệ nhất ở mức chi phí bất lợi hơn, rồi tài sản cuối. Không có ứng viên thì để trống; không chọn lại dựa trên tháng 6–8.</p><p>Cặp số trong bảng: cơ sở / chi phí cao. Mỗi cửa sổ khởi chạy riêng 500 USDT. Đối chứng Short được đặt cạnh ba ứng viên để so sánh; nó không phải lựa chọn mới của lượt này.</p><div class="scroll"><table><thead>__HEADER__</thead><tbody>__SELECTED__</tbody></table></div><p>__DIAGNOSIS__</p></section>
<section class="panel"><h2>Tài sản và lợi suất từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Giai đoạn<select id="window"><option value="later" selected>Tài khoản mới · 06–08/2026</option><option value="year">Cả năm · 09/2025–08/2026</option><option value="development">Giai đoạn chọn · 09/2025–05/2026</option></select></label><label>Chi phí<select id="cost"><option value="stress" selected>Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm Long và Short còn mở"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Toàn bộ phương án, kể cả không được chọn</h2><p>Danh nghĩa 25/100 USDT là tổng cả ba phần, tương ứng ký quỹ dự kiến 5/20 USDT. Mức 100 USDT và đóng sau 168 giờ là giả thuyết nghiên cứu; đóng theo thời gian có thể chốt lỗ. Kết quả bao gồm vị thế mở, phí và funding.</p><div class="scroll"><table><thead>__HEADER__</thead><tbody>__ROWS__</tbody></table></div></section>
<section class="panel"><h2>Quy tắc được kiểm tra</h2><p>Long theo xu hướng: EMA20 trên EMA60, đóng trên EMA20, lợi suất 24h dương và nến 4h xanh. Short xu hướng đối xứng. Điểm vào phá biên yêu cầu đóng vượt đỉnh/đáy 20 nến trước và khối lượng ít nhất 1,5 lần trung bình 20 nến trước. Điểm vào hồi EMA yêu cầu chạm EMA20 rồi đóng về phía xu hướng, khối lượng ít nhất bằng trung bình đó.</p><p>Lọc thị trường tùy chọn: ít nhất 24 coin đủ dữ liệu; ít nhất 60% trên EMA60 và BTC xác nhận xu hướng tăng mới mở Long. Short yêu cầu 60% dưới EMA60 và BTC xu hướng giảm. Hướng thị trường chỉ chặn lệnh mới, không tự đóng vị thế đang giữ. Toàn bộ điều kiện dùng nến đã đóng.</p><p>Ba cách ghép: chỉ Long xu hướng; Long/Short đều theo xu hướng; Long xu hướng cộng Short đảo chiều có lọc 6h của lượt trước. Ở nhóm ghép, ưu tiên chung theo độ lớn lợi suất 24h chia cho ATR/giá, thay cho điểm z-score cũ. Các đối chứng giữ nguyên thứ tự cũ.</p><p>Ba phần chỉ thêm khi giá thuận 0,25 ATR, hết hạn thêm sau 6h. Trailing kích hoạt 3 ATR, hồi 1%, quan sát mỗi 5 phút và khớp ở giá mở tiếp theo cộng trượt bất lợi. Mỗi coin một vị thế, không tự đảo chiều. Dừng mở mới ở mức giảm 20% giữ nguyên vị thế cũ, nên không giới hạn mức lỗ cuối cùng.</p><p>__AUDIT__</p></section>
<section class="panel"><h2>Đường không hoàn tất</h2><p>Hai đường của cùng cấu hình ghép Long phá biên + Short đảo chiều, 100 USDT, giữ không hạn, chi phí cơ sở chạm maintenance proxy tại cùng thời điểm. Đây là phần lịch sử chung của cửa sổ chọn và cả năm, không phải hai sự cố độc lập. Không giả định số dư thanh lý hoặc điền lợi suất 0% cho các tháng sau.</p><p>Mỗi mức chi phí chạy lại toàn bộ tài khoản, nên có thể đổi lượng khớp, lúc thoát và tín hiệu chiếm chỗ. Vì vậy đường chi phí cao không luôn thấp hơn đường cơ sở. Trong trường hợp này, các lần vào SOON khác nhau giữa hai mức; không thể diễn giải thành trả phí cao giúp chiến lược an toàn hơn.</p><div class="scroll"><table><thead><tr><th>Đường</th><th>Thời điểm UTC</th><th>Lý do</th></tr></thead><tbody>__STOPS__</tbody></table></div></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Không có bằng chứng đạt 50% mỗi tháng. Đây là dữ liệu lịch sử đã dùng nhiều lần, không phải kiểm định tương lai độc lập. Các cửa sổ và cấu hình chồng lấn; không xem chúng là hàng trăm thử nghiệm độc lập. Phí/trượt cơ sở 0,05%/0,20%, cao 0,10%/0,50% mỗi lần khớp. Dữ liệu funding thực và lỗ mở luôn được tính.</p><p>Bộ lọc sàn hiện tại, maintenance margin giả định 1% tổng danh nghĩa thay cho bậc lịch sử, thiếu sổ lệnh lịch sử và khả năng thiếu coin hủy niêm yết vẫn giới hạn độ tin cậy. Chưa bật live; không thay cấu hình tài khoản thật.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">306 kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a> · <a href="candidate_lock.json">Ứng viên đã khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,value in dict(STYLE=style,TITLE=escape(f["title"]),TARGET=escape(target),FINDING=escape(f["finding"]),DIAGNOSIS=escape(f["diagnosis"]),
        HEADER=header,SELECTED="".join(tr(r) for r in selected),OPTIONS=options,ROWS="".join(tr(r) for r in rows),AUDIT=escape(audit),STOPS=stops,SCRIPT=script).items():html=html.replace("__"+k+"__",value)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+f["title"],"",target,"",f["finding"],"",f["diagnosis"],"",
        "Mỗi cửa sổ khởi chạy riêng 500 USDT: chọn 09/2025–05/2026; kiểm tra 06–08/2026; cả năm 09/2025–08/2026. Cặp số: cơ sở / chi phí cao.","",
        "| Cấu hình |Giai đoạn chọn|3 tháng sau|Cả năm|DD3tháng|Vị thế3tháng|","|---|---:|---:|---:|---:|---|",
        *["| "+" | ".join(r)+" |" for r in rows],"",audit,"",
        "Lịch sử đã dùng lặp, không phải OOS sạch. Currentfilters,MMR1%proxy,5msampling,assumedslippage,universebias. Không thay live.","",
        "Hai đường không hoàn tất cùng chạm maintenance proxy ngày 14/11/2025, thuộc phần lịch sử chung của cùng cấu hình, không phải hai sự cố độc lập. Không gán tài sản thanh lý hoặc lợi suất cho phần sau. Mỗi mức chi phí chạy lại tài khoản và có thể đổi các vị thế vào/thoát; mức cao không luôn thấp hơn mức cơ sở.","",
        "[Dashboard](dashboard.html) · [Quy tắc khóa](protocol.json) · [Đối soát](verification.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=306,target_passes=s["target_met_rows"],
        evidence=f["finding"],next_steps=f["next_steps"],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
