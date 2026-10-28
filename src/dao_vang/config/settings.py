import os
import typing
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, StringConstraints, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BinanceConfig(BaseModel):
    base_url: HttpUrl = HttpUrl("https://fapi.binance.com")
    symbol: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]+$")] = "BTCUSDT"
    interval: Literal["5m"] = "5m"
    availability_lag_ms: int = Field(default=1000, ge=0)


class CollectionPolicy(BaseModel):
    timeout_seconds: int = Field(default=15, gt=0)
    max_retries: int = Field(default=5, ge=0)
    max_concurrency: int = Field(default=2, gt=0)


class PathsConfig(BaseModel):
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    normalized_dir: Path = Path("data/normalized")


class TelegramConfig(BaseModel):
    bot_token: str | None = Field(default=None, exclude=True)
    chat_id: str | None = Field(default=None, exclude=True)
    shadow_chat_id: str | None = Field(default=None, exclude=True)
    api_base: str = "https://api.telegram.org"
    timeout_seconds: int = Field(default=10, gt=0)
    max_retries: int = Field(default=3, ge=0)
    language: Literal["vi", "en"] = Field(
        default="vi",
        description="Language for Telegram alerts ('vi' for Vietnamese, 'en' for English)",
    )


class ScannerConfig(BaseModel):
    poll_interval_minutes: int = Field(default=5, ge=1)
    max_coins: int = Field(default=150, ge=1, le=500)
    min_volume_usd: float = Field(default=1_000_000, gt=0)
    cooldown_minutes: int = Field(default=120, ge=0)
    alert_levels: list[str] = Field(default_factory=lambda: ["CAO", "TRUNG BÌNH"])
    alert_flap_limit: int = Field(default=3, ge=1)
    alert_rearm_probability: float = Field(default=0.4, ge=0.0, le=1.0)
    frozen_model_id: str | None = None
    db_path: Path = Path("data/dev.duckdb")
    artifact_dir: Path = Path("artifacts")
    watchlist_path: Path = Path("data/watchlist.json")
    kill_switch_path: Path = Path("data/scanner_kill_switch.json")
    rollback_state_path: Path = Path("data/scanner_rollback.json")
    health_report_path: Path = Path("data/scanner_health.json")
    threshold_policy_version: str | None = None
    max_heartbeat_age_minutes: int = Field(default=15, ge=1, le=24 * 60)
    drift_min_samples: int = Field(default=30, ge=1)
    drift_psi_warning: float = Field(default=0.10, ge=0.0)
    drift_psi_critical: float = Field(default=0.25, ge=0.0)
    history_days: int = Field(default=30, ge=1)
    enabled: bool = False
    operating_mode: Literal[
        "research",
        "shadow",
        "canary",
        "production",
        "production_alerting",
    ] = Field(
        default="research",
        description="research/shadow/canary/production(_alerting)",
    )
    # Hard ceiling for successful Telegram deliveries in a rolling 24-hour
    # window.  The scanner ranks candidates inside this budget; it never
    # fabricates a signal merely to reach the target.
    global_daily_alert_limit: int = Field(default=10, ge=1)
    coin_daily_alert_limit: int = Field(default=1, ge=1)
    enable_meta_labeling: Literal["disabled", "shadow", "active"] = "disabled"
    meta_model_path: Path | None = None
    meta_model_min_confidence: float = 0.5
    # Regime Gate: filter alerts to only allowable market regimes (e.g. SIDEWAY_DISTRIBUTION, TRENDING_BEAR)
    regime_gate_enabled: bool = False
    regime_gate_allowed: list[str] = Field(
        default_factory=lambda: ["SIDEWAY_DISTRIBUTION", "TRENDING_BEAR"]
    )
    # Explicit opt-in for labelled observational Telegram messages for every
    # Radar detection while the scanner remains in shadow.
    shadow_telegram_enabled: bool = False
    # Strict Telegram delivery gate: probability must exceed this threshold (e.g. 75%).
    telegram_min_probability: float = Field(default=0.75, gt=0.0, lt=1.0)
    # Telegram cooldown in minutes: prevents duplicate alerts for the same coin within this window.
    telegram_cooldown_minutes: int = Field(default=120, ge=0)
    # Minimum 24h volume in USD required for a coin to be alerted on Telegram (avoids low liquidity spam).
    telegram_min_volume_usd: float = Field(default=500_000.0, ge=0.0)
    # Allowed risk tiers for Telegram alerting (defaults to only HIGH_CONFIDENCE).
    telegram_tiers: list[str] = Field(default_factory=lambda: ["HIGH_CONFIDENCE"])
    # Telegram digest mode: if true, multiple qualifying alerts in a cycle are sent as a single clean digest.
    telegram_digest_mode: bool = True
    # Delivery target is observational: 5 is the preferred minimum when the
    # market supplies enough valid candidates, while the hard ceiling above
    # remains the safety limit.
    telegram_daily_target_min: int = Field(default=5, ge=0)
    # Limit one digest to a small batch so a burst cannot consume the whole
    # daily budget before later, stronger candidates are seen.
    telegram_max_per_cycle: int = Field(default=2, ge=1)
    # A feature snapshot older than this must never produce an alert.
    max_feature_age_minutes: int = Field(default=25, ge=1, le=24 * 60)
    # Quality score is an explicit gate; missing score is derived from the
    # source quality_status (valid=1.0, warning=0.75).
    min_data_quality_score: float = Field(default=0.8, ge=0.0, le=1.0)

    # === Mở rộng chọn coin quét ===

    # scan_mode: cách chọn coin tự động
    #   "gainers"    — top coin tăng mạnh nhất 24h (mặc định)
    #   "losers"     — top coin giảm mạnh nhất 24h (cơ hội short đã xả)
    #   "volume"     — top coin theo khối lượng giao dịch 24h
    #   "volatile"   — top coin biến động mạnh (|price change| cao)
    #   "all"        — kết hợp gainers + losers + volume
    scan_mode: str = Field(default="gainers")
    # min_price_change_pct: lọc coin phải thay đổi ít nhất X% trong 24h
    # VD: 5.0 = chỉ quét coin tăng/giảm ≥5% (bỏ coin đi ngang)
    min_price_change_pct: float = Field(default=5.0, ge=0.0)
    # include_btc: luôn đảm bảo BTCUSDT trong danh sách quét (bối cảnh BTC)
    include_btc: bool = Field(default=True)
    # exclude_stablecoins: bỏ USDT/USDC/DAI/TUSD/FDUSD/BUSD pairs (không short stablecoin)
    exclude_stablecoins: bool = Field(default=True)

    @model_validator(mode="after")
    def validate_telegram_selection(self) -> "ScannerConfig":
        if self.telegram_daily_target_min > self.global_daily_alert_limit:
            raise ValueError(
                "telegram_daily_target_min must not exceed global_daily_alert_limit"
            )
        return self


