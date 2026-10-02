import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dao_vang.scanner.daemon import ScannerDaemon
from dao_vang.scanner.healthcheck import inspect_heartbeat, inspect_snapshot


@pytest.mark.parametrize("age,reason", [(0, "ok"), (901, "snapshot_stale"), (-61, "snapshot_clock_skew")])
def test_fresh_heartbeat_cannot_hide_stale_output(tmp_path, age, reason):
    now = datetime.now(timezone.utc)
    hb, snapshot = tmp_path / "hb.json", tmp_path / "snapshot.json"
    hb.write_text(json.dumps(dict(timestamp=now.isoformat(), status="running")))
    snapshot.write_text(json.dumps(dict(rows=[], generated_at=(now - timedelta(seconds=age)).isoformat())))
    result = inspect_heartbeat(hb, now=now, snapshot_path=snapshot)
    assert result["reason"] == reason
    assert result["healthy"] == (reason == "ok")
    snapshot.unlink()
    assert inspect_heartbeat(hb, now=now, snapshot_path=snapshot)["reason"] == "snapshot_missing"


def test_publication_failure_is_fatal(tmp_path):
    daemon = ScannerDaemon.__new__(ScannerDaemon)
    daemon._candidate_snapshot_path = tmp_path / "snapshot.json"
    conn = Mock()
    conn.execute.side_effect = RuntimeError("database invalidated")
    with pytest.raises(RuntimeError, match="invalidated"):
        daemon._publish_candidate_snapshot(SimpleNamespace(conn=conn))


def test_new_telemetry_cannot_hide_stale_source_data(tmp_path):
    now = datetime.now(timezone.utc)
    rows = [{"table": name, "max_time": now.isoformat()}
            for name in ("kline", "raw_timeline", "feature_results", "open_interest")]
    path = tmp_path / "stats.json"
    def check():
        path.write_text(json.dumps({"data_stats": rows, "generated_at": now.isoformat()}))
        return inspect_snapshot(path, now=now, rows_key="data_stats")
    assert check()["healthy"]
    rows[-1]["max_time"] = (now - timedelta(hours=2)).isoformat()
    assert check()["reason"] == "source_stale_open_interest"
    rows[-1]["max_time"] = "invalid"
    assert check()["healthy"] is False
