"""Direction quotas and start-date robustness on one comparable dashboard."""
import json
from html import escape
import pandas as pd
from compare_account_risk import ROOT,write
from search_side_capacity import OUT,REFERENCES


def name(sp):
    if sp["id"]=="short_control":return "Đối chứng Short đảo chiều · ký quỹ 5"
    ref=sp["reference_id"]
    label={REFERENCES[0]:"Phá biên hai chiều · ký quỹ 5",REFERENCES[1]:"Phá biên + lọc thị trường · ký quỹ 20",
           REFERENCES[2]:"Long hồi EMA + Short đảo chiều · ký quỹ 5"}[ref]
    alloc="chung 5 chỗ" if sp["allocation"]=="shared" else f"{sp['policy']['side_caps']['LONG']} Long / {sp['policy']['side_caps']['SHORT']} Short"
    return label+" · "+alloc


def main():
    s=json.loads((OUT/"summary.json").read_text(encoding="utf-8"));v=json.loads((OUT/"verification.json").read_text())
    f=json.loads((OUT/"findings.json").read_text(encoding="utf-8"));assert len(s["results"])==v["journals_audited"]==384
    control_dir=OUT/"long_contribution_control"
    control=json.loads((control_dir/"summary.json").read_text(encoding="utf-8"))
    cv=json.loads((control_dir/"verification.json").read_text());assert cv["journals_audited"]==len(control["results"])==24
    lookup={(r["strategy_id"],r["window"],r["cost"]):r for r in s["results"]}
    robust={(r["strategy_id"],r["cost"]):r for r in s["robustness"]};specs={sp["id"]:sp for sp in s["specs"]}
    num=lambda x:"Không hoàn tất" if x is None else f"{x:.2f}"
    tr=lambda xs:"<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in xs)+"</tr>"
    rows=[];selected=[];comparison=[];series=[];locked={r["strategy_id"] for r in s["selected"] if r["strategy_id"]}
    for sp in s["specs"]:
        rs=lambda w:[lookup[(sp["id"],w,c)] for c in ["base","stress"]]
        robs=[robust[(sp["id"],c)] for c in ["base","stress"]]
        row=[name(sp),*[' / '.join(num(r["ending_equity"]) for r in rs(w)) for w in ["year","later"]],
             ' / '.join(str(r["profitable"])+"/10" for r in robs),
             ' / '.join(num(r["worst_ending"]) for r in robs),
             ' / '.join(f"{r['worst_drawdown']*100:.2f}%" for r in robs),
             ' / '.join(str(r["nonoverlapping_profitable"])+"/4" for r in robs)]
        rows.append(row)
        if sp["id"] in locked or sp["id"]=="short_control":selected.append(row)
        if sp["reference_id"]==REFERENCES[0]:
            y=lookup[(sp["id"],"year","base")];q=lookup[(sp["id"],"later","base")]
            comparison.append(["Chung 5 chỗ" if sp["allocation"]=="shared" else sp["allocation"],num(y["ending_equity"]),num(q["ending_equity"]),
                f"{y['side_entries'].get('LONG',0)} L / {y['side_entries'].get('SHORT',0)} S",
                num(y["side_metrics"]["sides"]["LONG"]["total_contribution"]),num(y["side_metrics"]["sides"]["SHORT"]["total_contribution"]),
                f"{y['side_metrics']['fraction_time_both_sides']*100:.1f}%"])
    for row in s["results"]:
        curve=pd.read_parquet(OUT/"runs"/f"{row['id']}_equity.parquet");ix={0,len(curve)-1}
        for _,g in curve.groupby((curve["at"]-curve["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,points=[[int(p["at"]),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    for row in control["results"]:
        curve=pd.read_parquet(control_dir/"runs"/f"{row['id']}_equity.parquet");ix={0,len(curve)-1}
        for _,g in curve.groupby((curve["at"]-curve["at"].iloc[0])//86400000):ix.update([g.index[0],g.index[-1],g.equity.idxmin(),g.equity.idxmax()])
        series.append(dict(row,strategy_id="matched_short3",side_entries={side:row["side_metrics"]["sides"][side]["entries"] for side in ["LONG","SHORT"]},
            points=[[int(p["at"]),round(p.equity,6)] for _,p in curve.loc[sorted(ix)].iterrows()]))
    write(OUT/"dashboard_data.json",series)
    old=(ROOT/"artifacts/directional_trend_20260925/dashboard.html").read_text(encoding="utf-8")
    style=old.split("<style>",1)[1].split("</style>",1)[0];script=old.split("<script>",1)[1].split("</script>",1)[0]
    script="const spans="+json.dumps(s["protocol"]["windows"])+script[script.index(",labels="):]
    options='<option value="matched_short3" selected>Đối chứng bổ sung: chỉ 3 chỗ Short, cùng tín hiệu và thứ tự nhóm ghép</option>'+"".join(f'<option value="{sp["id"]}">'+escape(name(sp))+'</option>' for sp in s["specs"])
    periods="".join(f'<option value="{w}"'+(' selected' if w=="later" else '')+'>'+escape(
        {"year":"Cả năm 09/2025–08/2026","development":"Giai đoạn chọn 09/2025–05/2026","later":"3 tháng từ 06/2026"}.get(w,
        "3 tháng từ "+pd.Timestamp(span[0],unit="ms",tz="UTC").strftime("%m/%Y")))+'</option>' for w,span in s["protocol"]["windows"].items())
    header="<tr><th>Cấu hình</th><th>Tài sản cả năm</th><th>Tài sản 06–08</th><th>Cửa sổ 3 tháng có lời</th><th>Tài sản cửa sổ tệ nhất*</th><th>DD lớn nhất trong các cửa sổ</th><th>Quý không chồng lấn có lời</th></tr>"
    target=f"{s['target_met_rows']+control['target_met_rows']}/408 đường đạt 50% ở từng tháng: 384 đường chính + 24 đối chứng bổ sung."
    audit=(f"{v['journals_audited']} sổ đối soát, {v['baseline_paths_exact']} đối chứng dùng chung khớp lượt trước, {v['replayed_paths_exact']} đường chạy lại khớp. "
        f"Kiểm tra {v['quota_entry_checks']:,} lần vào theo giới hạn từng chiều, {v['directional_fills_checked']:,} lần khớp, "
        f"{v['funding_quantities_checked']:,} khoản funding và tái dựng {v['equity_states_reconstructed']:,} mốc tài sản. "
        f"{v['unit_tests_passed']} kiểm thử đạt; dữ liệu, mã nguồn khóa và cấu hình live khớp hash. Các phép đếm chồng lấn giữa cấu hình.")
    stops="".join(tr([r["id"],str(r["errors"])]) for r in v["incomplete_paths"]) or '<tr><td colspan="2">Không có đường bị dừng trong lượt này.</td></tr>'
    control_rows=[]
    for cost in ["base","stress"]:
        rs=[r for r in control["results"] if r["cost"]==cost and (r["window"]=="later" or r["window"].startswith("roll_"))]
        y=next(r for r in control["results"] if r["cost"]==cost and r["window"]=="year")
        q=next(r for r in control["results"] if r["cost"]==cost and r["window"]=="later")
        control_rows.append(["Cơ sở" if cost=="base" else "Cao",num(y["ending_equity"]),num(q["ending_equity"]),
            str(sum(r["ending_equity"]>500 for r in rs))+"/10",num(min(r["ending_equity"] for r in rs)),
            f"{max(r['max_drawdown'] for r in rs)*100:.2f}%",str(sum(r["comparison"]["hybrid_minus_control"]>0 for r in rs))+"/10"])
    html='''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đảo Vàng · Chia chỗ Long và Short</title><style>__STYLE__</style></head><body><main>
<div class="eyebrow">ĐẢO VÀNG / CHIA CHỖ HAI CHIỀU VÀ NGÀY KHỞI CHẠY · LƯỢT 21</div><h1>__TITLE__</h1><p class="muted">500 USDT · Cross x5 · tối đa 5 vị thế · cùng ba nguồn tín hiệu đã khóa</p><div class="notice"><b>__TARGET__</b><p>__FINDING__</p></div>
<div class="cards"><div class="card">Phân bổ thử<strong>Chung / 1–4 Long</strong></div><div class="card">Tài khoản ba tháng<strong>10 ngày khởi đầu</strong></div><div class="card">Đường chính / đối chứng thêm<strong>384 / 24</strong></div><div class="card">Kiểm thử đạt<strong>89</strong></div></div>
<section class="panel"><h2>Phân bổ được chọn bằng giai đoạn 09/2025–05/2026</h2><p>Chọn một tỷ lệ cho mỗi ứng viên: cả hai mức chi phí phải có lời, DD dưới 20%, ít nhất 20 vị thế đã đóng và đường tài khoản đầy đủ. Xếp theo lợi suất tháng tệ nhất rồi tài sản cuối. Khóa lựa chọn trước khi chạy các cửa sổ còn lại.</p><p>Cặp số: cơ sở / chi phí cao. Mọi cửa sổ bắt đầu riêng 500 USDT; số cửa sổ có lời tính đủ mẫu số 10, kể cả đường không hoàn tất.</p><div class="scroll"><table><thead>__HEADER__</thead><tbody>__SELECTED__</tbody></table></div><p>__DIAGNOSIS__</p></section>
<section class="panel"><h2>Riêng ứng viên phá biên hai chiều, ký quỹ 5 USDT</h2><p>Chi phí cơ sở. Đóng góp mỗi chiều gồm kết quả đã chốt, vị thế mở, phí và funding của tài khoản dùng chung; không phải cộng hai backtest riêng. L1S4 nghĩa là tối đa 1 Long và 4 Short.</p><div class="scroll"><table><thead><tr><th>Phân bổ</th><th>Tài sản cả năm</th><th>Tài sản 06–08</th><th>Vị thế vào cả năm</th><th>Đóng góp Long</th><th>Đóng góp Short</th><th>Thời gian giữ cả hai chiều</th></tr></thead><tbody>__COMPARISON__</tbody></table></div></section>
<section class="panel"><h2>Long có giúp hơn việc chỉ giảm số Short?</h2><p>Đối chứng bổ sung chỉ bỏ tín hiệu Long khỏi nhóm 2 Long / 3 Short, giữ nguyên 3 chỗ Short, tín hiệu, thứ tự ưu tiên, khối lượng và luật thoát. Hai chỗ Long để trống; vẫn một tài khoản 500 USDT. Đối chứng này được thiết kế sau khi xem 384 kết quả để giải thích cơ chế, không phải kiểm định độc lập.</p><div class="scroll"><table><thead><tr><th>Chi phí</th><th>Chỉ 3 Short: cả năm</th><th>Chỉ 3 Short: 06–08</th><th>Cửa sổ có lời</th><th>Tài sản cửa sổ tệ nhất</th><th>DD lớn nhất</th><th>Thêm Long nâng tài sản</th></tr></thead><tbody>__CONTROL_ROWS__</tbody></table></div><p>Có 10/10 cửa sổ có lời ở cả hai mức chi phí khi chỉ giữ 3 Short. Thêm Long chỉ nâng tài sản cuối ở 4/10 cửa sổ. Trong tài khoản cả năm cơ sở, phần Long đóng góp −4,37 USDT; tài sản nhóm ghép 561,56 USDT so với chỉ 3 Short 562,00 USDT. Tuy nhiên nhóm ghép có DD lớn nhất trên các cửa sổ thấp hơn: 3,30% so với 4,93%. Đây là sự đánh đổi quan sát được, chưa chứng minh hiệu quả phòng hộ bền vững.</p><p>Khi bỏ Long, các coin trước đó bị vị thế Long chiếm có thể nhận Short; danh sách Short thực vào thay đổi ở cả 24 đường. Vì vậy chênh lệch tổng tài sản không bằng riêng PnL Long. 24 sổ đã đối soát, 6 đường chạy lại khớp; toàn bộ số liệu vẫn gồm lỗ mở và funding.</p></section>
<section class="panel"><h2>Tài sản và từng tháng</h2><div class="filters"><label>Cấu hình<select id="strategy">__OPTIONS__</select></label><label>Cửa sổ<select id="window">__PERIODS__</select></label><label>Chi phí<select id="cost"><option value="stress" selected>Cơ sở và chi phí cao</option><option value="base">Chỉ cơ sở</option></select></label></div><div class="legend"><span><i style="background:#62d6c2"></i>Cơ sở</span><span><i style="background:#e6afed"></i>Chi phí cao</span></div><svg id="chart" viewBox="0 0 1200 340" role="img" aria-label="Tài sản gồm các vị thế chưa đóng"></svg><div id="chartStatus">Đang tải…</div><div class="scroll"><table><thead id="monthHead"></thead><tbody id="monthBody"></tbody></table></div></section>
<section class="panel"><h2>Toàn bộ phân bổ và độ phụ thuộc ngày khởi chạy</h2><p>10 tài khoản ba tháng khởi chạy ngày đầu mỗi tháng từ 09/2025 đến 06/2026. Chúng chồng lấn, không phải 10 mẫu độc lập. Bốn quý không chồng lấn là 09–11/2025, 12/2025–02/2026, 03–05/2026 và 06–08/2026. Dữ liệu đã dùng nghiên cứu trước đó; không coi đây là kiểm định tương lai mới.</p><div class="scroll"><table><thead>__HEADER__</thead><tbody>__ROWS__</tbody></table></div><p>*Tài sản tệ nhất chỉ tính trong đường hoàn tất; kiểm tra bảng đường bị dừng bên dưới trước khi diễn giải. Tỷ lệ có lời luôn giữ mẫu số 10.</p></section>
<section class="panel"><h2>Quy tắc và kiểm tra</h2><p>Giữ cùng một tài khoản 500 USDT, x5, 5 chỗ, mỗi coin một vị thế. Các tỷ lệ cứng là 1/4, 2/3, 3/2, 4/1 Long/Short. Chỗ trống của chiều kia không được mượn. Không ép đóng lệnh để cân lại tỷ lệ; tín hiệu bị từ chối không tự được gửi lại sau này. Ba phần vào vẫn tính là một vị thế.</p><p>Tổng danh nghĩa 25 hoặc 100 USDT cho cả ba phần, tương ứng ký quỹ dự kiến 5 hoặc 20 USDT; mức 100 chỉ là nghiên cứu. Thêm khi giá thuận 0,25 ATR, hết hạn thêm sau 6h. Trailing kích hoạt 3 ATR, hồi 1%, quan sát nến đóng 5 phút. Không SL, không đóng theo thời gian. Khi DD 20%, dừng mở mới nhưng giữ vị thế cũ và tiếp tục tính funding, lỗ mở.</p><p>__AUDIT__</p><div class="scroll"><table><thead><tr><th>Đường không hoàn tất</th><th>Lý do</th></tr></thead><tbody>__STOPS__</tbody></table></div></section>
<section class="panel"><h2>Giới hạn kết luận</h2><p>Mục tiêu 50% mỗi tháng chưa đạt. Phí/trượt cơ sở 0,05%/0,20%, cao 0,10%/0,50% mỗi lần khớp; mỗi mức chạy lại tài khoản nên có thể đổi vị thế và kết quả không luôn xếp theo mức phí. Funding thực và vị thế mở đều được tính. Bộ lọc sàn hiện tại, maintenance margin proxy 1%, thiếu sổ lệnh/bậc ký quỹ lịch sử và thiên lệch tập coin vẫn giới hạn kết luận. Không bật live, không thay vốn hay cấu hình tài khoản thật.</p><p><a href="report.md">Báo cáo</a> · <a href="comparison.csv">384 kết quả</a> · <a href="verification.json">Đối soát</a> · <a href="protocol.json">Quy tắc khóa</a></p></section></main><script>__SCRIPT__</script></body></html>'''
    for k,value in dict(STYLE=style,TITLE=escape(f["title"]),TARGET=escape(target),FINDING=escape(f["finding"]),DIAGNOSIS=escape(f["diagnosis"]),
        HEADER=header,SELECTED="".join(tr(r) for r in selected),COMPARISON="".join(tr(r) for r in comparison),OPTIONS=options,PERIODS=periods,
        ROWS="".join(tr(r) for r in rows),CONTROL_ROWS="".join(tr(r) for r in control_rows),AUDIT=escape(audit),STOPS=stops,SCRIPT=script).items():html=html.replace("__"+k+"__",value)
    (OUT/"dashboard.html").write_text(html,encoding="utf-8")
    md=["# "+f["title"],"",target,"",f["finding"],"",f["diagnosis"],"",
        "Cặp số: cơ sở / chi phí cao. Các tài khoản độc lập về số dư khởi đầu 500 USDT, nhưng cửa sổ dữ liệu chồng lấn và không phải mẫu độc lập.","",
        "| Cấu hình |Cả năm|06–08|Có lời/10|Tài sản cửa sổ tệ nhất|DD cửa sổ lớn nhất|Quý có lời/4|","|---|---:|---:|---:|---:|---:|---:|",
        *["| "+" | ".join(r)+" |" for r in rows],"",audit,"",
        "Đối chứng bổ sung (sau khi xem kết quả): chỉ giữ 3 Short, cùng tín hiệu/thứ tự/giới hạn với nhóm ghép 2L3S. Cả năm 562,00/560,65 USDT; có lời 10/10 cửa sổ ở cả hai chi phí; thêm Long chỉ nâng tài sản ở 4/10 cửa sổ. Danh sách Short thực vào thay đổi do Long chiếm coin. Nhóm ghép giảm DD cửa sổ cơ sở từ4,93% xuống3,30%, nhưng chưa chứng minh lợi thế lợi nhuận Long. 24 sổ được đối soát,6 đường chạy lại khớp.","",
        "Tài sản cửa sổ tệ nhất chỉ tính đường hoàn tất; số cửa sổ có lời giữ mẫu số 10. Lịch sử dùng lặp, current filters, MMR1%proxy, mẫu5phút, trượt giá giả định và thiên lệch tập coin. Chưa bật live.","",
        "[Dashboard](dashboard.html) · [Quy tắc](protocol.json) · [Đối soát](verification.json)"]
    (OUT/"report.md").write_text("\n".join(md),encoding="utf-8")
    write(OUT/"goal_progress.json",dict(classification="progress",goal_status="active",achieved=False,runs=408,main_runs=384,additional_controls=24,target_passes=s["target_met_rows"]+control["target_met_rows"],
        evidence=f["finding"],next_steps=f["next_steps"],live_config_unchanged=True))
    print(OUT/"dashboard.html")


if __name__=="__main__":main()
