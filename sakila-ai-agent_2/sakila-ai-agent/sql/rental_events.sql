-- One row per rental, enriched with film, category and payment amount.
-- Data model: customer -> rental -> inventory -> film -> film_category -> category ; rental -> payment
-- :end_date = analysis window upper bound (exclusive).
SELECT
    r.rental_id,
    r.customer_id,
    r.rental_date,
    r.return_date,
    r.inventory_id,
    i.store_id,
    f.film_id,
    f.title,
    f.rating,
    f.rental_rate,
    f.rental_duration,
    c.category_id,
    c.name AS category,
    COALESCE(p.amount, 0) AS amount
FROM rental r
JOIN inventory i      ON i.inventory_id = r.inventory_id
JOIN film f           ON f.film_id = i.film_id
JOIN film_category fc ON fc.film_id = f.film_id
JOIN category c       ON c.category_id = fc.category_id
LEFT JOIN (
    SELECT rental_id, SUM(amount) AS amount
    FROM payment
    WHERE rental_id IS NOT NULL
    GROUP BY rental_id
) p ON p.rental_id = r.rental_id
WHERE r.rental_date < :end_date
ORDER BY r.customer_id, r.rental_date, r.rental_id
