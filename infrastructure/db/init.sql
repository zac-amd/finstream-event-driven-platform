-- =============================================================================
-- FinStream - TimescaleDB Initialization Script
-- =============================================================================
-- This script creates the database schema for storing financial market data
-- with TimescaleDB hypertables for efficient time-series queries.
-- =============================================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- =============================================================================
-- TRADES TABLE
-- =============================================================================
-- Stores individual trade executions

CREATE TABLE IF NOT EXISTS trades (
    trade_id        TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    price           DECIMAL(18, 8) NOT NULL,
    quantity        BIGINT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    exchange        TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    trace_id        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    -- Composite primary key for deduplication
    PRIMARY KEY (symbol, timestamp, trade_id)
);

-- Convert to hypertable (partitioned by time)
SELECT create_hypertable(
    'trades', 
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_trades_symbol_time 
    ON trades (symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_trades_exchange_time 
    ON trades (exchange, timestamp DESC);

-- =============================================================================
-- QUOTES TABLE
-- =============================================================================
-- Stores bid/ask quote updates

CREATE TABLE IF NOT EXISTS quotes (
    symbol          TEXT NOT NULL,
    bid_price       DECIMAL(18, 8) NOT NULL,
    bid_size        BIGINT NOT NULL,
    ask_price       DECIMAL(18, 8) NOT NULL,
    ask_size        BIGINT NOT NULL,
    spread          DECIMAL(18, 8) GENERATED ALWAYS AS (ask_price - bid_price) STORED,
    exchange        TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (symbol, timestamp)
);

-- Convert to hypertable
SELECT create_hypertable(
    'quotes',
    'timestamp',
    chunk_time_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_quotes_symbol_time 
    ON quotes (symbol, timestamp DESC);

-- =============================================================================
-- CANDLES TABLE
-- =============================================================================
-- Stores OHLCV candlestick data at various intervals

CREATE TABLE IF NOT EXISTS candles (
    symbol          TEXT NOT NULL,
    interval        TEXT NOT NULL CHECK (interval IN ('1m', '5m', '15m', '1h', '4h', '1d')),
    open            DECIMAL(18, 8) NOT NULL,
    high            DECIMAL(18, 8) NOT NULL,
    low             DECIMAL(18, 8) NOT NULL,
    close           DECIMAL(18, 8) NOT NULL,
    volume          BIGINT NOT NULL,
    trade_count     INTEGER NOT NULL,
    vwap            DECIMAL(18, 8),
    timestamp       TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (symbol, interval, timestamp)
);

-- Convert to hypertable
SELECT create_hypertable(
    'candles',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_candles_symbol_interval_time 
    ON candles (symbol, interval, timestamp DESC);

-- =============================================================================
-- ALERTS TABLE
-- =============================================================================
-- Stores triggered alerts and anomalies

CREATE TABLE IF NOT EXISTS alerts (
    alert_id        TEXT NOT NULL,
    alert_type      TEXT NOT NULL CHECK (alert_type IN ('PRICE_SPIKE', 'VOLUME_ANOMALY', 'SPREAD_ANOMALY', 'CUSTOM')),
    symbol          TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    message         TEXT NOT NULL,
    details         JSONB,
    acknowledged    BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT,
    timestamp       TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    PRIMARY KEY (alert_id, timestamp)
);

-- Convert to hypertable
SELECT create_hypertable(
    'alerts',
    'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_alerts_symbol_time 
    ON alerts (symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_type_time 
    ON alerts (alert_type, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_unacknowledged 
    ON alerts (acknowledged, timestamp DESC) WHERE acknowledged = FALSE;

-- =============================================================================
-- SYMBOLS TABLE
-- =============================================================================
-- Reference table for tradable symbols

CREATE TABLE IF NOT EXISTS symbols (
    symbol          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    exchange        TEXT NOT NULL,
    asset_type      TEXT NOT NULL CHECK (asset_type IN ('STOCK', 'ETF', 'CRYPTO', 'FOREX', 'FUTURE')),
    currency        TEXT NOT NULL DEFAULT 'USD',
    is_active       BOOLEAN DEFAULT TRUE,
    lot_size        INTEGER DEFAULT 1,
    tick_size       DECIMAL(18, 8) DEFAULT 0.01,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default symbols
INSERT INTO symbols (symbol, name, exchange, asset_type) VALUES
    ('AAPL', 'Apple Inc.', 'NASDAQ', 'STOCK'),
    ('GOOGL', 'Alphabet Inc.', 'NASDAQ', 'STOCK'),
    ('MSFT', 'Microsoft Corporation', 'NASDAQ', 'STOCK'),
    ('AMZN', 'Amazon.com Inc.', 'NASDAQ', 'STOCK'),
    ('META', 'Meta Platforms Inc.', 'NASDAQ', 'STOCK'),
    ('NVDA', 'NVIDIA Corporation', 'NASDAQ', 'STOCK'),
    ('TSLA', 'Tesla Inc.', 'NASDAQ', 'STOCK'),
    ('JPM', 'JPMorgan Chase & Co.', 'NYSE', 'STOCK'),
    ('V', 'Visa Inc.', 'NYSE', 'STOCK'),
    ('JNJ', 'Johnson & Johnson', 'NYSE', 'STOCK')
ON CONFLICT (symbol) DO NOTHING;

-- =============================================================================
-- CONTINUOUS AGGREGATES
-- =============================================================================
-- Pre-computed materialized views for fast queries

-- 1-minute candles from raw trades
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1m
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 minute', timestamp) AS bucket,
    first(price, timestamp) AS open,
    max(price) AS high,
    min(price) AS low,
    last(price, timestamp) AS close,
    sum(quantity) AS volume,
    count(*) AS trade_count,
    sum(price * quantity) / NULLIF(sum(quantity), 0) AS vwap
FROM trades
GROUP BY symbol, time_bucket('1 minute', timestamp)
WITH NO DATA;

-- Add refresh policy for 1-minute candles
SELECT add_continuous_aggregate_policy('candles_1m',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

-- 5-minute candles from 1-minute candles
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_5m
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('5 minutes', bucket) AS bucket,
    first(open, bucket) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, bucket) AS close,
    sum(volume) AS volume,
    sum(trade_count) AS trade_count,
    sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap
FROM candles_1m
GROUP BY symbol, time_bucket('5 minutes', bucket)
WITH NO DATA;

-- Add refresh policy for 5-minute candles
SELECT add_continuous_aggregate_policy('candles_5m',
    start_offset => INTERVAL '6 hours',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

-- 1-hour candles from 5-minute candles
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_1h
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 hour', bucket) AS bucket,
    first(open, bucket) AS open,
    max(high) AS high,
    min(low) AS low,
    last(close, bucket) AS close,
    sum(volume) AS volume,
    sum(trade_count) AS trade_count,
    sum(vwap * volume) / NULLIF(sum(volume), 0) AS vwap
FROM candles_5m
GROUP BY symbol, time_bucket('1 hour', bucket)
WITH NO DATA;

-- Add refresh policy for 1-hour candles
SELECT add_continuous_aggregate_policy('candles_1h',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- =============================================================================
-- RETENTION POLICIES
-- =============================================================================
-- Automatically drop old data to manage storage

-- Keep raw trades for 7 days
SELECT add_retention_policy('trades', INTERVAL '7 days', if_not_exists => TRUE);

-- Keep quotes for 1 day
SELECT add_retention_policy('quotes', INTERVAL '1 day', if_not_exists => TRUE);

-- Keep alerts for 90 days
SELECT add_retention_policy('alerts', INTERVAL '90 days', if_not_exists => TRUE);

-- =============================================================================
-- COMPRESSION POLICIES
-- =============================================================================
-- Compress old chunks to save storage

-- Enable compression on trades table
ALTER TABLE trades SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add compression policy (compress chunks older than 1 day)
SELECT add_compression_policy('trades', INTERVAL '1 day', if_not_exists => TRUE);

-- Enable compression on candles table
ALTER TABLE candles SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol, interval',
    timescaledb.compress_orderby = 'timestamp DESC'
);

SELECT add_compression_policy('candles', INTERVAL '1 day', if_not_exists => TRUE);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to get latest price for a symbol
CREATE OR REPLACE FUNCTION get_latest_price(p_symbol TEXT)
RETURNS TABLE (
    symbol TEXT,
    price DECIMAL(18, 8),
    timestamp TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT t.symbol, t.price, t.timestamp
    FROM trades t
    WHERE t.symbol = p_symbol
    ORDER BY t.timestamp DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to get OHLCV for a time range
CREATE OR REPLACE FUNCTION get_ohlcv(
    p_symbol TEXT,
    p_interval TEXT,
    p_start TIMESTAMPTZ,
    p_end TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (
    symbol TEXT,
    interval TEXT,
    bucket TIMESTAMPTZ,
    open DECIMAL(18, 8),
    high DECIMAL(18, 8),
    low DECIMAL(18, 8),
    close DECIMAL(18, 8),
    volume BIGINT,
    trade_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.symbol,
        c.interval,
        c.timestamp AS bucket,
        c.open,
        c.high,
        c.low,
        c.close,
        c.volume,
        c.trade_count
    FROM candles c
    WHERE c.symbol = p_symbol
      AND c.interval = p_interval
      AND c.timestamp >= p_start
      AND c.timestamp <= p_end
    ORDER BY c.timestamp ASC;
END;
$$ LANGUAGE plpgsql;

-- Function to get market statistics
CREATE OR REPLACE FUNCTION get_market_stats(p_symbol TEXT, p_lookback INTERVAL DEFAULT '1 hour')
RETURNS TABLE (
    symbol TEXT,
    current_price DECIMAL(18, 8),
    high_price DECIMAL(18, 8),
    low_price DECIMAL(18, 8),
    vwap DECIMAL(18, 8),
    total_volume BIGINT,
    trade_count BIGINT,
    price_change DECIMAL(18, 8),
    price_change_pct DECIMAL(10, 4)
) AS $$
DECLARE
    v_first_price DECIMAL(18, 8);
    v_last_price DECIMAL(18, 8);
BEGIN
    -- Get first and last prices
    SELECT price INTO v_first_price
    FROM trades
    WHERE trades.symbol = p_symbol
      AND timestamp >= NOW() - p_lookback
    ORDER BY timestamp ASC
    LIMIT 1;
    
    SELECT price INTO v_last_price
    FROM trades
    WHERE trades.symbol = p_symbol
      AND timestamp >= NOW() - p_lookback
    ORDER BY timestamp DESC
    LIMIT 1;
    
    RETURN QUERY
    SELECT
        p_symbol,
        v_last_price,
        MAX(t.price),
        MIN(t.price),
        SUM(t.price * t.quantity) / NULLIF(SUM(t.quantity), 0),
        SUM(t.quantity),
        COUNT(*),
        v_last_price - v_first_price,
        CASE 
            WHEN v_first_price > 0 THEN ((v_last_price - v_first_price) / v_first_price) * 100
            ELSE 0
        END
    FROM trades t
    WHERE t.symbol = p_symbol
      AND t.timestamp >= NOW() - p_lookback
    GROUP BY p_symbol;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- GRANTS
-- =============================================================================
-- Grant permissions (adjust as needed for your security requirements)

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO finstream;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO finstream;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO finstream;

-- =============================================================================
-- COMPLETION MESSAGE
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE 'FinStream database initialization complete!';
    RAISE NOTICE 'Tables created: trades, quotes, candles, alerts, symbols';
    RAISE NOTICE 'Continuous aggregates: candles_1m, candles_5m, candles_1h';
    RAISE NOTICE 'Retention policies: trades (7d), quotes (1d), alerts (90d)';
END $$;
