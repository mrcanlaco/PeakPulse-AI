"""Read-only monitor: accounting, journal consistency, staleness and HTTP scope."""
import hashlib
import gzip
import importlib.util
import json
from pathlib import Path
import sqlite3
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("paper_monitor", ROOT / "apps/fibo-paper-monitor/server.py")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def append_event(art, state, event):
    payload = json.dumps(state, separators=(",", ":"))
    event = {**event, "state_sha256": hashlib.sha256(payload.encode()).hexdigest(),
             "protocol_sha256": state["protocol_sha256"]}
    body = json.dumps(event, sort_keys=True, separators=(",", ":"))
    with sqlite3.connect(art / "paper.sqlite3") as db:
        last = db.execute("select seq,digest from events order by seq desc limit 1").fetchone()
        seq, previous = (last[0] + 1, last[1]) if last else (1, "0" * 64)
        event_id = f"event:{seq}"
        digest = hashlib.sha256((previous + "\n" + event_id + "\n" + body).encode()).hexdigest()
        db.execute("insert into events values(?,?,?,?,?)", (seq, event_id, previous, digest, body))
        db.execute("insert or replace into snapshot values(1,?,?)", (seq, payload))


@pytest.fixture
def study(tmp_path):
    now = int(time.time() * 1000); start = now - 3600000
    protocol = {"family": [{"id": "sniper_risk"}], "scenarios": {"standard_vip6": {"fee_bps": 2.5, "slippage_bps": 10}, "stress_regular": {"fee_bps": 5, "slippage_bps": 50}}, "start_ms": start, "end_ms": now + 104 * 7 * 86400000, "first_full_week_ms": now + 86400000, "full_weeks": 104}
    write_json(tmp_path / "PROTOCOL.json", protocol)
    digest = hashlib.sha256((tmp_path / "PROTOCOL.json").read_bytes()).hexdigest()
    state = {"protocol_sha256": digest, "accounts": {}, "last_bar_ms": now - 30000,
             "last_signal_ms": now - 60000, "critical_incidents": [], "opportunity_incidents": [],
             "accepted_trades": {}, "closed_trades": {}}
    event_accounts = {}
    for scenario in protocol["scenarios"]:
        key = "sniper_risk__" + scenario
        closed = {"id": "closed", "symbol": "BTCUSDT", "pnl": 10, "fees": 1, "slippage": 2, "funding": -2}
        position = {"id": "open", "symbol": "SOLUSDT", "pnl": 2, "fees": .5, "slippage": .75, "funding": .25}
        state["accounts"][key] = {"policy": {"id": "sniper_risk"}, "equity": 112,
                                   "positions": {"open": position}, "rejected": {}, "filtered": {}}
        state["closed_trades"][key] = 1; state["accepted_trades"][key] = 2
        event_accounts[key] = {"equity": 112, "curve": [[now - 30000, 120], [now - 30000, 80], [now - 30000, 112]], "closed_trades": [closed]}
    with sqlite3.connect(tmp_path / "paper.sqlite3") as db:
        db.executescript("CREATE TABLE snapshot(id INTEGER PRIMARY KEY,revision INTEGER,payload TEXT); CREATE TABLE events(seq INTEGER PRIMARY KEY,event_id TEXT,previous_hash TEXT,digest TEXT,payload TEXT);")
    append_event(tmp_path, state, {"kind": "paper_batch", "steps": [{"timestamp_ms": now - 30000, "accounts": event_accounts}]})
    write_json(tmp_path / "STATUS.json", {"protocol_sha256": digest, "status": "OBSERVING", "heartbeat_ms": now, "error": None,
                                        "revision": 1, "last_bar_ms": now - 30000, "last_signal_ms": now - 60000})
    (tmp_path / "membership").mkdir()
    for month, timestamp in [("2026-10", start), ("2026-11", now + 1000000)]:
        write_json(tmp_path / "membership" / (month + ".json"), {"month": month, "effective_from_ms": timestamp, "members": []})
    return tmp_path, digest, state, now


def test_nav_signed_funding_intrabar_drawdown_read_only_and_no_double_count(study):
    art, digest, _, _ = study
    before = hashlib.sha256((art / "paper.sqlite3").read_bytes()).hexdigest()
    reader = monitor.PaperReader(art, digest)
    for _ in range(2):
        result = reader.snapshot(); a = result["accounts"][0]
        assert a["nav"] == 112 and a["return_pct"] == 12
        assert a["max_dd_pct"] == pytest.approx(100 / 3)
        assert a["costs"] == {"fees": 1.5, "slippage": 2.75, "funding": -1.75}
        assert a["closed"] == 1 and a["win_rate_pct"] == 100
        assert [p[1] for p in a["curve"]][-3:] == [120, 80, 112]
        assert result["membership"]["month"] == "2026-10"
    assert hashlib.sha256((art / "paper.sqlite3").read_bytes()).hexdigest() == before


