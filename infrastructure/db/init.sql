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
-- PORTFOLIO TRACKING TABLES
-- =============================================================================

-- Enable UUID extension for secure ID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table for authentication
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT NOT NULL UNIQUE,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    is_verified     BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMPTZ,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for login queries
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Portfolios table - users can have multiple portfolios
CREATE TABLE IF NOT EXISTS portfolios (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    is_default      BOOLEAN DEFAULT FALSE,
    currency        TEXT DEFAULT 'USD',
    initial_cash    DECIMAL(18, 2) DEFAULT 10000.00,
    current_cash    DECIMAL(18, 2) DEFAULT 10000.00,
    is_public       BOOLEAN DEFAULT FALSE,  -- For sharing/leaderboard
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_default_portfolio UNIQUE (user_id, is_default) 
        DEFERRABLE INITIALLY DEFERRED
);

-- Indexes for portfolio queries
CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolios_public ON portfolios(is_public) WHERE is_public = TRUE;

-- Holdings table - current positions in each portfolio
CREATE TABLE IF NOT EXISTS holdings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL REFERENCES symbols(symbol),
    quantity        DECIMAL(18, 8) NOT NULL DEFAULT 0,
    average_cost    DECIMAL(18, 8) NOT NULL DEFAULT 0,  -- Cost basis per share
    total_cost      DECIMAL(18, 2) NOT NULL DEFAULT 0,  -- Total invested amount
    first_bought_at TIMESTAMPTZ,
    last_traded_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_portfolio_symbol UNIQUE (portfolio_id, symbol),
    CONSTRAINT positive_quantity CHECK (quantity >= 0)
);

-- Indexes for holdings queries
CREATE INDEX IF NOT EXISTS idx_holdings_portfolio ON holdings(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol ON holdings(symbol);

-- Transactions table - complete trade history
CREATE TABLE IF NOT EXISTS transactions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol          TEXT NOT NULL REFERENCES symbols(symbol),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('BUY', 'SELL', 'DEPOSIT', 'WITHDRAWAL', 'DIVIDEND')),
    quantity        DECIMAL(18, 8) NOT NULL,
    price           DECIMAL(18, 8) NOT NULL,  -- Price per share at transaction
    total_amount    DECIMAL(18, 2) NOT NULL,  -- Total transaction value
    fees            DECIMAL(18, 2) DEFAULT 0,
    notes           TEXT,
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT positive_transaction CHECK (quantity > 0 AND price > 0)
);

