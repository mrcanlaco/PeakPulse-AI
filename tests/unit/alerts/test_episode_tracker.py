from datetime import datetime, timedelta, timezone

from dao_vang.alerts.store import AlertStore


def test_episode_state_machine_and_idempotency(tmp_path):
    store = AlertStore(str(tmp_path / "test.duckdb"))
    symbol = "ETH"
    horizon = 4
    t0 = datetime(2023, 1, 1, 12, 0, tzinfo=timezone.utc)
    
    # 1. NEW EPISODE
    res1 = store.process_snapshot(symbol, horizon, 0.8, 0.7, True, t0, 3, 0.4)
    assert res1.transition == "OPENED"
    assert res1.role == "FIRST"
    assert res1.episode_id is not None
    ep_id = res1.episode_id
    
    # 2. IDEMPOTENT (Same timestamp) -> NO_ACTION
    res2 = store.process_snapshot(symbol, horizon, 0.8, 0.7, True, t0, 3, 0.4)
    assert res2.transition == "NONE"
    assert res2.role == "NONE"
    assert res2.episode_id == ep_id
    
    # 3. UPDATE EPISODE (Valid High)
    t1 = t0 + timedelta(minutes=5)
    res3 = store.process_snapshot(symbol, horizon, 0.9, 0.7, True, t1, 3, 0.4)
    assert res3.transition == "CONTINUED"
    assert res3.role == "UPDATE"
    
    # 4. FLAP 1
    t2 = t1 + timedelta(minutes=5)
    res4 = store.process_snapshot(symbol, horizon, 0.6, 0.7, True, t2, 3, 0.4)
    assert res4.transition == "NONE"
    assert res4.role == "UPDATE"
    
    # 5. UNUSABLE -> NO FLAP
    t3 = t2 + timedelta(minutes=5)
    res5 = store.process_snapshot(symbol, horizon, None, 0.7, False, t3, 3, 0.4)
    assert res5.transition == "NONE"
    assert res5.role == "NONE"
    
    # 6. FLAP 2
    t4 = t3 + timedelta(minutes=5)
    res6 = store.process_snapshot(symbol, horizon, 0.6, 0.7, True, t4, 3, 0.4)
    assert res6.transition == "NONE"
    assert res6.role == "UPDATE"
    
    # 7. FLAP 3 -> CLOSE
    t5 = t4 + timedelta(minutes=5)
    res7 = store.process_snapshot(symbol, horizon, 0.6, 0.7, True, t5, 3, 0.4)
    assert res7.transition == "CLOSED"
    assert res7.role == "UPDATE"
    
    # 8. STILL HIGH -> NO ACTION (Lane is COOLING_DOWN)
    t6 = t5 + timedelta(minutes=5)
    res8 = store.process_snapshot(symbol, horizon, 0.9, 0.7, True, t6, 3, 0.4)
    assert res8.transition == "NONE"
    assert res8.role == "NONE"
    
    # 9. RE-ARM
    t7 = t6 + timedelta(minutes=5)
    res9 = store.process_snapshot(symbol, horizon, 0.3, 0.7, True, t7, 3, 0.4)
    assert res9.transition == "REARMED"
    assert res9.role == "NONE"
    
    # 10. NEW EPISODE
    t8 = t7 + timedelta(minutes=5)
    res10 = store.process_snapshot(symbol, horizon, 0.8, 0.7, True, t8, 3, 0.4)
    assert res10.transition == "OPENED"
    assert res10.role == "FIRST"
    assert res10.episode_id != ep_id

def test_get_episode_tracking_symbols(tmp_path):
    store = AlertStore(str(tmp_path / "test2.duckdb"))
    store.process_snapshot("SOL", 4, 0.9, 0.7, True, datetime.now(timezone.utc), 3, 0.4)
    
    t_old = datetime.now(timezone.utc) - timedelta(minutes=60)
    store.process_snapshot("ADA", 4, 0.9, 0.7, True, t_old, 3, 0.4)
    store.process_snapshot("ADA", 4, 0.2, 0.7, True, t_old + timedelta(minutes=5), 1, 0.4)
    
    symbols = store.get_episode_tracking_symbols()
    assert "SOL" in symbols
    assert "ADA" in symbols


def test_migration_removes_mutable_status_index_preserving_episodes(tmp_path):
    store = AlertStore(str(tmp_path / "migration.duckdb"))
    stamp = datetime.now(timezone.utc)
    opened = store.process_snapshot("BTCUSDT", 24, .9, .7, True, stamp)
    with store._conn() as conn:
        conn.execute("CREATE INDEX idx_alert_episodes_status ON alert_episodes(status, lane_id)")
    store = AlertStore(str(tmp_path / "migration.duckdb"))
    with store._conn() as conn:
        assert not conn.execute("SELECT 1 FROM duckdb_indexes() WHERE index_name='idx_alert_episodes_status'").fetchall()
        assert conn.execute("SELECT episode_id FROM alert_episodes").fetchone()[0] == opened.episode_id
    closed = store.process_snapshot("BTCUSDT", 24, .1, .7, True, stamp + timedelta(minutes=5), flap_limit=1)
    assert closed.transition == "CLOSED"
