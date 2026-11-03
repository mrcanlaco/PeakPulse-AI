"""Repository-level checks for the exact model selected by live config."""

import json
from pathlib import Path

import pandas as pd
import yaml

from dao_vang.experiments.forward_evidence import (
    canonical_metadata_sha256,
    load_forward_test_protocol,
)
from dao_vang.experiments.forward_test import (
    load_frozen_model,
    load_frozen_model_estimator,
)
from dao_vang.scoring.frozen_inference import _verify_bundle_checksums

ROOT = Path(__file__).resolve().parents[2]
LIVE_CONFIG_PATH = ROOT / "configs" / "live.yaml"
FORWARD_PROTOCOL_PATH = ROOT / "configs" / "forward_test_live_v1.json"
COMPOSE_PATH = ROOT / "docker-compose.yml"
SENSITIVE_CONFIG_KEYS = {
    "access_password",
    "api_key",
    "api_secret",
    "bot_token",
    "chat_id",
    "credential",
    "password",
    "secret",
    "token",
}


def _load_live_config() -> dict:
    return yaml.safe_load(LIVE_CONFIG_PATH.read_text(encoding="utf-8"))


def _sensitive_paths(value: object, prefix: str = "") -> list[str]:
    if not isinstance(value, dict):
        return []

    found: list[str] = []
    for raw_key, child in value.items():
        key = str(raw_key)
        path = f"{prefix}.{key}" if prefix else key
        if key.lower() in SENSITIVE_CONFIG_KEYS:
            found.append(path)
        found.extend(_sensitive_paths(child, path))
    return found


def test_live_config_is_safe_to_version_and_disables_self_update():
    config = _load_live_config()

    assert _sensitive_paths(config) == []
    assert config["updater"]["enabled"] is False


def test_scanner_healthcheck_does_not_import_the_full_scanner_package():
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    command = compose["services"]["scanner"]["healthcheck"]["test"]

    assert command[:2] == ["CMD", "python"]
    assert command[2] == "/app/src/dao_vang/scanner/healthcheck.py"
    assert "-m" not in command


def test_live_config_selects_a_complete_checksum_verified_bundle():
    config = _load_live_config()
    scanner = config["scanner"]
    model_id = scanner["frozen_model_id"]
    artifact_dir = ROOT / scanner["artifact_dir"]

    info = load_frozen_model(model_id, artifact_dir)
    metadata = json.loads(info.metadata_path.read_text(encoding="utf-8"))

    assert info.model_id == model_id
    assert info.model_path.is_file()
    assert info.calibrator_path is not None
    assert info.calibrator_path.is_file()
    assert info.train_cutoff
    assert info.threshold_policy
    assert _verify_bundle_checksums(info, metadata) is None

    estimator = load_frozen_model_estimator(model_id, artifact_dir)
    assert callable(getattr(estimator, "predict_proba", None))


def test_forward_protocol_is_locked_to_the_exact_live_bundle():
    config = _load_live_config()
    scanner = config["scanner"]
    info = load_frozen_model(
        scanner["frozen_model_id"],
        ROOT / scanner["artifact_dir"],
    )
    protocol = load_forward_test_protocol(FORWARD_PROTOCOL_PATH)

    evaluation_start = pd.Timestamp(protocol.evaluation_start)
    train_cutoff = pd.Timestamp(info.train_cutoff)
    freeze_time = pd.Timestamp(info.freeze_time)

    assert protocol.model_id == scanner["frozen_model_id"] == info.model_id
    assert protocol.expected_model_sha256 == info.checksums["model_sha256"]
    assert (
        protocol.expected_calibrator_sha256
        == info.checksums["calibrator_sha256"]
    )
    assert (
        protocol.expected_metadata_sha256
        == canonical_metadata_sha256(info.metadata_path)
    )
    assert evaluation_start >= max(train_cutoff, freeze_time)
    assert protocol.label_version == info.label_spec["version"]
    assert protocol.label_horizon_hours == info.label_spec["horizon_hours"]
    assert protocol.universe_policy["post_hoc_symbol_filtering"] is False


def test_live_config_enforces_two_tier_fibo_primary_and_v31_ui_radar_contract():
    config = _load_live_config()
    scanner = config["scanner"]
    fibo = config["fibo_trend_short"]
    execution = config["execution"]

    # Tier 1: V3.1 Frozen ML acts strictly as UI overheating radar (Telegram muted)
    assert scanner["enabled"] is True
    assert scanner["operating_mode"] == "shadow"
    assert scanner["shadow_telegram_enabled"] is False

    # Tier 2: Fibo Short v4.0.21 acts as the primary actionable signal & Telegram engine
    assert fibo["enabled"] is True
    assert fibo["universe_mode"] == "rolling_pit_top50"
    assert fibo["telegram_enabled"] is True
    assert fibo["telegram_require_qualified_short"] is True
    assert fibo["telegram_min_prior_pump_pct"] == 0.05
    assert set(fibo["telegram_allowed_policies"]) == {
        "elite_sniper_risk",
        "sniper_rr1_horizon24",
        "sniper_risk",
        "sniper_horizon24",
    }

    # Tier 3: Paper simulation runs at 10,000 USDT while real-money live trading stays fail-closed
    assert execution["enabled"] is True
    assert execution["environment"] == "simulation"
    assert execution["signal_source"] == "fibo_short"
    assert execution["initial_equity"] == 10000.0
    assert execution["live_activated"] is False
