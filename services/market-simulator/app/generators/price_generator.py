"""
Price generators using Geometric Brownian Motion (GBM) for realistic stock simulation.

Geometric Brownian Motion is the standard model for stock price dynamics:
    dS = μ*S*dt + σ*S*dW

Where:
    S = Stock price
    μ = Drift (expected return)
    σ = Volatility
    W = Wiener process (Brownian motion)
"""

import math
import random
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict


@dataclass
class SymbolConfig:
    """Configuration for a tradable symbol."""
    
    symbol: str
    initial_price: float
    volatility: float  # Annual volatility (e.g., 0.20 = 20%)
    drift: float = 0.0001  # Daily drift
    tick_size: float = 0.01
    lot_size: int = 100
    exchange: str = "NASDAQ"
    
    # Order book depth
    bid_levels: int = 5
    ask_levels: int = 5
    level_depth: int = 1000  # shares per level


# Default stock configurations with realistic parameters
DEFAULT_SYMBOLS: Dict[str, SymbolConfig] = {
    "AAPL": SymbolConfig(
        symbol="AAPL",
        initial_price=185.00,
        volatility=0.25,
        exchange="NASDAQ",
    ),
    "GOOGL": SymbolConfig(
        symbol="GOOGL",
        initial_price=140.00,
        volatility=0.28,
        exchange="NASDAQ",
    ),
    "MSFT": SymbolConfig(
        symbol="MSFT",
        initial_price=380.00,
        volatility=0.22,
        exchange="NASDAQ",
    ),
    "AMZN": SymbolConfig(
        symbol="AMZN",
        initial_price=170.00,
        volatility=0.30,
        exchange="NASDAQ",
    ),
    "META": SymbolConfig(
        symbol="META",
        initial_price=480.00,
        volatility=0.35,
        exchange="NASDAQ",
    ),
    "NVDA": SymbolConfig(
        symbol="NVDA",
        initial_price=720.00,
        volatility=0.45,
        exchange="NASDAQ",
    ),
    "TSLA": SymbolConfig(
        symbol="TSLA",
        initial_price=200.00,
        volatility=0.50,
        exchange="NASDAQ",
    ),
    "JPM": SymbolConfig(
        symbol="JPM",
        initial_price=185.00,
        volatility=0.18,
        exchange="NYSE",
    ),
    "V": SymbolConfig(
        symbol="V",
        initial_price=275.00,
        volatility=0.20,
        exchange="NYSE",
    ),
    "JNJ": SymbolConfig(
        symbol="JNJ",
        initial_price=160.00,
        volatility=0.15,
        exchange="NYSE",
    ),
}


@dataclass
class PriceState:
    """Current state of a symbol's price."""
    
    symbol: str
    price: float
    bid_price: float
    ask_price: float
    spread: float
    
    # Order book levels
    bid_sizes: list[int] = field(default_factory=list)
    ask_sizes: list[int] = field(default_factory=list)
    
    # Statistics
    high: float = 0.0
    low: float = float("inf")
    volume: int = 0
    trade_count: int = 0
    
    def __post_init__(self) -> None:
        if self.high == 0.0:
            self.high = self.price
        if self.low == float("inf"):
            self.low = self.price


