"""High-level package for ERC-20 MEV arbitrage bot."""

from .config import BotConfig
from .main import run_bot

__all__ = ["BotConfig", "run_bot"]
