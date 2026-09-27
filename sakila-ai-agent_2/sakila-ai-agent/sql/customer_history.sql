-- name: customer_profile
SELECT
    cu.customer_id,
    cu.first_name,
    cu.last_name,
    cu.email,
    cu.store_id,
    cu.active,
    ci.city,
    co.country,
    cu.create_date
FROM customer cu
JOIN address a  ON a.address_id = cu.address_id
JOIN city ci    ON ci.city_id = a.city_id
JOIN country co ON co.country_id = ci.country_id
WHERE cu.customer_id = :customer_id

-- name: customer_rentals
SELECT
    r.rental_id,
    r.rental_date,
    r.return_date,
    f.film_id,
    f.title,
    f.rating,
    c.name AS category,
    COALESCE(p.amount, 0) AS amount
FROM rental r
JOIN inventory i      ON i.inventory_id = r.inventory_id
JOIN film f           ON f.film_id = i.film_id
JOIN film_category fc ON fc.film_id = f.film_id
JOIN category c       ON c.category_id = fc.category_id
LEFT JOIN (SELECT rental_id, SUM(amount) AS amount FROM payment GROUP BY rental_id) p
       ON p.rental_id = r.rental_id
WHERE r.customer_id = :customer_id
  AND r.rental_date < :end_date
ORDER BY r.rental_date, r.rental_id

-- name: customer_all_film_ids
-- Every film the customer has EVER rented (no window) -> never re-recommend these.
SELECT DISTINCT i.film_id
FROM rental r
JOIN inventory i ON i.inventory_id = r.inventory_id
WHERE r.customer_id = :customer_id

-- name: customer_ids
SELECT customer_id, first_name, last_name FROM customer ORDER BY customer_id
