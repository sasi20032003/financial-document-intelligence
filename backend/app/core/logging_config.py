"""Central logging configuration."""

from __future__ import annotations

import logging
from logging.config import dictConfig

from backend.app.core.config import get_settings


def configure_logging() -> None:
    level = get_settings().log_level.upper()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s"
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {"uvicorn.access": {"level": level}},
        }
    )
    logging.getLogger(__name__).info("Logging configured", extra={"level": level})
