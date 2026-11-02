-- Acceptance query: average price over the most recent trading days.
--
-- Named parameters:
--   :name  commodity name (dim_commodity.name)
--   :as_of inclusive cutoff date (YYYY-MM-DD)
--   :days  window size in trading days (call sites default to 7)
--
-- A "trading day" is a date that actually has a price row for this
-- commodity, so holidays and gaps do not shorten the window. The aggregate
-- returns exactly one row: with no matching price rows it yields
-- days = 0 and avg_price = NULL instead of no row at all.

SELECT
    :name AS name,
    ROUND(AVG(price), 2) AS avg_price,
    COUNT(*) AS days
FROM (
    SELECT f.price
    FROM fact_price AS f
    JOIN dim_commodity AS c ON c.commodity_id = f.commodity_id
    WHERE c.name = :name
      AND f.date_id <= :as_of
    ORDER BY f.date_id DESC
    LIMIT :days
);
