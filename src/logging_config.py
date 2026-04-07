"""Logging configuration for QuickPulse V2.

Supports both plain-text and JSON structured log formats.
JSON mode includes a correlation/request ID for request tracing.
"""

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Context variable to store the current request's correlation ID.
# Middleware sets this per-request; log formatters read it.
request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> Optional[str]:
    """Return the current request correlation ID, if set."""
    return request_id_ctx.get()


def set_request_id(rid: Optional[str] = None) -> str:
    """Set (or generate) a request correlation ID for the current context.

    Returns the ID that was set.
    """
    if rid is None:
        rid = uuid.uuid4().hex
    request_id_ctx.set(rid)
    return rid


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects.

    Fields: timestamp, level, logger, message, request_id (if set).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = request_id_ctx.get()
        if rid is not None:
            log_entry["request_id"] = rid
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    json_format: bool = False,
) -> logging.Logger:
    """Configure application logging.

    Args:
        log_level: Logging level name (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path to write logs to.
        json_format: If True, use JSON structured format instead of plain text.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=handlers,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return logging.getLogger("quickpulse")
