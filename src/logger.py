"""logger.py — Centralised logging via loguru."""

import os
from loguru import logger as log

import config

os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

log.add(
    config.LOG_FILE,
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
)

__all__ = ["log"]