class SelfLearningConfig(BaseModel):
    """Guarded batch retraining settings.

    Self-learning creates and evaluates challengers, but promotion remains an
    explicit operator action until the rollout process has enough evidence.
    """

    enabled: bool = False
    check_interval_cycles: int = Field(default=12, ge=1)
    min_training_outcomes: int = Field(default=200, ge=20)
    min_new_outcomes: int = Field(default=50, ge=1)
    min_positive_events: int = Field(default=20, ge=1)
    min_precision_improvement: float = Field(default=0.01, ge=0.0, le=1.0)
    max_recall_regression: float = Field(default=0.05, ge=0.0, le=1.0)
    max_brier_regression: float = Field(default=0.01, ge=0.0, le=1.0)
    recent_window_days: int = Field(default=14, ge=1, le=365)
    recent_sample_weight: float = Field(default=2.0, ge=1.0, le=10.0)
    historical_max_rows: int = Field(default=100_000, ge=200)
    seed: int = Field(default=42, ge=0)
    state_path: Path = Path("artifacts/self_learning/state.json")
    report_dir: Path = Path("artifacts/self_learning/runs")


class PumpFilterConfig(BaseModel):
    """Config for pre-filter: find coins that pumped 50-300% in 1-5 days."""

    lookback_days: int = Field(default=5, ge=1, le=30)
    min_pump_pct: float = Field(default=0.50, ge=0.0, le=10.0)  # +50%
    max_pump_pct: float = Field(default=5.0, ge=0.0, le=20.0)  # +500% cap
    dump_threshold: float = Field(
        default=0.70, ge=0.0, le=1.0
    )  # skip if close < 70% peak
    min_volume_usd: float = Field(default=500_000, gt=0)


