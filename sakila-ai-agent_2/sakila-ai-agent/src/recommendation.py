"""Transparent next-category + movie recommendation engine.

Category score (all inputs from Sakila data, weights configurable in .env):

    score(B) = w_transition * P(next = B | customer's most recent category)
             + w_affinity   * affinity(B)

    P(next = B | A)  = count(A -> B) / count(A -> any)   over all customers' rental sequences
    affinity(B)      = (customer's rentals in B + 1) / (customer's rentals + #categories)
                       (Laplace-smoothed share of the customer's own history)

Movie ranking inside the chosen category:
    1. exclude films the customer has EVER rented
    2. keep films with at least one copy in stock (dataset snapshot) when available_only=True
    3. rank by rentals in the analysis window (popularity), then available copies, then title
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import analytics as an
from . import database as db
from .config import get_settings


def score_categories(history: list[str], P: pd.DataFrame, cats: list[str],
                     w_transition: float, w_affinity: float) -> pd.DataFrame:
    """Rank every category for a customer given their chronological category history."""
    last = history[-1]
    trans = P.loc[last].reindex(cats).fillna(0.0)
    counts = pd.Series(history).value_counts().reindex(cats, fill_value=0)
    affinity = (counts + 1) / (len(history) + len(cats))
    total_w = (w_transition + w_affinity) or 1.0
    score = (w_transition * trans + w_affinity * affinity) / total_w
    df = pd.DataFrame({
        "category": cats,
        "transition_probability": trans.values,
        "affinity": affinity.values,
        "customer_rentals_in_category": counts.values,
        "score": score.values,
    })
    return df.sort_values(["score", "transition_probability"], ascending=False).reset_index(drop=True)


def recommend_movies(customer_id: int, category: str, n: int = 5, available_only: bool = True) -> pd.DataFrame:
    seen = set(db.run("customer_history.sql", "customer_all_film_ids", customer_id=customer_id)["film_id"])
    cat = an.film_catalog()
    cand = cat[(cat["category"] == category) & (~cat["film_id"].isin(seen)) & (cat["copies"] > 0)]
    if available_only:
        cand = cand[cand["available_copies"] > 0]
    cand = cand.sort_values(["rentals_in_window", "available_copies", "title"], ascending=[False, False, True])
    return cand.head(n)[["film_id", "title", "category", "rating", "rental_rate", "length",
                         "rentals_in_window", "available_copies", "copies"]].reset_index(drop=True)


def recommend_for_customer(customer_id: int, n_categories: int = 3, n_movies: int = 5,
                           available_only: bool = True, exclude_current_category: bool = False) -> dict:
    """Full recommendation. `exclude_current_category=True` = 'exploration mode':
    only categories different from the most recent one are considered."""
    s = get_settings()
    journey = an.customer_journey(customer_id)
    if journey.empty:
        raise ValueError(f"Customer {customer_id} has no rentals in the analysis window (or does not exist).")
    history = journey["category"].tolist()
    cats = list(an.categories())
    P = an.probability_matrix()
    ranked = score_categories(history, P, cats, s.w_transition, s.w_affinity)
    if exclude_current_category:
        ranked = ranked[ranked["category"] != history[-1]].reset_index(drop=True)
    long = an.transition_long().set_index(["from_category", "to_category"])
    last = history[-1]
    ranked["lift"] = [float(long.loc[(last, c), "lift"]) for c in ranked["category"]]
    ranked["z_residual"] = [float(long.loc[(last, c), "z_residual"]) for c in ranked["category"]]
    ranked["transitions_from_last"] = [int(long.loc[(last, c), "transitions"]) for c in ranked["category"]]
    top = ranked.iloc[0]
    it = an.independence_test()
    movies = recommend_movies(customer_id, top["category"], n_movies, available_only)
    alt = {c: recommend_movies(customer_id, c, 3, available_only)["title"].tolist()
           for c in ranked["category"].iloc[1:n_categories]}
    outgoing = int(an.transition_counts().loc[last].sum())
    strength = ("weak" if it["p_value"] >= 0.05 or abs(top["z_residual"]) < 1.96 else "moderate")
    return {
        "customer_id": int(customer_id),
        "rentals_in_window": int(len(history)),
        "recent_categories": history[-5:],
        "recent_titles": journey["title"].tolist()[-5:],
        "last_rental_date": str(journey["rental_date"].iloc[-1]),
        "current_category": last,
        "mode": "exploration (current category excluded)" if exclude_current_category else "standard",
        "recommended_category": top["category"],
        "score": round(float(top["score"]), 4),
        "transition_probability": round(float(top["transition_probability"]), 4),
        "transitions_observed": int(top["transitions_from_last"]),
        "outgoing_transitions_from_current": outgoing,
        "lift_vs_baseline": round(float(top["lift"]), 3),
        "z_residual": round(float(top["z_residual"]), 2),
        "customer_affinity": round(float(top["affinity"]), 4),
        "customer_rentals_in_recommended_category": int(top["customer_rentals_in_category"]),
        "signal_strength": strength,
        "weights": {"transition": s.w_transition, "affinity": s.w_affinity},
        "ranked_categories": ranked.head(n_categories).round(4).to_dict(orient="records"),
        "recommended_movies": movies.to_dict(orient="records"),
        "alternative_category_movies": alt,
        "global_signal": {"chi2_p_value": it["p_value"], "cramers_v": it["cramers_v"]},
        "explanation_inputs": (
            f"Most recent category: {last}. Across all Sakila rental sequences, {top['transitions_from_last']} of "
            f"{outgoing} transitions out of {last} went to {top['category']} "
            f"(P={top['transition_probability']:.1%}, lift {top['lift']:.2f} vs its {top['transition_probability']/top['lift']:.1%} baseline share). "
            f"The customer has rented {int(top['customer_rentals_in_category'])} {top['category']} film(s) out of {len(history)}. "
            f"Score = {s.w_transition}*transition + {s.w_affinity}*affinity. Signal strength: {strength} "
            f"(overall transition matrix chi2 p={it['p_value']}, Cramer's V={it['cramers_v']})."
        ),
    }
