"""Local, read-only view of the locked prospective paper journal.

No trading-engine imports, market requests, or writes to study artifacts.
"""
from __future__ import annotations

import argparse
from collections import deque
from contextlib import closing
from datetime import datetime, timezone
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import threading
import time
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ART = ROOT / "artifacts/fibo_trend_short/paper_oos_v1"
EXPECTED_PROTOCOL = "3b394d2dc14e001a9c8794ce989014639ef7425ce87b512fa2f9499d543c28f8"
HOUR = 3_600_000
POLICY_NAMES = {
    "reference_m6_fixed": "Mốc 6 · Khối lượng cố định",
    "m6_risk": "Mốc 6 · Theo rủi ro",
    "elite_sniper_risk": "Elite + Sniper",
    "sniper_risk": "Sniper",
    "sniper_horizon24": "Sniper · 24 giờ",
    "sniper_rr1_horizon24": "Sniper · RR1 / 24 giờ",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def trade_view(trade):
    fields = ("id", "symbol", "tf", "entry_ts_ms", "exit_ts_ms", "entry",
              "mark", "active", "qty", "rem", "pnl", "fees", "slippage",
              "funding", "exit_reason")
    return {key: trade.get(key) for key in fields}


def chart_points(metric, budget=1200):
    points = []
    for bucket in [*metric.get("days", {}).values(), *metric["hours"].values()]:
        for point in sorted(bucket, key=lambda p: p[2]):
            if not points or points[-1] != point: points.append(point)
    if len(points) > budget:
        size = (len(points) + budget // 4 - 1) // (budget // 4)
        reduced = []
        for start in range(0, len(points), size):
            group = points[start:start + size]
            selected = [group[0], min(group, key=lambda p: p[1]), max(group, key=lambda p: p[1]), group[-1]]
            for point in sorted(selected, key=lambda p: p[2]):
                if not reduced or reduced[-1] != point: reduced.append(point)
        points = reduced
    return [point[:2] for point in points]


class PaperReader:
    def __init__(self, artifact_dir=ART, expected_protocol=EXPECTED_PROTOCOL):
        self.art = Path(artifact_dir)
        self.expected_protocol = expected_protocol
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.seq = 0
        self.last_hash = "0" * 64
        self.last_state_hash = None
        self.metrics = {}
        self.timeline = deque(maxlen=80)

    def point(self, account, timestamp, nav):
        metric = self.metrics[account]
        metric["peak"] = max(metric["peak"], nav)
        metric["max_dd_pct"] = max(metric["max_dd_pct"], (1 - nav / metric["peak"]) * 100)
        metric["point_seq"] += 1
        point = [int(timestamp), float(nav), metric["point_seq"]]
        hour = int(timestamp) // HOUR
        bucket = metric["hours"].get(hour)
        if bucket is None:
            metric["hours"][hour] = [point, point, point, point]
            # Keep seven days at hourly resolution; older display data needs
            # only daily extrema. Exact drawdown is calculated before compaction.
            for old_hour in list(metric["hours"]):
                if old_hour >= hour - 7 * 24: break
                old = metric["hours"].pop(old_hour)
                days = metric.setdefault("days", {})
                day = old_hour // 24
                candidates = days.get(day, []) + old
                days[day] = [min(candidates, key=lambda p: p[2]), min(candidates, key=lambda p: p[1]),
                             max(candidates, key=lambda p: p[1]), max(candidates, key=lambda p: p[2])]
        else:
            if nav < bucket[1][1]: bucket[1] = point
            if nav > bucket[2][1]: bucket[2] = point
            bucket[3] = point

    def ingest(self, event):
        kind = event.get("kind")
        if kind == "activation":
            self.timeline.append({"timestamp_ms": event.get("recorded_ms"), "kind": "activation", "proposals": 0, "rejections": 0})
        elif kind == "signal_decision":
            self.timeline.append({"timestamp_ms": event.get("recorded_ms"), "decision_ms": event.get("decision_ms"), "kind": kind,
                                  "proposals": len(event.get("proposals", [])), "rejections": len(event.get("rejections", []))})
        for step in event.get("steps", []):
            for name, account in step["accounts"].items():
                for timestamp, nav in account.get("curve", []): self.point(name, timestamp, nav)
                self.point(name, step["timestamp_ms"], account["equity"])
                metric = self.metrics[name]
                for trade in account.get("closed_trades", []):
                    metric["closed"] += 1
                    metric["wins"] += int(trade["pnl"] > 0)
                    for field in ("fees", "slippage", "funding", "pnl"): metric[field] += trade[field]
                    metric["trades"].append(trade_view(trade))

    def snapshot(self):
        with self.lock:
            try:
                return self._snapshot()
            except Exception:
                # A failed verification must not leave a partly advanced cache.
                self.reset()
                raise

    def pulse(self):
        """Cheap freshness check: no SQLite, history scan, or chart projection."""
        protocol_bytes = (self.art / "PROTOCOL.json").read_bytes()
        digest = hashlib.sha256(protocol_bytes).hexdigest()
        if digest != self.expected_protocol: raise ValueError("Giao thức không khớp bản đã khóa.")
        protocol = json.loads(protocol_bytes)
        status = read_json(self.art / "STATUS.json")
        if status.get("protocol_sha256") != digest: raise ValueError("Trạng thái thuộc giao thức khác.")
        now = int(time.time() * 1000)
        age = max(0, (now - status["heartbeat_ms"]) / 1000)
        bar_lag = max(0, (min(now, protocol["end_ms"]) - status["last_bar_ms"]) / 1000)
        health = "healthy"
        if status.get("error") or status.get("critical_incidents", 0): health = "error"
        elif age > 180 or (now >= protocol["start_ms"] and bar_lag > 600): health = "delayed"
        return {"server_time_ms": now, "heartbeat_ms": status["heartbeat_ms"], "heartbeat_age_seconds": age,
                "status": status["status"], "health": health, "error": status.get("error"),
                "revision": status["revision"], "last_bar_ms": status["last_bar_ms"],
                "last_signal_ms": status["last_signal_ms"], "critical_count": status.get("critical_incidents", 0),
                "opportunity_count": status.get("opportunity_incidents", 0)}

    def _snapshot(self):
        protocol_bytes = (self.art / "PROTOCOL.json").read_bytes()
        protocol_hash = hashlib.sha256(protocol_bytes).hexdigest()
        if protocol_hash != self.expected_protocol:
            raise ValueError("Giao thức không khớp bản đã khóa; dữ liệu đang tạm ẩn.")
        protocol = json.loads(protocol_bytes)
        if not self.metrics:
            for policy in protocol["family"]:
                for scenario in protocol["scenarios"]:
                    name = policy["id"] + "__" + scenario
                    self.metrics[name] = {"peak": 100., "max_dd_pct": 0., "closed": 0, "wins": 0,
                                          "fees": 0., "slippage": 0., "funding": 0., "pnl": 0.,
                                          "hours": {}, "point_seq": 0, "trades": deque(maxlen=100)}
                    self.point(name, protocol["start_ms"], 100.)
        with closing(sqlite3.connect((self.art / "paper.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            revision, payload = db.execute("SELECT revision,payload FROM snapshot WHERE id=1").fetchone()
            if revision < self.seq: raise ValueError("Nhật ký đã lùi phiên bản.")
            for seq, event_id, previous, digest, body in db.execute("SELECT * FROM events WHERE seq>? ORDER BY seq", (self.seq,)):
                expected = hashlib.sha256((previous + "\n" + event_id + "\n" + body).encode()).hexdigest()
                if seq != self.seq + 1 or previous != self.last_hash or digest != expected:
                    raise ValueError("Chuỗi nhật ký không toàn vẹn.")
                event = json.loads(body)
                if event.get("protocol_sha256") != protocol_hash: raise ValueError("Nhật ký thuộc giao thức khác.")
                self.ingest(event)
                self.seq, self.last_hash, self.last_state_hash = seq, digest, event["state_sha256"]
            if self.seq != revision or hashlib.sha256(payload.encode()).hexdigest() != self.last_state_hash:
                raise ValueError("Snapshot và nhật ký không khớp.")
            state = json.loads(payload)
            if state["protocol_sha256"] != protocol_hash: raise ValueError("Snapshot thuộc giao thức khác.")
        now = int(time.time() * 1000)
        status = read_json(self.art / "STATUS.json")
        if status.get("protocol_sha256") != protocol_hash: raise ValueError("Trạng thái thuộc giao thức khác.")
        heartbeat_age = max(0, (now - status["heartbeat_ms"]) / 1000)
        critical = len(state["critical_incidents"])
        bar_lag = max(0, (min(now, protocol["end_ms"]) - state["last_bar_ms"]) / 1000)
        health = "healthy"
        if status.get("error") or critical: health = "error"
        elif heartbeat_age > 180 or (now >= protocol["start_ms"] and bar_lag > 600): health = "delayed"
        accounts = []
        for name, account in state["accounts"].items():
            metric = self.metrics[name]
            if metric["closed"] != state["closed_trades"][name]: raise ValueError("Số lệnh đóng không khớp nhật ký.")
            positions = list(account["positions"].values())
            if abs(account["equity"] - 100 - metric["pnl"] - sum(t["pnl"] for t in positions)) > 1e-6:
                raise ValueError("NAV không khớp hạch toán giao dịch.")
            policy = account["policy"]["id"]
            accounts.append({"id": name, "policy": policy, "name": POLICY_NAMES.get(policy, policy),
                             "scenario": name.split("__", 1)[1], "nav": account["equity"],
                             "return_pct": account["equity"] - 100, "max_dd_pct": metric["max_dd_pct"],
                             "accepted": state["accepted_trades"][name], "closed": metric["closed"],
                             "win_rate_pct": metric["wins"] / metric["closed"] * 100 if metric["closed"] else None,
                             "costs": {k: metric[k] + sum(t[k] for t in positions) for k in ("fees", "slippage", "funding")},
                             "positions": [trade_view(t) for t in positions], "trades": list(reversed(metric["trades"])),
                             "curve": chart_points(metric), "rejected": account["rejected"], "filtered": account["filtered"]})
        memberships = []
        for file in sorted((self.art / "membership").glob("*.json")):
            candidate = read_json(file)
            if candidate["effective_from_ms"] <= now: memberships.append(candidate)
        membership = max(memberships, key=lambda m: m["effective_from_ms"]) if memberships else None
        study_end = min(now, protocol["end_ms"])
        completed_weeks = max(0, (study_end - protocol["first_full_week_ms"]) // (7 * 24 * HOUR))
        return {"schema": 1, "server_time_ms": now, "health": health, "status": status["status"],
                "heartbeat_ms": status["heartbeat_ms"], "heartbeat_age_seconds": heartbeat_age,
                "last_bar_ms": state["last_bar_ms"], "last_signal_ms": state["last_signal_ms"],
                "error": status.get("error"), "revision": revision, "protocol_sha256": protocol_hash,
                "start_ms": protocol["start_ms"], "end_ms": protocol["end_ms"], "full_weeks": protocol["full_weeks"],
                "completed_full_weeks": completed_weeks, "scenarios": protocol["scenarios"], "accounts": accounts,
                "policies": [{"id": p["id"], "name": POLICY_NAMES.get(p["id"], p["id"])} for p in protocol["family"]],
                "membership": {"month": membership["month"], "effective_from_ms": membership["effective_from_ms"],
                               "members": membership["members"]} if membership else None,
                "critical_incidents": state["critical_incidents"][-50:], "critical_count": critical,
                "opportunity_incidents": state["opportunity_incidents"][-50:], "opportunity_count": len(state["opportunity_incidents"]),
                "timeline": list(reversed(self.timeline)), "orders_allowed": False, "read_only": True,
                "verified_journal_revision": self.seq}


def make_handler(reader):
    assets = {}
    assets_lock = threading.Lock()

    def static_asset(name):
        path = HERE / name
        stat = path.stat()
        key = (stat.st_mtime_ns, stat.st_size)
        with assets_lock:
            if name not in assets or assets[name][0] != key:
                body = path.read_bytes()
                assets[name] = (key, body, gzip.compress(body, compresslevel=1, mtime=0))
            return assets[name][1:]

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, data, mime="application/json; charset=utf-8", cached_gzip=None, revalidate=False):
            if not isinstance(data, bytes): data = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
            encodings = {}
            for token in self.headers.get("Accept-Encoding", "").lower().split(","):
                parts = token.strip().split(";"); quality = 1.
                for part in parts[1:]:
                    if part.strip().startswith("q="):
                        try: quality = float(part.strip()[2:])
                        except ValueError: quality = 0.
                encodings[parts[0].strip()] = quality
            compressed = len(data) > 768 and encodings.get("gzip", encodings.get("*", 0)) > 0
            if compressed: data = cached_gzip if cached_gzip is not None else gzip.compress(data, compresslevel=1, mtime=0)
            etag = '"' + hashlib.sha256(data).hexdigest() + '"'
            if revalidate and self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Vary", "Accept-Encoding")
                self.send_header("Cache-Control", "private, no-cache")
                self.end_headers()
                return
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, no-cache" if revalidate else "no-store")
            self.send_header("Vary", "Accept-Encoding")
            if compressed: self.send_header("Content-Encoding", "gzip")
            if revalidate: self.send_header("ETag", etag)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ("/api/dashboard", "/api/pulse"):
                try: self.respond(200, reader.pulse() if path == "/api/pulse" else reader.snapshot())
                except Exception as exc:
                    self.respond(503, {"error": str(exc), "available": False, "read_only": True})
            elif path == "/api/health": self.respond(200, {"service": "fibo-paper-monitor", "read_only": True, "resource_mode": "lean-v2"})
            elif path in ("/", "/index.html", "/app.js", "/style.css"):
                name = "index.html" if path == "/" else path[1:]
                mime = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[name]
                body, compressed = static_asset(name)
                self.respond(200, body, mime + "; charset=utf-8", cached_gzip=compressed, revalidate=True)
            else: self.respond(404, {"error": "Không tìm thấy trang."})

        def do_POST(self): self.respond(405, {"error": "Trang chỉ đọc dữ liệu."})
        do_PUT = do_DELETE = do_PATCH = do_POST

        def log_message(self, fmt, *args):
            if len(args) > 1 and str(args[1]) in ("200", "304"): return
            super().log_message(fmt, *args)
    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(PaperReader()))
    print(json.dumps({"url": f"http://127.0.0.1:{args.port}", "read_only": True,
                      "started_at": datetime.now(timezone.utc).isoformat()}), flush=True)
    server.serve_forever()
