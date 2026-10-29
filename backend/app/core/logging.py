"""Structured (JSON) logging. ``log_event`` is the single entry point so Sentry / OpenTelemetry hooks can
be attached in one place."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_logger = logging.getLogger("sharetaxi")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": datetime.now(timezone.utc).isoformat(), "level": record.levelname.lower(),
            "logger": record.name, "msg": record.getMessage(),
        }
        base.update(getattr(record, "fields", {}))
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """e.g. log_event("match.created", match_id=3, score=91.3)"""
    _logger.log(level, event, extra={"fields": {"event": event, **fields}})
