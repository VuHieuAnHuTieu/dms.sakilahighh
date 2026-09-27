-- Category transitions built from each customer's chronological rental sequence.
-- Ordering: rental_date, then rental_id as deterministic tie-breaker (same as team SQL #2).
-- Portable window SQL: MySQL 8 / MariaDB 10.2+ / SQLite 3.25+.

-- name: transition_counts
WITH seq AS (
    SELECT
        r.customer_id,
        r.rental_id,
        c.name AS category,
        LAG(c.name) OVER (PARTITION BY r.customer_id ORDER BY r.rental_date, r.rental_id) AS prev_category
    FROM rental r
    JOIN inventory i      ON i.inventory_id = r.inventory_id
    JOIN film_category fc ON fc.film_id = i.film_id
    JOIN category c       ON c.category_id = fc.category_id
    WHERE r.rental_date < :end_date
)
SELECT
    prev_category              AS from_category,
    category                   AS to_category,
    COUNT(*)                   AS transitions,
    COUNT(DISTINCT customer_id) AS customers
FROM seq
WHERE prev_category IS NOT NULL
GROUP BY prev_category, category
ORDER BY prev_category, category

-- name: repeat_vs_switch
WITH seq AS (
    SELECT
        r.customer_id,
        c.name AS category,
        LAG(c.name) OVER (PARTITION BY r.customer_id ORDER BY r.rental_date, r.rental_id) AS prev_category
    FROM rental r
    JOIN inventory i      ON i.inventory_id = r.inventory_id
    JOIN film_category fc ON fc.film_id = i.film_id
    JOIN category c       ON c.category_id = fc.category_id
    WHERE r.rental_date < :end_date
)
SELECT
    COUNT(*) AS total_transitions,
    SUM(CASE WHEN category = prev_category THEN 1 ELSE 0 END)  AS same_category,
    SUM(CASE WHEN category <> prev_category THEN 1 ELSE 0 END) AS switched_category,
    ROUND(100.0 * SUM(CASE WHEN category = prev_category THEN 1 ELSE 0 END) / COUNT(*), 2)  AS repeat_pct,
    ROUND(100.0 * SUM(CASE WHEN category <> prev_category THEN 1 ELSE 0 END) / COUNT(*), 2) AS switch_pct
FROM seq
WHERE prev_category IS NOT NULL
