"""
Trade and Quote generator that produces events from price states.
"""

import random
from datetime import datetime
from decimal import Decimal
from typing import Iterator

from finstream_common.models import Trade, Quote, OrderSide

from app.generators.price_generator import MarketSimulator, PriceState, DEFAULT_SYMBOLS


class TradeGenerator:
    """
    Generates Trade and Quote events based on price movements.
    
    Features:
    - Realistic trade sizes following power-law distribution
    - Poisson-distributed trade arrival times
    - Correlated buy/sell pressure
    - Volume patterns that vary by time of day
    """
    
    def __init__(
        self,
        market: MarketSimulator,
        trades_per_second: float = 50.0,  # Average trades per second total
    ) -> None:
        """
        Initialize trade generator.
        
        Args:
            market: MarketSimulator instance for price data
            trades_per_second: Target number of trades per second
        """
        self.market = market
        self.trades_per_second = trades_per_second
        
        # Trade size distribution parameters (power law)
        self._size_alpha = 1.5  # Shape parameter
        self._min_size = 1
        self._max_size = 10000
        
        # Buy/sell pressure (0.5 = neutral)
        self._buy_pressure: dict[str, float] = {
            symbol: 0.5 for symbol in market.generators.keys()
        }
        
        # Volume multipliers per symbol (some stocks trade more)
        self._volume_weights: dict[str, float] = {
            "AAPL": 2.0,
            "NVDA": 1.8,
            "TSLA": 1.5,
            "MSFT": 1.3,
            "AMZN": 1.2,
            "GOOGL": 1.1,
            "META": 1.0,
            "JPM": 0.8,
            "V": 0.7,
            "JNJ": 0.5,
        }
    
    def generate_trade(self, symbol: str, state: PriceState) -> Trade:
        """
        Generate a single trade for a symbol.
        
        Args:
            symbol: Trading symbol
            state: Current price state
            
        Returns:
            Trade event
        """
        # Determine side based on buy pressure
        buy_pressure = self._buy_pressure.get(symbol, 0.5)
        side = OrderSide.BUY if random.random() < buy_pressure else OrderSide.SELL
        
        # Generate trade size (power law distribution)
        quantity = self._generate_trade_size()
        
        # Price is at bid for sells, ask for buys, with some variance
        if side == OrderSide.BUY:
            base_price = state.ask_price
        else:
            base_price = state.bid_price
        
        # Add small random variance
        price_variance = random.gauss(0, state.spread * 0.1)
        price = base_price + price_variance
        price = max(0.01, price)  # Ensure positive
        
        # Update state
        state.volume += quantity
        state.trade_count += 1
        
        # Update buy pressure (mean reverting)
        self._update_buy_pressure(symbol, side)
        
        # Get exchange from config
        config = DEFAULT_SYMBOLS.get(symbol)
        exchange = config.exchange if config else "NASDAQ"
        
        return Trade(
            symbol=symbol,
            price=Decimal(str(round(price, 2))),
            quantity=quantity,
            side=side,
            exchange=exchange,
            timestamp=datetime.utcnow(),
        )
    
    def generate_quote(self, symbol: str, state: PriceState) -> Quote:
        """
        Generate a quote for a symbol.
        
        Args:
            symbol: Trading symbol
            state: Current price state
            
        Returns:
            Quote event
        """
        config = DEFAULT_SYMBOLS.get(symbol)
        exchange = config.exchange if config else "NASDAQ"
        
        return Quote(
            symbol=symbol,
            bid_price=Decimal(str(round(state.bid_price, 2))),
            bid_size=state.bid_sizes[0] if state.bid_sizes else 100,
            ask_price=Decimal(str(round(state.ask_price, 2))),
            ask_size=state.ask_sizes[0] if state.ask_sizes else 100,
            exchange=exchange,
            timestamp=datetime.utcnow(),
        )
    
    def generate_batch(
        self,
        batch_size: int = 100,
    ) -> tuple[list[Trade], list[Quote]]:
        """
        Generate a batch of trades and quotes.
        
        Args:
            batch_size: Number of trades to generate
            
        Returns:
            Tuple of (trades list, quotes list)
        """
        trades: list[Trade] = []
        quotes: list[Quote] = []
        
        # Step all prices forward
        states = self.market.step_all()
        
        # Generate quotes for all symbols
        for symbol, state in states.items():
            quotes.append(self.generate_quote(symbol, state))
        
        # Distribute trades across symbols based on volume weights
        total_weight = sum(
            self._volume_weights.get(s, 1.0) for s in states.keys()
        )
        
        for symbol, state in states.items():
            weight = self._volume_weights.get(symbol, 1.0)
            symbol_trades = int(batch_size * weight / total_weight) or 1
            
            for _ in range(symbol_trades):
                trade = self.generate_trade(symbol, state)
                trades.append(trade)
        
        return trades, quotes
    
    def stream_trades(self) -> Iterator[Trade]:
        """
        Infinite iterator yielding trades.
        
        Yields:
            Trade events
        """
        while True:
            trades, _ = self.generate_batch(batch_size=10)
            for trade in trades:
                yield trade
    
    def stream_quotes(self) -> Iterator[Quote]:
        """
        Infinite iterator yielding quotes.
        
        Yields:
            Quote events
        """
        while True:
            _, quotes = self.generate_batch(batch_size=10)
            for quote in quotes:
                yield quote
    
    def _generate_trade_size(self) -> int:
        """
        Generate trade size using power law distribution.
        
        Returns:
            Trade size in shares
        """
        # Power law: P(x) ~ x^(-alpha)
        # Using inverse transform sampling
        u = random.random()
        
        # Pareto distribution
        x_min = self._min_size
        x_max = self._max_size
        alpha = self._size_alpha
        
        # Bounded Pareto
        size = x_min * (1 - u + u * (x_min / x_max) ** alpha) ** (-1 / alpha)
        
        # Round to lot size (typically 100 shares, but allow odd lots)
        if size > 100:
            size = round(size / 100) * 100
        else:
            size = max(1, round(size))
        
        return int(min(size, x_max))
    
    def _update_buy_pressure(self, symbol: str, last_side: OrderSide) -> None:
        """
        Update buy pressure with mean reversion.
        
        Args:
            symbol: Trading symbol
            last_side: Side of last trade
        """
        current = self._buy_pressure.get(symbol, 0.5)
        
        # Mean reversion toward 0.5
        reversion = 0.01 * (0.5 - current)
        
        # Small random walk
        random_walk = random.gauss(0, 0.02)
        
        # Momentum from last trade
        momentum = 0.01 if last_side == OrderSide.BUY else -0.01
        
        new_pressure = current + reversion + random_walk + momentum
        
        # Bound between 0.3 and 0.7
        self._buy_pressure[symbol] = max(0.3, min(0.7, new_pressure))
