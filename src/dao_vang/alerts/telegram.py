"""Telegram Bot API client for sending distribution alerts.

Reads bot_token + chat_id from TelegramConfig (env var or YAML).
Uses httpx (already a dependency via collectors) for HTTP calls.
Retries with tenacity on transient failures.

Supports bilingual formatting (Vietnamese 'vi' and English 'en').
Security: never logs the full bot token — only first 4 chars + ***.
"""

from __future__ import annotations

import os
from typing import Any, Mapping
from urllib.parse import quote

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from dao_vang.config.settings import TelegramConfig
from dao_vang.domain.time import system_iso
from dao_vang.logging import get_logger

logger = get_logger(__name__)


def _display_time(value: str, lang: str = "vi") -> str:
    """Format an ISO/DB timestamp for Telegram. UTC+7 for VI, UTC for EN."""
    if lang == "en":
        raw = str(value).replace("T", " ")[:19]
        return f"{raw} UTC"
    converted = system_iso(value)
    formatted = converted[:19].replace("T", " ") if converted else str(value)[:19]
    return f"{formatted} UTC+7"

def _ecosystem_utm_footer(lang: str = "vi", campaign: str = "radar_alert") -> str:
    """Return a 1-line UTM-tracked FreqPilot Studio & Free SHA-256 Bundle footer (vi/en/zh/ko)."""
    if os.environ.get("FREQPILOT_UTM_FOOTER", "1").strip() == "0":
        return ""
    norm = (lang or "vi").strip().lower()
    lang_code = norm if norm in {"vi", "en", "zh", "ko"} else "vi"
    url = f"https://freqpilot.dev/?utm_source=telegram_{lang_code}&utm_medium=alert_footer&utm_campaign={campaign}#pricing"
    copy = {
        "vi": f"🧪 [Tải miễn phí Gói Chiến Lược Freqtrade SHA-256 & Studio Kiểm Định]({url})",
        "en": f"🧪 [Free SHA-256 Verified Freqtrade Bundle & Quant Studio]({url})",
        "zh": f"🧪 [免费领取 SHA-256 验证 Freqtrade 策略包与量化工作台]({url})",
        "ko": f"🧪 [무료 SHA-256 검증 Freqtrade 전략 번들 & 퀀트 스튜디오]({url})",
    }
    return copy[lang_code]


_RISK_EMOJI = {
    "CRITICAL": "🟣",
    "CAO": "🟠",
    "HIGH": "🟠",
    "TRUNG BÌNH": "🟡",
    "MEDIUM": "🟡",
    "THẤP": "⚪",
    "LOW": "⚪",
    "RẤT THẤP": "⚪",
    "VERY LOW": "⚪",
    "SAFE": "⚪",
}

_RISK_LABELS_VI = {
    "CRITICAL": "TÍN HIỆU CỰC MẠNH",
    "CAO": "TÍN HIỆU MẠNH",
    "HIGH": "TÍN HIỆU MẠNH",
    "TRUNG BÌNH": "CẦN THEO DÕI",
    "MEDIUM": "CẦN THEO DÕI",
    "THẤP": "TÍN HIỆU YẾU",
    "LOW": "TÍN HIỆU YẾU",
    "RẤT THẤP": "TÍN HIỆU YẾU",
    "VERY LOW": "TÍN HIỆU YẾU",
    "SAFE": "TÍN HIỆU YẾU",
}

_RISK_LABELS_EN = {
    "CRITICAL": "VERY HIGH CONVICTION",
    "CAO": "HIGH CONVICTION",
    "HIGH": "HIGH CONVICTION",
    "TRUNG BÌNH": "WATCHLIST",
    "MEDIUM": "WATCHLIST",
    "THẤP": "WEAK SIGNAL",
    "LOW": "WEAK SIGNAL",
    "RẤT THẤP": "VERY WEAK",
    "VERY LOW": "VERY WEAK",
    "SAFE": "WEAK SIGNAL",
}

_MODE_LABELS_VI = {
    "research": "NGHIÊN CỨU",
    "shadow": "QUAN SÁT (SHADOW)",
    "canary": "CANARY / THỬ NGHIỆM",
    "production": "VẬN HÀNH THẬT",
    "production_alerting": "BÁO CÁO THAM KHẢO",
}

_MODE_LABELS_EN = {
    "research": "RESEARCH",
    "shadow": "SHADOW OBSERVATION",
    "canary": "CANARY / PILOT",
    "production": "PRODUCTION",
    "production_alerting": "REFERENCE REPORT",
}

_RECOMMENDATION_LABELS_VI = {
    "SHORT_CANDIDATE": "ỨNG VIÊN SHORT",
    "HIGH_CONFIDENCE": "TÍN HIỆU MẠNH",
    "WATCH": "THEO DÕI",
    "WAIT": "CHỜ THÊM",
}

_RECOMMENDATION_LABELS_EN = {
    "SHORT_CANDIDATE": "SHORT CANDIDATE",
    "HIGH_CONFIDENCE": "HIGH CONFIDENCE SIGNAL",
    "WATCH": "WATCHLIST",
    "WAIT": "WAIT / STANDBY",
}

_BTC_REGIME_LABELS_VI = {
    "FOMO": "TĂNG NÓNG (FOMO)",
    "NEUTRAL": "TRUNG TÍNH",
    "WEAK": "YẾU",
}

_BTC_REGIME_LABELS_EN = {
    "FOMO": "BULLISH HEAT (FOMO)",
    "NEUTRAL": "NEUTRAL",
    "WEAK": "WEAK",
}