-- Convert transactions to hypertable for time-series queries
SELECT create_hypertable(
    'transactions',
    'executed_at',
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Indexes for transaction queries
CREATE INDEX IF NOT EXISTS idx_transactions_portfolio_time 
    ON transactions(portfolio_id, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_transactions_symbol_time 
    ON transactions(symbol, executed_at DESC);

-- Watchlists table - symbols users want to track
CREATE TABLE IF NOT EXISTS watchlists (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL DEFAULT 'Default',
    symbols         TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_user_watchlist_name UNIQUE (user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);

-- Refresh tokens table for JWT auth
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    user_agent      TEXT,
    ip_address      INET
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);

-- =============================================================================
-- PORTFOLIO FUNCTIONS
-- =============================================================================

-- Function to get portfolio summary with real-time P&L
CREATE OR REPLACE FUNCTION get_portfolio_summary(p_portfolio_id UUID)
RETURNS TABLE (
    portfolio_id UUID,
    portfolio_name TEXT,
    cash_balance DECIMAL(18, 2),
    total_invested DECIMAL(18, 2),
    holdings_count BIGINT,
    total_cost_basis DECIMAL(18, 2)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        p.name,
        p.current_cash,
        COALESCE(SUM(h.total_cost), 0)::DECIMAL(18, 2),
        COUNT(DISTINCT h.symbol),
        COALESCE(SUM(h.total_cost), 0)::DECIMAL(18, 2)
    FROM portfolios p
    LEFT JOIN holdings h ON p.id = h.portfolio_id AND h.quantity > 0
    WHERE p.id = p_portfolio_id
    GROUP BY p.id, p.name, p.current_cash;
END;
$$ LANGUAGE plpgsql;

-- Function to execute a buy transaction
CREATE OR REPLACE FUNCTION execute_buy(
    p_portfolio_id UUID,
    p_symbol TEXT,
    p_quantity DECIMAL(18, 8),
    p_price DECIMAL(18, 8),
    p_notes TEXT DEFAULT NULL
)
RETURNS TABLE (
    transaction_id UUID,
    new_quantity DECIMAL(18, 8),
    new_average_cost DECIMAL(18, 8),
    remaining_cash DECIMAL(18, 2)
) AS $$
DECLARE
    v_total_amount DECIMAL(18, 2);
    v_current_cash DECIMAL(18, 2);
    v_transaction_id UUID;
    v_current_quantity DECIMAL(18, 8);
    v_current_cost DECIMAL(18, 2);
    v_new_quantity DECIMAL(18, 8);
    v_new_total_cost DECIMAL(18, 2);
    v_new_avg_cost DECIMAL(18, 8);
BEGIN
    -- Calculate total amount
    v_total_amount := p_quantity * p_price;
    
    -- Check available cash
    SELECT current_cash INTO v_current_cash
    FROM portfolios WHERE id = p_portfolio_id FOR UPDATE;
    
    IF v_current_cash < v_total_amount THEN
        RAISE EXCEPTION 'Insufficient funds. Available: %, Required: %', v_current_cash, v_total_amount;
    END IF;
    
    -- Deduct cash
    UPDATE portfolios 
    SET current_cash = current_cash - v_total_amount,
        updated_at = NOW()
    WHERE id = p_portfolio_id
    RETURNING current_cash INTO v_current_cash;
    
    -- Get current holding
    SELECT quantity, total_cost INTO v_current_quantity, v_current_cost
    FROM holdings 
    WHERE portfolio_id = p_portfolio_id AND symbol = p_symbol;
    
    IF NOT FOUND THEN
        v_current_quantity := 0;
        v_current_cost := 0;
    END IF;
    
    -- Calculate new values
    v_new_quantity := v_current_quantity + p_quantity;
    v_new_total_cost := v_current_cost + v_total_amount;
    v_new_avg_cost := v_new_total_cost / v_new_quantity;
    
    -- Upsert holding
    INSERT INTO holdings (portfolio_id, symbol, quantity, average_cost, total_cost, first_bought_at, last_traded_at)
    VALUES (p_portfolio_id, p_symbol, v_new_quantity, v_new_avg_cost, v_new_total_cost, NOW(), NOW())
    ON CONFLICT (portfolio_id, symbol) DO UPDATE SET
        quantity = v_new_quantity,
        average_cost = v_new_avg_cost,
        total_cost = v_new_total_cost,
        last_traded_at = NOW(),
        updated_at = NOW();
    
    -- Record transaction
    INSERT INTO transactions (portfolio_id, symbol, transaction_type, quantity, price, total_amount, notes, executed_at)
    VALUES (p_portfolio_id, p_symbol, 'BUY', p_quantity, p_price, v_total_amount, p_notes, NOW())
    RETURNING id INTO v_transaction_id;
    
    RETURN QUERY SELECT v_transaction_id, v_new_quantity, v_new_avg_cost, v_current_cash;
END;
$$ LANGUAGE plpgsql;

-- Function to execute a sell transaction
CREATE OR REPLACE FUNCTION execute_sell(
    p_portfolio_id UUID,
    p_symbol TEXT,
    p_quantity DECIMAL(18, 8),
    p_price DECIMAL(18, 8),
    p_notes TEXT DEFAULT NULL
)
RETURNS TABLE (
    transaction_id UUID,
    remaining_quantity DECIMAL(18, 8),
    realized_pnl DECIMAL(18, 2),
    new_cash DECIMAL(18, 2)
) AS $$
DECLARE
    v_total_amount DECIMAL(18, 2);
    v_transaction_id UUID;
    v_current_quantity DECIMAL(18, 8);
    v_current_avg_cost DECIMAL(18, 8);
    v_cost_basis DECIMAL(18, 2);
    v_realized_pnl DECIMAL(18, 2);
    v_new_quantity DECIMAL(18, 8);
    v_new_cash DECIMAL(18, 2);
BEGIN
    -- Calculate total amount
    v_total_amount := p_quantity * p_price;
    
    -- Get current holding
    SELECT quantity, average_cost INTO v_current_quantity, v_current_avg_cost
    FROM holdings 
    WHERE portfolio_id = p_portfolio_id AND symbol = p_symbol FOR UPDATE;
    
    IF NOT FOUND OR v_current_quantity < p_quantity THEN
        RAISE EXCEPTION 'Insufficient shares. Available: %, Requested: %', 
            COALESCE(v_current_quantity, 0), p_quantity;
    END IF;
    
    -- Calculate P&L
    v_cost_basis := p_quantity * v_current_avg_cost;
    v_realized_pnl := v_total_amount - v_cost_basis;
    v_new_quantity := v_current_quantity - p_quantity;
    
    -- Update holding
    IF v_new_quantity = 0 THEN
        DELETE FROM holdings WHERE portfolio_id = p_portfolio_id AND symbol = p_symbol;
    ELSE
        UPDATE holdings 
        SET quantity = v_new_quantity,
            total_cost = v_new_quantity * average_cost,
            last_traded_at = NOW(),
            updated_at = NOW()
        WHERE portfolio_id = p_portfolio_id AND symbol = p_symbol;
    END IF;
    
    -- Add cash
    UPDATE portfolios 
    SET current_cash = current_cash + v_total_amount,
        updated_at = NOW()
    WHERE id = p_portfolio_id
    RETURNING current_cash INTO v_new_cash;
    
    -- Record transaction
    INSERT INTO transactions (portfolio_id, symbol, transaction_type, quantity, price, total_amount, notes, executed_at)
    VALUES (p_portfolio_id, p_symbol, 'SELL', p_quantity, p_price, v_total_amount, p_notes, NOW())
    RETURNING id INTO v_transaction_id;
    
    RETURN QUERY SELECT v_transaction_id, v_new_quantity, v_realized_pnl, v_new_cash;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
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
    RAISE NOTICE 'Portfolio tables: users, portfolios, holdings, transactions, watchlists';
    RAISE NOTICE 'Continuous aggregates: candles_1m, candles_5m, candles_1h';
    RAISE NOTICE 'Retention policies: trades (7d), quotes (1d), alerts (90d)';
END $$;
