-- P0-B1 SQLite schema. Table creation is idempotent so init_db is re-runnable.

CREATE TABLE IF NOT EXISTS dim_date (
    date_id DATE NOT NULL PRIMARY KEY,
    year    INT,
    month   INT,
    day     INT,
    weekday INT
);

CREATE TABLE IF NOT EXISTS dim_commodity (
    commodity_id INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    category     TEXT,
    unit         TEXT DEFAULT 'kg'
);

CREATE TABLE IF NOT EXISTS fact_price (
    id           INTEGER PRIMARY KEY,
    date_id      DATE NOT NULL,
    commodity_id INTEGER NOT NULL,
    price        NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    source       TEXT,
    UNIQUE (date_id, commodity_id)
);

CREATE TABLE IF NOT EXISTS strategy_result (
    run_id     TEXT NOT NULL,
    date_id    DATE NOT NULL,
    planting   TEXT,
    score      NUMERIC,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, date_id)
);

CREATE TABLE IF NOT EXISTS pipeline_run (
    run_id      TEXT NOT NULL PRIMARY KEY,
    stage       TEXT NOT NULL,
    started_at  TIMESTAMP,
    finished_at TIMESTAMP,
    rows_in     INTEGER,
    rows_out    INTEGER,
    status      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline     TEXT NOT NULL PRIMARY KEY,
    last_date_id DATE,
    updated_at   TIMESTAMP
);