_SIGNAL_LABELS_VI = {
    "price_volume_divergence": "Phân kỳ giá - khối lượng",
    "funding_spike": "Funding tăng đột biến",
    "momentum_exhaustion": "Đà tăng suy yếu",
    "distance_from_high": "Xa đỉnh gần nhất",
    "taker_sell_pressure": "Áp lực bán chủ động",
    "btc_context": "Bối cảnh BTC",
    "oi_divergence": "Phân kỳ Open Interest",
    "fake_breakout": "Có dấu hiệu phá vỡ giả",
}

_SIGNAL_LABELS_EN = {
    "price_volume_divergence": "Price-Volume Divergence",
    "funding_spike": "Funding Rate Spike",
    "momentum_exhaustion": "Momentum Exhaustion",
    "distance_from_high": "Distance from Recent High",
    "taker_sell_pressure": "Taker Sell Pressure",
    "btc_context": "BTC Market Regime",
    "oi_divergence": "Open Interest Divergence",
    "fake_breakout": "Suspected Fake Breakout",
}


def _mode_label(mode: str, lang: str = "vi") -> str:
    """Return a stable, human-readable serving-mode label for Telegram."""
    normalized = str(mode).strip().lower()
    table = _MODE_LABELS_EN if lang == "en" else _MODE_LABELS_VI
    return table.get(normalized, normalized.upper() or "UNKNOWN")


def _recommendation_label(recommendation: str, lang: str = "vi") -> str:
    normalized = str(recommendation).strip().upper()
    table = _RECOMMENDATION_LABELS_EN if lang == "en" else _RECOMMENDATION_LABELS_VI
    return table.get(normalized, normalized.replace("_", " "))


def _risk_label(risk_level: str, lang: str = "vi") -> str:
    normalized = str(risk_level).strip().upper()
    table = _RISK_LABELS_EN if lang == "en" else _RISK_LABELS_VI
    default = "UNKNOWN" if lang == "en" else "KHÔNG XÁC ĐỊNH"
    return table.get(normalized, normalized or default)


def _btc_regime_label(regime: str, lang: str = "vi") -> str:
    normalized = str(regime).strip().upper()
    table = _BTC_REGIME_LABELS_EN if lang == "en" else _BTC_REGIME_LABELS_VI
    default = "UNKNOWN" if lang == "en" else "KHÔNG XÁC ĐỊNH"
    return table.get(normalized, normalized or default)


def _signal_label(name: str, lang: str = "vi") -> str:
    normalized = str(name).strip().lower()
    table = _SIGNAL_LABELS_EN if lang == "en" else _SIGNAL_LABELS_VI
    return table.get(normalized, normalized.replace("_", " ").title())


def _signal_grade(
    probability: float | None = None,
    total_score: float | None = None,
    recommendation: str = "",
    risk_level: str = "",
    lang: str = "vi",
) -> tuple[str, str, str]:
    """Calculate rating stars, badge color emoji, and human tier label.

    Returns:
        (stars_str, color_emoji, tier_title)
        Example: ("⭐⭐⭐⭐⭐", "🔴", "CỰC MẠNH" / "EXTREME")
    """
    prob = float(probability) if probability is not None else 0.0
    score = float(total_score) if total_score is not None else 0.0
    rec = str(recommendation).strip().upper()
    risk = str(risk_level).strip().upper()

    if prob >= 0.85 or score >= 85 or (risk in {"CAO", "HIGH"} and prob >= 0.82):
        stars = "⭐⭐⭐⭐⭐"
        color = "🔴"
        title = "CỰC MẠNH" if lang == "vi" else "EXTREME"
    elif prob >= 0.80 or score >= 75 or rec in {"SHORT_CANDIDATE", "HIGH_CONFIDENCE"}:
        stars = "⭐⭐⭐⭐"
        color = "🟠"
        title = "RẤT MẠNH" if lang == "vi" else "VERY HIGH"
    elif prob >= 0.70 or score >= 60:
        stars = "⭐⭐⭐"
        color = "🟡"
        title = "TIÊU CHUẨN" if lang == "vi" else "STANDARD"
    elif prob >= 0.50 or rec == "WATCH" or risk in {"TRUNG BÌNH", "MEDIUM"}:
        stars = "⭐⭐"
        color = "🟢"
        title = "THEO DÕI" if lang == "vi" else "WATCH"
    else:
        stars = "⭐"
        color = "⚪"
        title = "THẤP" if lang == "vi" else "LOW"

    return stars, color, title


def _coin_url(base_url: str | None, symbol: str) -> str | None:
    """Build the frontend hash link that opens the selected coin directly."""
    base = str(base_url or "").strip().rstrip("/")
    normalized_symbol = str(symbol).strip().upper()
    if not base or not normalized_symbol:
        return None
    return f"{base}/#coin={quote(normalized_symbol, safe='')}"