class MarketAnomalyConfig(BaseModel):
    """Thresholds for the independent market-anomaly radar layer.

    These rules enrich the frozen model output; they never masquerade as a
    calibrated probability and therefore can evolve without invalidating a
    frozen model bundle.
    """

    enabled: bool = True
    min_signal_score: float = Field(default=35.0, ge=0.0, le=100.0)
    volume_zscore_threshold: float = Field(default=2.5, ge=0.0)
    volume_ratio_1h_threshold: float = Field(default=1.8, gt=1.0)
    volume_percentile_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    funding_zscore_threshold: float = Field(default=2.0, ge=0.0)
    funding_change_8h_threshold: float = Field(default=0.0003, ge=0.0)
    funding_max_age_minutes: float = Field(default=720.0, ge=0.0)
    reversal_prior_return_threshold: float = Field(default=0.03, ge=0.0, le=1.0)
    reversal_current_return_threshold: float = Field(default=0.01, ge=0.0, le=1.0)
    oi_unwind_threshold: float = Field(default=0.03, ge=0.0, le=1.0)
    taker_buy_ratio_threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    taker_ratio_change_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    crowded_long_ratio_threshold: float = Field(default=1.5, ge=0.0)


class CandidateComparisonConfig(BaseModel):
    """Shadow comparison between the production pump filter and a challenger.

    The challenger is observational only.  Enabling this section records
    paired decisions and future market outcomes; it never grants the
    challenger permission to score, alert, or send Telegram messages.
    """

    enabled: bool = False
    # Keep the safe production lane as the default.  A live config may
    # explicitly promote another version only after the comparison gates pass
    # and a human approves the promotion.
    champion_version: str = "pump_filter_v1"
    challenger_version: str = "candidate_filter_v2"
    universe_size: int = Field(default=150, ge=10, le=500)
    max_candidates: int = Field(default=30, ge=1, le=100)
    max_workers: int = Field(default=4, ge=1, le=16)
    decision_interval_minutes: int = Field(default=60, ge=5, le=24 * 60)
    outcome_check_interval_cycles: int = Field(default=12, ge=1)
    horizon_hours: int = Field(default=24, ge=1, le=168)
    target_drawdown: float = Field(default=0.20, gt=0.0, lt=1.0)
    max_adverse_excursion: float = Field(default=0.16, gt=0.0, lt=1.0)
    gap_tolerance_minutes: int = Field(default=15, ge=5, le=120)
    metrics_window_days: int = Field(default=30, ge=1, le=365)
    min_resolved: int = Field(default=200, ge=1)
    min_positive_events: int = Field(default=50, ge=1)
    min_evaluation_days: int = Field(default=14, ge=1, le=365)
    truth_event_gap_minutes: int = Field(default=240, ge=60, le=24 * 60)
    min_challenger_event_recall: float = Field(default=0.80, ge=0.0, le=1.0)
    precision_at_10_relative_gain: float = Field(default=0.10, ge=0.0, le=1.0)
    max_recall_regression: float = Field(default=0.05, ge=0.0, le=1.0)
    snapshot_path: Path | None = None
    state_path: Path | None = None

    @model_validator(mode="after")
    def validate_comparison(self) -> "CandidateComparisonConfig":
        if self.champion_version == self.challenger_version:
            raise ValueError("champion_version and challenger_version must differ")
        if self.max_candidates > self.universe_size:
            raise ValueError("max_candidates must not exceed universe_size")
        return self



