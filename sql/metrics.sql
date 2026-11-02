-- P1-1 metric queries. Each section is delimited by a `-- query: <name>` marker
-- so src/storage/metrics.py can load one statement at a time.
--
-- The moving averages mirror src/features.py::add_price_features:
--   pandas: groupby(name).rolling(size, min_periods=1).mean()
--   SQL:    AVG(price) OVER (... ROWS BETWEEN size-1 PRECEDING AND CURRENT ROW)
-- Early rows naturally average only the rows that already exist, which is the
-- SQL equivalent of min_periods=1.

-- query: price_metrics
SELECT
    f.date_id,
    c.name,
    f.commodity_id,
    f.price,
    AVG(f.price) OVER (
        PARTITION BY f.commodity_id
        ORDER BY f.date_id
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS ma7,
    AVG(f.price) OVER (
        PARTITION BY f.commodity_id
        ORDER BY f.date_id
        ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
    ) AS ma14,
    AVG(f.price) OVER (
        PARTITION BY f.commodity_id
        ORDER BY f.date_id
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS ma30,
    RANK() OVER (
        PARTITION BY f.date_id
        ORDER BY f.price DESC
    ) AS price_rank
FROM fact_price AS f
JOIN dim_commodity AS c ON c.commodity_id = f.commodity_id
ORDER BY c.name, f.date_id
;

-- query: max_consecutive_up_days
-- "Consecutive up days" counts the days belonging to the longest run of
-- strictly increasing prices, so 1,2,3,2,3,4,5 yields 4 (the run 2,3,4,5).
-- A day is an "up" row when its price is strictly greater than the previous
-- day's price for the same commodity. gaps-and-islands: every non-up row
-- starts a new block, and consecutive up rows share a block.
WITH deltas AS (
    SELECT
        f.commodity_id,
        f.date_id,
        f.price,
        LAG(f.price) OVER (
            PARTITION BY f.commodity_id
            ORDER BY f.date_id
        ) AS prev_price
    FROM fact_price AS f
),
flagged AS (
    SELECT
        commodity_id,
        date_id,
        CASE
            WHEN prev_price IS NOT NULL AND price > prev_price THEN 1
            ELSE 0
        END AS is_up
    FROM deltas
),
islands AS (
    SELECT
        commodity_id,
        date_id,
        is_up,
        SUM(CASE WHEN is_up = 0 THEN 1 ELSE 0 END) OVER (
            PARTITION BY commodity_id
            ORDER BY date_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS block_id
    FROM flagged
),
runs AS (
    SELECT
        commodity_id,
        block_id,
        COUNT(*) AS up_days
    FROM islands
    WHERE is_up = 1
    GROUP BY commodity_id, block_id
),
best AS (
    SELECT commodity_id, MAX(up_days) AS up_days
    FROM runs
    GROUP BY commodity_id
)
SELECT
    c.commodity_id,
    c.name,
    COALESCE(b.up_days + 1, 0) AS days
FROM dim_commodity AS c
LEFT JOIN best AS b ON b.commodity_id = c.commodity_id
ORDER BY c.name
;
