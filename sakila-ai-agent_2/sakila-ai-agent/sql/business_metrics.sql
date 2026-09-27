-- name: headline
SELECT
    (SELECT COUNT(*) FROM store)                                             AS total_stores,
    (SELECT COUNT(*) FROM customer)                                          AS total_customers,
    (SELECT COUNT(DISTINCT customer_id) FROM rental WHERE rental_date < :end_date) AS renting_customers,
    (SELECT COUNT(*) FROM rental WHERE rental_date < :end_date)              AS total_rentals,
    (SELECT SUM(amount) FROM payment WHERE payment_date < :end_date)         AS total_revenue,
    (SELECT AVG(rental_rate) FROM film)                                      AS avg_catalog_rental_rate,
    (SELECT COUNT(*) FROM film)                                              AS total_films,
    (SELECT COUNT(*) FROM inventory)                                         AS total_copies,
    (SELECT MIN(rental_date) FROM rental WHERE rental_date < :end_date)      AS first_rental,
    (SELECT MAX(rental_date) FROM rental WHERE rental_date < :end_date)      AS last_rental,
    (SELECT COUNT(*) FROM rental)                                            AS all_time_rentals,
    (SELECT COUNT(*) FROM rental WHERE rental_date >= :end_date)             AS rentals_excluded_from_window,
    (SELECT SUM(amount) FROM payment)                                        AS all_time_revenue

-- name: category_performance
SELECT
    c.name AS category,
    COUNT(r.rental_id)          AS rentals,
    COUNT(DISTINCT r.customer_id) AS customers,
    ROUND(SUM(COALESCE(p.amount, 0)), 2) AS revenue,
    ROUND(AVG(f.rental_rate), 2) AS avg_rental_rate
FROM rental r
JOIN inventory i      ON i.inventory_id = r.inventory_id
JOIN film f           ON f.film_id = i.film_id
JOIN film_category fc ON fc.film_id = f.film_id
JOIN category c       ON c.category_id = fc.category_id
LEFT JOIN (SELECT rental_id, SUM(amount) AS amount FROM payment GROUP BY rental_id) p
       ON p.rental_id = r.rental_id
WHERE r.rental_date < :end_date
GROUP BY c.name
ORDER BY rentals DESC

-- name: payments
SELECT payment_id, customer_id, rental_id, amount, payment_date
FROM payment
WHERE payment_date < :end_date

-- name: stores
-- One row per store (branch): location, manager, customers registered, inventory, rentals and revenue in the window.
-- Rentals/revenue are attributed to the store that owns the rented copy (inventory.store_id).
SELECT
    s.store_id,
    ci.city,
    co.country,
    st.first_name AS manager_first_name,
    st.last_name  AS manager_last_name,
    (SELECT COUNT(*) FROM customer cu WHERE cu.store_id = s.store_id)            AS customers,
    (SELECT COUNT(*) FROM staff sf WHERE sf.store_id = s.store_id)               AS staff,
    (SELECT COUNT(*) FROM inventory i WHERE i.store_id = s.store_id)             AS copies,
    (SELECT COUNT(DISTINCT i.film_id) FROM inventory i WHERE i.store_id = s.store_id) AS distinct_films,
    (SELECT COUNT(*) FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id
      WHERE i.store_id = s.store_id AND r.rental_date < :end_date)               AS rentals,
    (SELECT ROUND(SUM(p.amount), 2) FROM payment p JOIN rental r ON r.rental_id = p.rental_id
      JOIN inventory i ON i.inventory_id = r.inventory_id
      WHERE i.store_id = s.store_id AND r.rental_date < :end_date)               AS revenue
FROM store s
JOIN address a ON a.address_id = s.address_id
JOIN city ci   ON ci.city_id = a.city_id
JOIN country co ON co.country_id = ci.country_id
JOIN staff st  ON st.staff_id = s.manager_staff_id
ORDER BY s.store_id

-- name: payment_components
-- Each payment compared with the film's rental_rate: the part above the rate is the late fee
-- (Sakila charges $1 per day beyond rental_duration; correlation with days late ~0.99).
SELECT p.payment_id, p.amount, f.rental_rate, f.rental_duration, r.rental_date, r.return_date
FROM payment p
JOIN rental r    ON r.rental_id = p.rental_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f      ON f.film_id = i.film_id
WHERE r.rental_date < :end_date

-- name: film_utilization
SELECT f.film_id, f.title, c.name AS category,
       COUNT(DISTINCT i.inventory_id) AS copies,
       COUNT(r.rental_id)             AS rentals
FROM film f
JOIN film_category fc ON fc.film_id = f.film_id
JOIN category c       ON c.category_id = fc.category_id
LEFT JOIN inventory i ON i.film_id = f.film_id
LEFT JOIN rental r    ON r.inventory_id = i.inventory_id AND r.rental_date < :end_date
GROUP BY f.film_id, f.title, c.name
