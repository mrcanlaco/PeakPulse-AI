import urllib.request
import json

with urllib.request.urlopen("http://127.0.0.1:8899/api/shadows") as resp:
    shadows = json.loads(resp.read().decode())
    active_pos_count = sum(len(s.get("active_positions", [])) for s in shadows)
    print(f"Total active positions across 20 bots: {active_pos_count}")
    for s in shadows[:5]:
        pos = s.get("active_positions", [])
        print(f"Bot {s['id']}: Status={s['status']} | Equity=${s['equity']:,.2f} | Open Positions={len(pos)}")
        for p in pos:
            print(f"   -> {p['symbol']} | Qty: {p['qty']:.4f} | Entry: ${p['entry_price']:,.2f} | Mark: ${p['mark_price']:,.2f} | PnL: ${p['unrealized_pnl']:+,.2f} ({p['unrealized_pnl_pct']:+.2f}%)")
