"""
MEV Bot - Maximum Extractable Value Bot
========================================

A sophisticated MEV bot for detecting and exploiting profitable opportunities
on decentralized exchanges including arbitrage, sandwich attacks, and front-running.

Author: Cezmi Bot Team
License: MIT
"""

__version__ = "1.0.0"
__author__ = "Cezmi Bot Team"

from .mev_bot import MEVBot
from .config import Config

__all__ = ["MEVBot", "Config"]
