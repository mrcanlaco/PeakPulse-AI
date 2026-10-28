import urllib.request
import json

req = urllib.request.Request(
    "http://127.0.0.1:8899/api/shadows/control-all",
    data=json.dumps({"action": "RUNNING"}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode())
    print("Toggle action result:", res["status"])

with urllib.request.urlopen("http://127.0.0.1:8899/api/status") as resp:
    st = json.loads(resp.read().decode())
    print(f"Shadow Status: {st['active_shadows_count']} / {st['total_shadows_count']} RUNNING")
    print(f"Total Equity: ${st['total_equity']:,.2f}")
    print(f"Feeder Status: {st['feeder_status']}")
