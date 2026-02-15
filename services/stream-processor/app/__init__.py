"""
FinStream Stream Processor Application.
"""

from app.aggregator import CandleAggregator
from app.repository import TradeRepository

__version__ = "0.1.0"
__all__ = ["CandleAggregator", "TradeRepository"]
