CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Convert posts table to hypertable
SELECT create_hypertable('posts', 'created_at', 
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- Set retention policy (e.g., 30 days)
SELECT add_retention_policy('posts', INTERVAL '30 days', if_not_exists => TRUE);

-- Create compression policy (compress chunks older than 1 day)
SELECT add_compression_policy('posts', INTERVAL '1 day', if_not_exists => TRUE);
