"""
Alert Detector - Anomaly Detection for Market Data

Implements multiple detection strategies:
- Z-Score based price spike detection
- Volume anomaly detection
- Spread anomaly detection
- Rolling statistics with exponential moving averages
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict

import numpy as np

from finstream_common.models import Trade, Quote, Alert, AlertType, AlertSeverity
from finstream_common.logging import get_logger
from finstream_common.metrics import get_metrics

logger = get_logger(__name__)
metrics = get_metrics()


@dataclass
class SymbolStats:
    """Rolling statistics for a symbol."""
    
    # Price statistics
    prices: deque = field(default_factory=lambda: deque(maxlen=1000))
    price_ema: float = 0.0
    price_ema_variance: float = 0.0
    
    # Volume statistics
    volumes: deque = field(default_factory=lambda: deque(maxlen=1000))
    volume_ema: float = 0.0
    
    # Spread statistics
    spreads: deque = field(default_factory=lambda: deque(maxlen=500))
    spread_ema: float = 0.0
    
    # Tracking
    last_price: float = 0.0
    last_volume: int = 0
    last_update: datetime | None = None
    trade_count: int = 0
    
    # EMA smoothing factor
    alpha: float = 0.01  # Slow EMA for baseline


class AlertDetector:
    """
    Detects market anomalies and generates alerts.
    
    Detection strategies:
    1. Price Spike: Z-score > threshold (sudden price movements)
    2. Volume Anomaly: Volume >> EMA (unusual trading activity)
    3. Spread Anomaly: Spread >> normal (liquidity concerns)
    """
    
    def __init__(
        self,
        price_spike_threshold: float = 3.0,  # Z-score threshold
        volume_anomaly_multiplier: float = 5.0,  # X times normal volume
        spread_anomaly_multiplier: float = 3.0,  # X times normal spread
        min_samples: int = 100,  # Minimum samples before alerting
    ) -> None:
        """
        Initialize detector.
        
        Args:
            price_spike_threshold: Z-score threshold for price spikes
            volume_anomaly_multiplier: Multiplier for volume anomalies
            spread_anomaly_multiplier: Multiplier for spread anomalies
            min_samples: Minimum samples before generating alerts
        """
        self.price_spike_threshold = price_spike_threshold
        self.volume_anomaly_multiplier = volume_anomaly_multiplier
        self.spread_anomaly_multiplier = spread_anomaly_multiplier
        self.min_samples = min_samples
        
        # Per-symbol statistics
        self._stats: Dict[str, SymbolStats] = {}
        
        # Alert cooldown (prevent alert flooding)
        self._last_alert: Dict[str, Dict[AlertType, datetime]] = {}
        self._cooldown_seconds = 60  # Minimum time between same alert type
    
    def _get_stats(self, symbol: str) -> SymbolStats:
        """Get or create stats for a symbol."""
        if symbol not in self._stats:
            self._stats[symbol] = SymbolStats()
        return self._stats[symbol]
    
    def _can_alert(self, symbol: str, alert_type: AlertType) -> bool:
        """Check if we can generate an alert (cooldown)."""
        if symbol not in self._last_alert:
            return True
        
        if alert_type not in self._last_alert[symbol]:
            return True
        
        last_time = self._last_alert[symbol][alert_type]
        elapsed = (datetime.utcnow() - last_time).total_seconds()
        return elapsed >= self._cooldown_seconds
    
    def _record_alert(self, symbol: str, alert_type: AlertType) -> None:
        """Record that an alert was generated."""
        if symbol not in self._last_alert:
            self._last_alert[symbol] = {}
        self._last_alert[symbol][alert_type] = datetime.utcnow()
    
    def process_trade(self, trade: Trade) -> Alert | None:
        """
        Process a trade and detect anomalies.
        
        Args:
            trade: Trade to analyze
            
        Returns:
            Alert if anomaly detected, None otherwise
        """
        stats = self._get_stats(trade.symbol)
        price = float(trade.price)
        volume = trade.quantity
        
        alert = None
        
        # Update statistics
        stats.prices.append(price)
        stats.volumes.append(volume)
        stats.trade_count += 1
        
        # Update EMAs
        if stats.price_ema == 0:
            stats.price_ema = price
            stats.volume_ema = volume
        else:
            # Exponential moving average
            stats.price_ema = stats.alpha * price + (1 - stats.alpha) * stats.price_ema
            stats.volume_ema = stats.alpha * volume + (1 - stats.alpha) * stats.volume_ema
            
            # Update EMA variance for price
            diff_sq = (price - stats.price_ema) ** 2
            stats.price_ema_variance = (
                stats.alpha * diff_sq + (1 - stats.alpha) * stats.price_ema_variance
            )
        
        # Only alert after collecting enough samples
        if stats.trade_count >= self.min_samples:
            # Check for price spike
            alert = self._check_price_spike(trade, stats, price)
            
            # Check for volume anomaly if no price alert
            if alert is None:
                alert = self._check_volume_anomaly(trade, stats, volume)
        
        # Update last values
        stats.last_price = price
        stats.last_volume = volume
        stats.last_update = trade.timestamp
        
        return alert
    
    def process_quote(self, quote: Quote) -> Alert | None:
        """
        Process a quote and detect spread anomalies.
        
        Args:
            quote: Quote to analyze
            
        Returns:
            Alert if anomaly detected, None otherwise
        """
        stats = self._get_stats(quote.symbol)
        spread = float(quote.ask_price - quote.bid_price)
        
        # Update spread statistics
        stats.spreads.append(spread)
        
        # Update spread EMA
        if stats.spread_ema == 0:
            stats.spread_ema = spread
        else:
            stats.spread_ema = stats.alpha * spread + (1 - stats.alpha) * stats.spread_ema
        
        # Check for spread anomaly
        if len(stats.spreads) >= self.min_samples:
            return self._check_spread_anomaly(quote, stats, spread)
        
        return None
    
    def _check_price_spike(
        self,
        trade: Trade,
        stats: SymbolStats,
        price: float,
    ) -> Alert | None:
        """Check for price spike anomaly using Z-score."""
        if stats.price_ema_variance <= 0:
            return None
        
        if not self._can_alert(trade.symbol, AlertType.PRICE_SPIKE):
            return None
        
        # Calculate Z-score
        std_dev = np.sqrt(stats.price_ema_variance)
        z_score = abs(price - stats.price_ema) / std_dev if std_dev > 0 else 0
        
        if z_score >= self.price_spike_threshold:
            # Determine severity based on Z-score
            if z_score >= 5.0:
                severity = AlertSeverity.CRITICAL
            elif z_score >= 4.0:
                severity = AlertSeverity.HIGH
            elif z_score >= 3.5:
                severity = AlertSeverity.MEDIUM
            else:
                severity = AlertSeverity.LOW
            
            pct_change = ((price - stats.price_ema) / stats.price_ema) * 100
            
            alert = Alert(
                alert_type=AlertType.PRICE_SPIKE,
                symbol=trade.symbol,
                severity=severity,
                message=f"Price spike detected: {price:.2f} (Z-score: {z_score:.2f}, {pct_change:+.2f}%)",
                details={
                    "price": price,
                    "ema": round(stats.price_ema, 2),
                    "z_score": round(z_score, 2),
                    "pct_change": round(pct_change, 2),
                    "trade_id": trade.trade_id,
                },
            )
            
            self._record_alert(trade.symbol, AlertType.PRICE_SPIKE)
            
            metrics.alerts_triggered.labels(
                alert_type=AlertType.PRICE_SPIKE.value,
                severity=severity.value,
                symbol=trade.symbol,
            ).inc()
            
            logger.warning(
                "price_spike_detected",
                symbol=trade.symbol,
                price=price,
                z_score=z_score,
                severity=severity.value,
            )
            
            return alert
        
        return None
    
    def _check_volume_anomaly(
        self,
        trade: Trade,
        stats: SymbolStats,
        volume: int,
    ) -> Alert | None:
        """Check for volume anomaly."""
        if stats.volume_ema <= 0:
            return None
        
        if not self._can_alert(trade.symbol, AlertType.VOLUME_ANOMALY):
            return None
        
        volume_ratio = volume / stats.volume_ema
        
        if volume_ratio >= self.volume_anomaly_multiplier:
            # Determine severity
            if volume_ratio >= 20:
                severity = AlertSeverity.CRITICAL
            elif volume_ratio >= 10:
                severity = AlertSeverity.HIGH
            elif volume_ratio >= 7:
                severity = AlertSeverity.MEDIUM
            else:
                severity = AlertSeverity.LOW
            
            alert = Alert(
                alert_type=AlertType.VOLUME_ANOMALY,
                symbol=trade.symbol,
                severity=severity,
                message=f"Volume anomaly: {volume:,} shares ({volume_ratio:.1f}x normal)",
                details={
                    "volume": volume,
                    "volume_ema": round(stats.volume_ema, 0),
                    "volume_ratio": round(volume_ratio, 2),
                    "trade_id": trade.trade_id,
                },
            )
            
            self._record_alert(trade.symbol, AlertType.VOLUME_ANOMALY)
            
            metrics.alerts_triggered.labels(
                alert_type=AlertType.VOLUME_ANOMALY.value,
                severity=severity.value,
                symbol=trade.symbol,
            ).inc()
            
            logger.warning(
                "volume_anomaly_detected",
                symbol=trade.symbol,
                volume=volume,
                ratio=volume_ratio,
                severity=severity.value,
            )
            
            return alert
        
        return None
    
    def _check_spread_anomaly(
        self,
        quote: Quote,
        stats: SymbolStats,
        spread: float,
    ) -> Alert | None:
        """Check for spread anomaly."""
        if stats.spread_ema <= 0:
            return None
        
        if not self._can_alert(quote.symbol, AlertType.SPREAD_ANOMALY):
            return None
        
        spread_ratio = spread / stats.spread_ema
        
        if spread_ratio >= self.spread_anomaly_multiplier:
            # Determine severity
            if spread_ratio >= 10:
                severity = AlertSeverity.CRITICAL
            elif spread_ratio >= 5:
                severity = AlertSeverity.HIGH
            elif spread_ratio >= 4:
                severity = AlertSeverity.MEDIUM
            else:
                severity = AlertSeverity.LOW
            
            alert = Alert(
                alert_type=AlertType.SPREAD_ANOMALY,
                symbol=quote.symbol,
                severity=severity,
                message=f"Spread anomaly: ${spread:.4f} ({spread_ratio:.1f}x normal)",
                details={
                    "spread": spread,
                    "spread_ema": round(stats.spread_ema, 4),
                    "spread_ratio": round(spread_ratio, 2),
                    "bid": float(quote.bid_price),
                    "ask": float(quote.ask_price),
                },
            )
            
            self._record_alert(quote.symbol, AlertType.SPREAD_ANOMALY)
            
            metrics.alerts_triggered.labels(
                alert_type=AlertType.SPREAD_ANOMALY.value,
                severity=severity.value,
                symbol=quote.symbol,
            ).inc()
            
            logger.warning(
                "spread_anomaly_detected",
                symbol=quote.symbol,
                spread=spread,
                ratio=spread_ratio,
                severity=severity.value,
            )
            
            return alert
        
        return None
    
    def get_stats(self, symbol: str) -> dict | None:
        """Get current statistics for a symbol."""
        if symbol not in self._stats:
            return None
        
        stats = self._stats[symbol]
        return {
            "symbol": symbol,
            "price_ema": round(stats.price_ema, 2),
            "price_std": round(np.sqrt(stats.price_ema_variance), 4) if stats.price_ema_variance > 0 else 0,
            "volume_ema": round(stats.volume_ema, 0),
            "spread_ema": round(stats.spread_ema, 4),
            "trade_count": stats.trade_count,
            "last_price": stats.last_price,
            "last_update": stats.last_update.isoformat() if stats.last_update else None,
        }
    
    def get_all_stats(self) -> Dict[str, dict]:
        """Get statistics for all symbols."""
        return {
            symbol: self.get_stats(symbol)
            for symbol in self._stats.keys()
        }