class GBMPriceGenerator:
    """
    Generates realistic stock prices using Geometric Brownian Motion.
    
    This simulates price movements with:
    - Continuous price evolution
    - Mean-reverting volatility
    - Realistic bid-ask spreads
    - Volume patterns
    """
    
    def __init__(
        self,
        config: SymbolConfig,
        time_step: float = 1.0 / (252 * 6.5 * 60 * 60),  # 1 second in trading year
    ) -> None:
        """
        Initialize the price generator.
        
        Args:
            config: Symbol configuration
            time_step: Time step size (default: 1 second of trading time)
        """
        self.config = config
        self.time_step = time_step
        
        # Initialize state
        self.state = PriceState(
            symbol=config.symbol,
            price=config.initial_price,
            bid_price=config.initial_price - config.tick_size,
            ask_price=config.initial_price + config.tick_size,
            spread=2 * config.tick_size,
        )
        
        # Initialize order book
        self._init_order_book()
        
        # Volatility state for mean reversion
        self._current_volatility = config.volatility
        self._volatility_mean = config.volatility
        self._volatility_reversion_speed = 0.1
    
    def _init_order_book(self) -> None:
        """Initialize the order book with random depths."""
        base_size = self.config.level_depth
        
        self.state.bid_sizes = [
            random.randint(int(base_size * 0.5), int(base_size * 1.5))
            for _ in range(self.config.bid_levels)
        ]
        self.state.ask_sizes = [
            random.randint(int(base_size * 0.5), int(base_size * 1.5))
            for _ in range(self.config.ask_levels)
        ]
    
    def step(self) -> PriceState:
        """
        Generate the next price using GBM.
        
        Returns:
            Updated PriceState
        """
        # Update volatility with mean reversion
        self._update_volatility()
        
        # Generate GBM price movement
        drift = self.config.drift * self.time_step
        volatility = self._current_volatility * math.sqrt(self.time_step)
        
        # Wiener process increment
        dW = random.gauss(0, 1)
        
        # GBM formula: S(t+dt) = S(t) * exp((μ - σ²/2)dt + σdW)
        exponent = (drift - 0.5 * volatility ** 2) + volatility * dW
        price_multiplier = math.exp(exponent)
        
        # Update price
        new_price = self.state.price * price_multiplier
        
        # Round to tick size
        new_price = self._round_to_tick(new_price)
        
        # Ensure price is positive
        new_price = max(new_price, self.config.tick_size)
        
        # Update spread (varies with volatility)
        self._update_spread(new_price)
        
        # Update state
        self.state.price = new_price
        self.state.high = max(self.state.high, new_price)
        self.state.low = min(self.state.low, new_price)
        
        # Update order book sizes with some randomness
        self._update_order_book()
        
        return self.state
    
    def _update_volatility(self) -> None:
        """Update volatility with mean reversion (Ornstein-Uhlenbeck process)."""
        # Mean-reverting volatility
        vol_innovation = random.gauss(0, 0.001)
        self._current_volatility = (
            self._current_volatility
            + self._volatility_reversion_speed * (self._volatility_mean - self._current_volatility)
            + vol_innovation
        )
        # Bound volatility
        self._current_volatility = max(0.05, min(1.0, self._current_volatility))
    
    def _update_spread(self, price: float) -> None:
        """Update bid-ask spread based on price and volatility."""
        # Base spread proportional to tick size
        base_spread = self.config.tick_size * 2
        
        # Add volatility component
        vol_spread = price * self._current_volatility * 0.0001
        
        # Add random component
        random_spread = random.uniform(0, self.config.tick_size)
        
        total_spread = base_spread + vol_spread + random_spread
        half_spread = total_spread / 2
        
        self.state.bid_price = self._round_to_tick(price - half_spread)
        self.state.ask_price = self._round_to_tick(price + half_spread)
        self.state.spread = self.state.ask_price - self.state.bid_price
        
        # Ensure spread is at least one tick
        if self.state.spread < self.config.tick_size:
            self.state.ask_price = self.state.bid_price + self.config.tick_size
            self.state.spread = self.config.tick_size
    
    def _update_order_book(self) -> None:
        """Update order book sizes with random changes."""
        for i in range(len(self.state.bid_sizes)):
            change = random.randint(-100, 100)
            self.state.bid_sizes[i] = max(100, self.state.bid_sizes[i] + change)
        
        for i in range(len(self.state.ask_sizes)):
            change = random.randint(-100, 100)
            self.state.ask_sizes[i] = max(100, self.state.ask_sizes[i] + change)
    
    def _round_to_tick(self, price: float) -> float:
        """Round price to nearest tick size."""
        tick = self.config.tick_size
        return round(price / tick) * tick
    
    def get_price_decimal(self) -> Decimal:
        """Get current price as Decimal for precision."""
        return Decimal(str(self.state.price)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    
    def get_bid_decimal(self) -> Decimal:
        """Get current bid price as Decimal."""
        return Decimal(str(self.state.bid_price)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    
    def get_ask_decimal(self) -> Decimal:
        """Get current ask price as Decimal."""
        return Decimal(str(self.state.ask_price)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    
    def reset_daily_stats(self) -> None:
        """Reset daily statistics (high, low, volume)."""
        self.state.high = self.state.price
        self.state.low = self.state.price
        self.state.volume = 0
        self.state.trade_count = 0


class MarketSimulator:
    """
    Manages multiple price generators for a simulated market.
    """
    
    def __init__(self, symbols: list[str] | None = None) -> None:
        """
        Initialize market simulator.
        
        Args:
            symbols: List of symbols to simulate (uses defaults if None)
        """
        self.generators: Dict[str, GBMPriceGenerator] = {}
        
        # Initialize generators for requested symbols
        if symbols:
            for symbol in symbols:
                config = DEFAULT_SYMBOLS.get(
                    symbol,
                    SymbolConfig(symbol=symbol, initial_price=100.0, volatility=0.25)
                )
                self.generators[symbol] = GBMPriceGenerator(config)
        else:
            # Use all default symbols
            for symbol, config in DEFAULT_SYMBOLS.items():
                self.generators[symbol] = GBMPriceGenerator(config)
    
    def step_all(self) -> Dict[str, PriceState]:
        """
        Advance all price generators by one step.
        
        Returns:
            Dict mapping symbol to updated PriceState
        """
        return {
            symbol: generator.step()
            for symbol, generator in self.generators.items()
        }
    
    def get_state(self, symbol: str) -> PriceState | None:
        """Get current state for a symbol."""
        generator = self.generators.get(symbol)
        if generator:
            return generator.state
        return None
    
    def reset_daily_stats(self) -> None:
        """Reset daily stats for all symbols."""
        for generator in self.generators.values():
            generator.reset_daily_stats()