class ThresholdPolicy(BaseModel):
    version: str = "1.0"
    high_confidence_min_prob: float = Field(default=0.60, ge=0.0, le=1.0)
    watch_min_prob: float = Field(default=0.40, ge=0.0, le=1.0)
    high_confidence_min_evidence_groups: int = Field(default=2, ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> "ThresholdPolicy":
        if self.watch_min_prob > self.high_confidence_min_prob:
            raise ValueError("watch_min_prob must not exceed high_confidence_min_prob")
        return self

class ScoringConfig(BaseModel):
    """Composite distribution score 0-100."""

    alert_score_threshold: float = Field(default=40.0, ge=0.0, le=100.0)
    # Signal weights (must sum to 1.0)
    weight_price_volume_divergence: float = Field(default=0.20, ge=0.0, le=1.0)
    weight_funding_spike: float = Field(default=0.15, ge=0.0, le=1.0)
    weight_momentum_exhaustion: float = Field(default=0.15, ge=0.0, le=1.0)
    weight_distance_from_high: float = Field(default=0.07, ge=0.0, le=1.0)
    weight_taker_sell_pressure: float = Field(default=0.10, ge=0.0, le=1.0)
    weight_btc_context: float = Field(default=0.15, ge=0.0, le=1.0)
    weight_oi_divergence: float = Field(default=0.10, ge=0.0, le=1.0)
    weight_fake_breakout: float = Field(default=0.03, ge=0.0, le=1.0)
    weight_multi_tf_exhaustion: float = Field(default=0.05, ge=0.0, le=1.0)
    # BTC context thresholds
    btc_fomo_threshold: float = Field(default=0.05, ge=0.0, le=1.0)  # BTC +5% → FOMO
    btc_weak_threshold: float = Field(default=-0.02, le=0.0)  # BTC -2% → weak


    @model_validator(mode="after")
    def validate_weights(self) -> "ScoringConfig":
        weight_names = (
            "weight_price_volume_divergence",
            "weight_funding_spike",
            "weight_momentum_exhaustion",
            "weight_distance_from_high",
            "weight_taker_sell_pressure",
            "weight_btc_context",
            "weight_oi_divergence",
            "weight_fake_breakout",
            "weight_multi_tf_exhaustion",
        )
        total = sum(float(getattr(self, name)) for name in weight_names)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1.0, got {total:.8f}")
        return self


class CoinGeckoConfig(BaseModel):
    enabled: bool = Field(default=False)
    market_cap_lookup_enabled: bool = Field(default=True)
    base_url: str = "https://api.coingecko.com/api/v3"
    timeout_seconds: int = Field(default=15, gt=0)
    max_retries: int = Field(default=3, ge=0)
    price_mismatch_threshold: float = Field(default=0.05, ge=0.0, le=1.0)  # 5%


class CoinMarketCapConfig(BaseModel):
    """CoinMarketCap token & market cap settings via Binance promo CMC API."""

    enabled: bool = Field(default=True)
    base_url: str = "https://www.binance.com"
    timeout_seconds: int = Field(default=10, gt=0)
    cache_minutes: int = Field(default=30, ge=1, le=1440)


class BinanceAgentOSConfig(BaseModel):
    """Public Binance Agent OS token-information endpoint settings."""

    enabled: bool = Field(default=True)
    base_url: str = "https://web3.binance.com"
    timeout_seconds: int = Field(default=10, gt=0)
    cache_minutes: int = Field(default=15, ge=1, le=1440)
    # The Agent OS query-token-info skill supports these chains. Searching
    # across all of them keeps symbol-only lookups useful for Binance-listed
    # spot/futures assets while the collector prefers an exact symbol match.
    chain_ids: str = "1,56,8453,CT_501"


class WebConfig(BaseModel):
    port: int = Field(default=8000, gt=0, le=65535)
    host: str = Field(default="127.0.0.1")
    # Public address used in Telegram deep links. Keep this separate from
    # `host`: the web server may bind locally while users open the dashboard
    # through a domain or tunnel.
    public_url: str = Field(default="http://127.0.0.1:8000")
    # Access password is intentionally unset by default. The server fails
    # closed until an operator supplies it through the environment or .env.
    access_password: str | None = Field(
        default=None,
        description="Password required to access the dashboard and APIs",
    )
    # CORS is opt-in. Same-origin deployments do not need it, and a wildcard
    # origin is unsafe when authenticated cookies are in use.
    allowed_origins: list[str] = Field(default_factory=list)
    auth_session_ttl_seconds: int = Field(default=2592000, ge=300, le=2592000, description="Session TTL, default 30 days")


class UpdaterConfig(BaseModel):
    """Configuration for automatic and manual git updates."""

    # Updating a live checkout from the dashboard is an explicit operator
    # decision. Keep it disabled until the deployment has a release process.
    enabled: bool = Field(default=False)
    poll_interval_minutes: int = Field(default=10, ge=1)
    remote_name: str = Field(default="origin")
    branch_name: str = Field(default="main")
    auto_restart_services: bool = Field(default=False)
    rebuild_frontend: bool = Field(default=True)
    telegram_notify: bool = Field(default=False)
    auto_deploy_remote: bool = Field(default=False)


class AccountMonitorConfig(BaseModel):
    """Independent live-account reader. Never authorizes trading."""

    enabled: bool = False
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    api_secret: str | None = Field(default=None, exclude=True, repr=False)
    credentials_file: Path = Path(".env.binance-readonly")
    poll_seconds: int = Field(default=15, ge=10, le=60)


class ExecutionConfig(BaseModel):
    """Short-only Cross pilot. Environments never share credentials or state."""
    enabled: bool = Field(default=False)
    paper_trading: bool = True  # Legacy compatibility; environment is authoritative.
    environment: Literal["simulation", "demo", "live"] = "simulation"
    base_url: HttpUrl = HttpUrl("https://demo-fapi.binance.com")
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    api_secret: str | None = Field(default=None, exclude=True, repr=False)
    live_api_key: str | None = Field(default=None, exclude=True, repr=False)
    live_api_secret: str | None = Field(default=None, exclude=True, repr=False)
    initial_equity: float = Field(default=500.0, ge=500, le=500, allow_inf_nan=False)
    margin_per_position: float = Field(default=5.0, ge=5, le=5, allow_inf_nan=False)
    leverage: Literal[5] = 5
    margin_type: Literal["CROSSED"] = "CROSSED"
    max_position_usd: float = Field(default=25.0, ge=25, le=25, allow_inf_nan=False)
    max_open_positions: Literal[1, 3, 5] = 1
    entry_pause_drawdown: float = Field(default=0.20, ge=0.20, le=0.20, allow_inf_nan=False)
    tp_min_usdt: float = Field(default=0.5, gt=0, le=5)
    tp_max_usdt: float = Field(default=5.0, ge=5, le=5, allow_inf_nan=False)
    atr_period: Literal[14] = 14
    atr_multiplier: float = Field(default=2.0, ge=2, le=2, allow_inf_nan=False)
    fee_rate: float = Field(default=0.0005, ge=0, le=0.01)
    max_spread_bps: float = Field(default=20, gt=0, le=100)
    max_slippage_bps: float = Field(default=20, gt=0, le=100)
    signal_ttl_seconds: int = Field(default=300, ge=10, le=900)
    poll_seconds: int = Field(default=10, ge=1, le=60)
    manifest_path: Path | None = None
    evidence_path: Path | None = None
    evidence_sha256: str | None = None
    live_activated: bool = False
    # Automated Risk and Profit Enhancement
    enable_stop_loss: bool = Field(default=True, description="Enable automated position risk stop loss")
    sl_max_loss_usdt: float = Field(default=5.0, ge=0.5, le=50.0, description="Max dollar loss per trade in USDT")
    sl_atr_multiplier: float = Field(default=3.0, ge=0.5, le=10.0, description="Stop loss distance in ATR units")
    stop_loss_pct: float = Field(default=0.12, ge=0.01, le=0.5, description="12% default stop loss")
    take_profit_pct: float = Field(default=0.10, ge=0.01, le=1.0, description="10% default take profit")
    max_hold_hours: int = Field(default=72, ge=1, le=720, description="Max position holding hours before time-exit")
    enable_trailing_tp: bool = Field(default=True, description="Enable trailing profit locking")
    trailing_trigger_atr: float = Field(default=1.5, ge=0.5, le=10.0, description="ATR gain required to activate trailing stop")
    trailing_callback_atr: float = Field(default=1.0, ge=0.2, le=5.0, description="ATR callback distance from lowest price")
    require_price_confirmation: bool = Field(default=False, description="Require price confirmation on entry")


class ScaleInTemplateConfig(BaseModel):
    """One frozen execution template selected by the policy router."""

    policy_id: str
    version: str = "1.0"
    entry_offsets: list[float] = Field(min_length=3, max_length=3)
    allocations: list[float] = Field(min_length=3, max_length=3)
    hard_stop_pct: float = Field(gt=0.0, lt=1.0)
    scale_in_hours: int = Field(default=6, ge=1, le=23)
    horizon_hours: int = Field(default=24, ge=1, le=168)
    risk_multiplier: float = Field(default=1.0, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_template(self) -> "ScaleInTemplateConfig":
        if self.entry_offsets[0] != 0.0:
            raise ValueError("the first entry offset must be 0")
        if any(value < 0.0 for value in self.entry_offsets):
            raise ValueError("entry offsets must be non-negative")
        if self.entry_offsets != sorted(self.entry_offsets):
            raise ValueError("entry offsets must be sorted")
        if self.entry_offsets[-1] >= self.hard_stop_pct:
            raise ValueError("the last entry must be below the hard stop")
        if any(value <= 0.0 for value in self.allocations):
            raise ValueError("allocations must be positive")
        if abs(sum(self.allocations) - 1.0) > 1e-6:
            raise ValueError("allocations must sum to 1.0")
        if self.scale_in_hours >= self.horizon_hours:
            raise ValueError("scale_in_hours must be shorter than horizon_hours")
        return self


def _default_scale_in_templates() -> list[ScaleInTemplateConfig]:
    return [
        ScaleInTemplateConfig(
            policy_id="scale_in_compact",
            entry_offsets=[0.0, 0.03, 0.06],
            allocations=[0.20, 0.30, 0.50],
            hard_stop_pct=0.12,
            risk_multiplier=1.0,
        ),
        ScaleInTemplateConfig(
            policy_id="scale_in_balanced",
            entry_offsets=[0.0, 0.05, 0.10],
            allocations=[0.20, 0.30, 0.50],
            hard_stop_pct=0.16,
            risk_multiplier=0.75,
        ),
        ScaleInTemplateConfig(
            policy_id="scale_in_deep_squeeze",
            entry_offsets=[0.0, 0.08, 0.14],
            allocations=[0.10, 0.30, 0.60],
            hard_stop_pct=0.16,
            scale_in_hours=12,
            risk_multiplier=0.50,
        ),
    ]


class ExecutionPolicyRouterConfig(BaseModel):
    """Versioned policy selection, with a safe shadow-model upgrade path."""

    enabled: bool = True
    advisory_only: bool = True
    router_version: str = "scale_in_router_v1"
    feature_schema_version: str = "execution_profile_features_v1"
    required_label_version: str = "distribution_short_v2"
    require_matching_label: bool = True
    selector_mode: Literal["rules", "shadow_model", "model"] = "rules"
    fallback_policy_id: str = "scale_in_balanced"
    compact_policy_id: str = "scale_in_compact"
    deep_policy_id: str = "scale_in_deep_squeeze"
    min_signal_score: float = Field(default=55.0, ge=0.0, le=100.0)
    min_quality_score: float = Field(default=80.0, ge=0.0, le=100.0)
    min_liquidity_score: float = Field(default=35.0, ge=0.0, le=100.0)
    compact_volatility_max: float = Field(default=60.0, ge=0.0, le=100.0)
    deep_volatility_min: float = Field(default=90.0, ge=0.0, le=100.0)
    deep_squeeze_min: float = Field(default=75.0, ge=0.0, le=100.0)
    deep_signal_min: float = Field(default=75.0, ge=0.0, le=100.0)
    skip_volatility_min: float = Field(default=97.0, ge=0.0, le=100.0)
    target_drawdown: float = Field(default=0.20, gt=0.0, lt=1.0)
    templates: list[ScaleInTemplateConfig] = Field(
        default_factory=_default_scale_in_templates
    )

    @model_validator(mode="after")
    def validate_router(self) -> "ExecutionPolicyRouterConfig":
        ids = [template.policy_id for template in self.templates]
        if len(ids) != len(set(ids)):
            raise ValueError("execution policy ids must be unique")
        references = {
            "fallback_policy_id": self.fallback_policy_id,
            "compact_policy_id": self.compact_policy_id,
            "deep_policy_id": self.deep_policy_id,
        }
        for field_name, policy_id in references.items():
            if policy_id not in ids:
                raise ValueError(f"{field_name} must reference a configured template")
        if self.compact_volatility_max >= self.deep_volatility_min:
            raise ValueError("compact volatility cutoff must be below deep cutoff")
        if self.deep_volatility_min >= self.skip_volatility_min:
            raise ValueError("deep volatility cutoff must be below skip cutoff")
        return self


class AiConfig(BaseModel):

    provider: str = Field(default="openai", description="Default LLM provider (openai, gemini, claude, deepseek, ollama)")
    api_key: str | None = Field(default=None, exclude=True, description="Default API key for AI analyst")
    model_id: str = Field(default="antigravity/gemini-3.7-flash-tiered", description="Default model ID")
    base_url: str = Field(default="https://proxy-ai.comaygiauco.com/v1", description="Default OpenAI-compatible base URL")
    enabled: bool = Field(default=True, description="Enable AI analyst by default")


class FiboTrendShortConfig(BaseModel):
    """Configuration for the Confirmed Reversal & Fibonacci Short branch (H4/D1 -> H1)."""

    enabled: bool = True
    higher_timeframes: list[Literal["4h", "1d"]] = Field(
        default_factory=lambda: ["4h", "1d"]
    )
    confirm_timeframe: Literal["1h"] = "1h"
    swing_lookback_bars: int = Field(default=30, ge=10, le=120)
    swing_pivot_left_bars: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of lower/equal highs required to the left of Swing High",
    )
    swing_pivot_right_bars: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of lower/equal highs required to the right of Swing High (confirmed pivot)",
    )
    min_prior_pump_pct: float = Field(default=0.05, ge=0.01, le=5.0)
    min_impulse_drop_pct: float = Field(default=0.04, ge=0.01, le=0.80)
    fibo_entry_min: float = Field(default=0.500, gt=0.0, lt=1.0)
    fibo_entry_max: float = Field(default=0.618, gt=0.0, lt=1.0)
    fibo_watch_min: float = Field(default=0.382, gt=0.0, lt=1.0)
    fibo_watch_max: float = Field(default=0.786, gt=0.0, lt=1.0)
    fibo_invalidation_level: float = Field(default=1.000, gt=0.5, le=1.5)
    sl_mode: Literal["above_swing_high", "above_0886", "above_0786"] = "above_swing_high"
    sl_atr_buffer: float = Field(default=0.20, ge=0.0, le=3.0)
    m6_sl_atr_buffer: float = Field(
        default=0.25,
        ge=0.0,
        le=3.0,
        description="ATR buffer used when tightening Stop Loss to Fibo 0.886 in Mốc 6",
    )
    tp1_fibo_level: float = Field(default=0.000, ge=-0.5, le=0.5)
    tp2_extension_level: float = Field(default=1.272, gt=1.0, le=3.0)
    tp3_extension_level: float = Field(default=1.618, gt=1.0, le=5.0)
    require_both_h1_conditions: bool = False
    # 4-Layer Orthogonal Alpha Architecture parameters (Factor #1, #2, #3, #4)
    enable_pst_gate: bool = Field(
        default=False,
        description="Enforce pysystemtrade (ewmac_16_64 <= 0 OR accel_4_16 <= -1.0) or parabolic wave_ker >= 0.65",
    )
    min_wave_ker: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum Kaufman Efficiency Ratio of the prior pump wave (0.35 recommended)",
    )
    min_impulse_ker: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum Kaufman Efficiency Ratio of the downward impulse wave (0.50 recommended)",
    )
    min_conviction_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Minimum 4-Factor Orthogonal Conviction Score (55.0 recommended for production)",
    )
    dynamic_conviction_sizing: bool = Field(
        default=True,
        description="Assign Conviction Tier (S/A/B/C) and recommended risk multiplier (1.50x/1.15x/0.80x)",
    )
    conviction_tier_s_threshold: float = Field(default=80.0, ge=0.0, le=100.0)
    conviction_tier_a_threshold: float = Field(default=68.0, ge=0.0, le=100.0)
    conviction_tier_b_threshold: float = Field(default=55.0, ge=0.0, le=100.0)
    conviction_mult_s: float = Field(default=1.50, ge=0.1, le=5.0)
    conviction_mult_a: float = Field(default=1.15, ge=0.1, le=5.0)
    conviction_mult_b: float = Field(default=0.80, ge=0.1, le=5.0)
    conviction_mult_c: float = Field(default=0.50, ge=0.0, le=5.0)
    max_candidates: int = Field(default=60, ge=5, le=200)
    universe_mode: Literal[
        "tiered_whitelist",
        "tier_s_only",
        "pit_zero_bias_mcap_float",
        "rolling_pit_top50",
        "dynamic_all",
    ] = Field(
        default="tiered_whitelist",
        description="tiered_whitelist (PIT Top-50 + Tier S + Tier A v1.2), rolling_pit_top50 (Monthly Rolling PIT Top-50 Volume + Wick p90<=3.2%), tier_s_only, pit_zero_bias_mcap_float, or dynamic_all",
    )
    universe_config_path: Path = Path("artifacts/fibo_trend_short/fibo_coin_universe_config.json")
    blacklist_symbols: list[str] = Field(
        default_factory=lambda: [
            "BTCUSDT",
            "ETHUSDT",
            "BNBUSDT",
            "PAXGUSDT",
            "XAUTUSDT",
            "BTCDOMUSDT",
            "DEFIUSDT",
            "USDCUSDT",
            "FDUSDUSDT",
            "TUSDUSDT",
            "DAIUSDT",
            "BUSDUSDT",
            "EURUSDT",
        ]
    )
    horizon_hours: int = Field(default=72, ge=6, le=336)
    horizon_hours_1d: int = Field(default=120, ge=6, le=336)
    min_cooldown_hours: int = Field(default=4, ge=1, le=168)
    round_trip_fee_bps: float = Field(default=20.0, ge=0.0, le=200.0)
    telegram_enabled: bool = True
    telegram_cooldown_minutes: int = Field(default=180, ge=0)
    telegram_require_qualified_short: bool = Field(
        default=True,
        description="Only send Telegram alerts for FIRED_CONFIRMED_SHORT signals that pass the v4.0.21 Short qualification gates (matched_policies non-empty)",
    )
    telegram_allowed_policies: list[str] = Field(
        default_factory=lambda: [
            "sniper_risk",
            "sniper_horizon24",
            "sniper_rr1_horizon24",
            "elite_sniper_risk",
        ],
        description="Validated v4.0.21 Short policies with positive expectancy (Sniper / Elite Sniper) that qualify a confirmed Short signal for Telegram dispatch",
    )
    # Hard cutoff for In-Sample Backtest (<= 2025-12-31) to preserve 2026+ as OOS
    in_sample_end_utc: str = "2025-12-31T23:59:59+00:00"

    @model_validator(mode="after")
    def validate_fibo_ranges(self) -> "FiboTrendShortConfig":
        if self.fibo_entry_min >= self.fibo_entry_max:
            raise ValueError("fibo_entry_min must be strictly less than fibo_entry_max")
        if self.fibo_watch_min > self.fibo_entry_min:
            raise ValueError("fibo_watch_min must be <= fibo_entry_min")
        if self.fibo_watch_max < self.fibo_entry_max:
            raise ValueError("fibo_watch_max must be >= fibo_entry_max")
        return self


