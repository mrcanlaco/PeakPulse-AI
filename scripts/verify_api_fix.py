import urllib.request
import json
import time

time.sleep(1)

# Check /api/status
with urllib.request.urlopen("http://127.0.0.1:8899/api/status") as resp:
    st = json.loads(resp.read().decode())
    print("=== STATUS API CHECK ===")
    print(f"Running: {st['running_count']} / {st['total_count']}")
    print(f"Total Equity: ${st['total_equity']:,.2f}")
    print(f"BTC Regime: {st['btc_macro_regime']}")
    print(f"Feeder Status: {st['feeder_status']}")
    print(f"Global Win Rate: {st['global_win_rate']}%")

# Check /api/shadows
with urllib.request.urlopen("http://127.0.0.1:8899/api/shadows") as resp:
    shadows = json.loads(resp.read().decode())
    print("\n=== SHADOWS API CHECK ===")
    print(f"Total Shadows: {len(shadows)}")
    for s in shadows:
        if "21" in s["id"] or s == shadows[0]:
            print(f"Shadow [{s['id']}]: Calmar={s['calmar_benchmark']} | Status={s['status']} | Universe={s['universe']}")
