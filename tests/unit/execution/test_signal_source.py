from datetime import datetime, timedelta, timezone

import duckdb

from dao_vang.config.settings import ExecutionConfig
from dao_vang.execution.contracts import StrategyManifest, policy_contract
from dao_vang.execution.sources import scanner_signals


def test_scanner_contract_uses_closed_hours_and_preserves_rejections(tmp_path):
    now = datetime(2026, 9, 24, 12, 1, tzinfo=timezone.utc)
    path = tmp_path / "source.duckdb"
    db = duckdb.connect(str(path))
    db.execute("""CREATE TABLE predictions(prediction_id VARCHAR,symbol VARCHAR,signal_time TIMESTAMP,
        model_id VARCHAR,label_version VARCHAR,candidate_passed BOOLEAN,quality_status VARCHAR,
        calibrated_probability DOUBLE,max_feature_age_minutes DOUBLE,invalidation_time TIMESTAMP,
        alert_episode_id VARCHAR,event_id VARCHAR,state VARCHAR,tier VARCHAR)""")
    db.execute(
        """INSERT INTO predictions VALUES ('p1','ABCUSDT',?,'m','v',TRUE,'valid',.8,1,NULL,'episode1',NULL,'confirmed_distribution','HIGH_CONFIDENCE'),
        ('p2','ABCUSDT',?,'m','v',TRUE,'valid',.2,1,NULL,'episode2',NULL,'early_watch','WATCH')""",
        [now.replace(tzinfo=None), now.replace(tzinfo=None)],
    )
    db.execute("""CREATE TABLE kline(symbol VARCHAR,interval VARCHAR,market VARCHAR,quality_status VARCHAR,
        close_time TIMESTAMP,high DOUBLE,low DOUBLE,close DOUBLE)""")
    end = now.replace(minute=0, second=0)
    rows = []
    for i in range(180):
        at = end - timedelta(minutes=5 * i, milliseconds=1)
        rows.append(
            (
                "ABCUSDT",
                "5m",
                "USD-M Futures",
                "valid",
                at.replace(tzinfo=None),
                102,
                98,
                100,
            )
        )
    db.executemany("INSERT INTO kline VALUES (?,?,?,?,?,?,?,?)", rows)
    db.close()
    config = ExecutionConfig()
    manifest = StrategyManifest(
        frozen_at=now - timedelta(days=1),
        model_id="m",
        label_version="v",
        threshold=0.5,
        files={"model": "checksum"},
        policy=policy_contract(config),
    )
    signals = list(scanner_signals(path, manifest, config, now))
    assert signals[0].eligible
    assert signals[0].atr == 4
    assert signals[0].event_id == "episode1"
    assert not signals[1].eligible
    assert "below_frozen_threshold" in signals[1].reasons
    # Remove one candle from the newest full hour; an older complete hour must
    # not hide this missing input from the ATR contract.
    db = duckdb.connect(str(path))
    db.execute("DELETE FROM kline WHERE close_time=(SELECT max(close_time) FROM kline)")
    db.close()
    changed = list(scanner_signals(path, manifest, config, now))
    assert not changed[0].eligible
    assert "atr_unavailable" in changed[0].reasons
