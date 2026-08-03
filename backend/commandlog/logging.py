import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extra_data = getattr(record, "data", None)

        if isinstance(extra_data, dict):
            payload.update(extra_data)

        return json.dumps(payload, default=str)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    logger.addHandler(handler)
    logger.setLevel(
        os.getenv("LOG_LEVEL", "INFO").upper()
    )
    logger.propagate = False

    return logger