#!/usr/bin/env python3
"""
NexusAGY Computer Engine - Structured High-Visibility Logger.
Persists execution logs to ~/.nexusagy/computer.log with rotation and timing telemetry.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOG_DIR = Path.home() / ".nexusagy"
LOG_FILE = LOG_DIR / "computer.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("nexusagy.computer")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Prevent duplicate handlers on reload
    if not logger.handlers:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _logger = logger
    return _logger


def log_action(
    action: str,
    method: str,
    target: str | int | None = None,
    duration_ms: float = 0.0,
    status: str = "SUCCESS",
    details: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Logs a computer action with structured metadata and timing."""
    logger = get_logger()
    details_str = ""
    if details:
        # Sanitize details (truncate long texts)
        clean_details = {}
        for k, v in details.items():
            if isinstance(v, str) and len(v) > 80:
                clean_details[k] = f"{v[:77]}..."
            else:
                clean_details[k] = v
        details_str = f" | {clean_details}"

    msg = f"[{action.upper()}] method={method} target={target} took={duration_ms:.1f}ms status={status}{details_str}"
    if error:
        msg += f" | ERROR: {error}"
        logger.error(msg)
    else:
        logger.info(msg)
