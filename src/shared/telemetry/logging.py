"""Logging configuration for Timeline application"""
import logging
import sys

from src.infrastructure.config.settings import get_settings

settings = get_settings()


def setup_logging():
    """Configure application-wide logging"""
    log_level = logging.DEBUG if settings.debug else logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_logger(name: str) -> logging.Logger:
    """Get logger for module"""
    return logging.getLogger(name)