class AppSettings(BaseSettings):
    fibo_trend_short: FiboTrendShortConfig = FiboTrendShortConfig()
    web: WebConfig = WebConfig()
    ai: AiConfig = AiConfig()
    updater: UpdaterConfig = UpdaterConfig()
    binance: BinanceConfig = BinanceConfig()
    collection: CollectionPolicy = CollectionPolicy()
    paths: PathsConfig = PathsConfig()
    telegram: TelegramConfig = TelegramConfig()
    scanner: ScannerConfig = ScannerConfig()
    scoring: ScoringConfig = ScoringConfig()
    self_learning: SelfLearningConfig = SelfLearningConfig()
    pump_filter: PumpFilterConfig = PumpFilterConfig()
    market_anomalies: MarketAnomalyConfig = MarketAnomalyConfig()
    candidate_comparison: CandidateComparisonConfig = CandidateComparisonConfig()
    threshold: ThresholdPolicy = ThresholdPolicy()
    binance_agent_os: BinanceAgentOSConfig = BinanceAgentOSConfig()
    coinmarketcap: CoinMarketCapConfig = CoinMarketCapConfig()
    execution: ExecutionConfig = ExecutionConfig()
    account_monitor: AccountMonitorConfig = AccountMonitorConfig()
    execution_policy: ExecutionPolicyRouterConfig = ExecutionPolicyRouterConfig()
    coingecko: CoinGeckoConfig = CoinGeckoConfig()
    api_key: str | None = Field(default=None, exclude=True)
    api_secret: str | None = Field(default=None, exclude=True)

    model_config = SettingsConfigDict(
        env_prefix="DAO_VANG_",
        env_nested_delimiter="__",
        env_file=(".env", str(Path(__file__).resolve().parents[3] / ".env")),
    )

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "AppSettings":
        if not yaml_path.exists():
            return cls()

        with open(yaml_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            config_dict = typing.cast(dict[str, typing.Any], loaded) if loaded else {}

        return cls(**config_dict)


RUNTIME_CONFIG_ENV = "DAO_VANG_CONFIG_PATH"


def load_runtime_settings(config_path: str | Path | None = None) -> AppSettings:
    """Load one versioned runtime config while retaining env-only secrets.

    YAML values intentionally win over duplicate environment values. This keeps
    the production model and scanner policy canonical, while nested fields that
    are absent from YAML (passwords, tokens and API keys) still come from the
    environment through `BaseSettings`.
    """

    configured_path = str(config_path or os.getenv(RUNTIME_CONFIG_ENV, "")).strip()
    if not configured_path:
        return AppSettings()

    path = Path(configured_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Runtime config from {RUNTIME_CONFIG_ENV} does not exist: {path}"
        )
    return AppSettings.from_yaml(path)
