"""
src/utils.py
Shared helpers: logging setup and a cached SQLAlchemy engine.
Import get_logger()/get_engine() instead of re-creating these in every module.
"""

import logging
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.config import DATABASE_URL, LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """Consistent logger config across the whole pipeline."""
    logger = logging.getLogger(name)
    if not logger.handlers:  # avoid duplicate handlers on re-import
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(LOG_LEVEL)
    return logger


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """
    Returns a single cached SQLAlchemy engine for the whole process.
    Cached so extract/transform/load/main.py all share one connection pool
    instead of each opening its own.
    """
    return create_engine(DATABASE_URL, pool_pre_ping=True)