class TelegramNotifier:
    """Send alerts via Telegram Bot API.

    Args:
        config: TelegramConfig with bot_token + chat_id + language.
    """

    def __init__(self, config: TelegramConfig, web_base_url: str | None = None) -> None:
        self._config = config
        self._web_base_url = web_base_url
        self._base_url = f"{config.api_base}/bot{config.bot_token}"
        self._lang = getattr(config, "language", "vi") or "vi"
        token_display = f"{config.bot_token[:4]}***" if config.bot_token else "NOT_SET"
        logger.info("telegram_notifier_init", token=token_display, language=self._lang)

    @property
    def is_configured(self) -> bool:
        """True when the bot and at least one configured destination are set."""
        return bool(self._config.bot_token and (self._config.chat_id or self._config.shadow_chat_id))

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, OSError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to Telegram API with retry."""
        url = f"{self._base_url}/sendMessage"
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def send_message(
        self,
        text: str,
        parse_mode: str = "Markdown",
        disable_web_page_preview: bool = True,
        chat_id: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> bool:
        """Send a plain text message.

        Returns True on success, False on failure (logged, not raised).
        """
        if not self.is_configured:
            logger.warning("telegram_not_configured_skip")
            return False
        target_chat_id = chat_id or self._config.chat_id
        if not target_chat_id:
            logger.warning("telegram_no_chat_id_skip")
            return False
        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
            "link_preview_options": {"is_disabled": disable_web_page_preview},
        }
        if reply_to_message_id is not None:
            payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
        try:
            result = self._post(payload)
            ok = result.get("ok", False)
            if not ok:
                logger.error("telegram_send_failed", response=result)
            return ok
        except Exception as exc:
            logger.error("telegram_send_error", error=str(exc))
            return False

    def send_message_result(
        self,
        text: str,
        parse_mode: str = "Markdown",
        disable_web_page_preview: bool = True,
        chat_id: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Send a message and return Telegram's result object.

        ``send_message`` intentionally remains a bool-returning compatibility
        wrapper.  Durable V3 dispatch needs Telegram's ``message_id`` so later
        fill/outcome updates can reply to the original signal.
        """
        if not self._config.bot_token:
            logger.warning("telegram_not_configured_skip")
            return None
        target_chat_id = chat_id or self._config.chat_id
        if not target_chat_id:
            logger.warning("telegram_no_chat_id_skip")
            return None
        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
            "link_preview_options": {"is_disabled": disable_web_page_preview},
        }
        if reply_to_message_id is not None:
            payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
        try:
            response = self._post(payload)
            if not response.get("ok", False):
                logger.error("telegram_send_failed", response=response)
                return None
            result = response.get("result")
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.error("telegram_send_error", error=str(exc))
            return None

    def send_alert(
        self,
        symbol: str,
        risk_level: str,
        probability: float,
        threshold: float,
        close_price: float | None,
        feature_time: str,
        invalidation_time: str,
        model_id: str,
        web_url: str | None = None,
        operating_mode: str = "production",
    ) -> bool:
        """Send a compact, mobile-friendly distribution alert with star rating."""
        if str(risk_level).strip().upper() not in {"CAO", "HIGH", "HIGH_CONFIDENCE"}:
            return False
        stars, color_badge, grade_title = _signal_grade(
            probability=probability,
            risk_level=risk_level,
            lang=self._lang,
        )
        price_str = f"${close_price:,.4f}" if close_price else "N/A"
        mode_label = _mode_label(operating_mode, self._lang)
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""

        if self._lang == "en":
            lines = [
                f"{color_badge} *DISTRIBUTION ALERT — `{symbol}`* {stars}{mode_prefix}",
                f"• *Signal Grade:* {stars} `{grade_title}` ({color_badge})",
                f"• *Conviction:* {_risk_label(risk_level, 'en')}",
                f"• *Model Probability:* {probability:.1%}",
                f"• *Close Price:* {price_str}",
                f"• *Signal Time:* {_display_time(feature_time, 'en')}",
            ]
            if detail_url:
                lines.append(f"[🔗 Open {symbol} Analysis Dashboard]({detail_url})")
            lines.extend(["", "_Reference only. Please DYOR before making any trading decisions._"])
        else:
            lines = [
                f"{color_badge} *CẢNH BÁO PHÂN PHỐI — `{symbol}`* {stars}{mode_prefix}",
                f"• *Cấp độ tín hiệu:* {stars} `{grade_title}` ({color_badge})",
                f"• *Độ tin cậy:* {_risk_label(risk_level, 'vi')}",
                f"• *Xác suất mô hình:* {probability:.1%}",
                f"• *Giá đóng cửa:* {price_str}",
                f"• *Thời điểm tín hiệu:* {_display_time(feature_time, 'vi')}",
            ]
            if detail_url:
                lines.append(f"[🔗 Mở trang phân tích {symbol}]({detail_url})")
            lines.extend(["", "_Báo cáo tham khảo; hãy tự kiểm tra trước khi quyết định._"])

        utm_line = _ecosystem_utm_footer(self._lang, "distribution_alert")
        if utm_line:
            lines.append(utm_line)
        text = "\n".join(lines)
        return self.send_message(text)

    def send_scored_alert(
        self,
        symbol: str,
        total_score: float,
        recommendation: str,
        pump_pct: float,
        pump_days: int,
        top_signals: list[tuple[str, float, float, str]],
        btc_regime: str,
        btc_explanation: str,
        close_price: float | None,
        feature_time: str,
        invalidation_time: str,
        evidence_precision: float | None = None,
        evidence_n_judged: int = 0,
        web_url: str | None = None,
        model_probability: float | None = None,
        horizon_hours: int | None = None,
        data_quality_score: float | None = None,
        model_id: str | None = None,
        label_version: str | None = None,
        operating_mode: str = "production",
    ) -> bool:
        """Send a compact composite-score distribution alert with star rating."""
        normalized_recommendation = str(recommendation).strip().upper()
        if normalized_recommendation not in {"SHORT_CANDIDATE", "HIGH_CONFIDENCE"}:
            return False
        stars, color_badge, grade_title = _signal_grade(
            probability=model_probability,
            total_score=total_score,
            recommendation=normalized_recommendation,
            lang=self._lang,
        )
        price = close_price or 0.0
        price_str = f"${price:,.4f}" if price > 0 else "N/A"
        mode_label = _mode_label(operating_mode, self._lang)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""
        detail_url = web_url or _coin_url(self._web_base_url, symbol)

        if self._lang == "en":
            stage_badge = "⚡ *[DISTRIBUTION SIGNAL — HIGH CONFIDENCE]*"
            sig_lines = []
            for s in top_signals[:3]:
                sig_name = _signal_label(s[0], "en")
                sig_exp = f" ({s[3]})" if len(s) > 3 and s[3] and s[3] != s[0] else ""
                sig_lines.append(f"  • *{sig_name}*{sig_exp}")
            sig_text = "\n".join(sig_lines) if sig_lines else "  • Distribution pattern detected on order flow"
            prob_str = f"{model_probability:.1%}" if model_probability is not None else "N/A"
            pump_str = f"+{pump_pct:.0%} in {pump_days}d" if pump_days > 0 else f"+{pump_pct:.0%}"

            lines = [
                f"{stage_badge} `{symbol}` {stars}{mode_prefix}",
                f"• *Market Price:* `{price_str}` | *Pump Amplitude:* `{pump_str}`",
                f"• *Distribution Score:* `{total_score:.0f}/100` | *Short Probability:* `{prob_str}`",
                f"• *BTC Market Context:* {_btc_regime_label(btc_regime, 'en')}",
                "• *Key Distribution Reasons:*",
                sig_text,
            ]
            if detail_url:
                lines.append(f"[🔗 Open {symbol} Analysis Dashboard]({detail_url})")
            lines.extend(["", "_Distribution radar analysis from Dao Vang AI._"])
        else:
            stage_badge = "⚡ *[CẢNH BÁO TÍN HIỆU SHORT — PHÂN PHỐI ĐỈNH]* 🚨"
            sig_lines = []
            for s in top_signals[:3]:
                sig_name = _signal_label(s[0], "vi")
                sig_exp = f" ({s[3]})" if len(s) > 3 and s[3] and s[3] != s[0] else ""
                sig_lines.append(f"  • *{sig_name}*{sig_exp}")
            sig_text = "\n".join(sig_lines) if sig_lines else "  • Phát hiện dấu hiệu phân phối đỉnh trên dữ liệu phái sinh"
            prob_str = f"{model_probability:.1%}" if model_probability is not None else "N/A"
            pump_str = f"+{pump_pct:.0%} trong {pump_days} ngày" if pump_days > 0 else f"+{pump_pct:.0%}"

            lines = [
                f"{stage_badge} `{symbol}` {stars}{mode_prefix}",
                f"• *Giá thị trường:* `{price_str}` | *Biên độ bơm:* `{pump_str}`",
                f"• *Điểm phân phối 2 Tầng:* *{total_score:.0f}/100* | *Xác suất Short:* `{prob_str}`",
                f"• *Bối cảnh BTC:* {_btc_regime_label(btc_regime, 'vi')}",
                "• *Căn cứ & Tín hiệu phân phối chính:*",
                sig_text,
            ]
            if detail_url:
                lines.append(f"[🔗 Mở Biểu Đồ & Phân Tích {symbol}]({detail_url})")
            lines.extend(["", "_Báo cáo phân tích xác suất phân phối từ Đảo Vàng AI._"])
        utm_line = _ecosystem_utm_footer(self._lang, "scored_alert")
        if utm_line:
            lines.append(utm_line)
        text = "\n".join(lines)
        return self.send_message(text)

    @staticmethod
    def _v3_condition_summary(conditions: dict[str, Any] | None) -> str:
        """Render the five configured V3 gates without implying calibration."""
        if not conditions:
            return "5-condition gate status unavailable"
        aliases = {
            "pump": ("pump",),
            "reversal": ("reversal",),
            "funding": ("funding",),
            "funding change": ("funding_change", "funding_change_8h"),
            "reference score": ("score", "reference_score", "model_score"),
        }
        passed = 0
        total = 0
        labels: list[str] = []
        for name, keys in aliases.items():
            value = next((conditions.get(key) for key in keys if key in conditions), None)
            if isinstance(value, dict):
                value = value.get("passed", value.get("met"))
            if isinstance(value, bool):
                total += 1
                passed += int(value)
                labels.append(f"{name} {'✓' if value else '✗'}")
        if not total:
            return "5-condition gate status unavailable"
        persistence = next(
            (conditions.get(key) for key in ("funding_persistence", "funding_persistence_7d") if key in conditions),
            None,
        )
        if isinstance(persistence, dict):
            persistence = persistence.get("passed", persistence.get("met"))
        if isinstance(persistence, bool):
            labels.append(f"funding persistence {'✓' if persistence else '✗'} (extra gate)")
        return f"{passed}/5 configured conditions met · " + ", ".join(labels)

    @staticmethod
    def _v3_discrepancy_text(value: Any) -> str:
        """Keep structured pattern discrepancies readable in Markdown."""
        if not isinstance(value, list):
            return str(value)
        rendered: list[str] = []
        for entry in value:
            if isinstance(entry, Mapping):
                feature = entry.get("feature", "feature")
                current = entry.get("value", "—")
                template = entry.get("template_value", "—")
                error = entry.get("standardized_abs_error")
                suffix = f" (|z| {error})" if error is not None else ""
                rendered.append(f"{feature}: {current} vs {template}{suffix}")
            else:
                rendered.append(str(entry))
        return ", ".join(rendered)

    def _v3_target_chat(self, operating_mode: str, shadow_chat_id: str | None) -> str | None:
        """Resolve V3's destination while keeping research out of production."""
        explicit_shadow = shadow_chat_id or getattr(self._config, "shadow_chat_id", None)
        if operating_mode in {"research", "shadow"}:
            if not explicit_shadow:
                logger.info("v3_telegram_suppressed_research_mode_no_shadow_chat")
            return explicit_shadow
        return explicit_shadow or self._config.chat_id

    def _render_v3_alert(
        self,
        *,
        symbol: str,
        entry_price: float,
        probability: float,
        pump_pct: float,
        distance_from_high: float,
        funding_percentile: float,
        feature_time: str,
        is_champion: bool,
        is_scout: bool,
        web_url: str | None,
        operating_mode: str,
        pattern_id: str | None,
        pattern_type: str | None,
        pattern_stage: str | None,
        pattern_status: str | None,
        nearest_pattern: str | None,
        pattern_distance: float | None,
        pattern_discrepancies: list[Any] | str | None,
        pattern_quality: str | None,
        conditions: dict[str, Any] | None,
        quality_validated: bool | None,
        evidence_kind: str | None,
        score_kind: str,
        score_confirmation: str | None,
    ) -> str:
        price_str = f"${entry_price:,.4f}" if entry_price < 10 else f"${entry_price:,.2f}"
        e2, e3 = entry_price * 1.03, entry_price * 1.06
        e2_str = f"${e2:,.4f}" if e2 < 10 else f"${e2:,.2f}"
        e3_str = f"${e3:,.4f}" if e3 < 10 else f"${e3:,.2f}"
        tp_price, sl_price = entry_price * 0.80, entry_price * 1.16
        tp_str = f"${tp_price:,.4f}" if tp_price < 10 else f"${tp_price:,.2f}"
        sl_str = f"${sl_price:,.4f}" if sl_price < 10 else f"${sl_price:,.2f}"

        lane_badge = "🏆 *[V3 CHAMPION]*" if is_champion else (
            "🎯 *[V3 FUNDING SCOUT]*" if is_scout else "🔬 *[V3 CHALLENGER]*"
        )
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        formatted_time = _display_time(feature_time, self._lang)
        mode_label = _mode_label(operating_mode, self._lang)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""
        stage = str(pattern_stage or "SIGNAL").strip().upper()
        pattern_name = pattern_type or pattern_id
        pattern_state = str(pattern_status or "matched").strip().lower()
        pattern_tag = pattern_name or "UNKNOWN"
        score_label = (
            "Calibrated probability" if score_kind.lower() in {"probability", "calibrated_probability"}
            else "Reference model score"
        )
        try:
            score_value = float(probability)
            score_text = (
                f"{score_value:.1%}"
                if score_kind.lower() in {"probability", "calibrated_probability"}
                else f"{score_value:.3f}"
            ) if 0.0 <= score_value <= 1.0 else "N/A"
        except (TypeError, ValueError):
            score_text = "N/A"
        evidence_label = (
            "Validated high-quality evidence"
            if quality_validated is True
            else "Evidence not validated for quality"
        )
        if evidence_kind:
            evidence_label += f" · {evidence_kind}"

        lines = [
            f"{lane_badge} 🚨 *V3 RESEARCH SIGNAL — `{symbol}`*{mode_prefix}",
            f"• *Tags:* `[PATTERN:{pattern_tag}]` `[STAGE:{stage}]`",
            f"• *Pattern:* `{pattern_tag}` · status `{pattern_state}`",
        ]
        if pattern_state in {"unknown", "unmatched", "uncertain"}:
            nearest = nearest_pattern or "none"
            distance = f" (distance {pattern_distance:.3f})" if pattern_distance is not None else ""
            lines.append(f"• *Nearest pattern:* `{nearest}`{distance}")
            if pattern_discrepancies:
                lines.append(f"• *Discrepancies:* {self._v3_discrepancy_text(pattern_discrepancies)}")
        elif pattern_quality:
            lines.append(f"• *Pattern quality:* `{pattern_quality}`")
        lines.extend([
            f"• *Stage:* `{stage}` · *Time:* {formatted_time}",
            f"• *{score_label}:* `{score_text}`",
            f"• *Score confirmation:* `{score_confirmation}`" if score_confirmation else "• *Score confirmation:* `reference threshold status only`",
            f"• *Evidence:* {evidence_label}",
            f"• *Conditions:* {self._v3_condition_summary(conditions)}",
            "",
            "📊 *Configured market conditions:*",
            f"  ▫️ Pump 24h: `+{pump_pct * 100:.1f}%`",
            f"  ▫️ Drop from 24h high: `{distance_from_high * 100:.1f}%`",
            f"  ▫️ Funding 30d percentile: `{funding_percentile * 100:.0f}%`",
            "",
            "🎯 *Observed compact plan (0, +3%, +6% | 20/30/50):*",
            f"  ▫️ *Entry 1 (20%):* `{price_str}`",
            f"  ▫️ *Entry 2 (30%):* `{e2_str}` (+3% from E1)",
            f"  ▫️ *Entry 3 (50%):* `{e3_str}` (+6% from E1)",
            f"  ▫️ *TP reference from initial Entry 1:* `-20%` (~`{tp_str}`; recompute after fills)",
            f"  ▫️ *Stop reference from initial Entry 1:* `+16%` (~`{sl_str}`; recompute after fills)",
            "  ▫️ *Observation horizon:* `48 hours`",
        ])
        if detail_url:
            lines.extend(["", f"[🔗 Open {symbol} research panel]({detail_url})"])
        lines.extend(["", "⚠️ _Independent V3 research observation; not financial advice._"])
        return "\n".join(lines)

    def send_v3_alert_with_result(
        self,
        symbol: str,
        entry_price: float,
        probability: float,
        pump_pct: float,
        distance_from_high: float,
        funding_percentile: float,
        feature_time: str,
        is_champion: bool = False,
        is_scout: bool = False,
        web_url: str | None = None,
        operating_mode: str = "research",
        shadow_chat_id: str | None = None,
        *,
        pattern_id: str | None = None,
        pattern_type: str | None = None,
        pattern_stage: str | None = None,
        pattern_status: str | None = None,
        nearest_pattern: str | None = None,
        pattern_distance: float | None = None,
        pattern_discrepancies: list[Any] | str | None = None,
        pattern_quality: str | None = None,
        conditions: dict[str, Any] | None = None,
        quality_validated: bool | None = None,
        evidence_kind: str | None = None,
        score_kind: str = "reference_model_score",
        score_confirmation: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Send a V3 signal and return Telegram metadata for durable dispatch."""
        target_chat = self._v3_target_chat(operating_mode, shadow_chat_id)
        if not target_chat:
            return None
        text = self._render_v3_alert(
            symbol=symbol,
            entry_price=entry_price,
            probability=probability,
            pump_pct=pump_pct,
            distance_from_high=distance_from_high,
            funding_percentile=funding_percentile,
            feature_time=feature_time,
            is_champion=is_champion,
            is_scout=is_scout,
            web_url=web_url,
            operating_mode=operating_mode,
            pattern_id=pattern_id,
            pattern_type=pattern_type,
            pattern_stage=pattern_stage,
            pattern_status=pattern_status,
            nearest_pattern=nearest_pattern,
            pattern_distance=pattern_distance,
            pattern_discrepancies=pattern_discrepancies,
            pattern_quality=pattern_quality,
            conditions=conditions,
            quality_validated=quality_validated,
            evidence_kind=evidence_kind,
            score_kind=score_kind,
            score_confirmation=score_confirmation,
        )
        return self.send_message_result(
            text,
            chat_id=target_chat,
            reply_to_message_id=reply_to_message_id,
        )

    def send_v3_alert(
        self,
        symbol: str,
        entry_price: float,
        probability: float,
        pump_pct: float,
        distance_from_high: float,
        funding_percentile: float,
        feature_time: str,
        is_champion: bool = False,
        is_scout: bool = False,
        web_url: str | None = None,
        operating_mode: str = "research",
        shadow_chat_id: str | None = None,
        **kwargs: Any,
    ) -> bool:
        """Send a dedicated V3 research signal while preserving bool callers."""
        return self.send_v3_alert_with_result(
            symbol=symbol,
            entry_price=entry_price,
            probability=probability,
            pump_pct=pump_pct,
            distance_from_high=distance_from_high,
            funding_percentile=funding_percentile,
            feature_time=feature_time,
            is_champion=is_champion,
            is_scout=is_scout,
            web_url=web_url,
            operating_mode=operating_mode,
            shadow_chat_id=shadow_chat_id,
            **kwargs,
        ) is not None

    def send_v3_outcome_update_with_result(
        self,
        *,
        symbol: str,
        outcome_type: str,
        status: str | None = None,
        event_time: str | None = None,
        feature_time: str | None = None,
        average_entry: float | None = None,
        exit_price: float | None = None,
        filled_legs: int | None = None,
        actual_fill: bool | None = None,
        price_only_post_stop: bool = False,
        stop_average_entry: float | None = None,
        frozen_average_entry: float | None = None,
        frozen_target_price: float | None = None,
        post_stop_return: float | None = None,
        original_horizon_hours: int = 48,
        horizon_time: str | None = None,
        target_time: str | None = None,
        operating_mode: str = "research",
        shadow_chat_id: str | None = None,
        chat_id: str | None = None,
        reply_to_message_id: int | None = None,
        web_url: str | None = None,
        pattern_id: str | None = None,
        pattern_type: str | None = None,
        pattern_stage: str | None = None,
        pattern_status: str | None = None,
        pattern_quality: str | None = None,
        evidence_kind: str | None = None,
    ) -> dict[str, Any] | None:
        """Send a threaded V3 lifecycle update.

        ``price_only_post_stop`` is deliberately rendered as a separate state:
        it is a frozen-average mark after a stop, not a second trade outcome.
        """
        target_chat = chat_id or self._v3_target_chat(operating_mode, shadow_chat_id)
        if not target_chat:
            return None
        raw_kind = str(outcome_type or status or "update").strip().lower()
        labels = {
            "entry": ("ENTRY FILLED", "ENTRY"),
            "entry_fill": ("ENTRY FILLED", "ENTRY"),
            "fill": ("ENTRY FILLED", "ENTRY"),
            "target": ("TP HIT", "OUTCOME"),
            "tp": ("TP HIT", "OUTCOME"),
            "stop": ("STOP HIT", "OUTCOME"),
            "stop_ambiguous": ("STOP HIT (ORDER AMBIGUOUS)", "OUTCOME"),
            "timeout": ("48H TIMEOUT", "OUTCOME"),
            "post_stop": ("POST-STOP PRICE-ONLY TRACK", "POST_STOP"),
            "post_stop_price_only": ("POST-STOP PRICE-ONLY TRACK", "POST_STOP"),
            "target_after_stop": ("POST-STOP PRICE-ONLY TRACK", "POST_STOP"),
        }
        title, stage = labels.get(raw_kind, (str(status or outcome_type).upper(), "OUTCOME"))
        if price_only_post_stop or raw_kind in {"post_stop", "post_stop_price_only", "target_after_stop"}:
            title, stage = "POST-STOP PRICE-ONLY TRACK", "POST_STOP"
        time_value = event_time or feature_time
        pattern_tag = pattern_type or pattern_id or "UNKNOWN"
        lines = [
            f"🔔 *V3 UPDATE — `{symbol}`*",
            f"• *Tags:* `[PATTERN:{pattern_tag}]` `[STAGE:{stage}]` `[EVENT:{raw_kind.upper()}]`",
            f"• *State:* *{title}*",
        ]
        if pattern_id or pattern_type or pattern_stage or pattern_status:
            lines.append(
                f"• *Pattern context:* `{pattern_type or pattern_id or 'UNKNOWN'}`"
                f" · stage `{str(pattern_stage or stage).upper()}`"
                f" · status `{pattern_status or 'unknown'}`"
            )
        if pattern_quality or evidence_kind:
            lines.append(f"• *Evidence:* `{pattern_quality or 'unconfirmed'}`{f' · {evidence_kind}' if evidence_kind else ''}")
        if time_value:
            lines.append(f"• *Time:* {_display_time(time_value, self._lang)}")
        if status and str(status).lower() not in raw_kind:
            lines.append(f"• *Runtime status:* `{status}`")
        if filled_legs is not None:
            lines.append(f"• *Filled legs:* `{int(filled_legs)}`")
        if average_entry is not None:
            lines.append(f"• *Average entry:* `{average_entry:g}`")
        if exit_price is not None:
            lines.append(f"• *Exit price:* `{exit_price:g}`")
        if price_only_post_stop or stage == "POST_STOP":
            frozen = (
                frozen_average_entry
                if frozen_average_entry is not None
                else stop_average_entry if stop_average_entry is not None else average_entry
            )
            lines.extend([
                "",
                "📌 *Price-only post-stop tracking (not an actual outcome)*",
                "  ▫️ No fills are added after the stop.",
                f"  ▫️ Frozen average at stop: `{frozen:g}`" if frozen is not None else "  ▫️ Frozen average at stop: `N/A`",
                f"  ▫️ Original horizon: `{int(original_horizon_hours)}h`",
            ])
            if frozen_target_price is not None:
                lines.append(f"  ▫️ Price-only target reference: `{frozen_target_price:g}`")
            if target_time:
                lines.append(f"  ▫️ Price target time: {_display_time(target_time, self._lang)}")
            if horizon_time:
                lines.append(f"  ▫️ Price-only horizon end: {_display_time(horizon_time, self._lang)}")
            if post_stop_return is not None:
                lines.append(f"  ▫️ Price-only return from frozen average: `{post_stop_return:+.1%}`")
        elif actual_fill is False:
            lines.append("• *Execution:* no actual fill recorded")
        else:
            lines.append("• *Execution:* actual simulated fill/outcome state")
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        if detail_url:
            lines.extend(["", f"[🔗 Open {symbol} research panel]({detail_url})"])
        lines.extend(["", "_Independent V3 research update; not financial advice._"])
        return self.send_message_result(
            "\n".join(lines),
            chat_id=target_chat,
            reply_to_message_id=reply_to_message_id,
        )

    def send_v3_outcome_update(self, **kwargs: Any) -> bool:
        """Bool-returning compatibility wrapper for a V3 lifecycle update."""
        return self.send_v3_outcome_update_with_result(**kwargs) is not None

    def send_cycle_digest(
        self,
        alerts: list[dict[str, Any]],
        btc_regime: str = "NEUTRAL",
        scan_time: str | None = None,
        operating_mode: str = "production",
    ) -> bool:
        """Send a consolidated cycle digest when multiple coins are detected."""
        alerts = [
            item for item in alerts
            if str(item.get("recommendation", "")).strip().upper()
            in {"SHORT_CANDIDATE", "HIGH_CONFIDENCE"}
        ]
        if not alerts:
            return False
        if len(alerts) == 1:
            a = alerts[0]
            return self.send_scored_alert(
                symbol=a["symbol"],
                total_score=a.get("total_score", 0.0),
                recommendation=a["recommendation"],
                pump_pct=a.get("pump_pct", 0.0),
                pump_days=a.get("pump_days", 0),
                top_signals=a.get("top_signals", []),
                btc_regime=btc_regime,
                btc_explanation=a.get("btc_explanation", ""),
                close_price=a.get("close_price"),
                feature_time=a.get("feature_time", scan_time or ""),
                invalidation_time=a.get("invalidation_time", ""),
                model_probability=a.get("model_probability"),
                operating_mode=operating_mode,
                web_url=a.get("web_url"),
            )

        mode_label = _mode_label(operating_mode, self._lang)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""
        formatted_time = _display_time(scan_time, self._lang) if scan_time else ""

        fired_alerts = alerts

        if self._lang == "en":
            lines = [
                f"📊 *RADAR CYCLE DIGEST (DISTRIBUTION SIGNALS)* ({len(alerts)} coins){mode_prefix}",
            ]
            if formatted_time:
                lines.append(f"• *Time:* {formatted_time}")
            lines.append(f"• *BTC Context:* {_btc_regime_label(btc_regime, 'en')}")
            lines.append(f"• *Summary:* ⚡ *{len(fired_alerts)} Distribution signals*")
            lines.append("")

            if fired_alerts:
                lines.append("⚡ *[HIGH CONFIDENCE SHORT SIGNALS]*")
                for i, a in enumerate(fired_alerts, 1):
                    sym = a["symbol"]
                    prob = a.get("model_probability")
                    score_val = a.get("total_score") or 0.0
                    c_stars, _, _ = _signal_grade(probability=prob, total_score=score_val, recommendation="HIGH_CONFIDENCE", lang="en")
                    prob_str = f"{prob:.1%}" if prob is not None else "N/A"
                    price = a.get("close_price") or 0.0
                    price_str = f"${price:,.4f}" if price > 0 else "N/A"
                    pump_pct = a.get("pump_pct", 0.0)
                    pump_days = a.get("pump_days", 0)
                    pump_str = f"+{pump_pct:.0%} ({pump_days}d)" if pump_days > 0 else f"+{pump_pct:.0%}"
                    top_sigs = a.get("top_signals", [])
                    sig_names = [_signal_label(s[0], "en") for s in top_sigs[:2]]
                    sig_str = ", ".join(sig_names) if sig_names else "Order flow distribution detected"
                    detail_url = a.get("web_url") or _coin_url(self._web_base_url, sym)

                    lines.append(f"{i}. ⚡ `{sym}` {c_stars} — Price: `{price_str}` (Pumped {pump_str})")
                    lines.append(f"   • Score: *{score_val:.0f}/100* | Short Prob: *{prob_str}*")
                    lines.append(f"   • Reasons: {sig_str}")
                    if detail_url:
                        lines.append(f"   • [🔗 View Analysis]({detail_url})")
                    lines.append("")

            lines.extend(["", "_Reference report from Dao Vang AI; analyze carefully._"])
        else:
            lines = [
                f"📊 *TỔNG HỢP TÍN HIỆU PHÂN PHỐI CHU KỲ* ({len(alerts)} coin){mode_prefix}",
            ]
            if formatted_time:
                lines.append(f"• *Thời điểm:* {formatted_time}")
            lines.append(f"• *Bối cảnh BTC:* {_btc_regime_label(btc_regime, 'vi')}")
            lines.append(f"• *Tổng quan:* ⚡ *{len(fired_alerts)} Tín hiệu phân phối*")
            lines.append("")

            if fired_alerts:
                lines.append("⚡ *[DANH SÁCH TÍN HIỆU SHORT MẠNH]* 🚨")
                for i, a in enumerate(fired_alerts, 1):
                    sym = a["symbol"]
                    prob = a.get("model_probability")
                    score_val = a.get("total_score") or 0.0
                    c_stars, _, _ = _signal_grade(probability=prob, total_score=score_val, recommendation="HIGH_CONFIDENCE", lang="vi")
                    prob_str = f"{prob:.1%}" if prob is not None else "N/A"
                    price = a.get("close_price") or 0.0
                    price_str = f"${price:,.4f}" if price > 0 else "N/A"
                    pump_pct = a.get("pump_pct", 0.0)
                    pump_days = a.get("pump_days", 0)
                    pump_str = f"+{pump_pct:.0%} ({pump_days} ngày)" if pump_days > 0 else f"+{pump_pct:.0%}"
                    top_sigs = a.get("top_signals", [])
                    sig_names = [_signal_label(s[0], "vi") for s in top_sigs[:2]]
                    sig_str = ", ".join(sig_names) if sig_names else "Xác nhận dấu hiệu xả 5m"
                    detail_url = a.get("web_url") or _coin_url(self._web_base_url, sym)

                    lines.append(f"{i}. ⚡ `{sym}` {c_stars} — Giá: `{price_str}` (Đã tăng {pump_str})")
                    lines.append(f"   • Điểm phân phối: *{score_val:.0f}/100* | Xác suất Short: *{prob_str}*")
                    lines.append(f"   • Lý do: {sig_str}")
                    if detail_url:
                        lines.append(f"   • [🔗 Xem phân tích {sym}]({detail_url})")
                    lines.append("")

            lines.extend(["", "_Báo cáo tự động từ Đảo Vàng AI — Phục vụ mục đích tham khảo & phân tích._"])
        utm_line = _ecosystem_utm_footer(self._lang, "radar_digest")
        if utm_line:
            lines.append(utm_line)
        text = "\n".join(lines)
        return self.send_message(text)

    def send_two_tier_alert(
        self,
        symbol: str,
        stage: str,
        total_score: float,
        htf_score: float,
        ltf_score: float,
        pump_pct: float,
        pump_days: int,
        close_price: float | None,
        feature_time: str,
        peak_wick_price: float | None = None,
        web_url: str | None = None,
        operating_mode: str = "production",
    ) -> bool:
        """Send only a confirmed FIRED signal; ARMED remains an in-app watch."""
        if str(stage).strip().upper() != "FIRED":
            return False
        price = close_price or 0.0
        price_str = f"${price:,.4f}" if price > 0 else "N/A"
        mode_label = _mode_label(operating_mode, self._lang)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        if self._lang == "en":
            lines = [
                f"⚡ *[DISTRIBUTION SIGNAL — FIRED]* `{symbol}` 🚨{mode_prefix}",
                f"• *Market Price:* `{price_str}` | *Pump Amplitude:* `+{pump_pct:.0%}` ({pump_days}d)",
                f"• *2-Tier Confluence Score:* *{total_score:.0f}/100* (HTF: {htf_score:.0f} | LTF: {ltf_score:.0f})",
                "• *Why Short:* Both HTF pump climax and 5m order flow sell pressure have confirmed.",
            ]
            if detail_url:
                lines.append(f"[🔗 Open {symbol} Analysis Dashboard]({detail_url})")
        else:
            lines = [
                f"⚡ *[CẢNH BÁO TÍN HIỆU SHORT — PHÂN PHỐI ĐỈNH]* `{symbol}` 🚨{mode_prefix}",
                f"• *Giá thị trường:* `{price_str}` | *Biên độ bơm:* `+{pump_pct:.0%}` ({pump_days} ngày)",
                f"• *Điểm hợp lưu 2 Tầng:* *{total_score:.0f}/100* (Khung lớn: {htf_score:.0f} | Khung 5m: {ltf_score:.0f})",
                "• *Lý do nên Short:* Hợp lưu đồng thời giữa đỉnh bơm khung lớn và áp lực xả chủ động khung 5m.",
            ]
            if detail_url:
                lines.append(f"[🔗 Mở Biểu Đồ & Phân Tích {symbol}]({detail_url})")

        lines.extend(["", "_Báo cáo phân tích xác suất từ Đảo Vàng AI._"])
        utm_line = _ecosystem_utm_footer(self._lang, "two_tier_fired")
        if utm_line:
            lines.append(utm_line)
        text = "\n".join(lines)
        return self.send_message(text)

    def send_test(self) -> bool:
        """Send a test message to verify configuration."""
        if self._lang == "en":
            return self.send_message(
                "🧪 *DAO VANG — Test Alert*\n\n"
                "Telegram bot connected successfully. "
                "You will receive alerts when the scanner detects Distribution signals."
            )
        return self.send_message(
            "🧪 *Đảo Vàng — Test*\n\n"
            "Telegram bot đã kết nối thành công. "
            "Bạn sẽ nhận alert khi scanner phát hiện Distribution."
        )