def test_incremental_events_update_nav_without_recounting_closed_trades(study):
    art, digest, state, now = study; reader = monitor.PaperReader(art, digest); reader.snapshot()
    updates = {}
    for key, a in state["accounts"].items():
        a["equity"] = 113; a["positions"]["open"]["pnl"] = 3
        updates[key] = {"equity": 113, "curve": [[now, 113]], "closed_trades": []}
    append_event(art, state, {"kind": "paper_batch", "steps": [{"timestamp_ms": now, "accounts": updates}]})
    result = reader.snapshot()
    assert result["revision"] == 2 and result["accounts"][0]["nav"] == 113
    assert result["accounts"][0]["closed"] == 1


def test_snapshot_tampering_fails_closed_and_resets_cache(study):
    art, digest, state, _ = study; reader = monitor.PaperReader(art, digest); reader.snapshot()
    state["accounts"][next(iter(state["accounts"]))]["equity"] = 999
    with sqlite3.connect(art / "paper.sqlite3") as db:
        db.execute("update snapshot set payload=?", (json.dumps(state),))
    with pytest.raises(ValueError, match="Snapshot"): reader.snapshot()
    assert reader.seq == 0


def test_stale_heartbeat_and_protocol_mismatch(study):
    art, digest, _, now = study
    write_json(art / "STATUS.json", {"protocol_sha256": digest, "status": "OBSERVING", "heartbeat_ms": now - 240000, "error": None})
    reader = monitor.PaperReader(art, digest)
    assert reader.snapshot()["health"] == "delayed"
    (art / "PROTOCOL.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Giao thức"): reader.snapshot()


def test_downsample_keeps_endpoints_and_extrema_in_recorded_order():
    reader = monitor.PaperReader(); name = "a"
    reader.metrics[name] = {"peak": 100, "max_dd_pct": 0, "hours": {}, "point_seq": 0}
    for i in range(3000): reader.point(name, i * monitor.HOUR, 200 if i == 777 else 50 if i == 778 else 100)
    points = monitor.chart_points(reader.metrics[name], budget=120)
    assert len(points) <= 120 and points[0] == [0, 100] and points[-1] == [2999 * monitor.HOUR, 100]
    assert [777 * monitor.HOUR, 200] in points and [778 * monitor.HOUR, 50] in points


def test_http_is_local_read_only_and_does_not_expose_arbitrary_files(study):
    art, digest, _, _ = study
    server = monitor.ThreadingHTTPServer(("127.0.0.1", 0), monitor.make_handler(monitor.PaperReader(art, digest)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(url + "/api/dashboard") as response: assert json.load(response)["read_only"]
        for path, method, expected in [("/api/dashboard", "POST", 405), ("/../PROTOCOL.json", "GET", 404)]:
            with pytest.raises(HTTPError) as error: urlopen(Request(url + path, method=method))
            assert error.value.code == expected
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_pulse_skips_database_and_still_detects_stale_heartbeat(study, monkeypatch):
    art, digest, _, now = study
    reader = monitor.PaperReader(art, digest)
    monkeypatch.setattr(monitor.sqlite3, "connect", lambda *a, **k: pytest.fail("Pulse must not open SQLite"))
    assert reader.pulse()["health"] == "healthy"
    status = monitor.read_json(art / "STATUS.json"); status["heartbeat_ms"] = now - 240000
    write_json(art / "STATUS.json", status)
    assert reader.pulse()["health"] == "delayed"


def test_chart_memory_compaction_preserves_extrema_and_exact_drawdown():
    reader = monitor.PaperReader(); name = "a"
    reader.metrics[name] = {"peak": 100, "max_dd_pct": 0, "hours": {}, "point_seq": 0}
    for i in range(104 * 7 * 24):
        reader.point(name, i * monitor.HOUR, 200 if i == 5 else 20 if i == 6 else 100)
    metric = reader.metrics[name]
    assert len(metric["hours"]) <= 169 and len(metric["days"]) <= 729
    assert metric["max_dd_pct"] == pytest.approx(90)
    points = monitor.chart_points(metric)
    assert [5 * monitor.HOUR, 200] in points and [6 * monitor.HOUR, 20] in points
    assert len(points) <= 1200


def test_gzip_revalidation_and_encoding_opt_out(study):
    art, digest, _, _ = study
    server = monitor.ThreadingHTTPServer(("127.0.0.1", 0), monitor.make_handler(monitor.PaperReader(art, digest)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(Request(url + "/app.js", headers={"Accept-Encoding": "gzip"})) as response:
            compressed = response.read(); etag = response.headers["ETag"]
            assert response.headers["Content-Encoding"] == "gzip"
        original = (monitor.HERE / "app.js").read_bytes()
        assert gzip.decompress(compressed) == original and len(compressed) < len(original) * .6
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url + "/app.js", headers={"Accept-Encoding": "gzip", "If-None-Match": etag}))
        assert error.value.code == 304 and error.value.read() == b""
        with urlopen(Request(url + "/app.js", headers={"Accept-Encoding": "gzip;q=0, *;q=1"})) as response:
            assert response.headers.get("Content-Encoding") is None and response.read() == original
        with urlopen(Request(url + "/api/dashboard", headers={"Accept-Encoding": "gzip"})) as response:
            payload = json.loads(gzip.decompress(response.read()))
        assert payload["accounts"][0]["nav"] == 112
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
