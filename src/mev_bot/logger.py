"""Logging utilities."""

from __future__ import annotations

import logging
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    """Configure Rich logging once and reuse the root logger."""

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(console=Console(), rich_tracebacks=True)],
    )
    return logging.getLogger("mev_bot")


LOGGER: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Return a cached logger instance."""

    global LOGGER  # noqa: PLW0603 - intentional module-level cache
    if LOGGER is None:
        LOGGER = setup_logger()
    return LOGGER
