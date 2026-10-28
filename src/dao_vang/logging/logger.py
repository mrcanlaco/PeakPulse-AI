import logging
import sys
from datetime import datetime
from typing import Any

try:
    import structlog
    from structlog.typing import EventDict
except ImportError:  # pragma: no cover - stdlib fallback when structlog is absent
    structlog = None  # type: ignore[assignment]
    EventDict = dict[str, Any]  # type: ignore[misc]

from dao_vang.domain.time import SYSTEM_TIMEZONE

SECRET_KEYS = {"api_key", "secret", "password", "token"}

# Windows consoles default to a legacy codepage (e.g. cp1252) that cannot
# encode Vietnamese text or emoji used in log messages, which raises
# OSError/UnicodeEncodeError and crashes the process. Force UTF-8 on
# stdout/stderr at import time (before any logger — structlog's default
# PrintLogger writes straight to sys.stdout without going through
# configure_logging) so logging never takes the app down.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            pass


def redact_secrets(
    logger: logging.Logger, name: str, event_dict: EventDict
) -> EventDict:
    """Redact secret fields from the event dict."""
    for key in list(event_dict.keys()):
        if any(secret in key.lower() for secret in SECRET_KEYS):
            event_dict[key] = "***REDACTED***"
    return event_dict


def system_time_stamper(
    logger: logging.Logger, name: str, event_dict: EventDict
) -> EventDict:
    """Stamp logs in the application's fixed Vietnam timezone."""
    event_dict["timestamp"] = datetime.now(SYSTEM_TIMEZONE).isoformat()
    return event_dict


def configure_logging(json_format: bool = True, log_level: str = "INFO") -> None:
    """Configure structured logging for the application."""
    shared_processors: list[Any] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        system_time_stamper,
        redact_secrets,
        structlog.contextvars.merge_contextvars,
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]

    if json_format:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))


class _StdlibBoundLogger:
    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)

    def _fmt(self, event: str, kwargs: dict[str, Any]) -> str:
        if not kwargs:
            return str(event)
        kv = " ".join(
            f"{k}={'***REDACTED***' if any(s in k.lower() for s in SECRET_KEYS) else repr(v)}"
            for k, v in kwargs.items()
        )
        return f"{event:<30} {kv}"

    def info(self, event: str, **kwargs: Any) -> None:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [info     ] {self._fmt(event, kwargs)}", flush=True)

    def warning(self, event: str, **kwargs: Any) -> None:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [warning  ] {self._fmt(event, kwargs)}", flush=True)

    def error(self, event: str, **kwargs: Any) -> None:
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [error    ] {self._fmt(event, kwargs)}", flush=True)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._log.debug(self._fmt(event, kwargs))


def get_logger(name: str) -> Any:
    if structlog is None:
        return _StdlibBoundLogger(name)
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """Bind variables to the logging context."""
    if structlog is not None:
        structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear the logging context."""
    if structlog is not None:
        structlog.contextvars.clear_contextvars()
