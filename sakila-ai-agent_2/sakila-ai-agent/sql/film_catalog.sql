-- Film catalogue with category, stock and popularity.
-- copies_out = copies whose latest rental has no return_date (Sakila's own inventory_in_stock logic).
-- available_copies = copies - copies_out, as of the dataset snapshot.
SELECT
    f.film_id,
    f.title,
    f.description,
    c.name AS category,
    f.rating,
    f.rental_rate,
    f.length,
    f.release_year,
    COALESCE(inv.copies, 0)     AS copies,
    COALESCE(o.copies_out, 0)   AS copies_out,
    COALESCE(inv.copies, 0) - COALESCE(o.copies_out, 0) AS available_copies,
    COALESCE(rw.rentals, 0)     AS rentals_in_window
FROM film f
JOIN film_category fc ON fc.film_id = f.film_id
JOIN category c       ON c.category_id = fc.category_id
LEFT JOIN (SELECT film_id, COUNT(*) AS copies FROM inventory GROUP BY film_id) inv
       ON inv.film_id = f.film_id
LEFT JOIN (
    SELECT i.film_id, COUNT(DISTINCT r.inventory_id) AS copies_out
    FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id
    WHERE r.return_date IS NULL
    GROUP BY i.film_id
) o ON o.film_id = f.film_id
LEFT JOIN (
    SELECT i.film_id, COUNT(*) AS rentals
    FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id
    WHERE r.rental_date < :end_date
    GROUP BY i.film_id
) rw ON rw.film_id = f.film_id
ORDER BY f.film_id
