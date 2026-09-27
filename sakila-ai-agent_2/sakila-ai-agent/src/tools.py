"""Agent tools. Each tool is a plain Python function that reads real Sakila data
(via analytics / recommendation / SQL) and returns JSON-serialisable output.
`TOOL_SCHEMAS` exposes them to an LLM with OpenAI/Groq-style function calling.
"""
from __future__ import annotations

import json
import re
import math
from datetime import date, datetime
from typing import Any, Callable

import numpy as np
import pandas as pd

from . import analytics as an
from . import database as db
from . import charts as ch
from . import insights as ins
from .recommendation import recommend_for_customer


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return _clean(obj.to_dict(orient="records"))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) else round(f, 4)
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return str(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


# ---------------------------------------------------------------------------
# Tool 1
# ---------------------------------------------------------------------------
def get_customer_history(customer_id: int, max_rentals: int = 50) -> dict:
    """Customer profile + chronological rental journey with categories."""
    customer_id = int(customer_id)
    prof = db.run("customer_history.sql", "customer_profile", customer_id=customer_id)
    if prof.empty:
        return {"error": f"Customer {customer_id} does not exist. Valid IDs are 1-599."}
    j = an.customer_journey(customer_id)
    cats = j["category"].value_counts()
    return _clean({
        "customer": prof.iloc[0].to_dict(),
        "rental_count": int(len(j)),
        "distinct_categories": int(j["category"].nunique()),
        "category_counts": cats.to_dict(),
        "repeat_transitions": int((j["transition"] == "repeat").sum()),
        "switch_transitions": int((j["transition"] == "switch").sum()),
        "category_journey": " -> ".join(j["category"].tolist()),
        "rentals": j[["rental_number", "rental_date", "title", "category", "rating", "amount", "transition"]]
            .tail(int(max_rentals)).to_dict(orient="records"),
        "note": f"Showing the last {min(int(max_rentals), len(j))} of {len(j)} rentals in the analysis window.",
    })


# ---------------------------------------------------------------------------
# Tool 2
# ---------------------------------------------------------------------------
def get_category_transitions(category_name: str, direction: str = "outgoing", top_n: int = 5) -> dict:
    """Where customers go after `category_name` (outgoing) or which categories lead into it (incoming)."""
    try:
        prof = an.category_transition_profile(category_name, top_n=int(top_n))
    except ValueError as e:
        return {"error": str(e)}
    long = an.transition_long()
    cat = prof["category"]
    out: dict[str, Any] = {k: v for k, v in prof.items() if k != "top_sources_into_category"}
    if direction == "incoming":
        inc = long[(long["to_category"] == cat) & (~long["is_self"])].sort_values("probability", ascending=False)
        out = {
            "category": cat,
            "direction": "incoming",
            "incoming_transitions": prof["incoming_transitions"],
            "top_source_categories": [
                {"from_category": r.from_category, "transitions": int(r.transitions),
                 "probability_from_source": round(float(r.probability), 4), "lift": round(float(r.lift), 3),
                 "z_residual": round(float(r.z_residual), 2)}
                for r in inc.head(int(top_n)).itertuples()
            ],
            "meaning": "probability_from_source = P(next is this category | previous was source).",
        }
    out["statistical_context"] = {
        k: an.independence_test()[k] for k in ("p_value", "cramers_v", "uniform_probability", "cells_significant_after_bonferroni")
    }
    out["reading_guide"] = ("Probabilities near 1/16 = 6.25% equal chance level. lift = probability / baseline share of the "
                            "destination. |z_residual| > 1.96 is nominally notable, but with 256 cells ~13 such cells "
                            "are expected by chance.")
    return _clean(out)


# ---------------------------------------------------------------------------
# Tool 3
# ---------------------------------------------------------------------------
def get_customer_recommendation(customer_id: int, n_movies: int = 5, exploration_mode: bool = False) -> dict:
    """Next-category + movie recommendation with explanation inputs."""
    try:
        return _clean(recommend_for_customer(int(customer_id), n_movies=int(n_movies),
                                             exclude_current_category=bool(exploration_mode)))
    except ValueError as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool 4
# ---------------------------------------------------------------------------
# Everyday words customers use -> closest Sakila categories. Sakila has only 16 categories, so words
# like "history" have NO exact category; these are clearly-labelled nearest suggestions, not facts.
GENRE_SYNONYMS = {
    "history": ["Documentary", "Classics"], "historical": ["Documentary", "Classics"], "war": ["Documentary", "Classics"],
    "biography": ["Documentary"], "nature": ["Documentary", "Travel"], "science": ["Documentary", "Sci-Fi"],
    "kids": ["Children", "Family"], "kid": ["Children", "Family"], "cartoon": ["Animation", "Children"], "anime": ["Animation"],
    "scary": ["Horror"], "thriller": ["Horror", "Action"], "funny": ["Comedy"], "romance": ["Drama", "Classics"],
    "romantic": ["Drama", "Classics"], "science fiction": ["Sci-Fi"], "scifi": ["Sci-Fi"], "space": ["Sci-Fi"],
    "fantasy": ["Sci-Fi", "Animation"], "adventure": ["Action", "Travel"], "musical": ["Music"], "sport": ["Sports"],
    "old": ["Classics"], "classic": ["Classics"], "latest": ["New"], "newest": ["New"], "foreign": ["Foreign"],
    "video game": ["Games"], "game": ["Games"], "travel": ["Travel"], "family": ["Family"],
}
# Description words in the Sakila catalogue that hint at a theme (checked against the real descriptions).
KID_WORDS = {"kids", "kid", "children", "child", "family", "cartoon"}
THEME_KEYWORDS = {"history": "Ancient", "historical": "Ancient", "ancient": "Ancient", "space": "Astronaut", "shark": "Shark"}


def resolve_genre(text: str) -> dict:
    """Map a free-text genre word to Sakila categories. exact=True only for a real category name."""
    t = (text or "").strip().lower()
    for c in an.categories():
        if c.lower() == t or c.lower().rstrip("s") == t.rstrip("s"):
            return {"requested": text, "exact": True, "categories": [c], "description_keyword": None,
                    "kid_safe": c.lower() in KID_WORDS}
    for k in sorted(GENRE_SYNONYMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(k)}\b", t):
            return {"requested": text, "exact": False, "categories": GENRE_SYNONYMS[k],
                    "description_keyword": THEME_KEYWORDS.get(k), "kid_safe": k in KID_WORDS}
    return {"requested": text, "exact": False, "categories": [], "description_keyword": None}


def search_movies(category: str | None = None, title: str | None = None, rating: str | None = None,
                  available_only: bool = False, limit: int = 10, sort_by: str = "popularity",
                  keyword: str | None = None) -> dict:
    """Search films. `category` may be a Sakila category OR an everyday genre word (e.g. 'history'),
    which is mapped to the closest categories and reported as such. `keyword` searches title + description."""
    cat = an.film_catalog().copy()
    genre_note = None
    if category:
        g = resolve_genre(category)
        if not g["categories"]:
            return {"error": f"'{category}' is not a Sakila category and has no close match.",
                    "valid_categories": list(an.categories())}
        cat = cat[cat["category"].isin(g["categories"])]
        if not g["exact"]:
            genre_note = (f"Sakila has no '{category}' category. Closest categories: {', '.join(g['categories'])}"
                          + (f"; films whose description mentions '{g['description_keyword']}' are listed first."
                             if g["description_keyword"] else "."))
            if g["description_keyword"]:
                cat = cat.assign(_theme=cat["description"].str.contains(g["description_keyword"], case=False))
        if g.get("kid_safe") and not rating:
            cat = cat[cat["rating"].isin(["G", "PG"])]
            genre_note = (genre_note + " " if genre_note else "") + "Only G and PG rated films are shown for a family/kids request."
    if title:
        cat = cat[cat["title"].str.contains(title.strip(), case=False, regex=False)]
    if keyword:
        k = keyword.strip()
        cat = cat[cat["title"].str.contains(k, case=False, regex=False) | cat["description"].str.contains(k, case=False, regex=False)]
    if rating:
        cat = cat[cat["rating"].str.upper() == rating.strip().upper()]
    if available_only:
        cat = cat[cat["available_copies"] > 0]
    order = {"popularity": ("rentals_in_window", False), "title": ("title", True),
             "rental_rate": ("rental_rate", False), "length": ("length", False)}.get(sort_by, ("rentals_in_window", False))
    keys, asc = [order[0]], [order[1]]
    if "_theme" in cat:
        keys, asc = ["_theme"] + keys, [False] + asc
    cat = cat.sort_values(keys, ascending=asc)
    out = {
        "matches": int(len(cat)),
        "movies": cat.head(int(limit))[["film_id", "title", "category", "rating", "rental_rate", "length",
                                        "rentals_in_window", "copies", "available_copies", "description"]],
        "availability_definition": "available_copies = copies not currently out on an unreturned rental (dataset snapshot).",
        "business_model": "Sakila RENTS DVDs (rental_rate per rental); it does not sell them.",
    }
    if genre_note:
        out["genre_note"] = genre_note
    return _clean(out)


# ---------------------------------------------------------------------------
# Tool 5
# ---------------------------------------------------------------------------
METRICS: dict[str, Callable[[], Any]] = {
    "overview": an.headline_metrics,
    "stores": lambda: {"total_stores": int(len(an.store_summary())), "stores": an.store_summary(),
                       "note": "Rentals/revenue attributed to the store owning the rented copy (inventory.store_id)."},
    "total_customers": lambda: {k: an.headline_metrics()[k] for k in ("total_customers", "renting_customers")},
    "total_rentals": lambda: {"total_rentals": an.headline_metrics()["total_rentals"]},
    "total_revenue": lambda: {"total_revenue": an.headline_metrics()["total_revenue"]},
    "average_rental_rate": lambda: {"avg_catalog_rental_rate": an.headline_metrics()["avg_catalog_rental_rate"],
                                    "avg_payment_per_rental": an.headline_metrics()["avg_payment_per_rental"]},
    "most_rented_categories": lambda: an.category_performance()[["category", "rentals", "rental_share_pct", "customers"]],
    "category_revenue": lambda: an.category_performance()[["category", "revenue", "revenue_share_pct", "avg_rental_rate"]],
    "rental_trends": an.monthly_trend,
    "customer_return": an.customer_return_stats,
    "repeat_vs_switch": lambda: {**an.repetition_stats(), "field_meanings": {
        "shuffled_repeat_p_value": "PERMUTATION test p-value: is the observed repeat rate higher than when each customer's history is shuffled? (NOT the chi-square test)",
        "random_choice_repeat_pct": "repeat rate expected if categories were picked at random with their overall shares (sum of p^2)"}},
    "category_diversity": an.category_diversity,
    "transition_statistics": lambda: {**an.independence_test(), "field_meanings": {
        "p_value": "CHI-SQUARE independence test p-value for previous category vs next category (>= 0.05 = no evidence of dependence)",
        "cramers_v": "strength of association, 0 = none, below 0.1 = negligible"}},
    "revenue_breakdown": an.revenue_breakdown,
    "inventory_utilization": an.inventory_utilization,
    "key_insights": lambda: ins.all_insights(),
    "verified_facts": an.key_insights,
    "chronology": ins.chronology,
    "category_share_by_burst": ins.category_by_burst,
    "misc_facts": ins.misc_facts,
    "customer_segments": ins.customer_segments,
    "top_transitions": lambda: an.top_transitions(10)[["from_category", "to_category", "transitions", "probability", "lift", "z_residual"]],
    "high_transition_categories": lambda: {"assessment": an.gateway_assessment(), "table": an.high_transition_table()},
    "recommendation_backtest": an.next_category_backtest,
}


def get_business_metrics(metric_name: str) -> dict:
    key = metric_name.strip().lower().replace(" ", "_")
    if key not in METRICS:
        return {"error": f"Unknown metric '{metric_name}'.", "available_metrics": sorted(METRICS)}
    return _clean({"metric": key, "analysis_window_end": an.headline_metrics()["analysis_end_date"], "value": METRICS[key]()})


# ---------------------------------------------------------------------------
# Tool 6 - read-only SQL for anything the other tools do not cover
# ---------------------------------------------------------------------------
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|grant|revoke|"
                        r"vacuum|reindex|load_file|outfile|dumpfile|sleep|benchmark|call|exec|handler|lock|set)\b", re.I)
SCHEMA_HINT = ("Sakila tables: store(store_id, manager_staff_id, address_id); staff(staff_id, first_name, last_name, store_id, active); "
               "customer(customer_id, store_id, first_name, last_name, email, address_id, active, create_date); "
               "address(address_id, address, district, city_id, postal_code, phone); city(city_id, city, country_id); country(country_id, country); "
               "film(film_id, title, description, release_year, language_id, rental_duration, rental_rate, length, replacement_cost, rating, special_features); "
               "film_category(film_id, category_id); category(category_id, name); film_actor(actor_id, film_id); actor(actor_id, first_name, last_name); "
               "language(language_id, name); inventory(inventory_id, film_id, store_id); "
               "rental(rental_id, rental_date, inventory_id, customer_id, return_date, staff_id); "
               "payment(payment_id, customer_id, staff_id, rental_id, amount, payment_date). "
               "Dates are 'YYYY-MM-DD HH:MM:SS' text; compare with strings. Use standard SQL (no || concatenation, no DATE_FORMAT/strftime).")


def run_sql_query(sql: str, max_rows: int = 50) -> dict:
    """Run ONE read-only SELECT against Sakila and return up to `max_rows` rows."""
    q = "\n".join(l for l in (sql or "").splitlines() if not l.strip().startswith("--")).strip().rstrip(";").strip()
    q = re.sub(r"--[^\n]*", "", q)
    if not re.match(r"^(select|with)\b", q, re.I) or ";" in q or _FORBIDDEN.search(q):
        return {"error": "Only a single read-only SELECT (or WITH ... SELECT) statement is allowed."}
    try:
        df = db.query(f"SELECT * FROM ({q}) AS _q LIMIT {max(1, min(int(max_rows), 200))}")
    except Exception as e:
        return {"error": f"SQL error: {str(e).splitlines()[0][:300]}", "schema": SCHEMA_HINT}
    return _clean({"columns": list(df.columns), "rows": df.to_dict(orient="records"), "row_count": int(len(df)),
                   "note": "Covers ALL data unless you filter; the dashboard's analysis window is rental_date < '2006-01-01'."})


# ---------------------------------------------------------------------------
# Tools 7-10: the team's six insights, data limitations, trends, charts
# ---------------------------------------------------------------------------
def get_insights(insight_id: int | None = None, detail: bool = True) -> dict:
    """All six report insights (summary) or one insight in full detail."""
    if insight_id in (None, 0, "", "all"):
        return _clean(ins.all_insights(detail=False))
    i = int(insight_id)
    if i not in ins.INSIGHTS:
        return {"error": "insight_id must be 1-6", "count": len(ins.INSIGHTS)}
    x = ins.INSIGHTS[i]()
    keep = x if detail else {k: x[k] for k in ("id", "title", "verified_findings")}
    return _clean(keep)


def get_data_limitations(topic: str | None = None) -> dict:
    return ins.data_limitations(topic)


def get_trends(granularity: str = "month") -> dict:
    return _clean(ins.trends(granularity))


def visualize(chart_ids: list[str] | str) -> dict:
    ids = [chart_ids] if isinstance(chart_ids, str) else list(chart_ids or [])
    out, bad = [], []
    for cid in ids[:8]:
        if cid in ch.CHARTS:
            out.append({"chart_id": cid, "plotly": ch.CHARTS[cid]()})
        else:
            bad.append(cid)
    res = {"rendered": [c["chart_id"] for c in out], "charts": out,
           "note": "Charts are rendered in the app below your answer; describe what each shows using tool numbers."}
    if bad:
        res["unknown_chart_ids"] = bad
        res["available_chart_ids"] = sorted(ch.CHARTS)
    return res


# ---------------------------------------------------------------------------
# Registry + LLM schemas
# ---------------------------------------------------------------------------
TOOLS: dict[str, Callable[..., dict]] = {
    "get_customer_history": get_customer_history,
    "get_category_transitions": get_category_transitions,
    "get_customer_recommendation": get_customer_recommendation,
    "search_movies": search_movies,
    "get_business_metrics": get_business_metrics,
    "run_sql_query": run_sql_query,
    "get_insights": get_insights,
    "get_data_limitations": get_data_limitations,
    "get_trends": get_trends,
    "visualize": visualize,
}


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_insights",
        "description": "The team report's SIX insights, recomputed from the database: 1 rental-duration policy vs holding time, "
                       "2 category loyalty vs switching, 3 DVDs held at checkout / zero state / reactivation, 4 category transitions & lift, "
                       "5 hybrid buyers / baskets / price tiers / bundling, 6 inventory copies vs rentals productivity. "
                       "No insight_id = list of all six with key findings. With insight_id = full detail: verified findings, report_check "
                       "(where the written report over-claims), metrics_to_watch with definitions, caveats, hypotheses, follow_up_sql.",
        "parameters": {"type": "object", "properties": {
            "insight_id": {"type": "integer", "description": "1-6; omit for all"}, "detail": {"type": "boolean"}}}}},
    {"type": "function", "function": {
        "name": "get_data_limitations",
        "description": "What the Sakila data CANNOT show (chronology gap, visits, demographics, causality, unmet demand, costs/profit, "
                       "ratings, staff/store attribution, actors, churn, forecasting, BCG). Call before answering any question about causes, "
                       "predictions, profit, customers' motives, demographics, visits, churn or market share.",
        "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "get_trends",
        "description": "Rentals, revenue and active customers by month, quarter or year, with the 174-day gap and missing months flagged.",
        "parameters": {"type": "object", "properties": {"granularity": {"type": "string", "enum": ["month", "quarter", "year"]}}}}},
    {"type": "function", "function": {
        "name": "visualize",
        "description": "Render verified charts in the app. chart_ids from: insight_1, hold_days, insight_2, insight_3, prior_open, insight_4, "
                       "transition_heatmap, insight_5, price_tiers, insight_6, monthly_trend_with_gap, category_share, stores, customer_segments.",
        "parameters": {"type": "object", "properties": {"chart_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["chart_ids"]}}},
    {"type": "function", "function": {
        "name": "run_sql_query",
        "description": "Run ONE read-only SQL SELECT on the Sakila database for facts the other tools do not cover "
                       "(stores/branches, staff, actors, addresses, late returns, replacement cost, specific counts...). "
                       + SCHEMA_HINT,
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string", "description": "a single SELECT statement"},
            "max_rows": {"type": "integer"}}, "required": ["sql"]}}},
    {"type": "function", "function": {
        "name": "get_customer_history",
        "description": "Get a customer's profile, rental count and chronological rental journey (titles, categories, dates, repeat/switch flags).",
        "parameters": {"type": "object", "properties": {
            "customer_id": {"type": "integer", "description": "Sakila customer_id (1-599)"},
            "max_rentals": {"type": "integer", "description": "How many most-recent rentals to list (default 50)"}},
            "required": ["customer_id"]}}},
    {"type": "function", "function": {
        "name": "get_category_transitions",
        "description": "Category transition statistics from all customers' consecutive rentals. direction='outgoing' answers 'where do customers go after X?'; direction='incoming' answers 'which categories lead to X / strongest transition to X?'.",
        "parameters": {"type": "object", "properties": {
            "category_name": {"type": "string", "description": "Film category name, e.g. Action, Comedy, Sci-Fi"},
            "direction": {"type": "string", "enum": ["outgoing", "incoming"]},
            "top_n": {"type": "integer"}},
            "required": ["category_name"]}}},
    {"type": "function", "function": {
        "name": "get_customer_recommendation",
        "description": "Data-driven next-category and movie recommendation for a customer, with every input needed to explain it (transition probability, lift, customer affinity, weights, signal strength).",
        "parameters": {"type": "object", "properties": {
            "customer_id": {"type": "integer"},
            "n_movies": {"type": "integer", "description": "number of movies (default 5)"},
            "exploration_mode": {"type": "boolean", "description": "true = exclude the customer's current category"}},
            "required": ["customer_id"]}}},
    {"type": "function", "function": {
        "name": "search_movies",
        "description": "Search the Sakila film catalogue (also for shoppers: 'I want a scary movie'). category accepts a Sakila category or an everyday genre word such as 'history' or 'kids' (mapped to the closest categories, with a genre_note). keyword searches title and description. Returns films with rating, price, popularity, stock and description.",
        "parameters": {"type": "object", "properties": {
            "category": {"type": "string"}, "title": {"type": "string"},
            "keyword": {"type": "string", "description": "word to find in title or description, e.g. 'Ancient', 'Shark'"},
            "rating": {"type": "string", "enum": ["G", "PG", "PG-13", "R", "NC-17"]},
            "available_only": {"type": "boolean"}, "limit": {"type": "integer"},
            "sort_by": {"type": "string", "enum": ["popularity", "title", "rental_rate", "length"]}}}}},
    {"type": "function", "function": {
        "name": "get_business_metrics",
        "description": "Business KPIs and analysis results computed from Sakila. Use metric_name='key_insights' for any request for "
                       "insights / findings / summary: it returns pre-verified insights with evidence and caveats. "
                       "'revenue_breakdown' = base rental fees vs late fees; 'inventory_utilization' = copies vs rentals; 'stores' = the 2 branches.",
        "parameters": {"type": "object", "properties": {
            "metric_name": {"type": "string", "enum": sorted(METRICS)}},
            "required": ["metric_name"]}}},
]


def call_tool(name: str, arguments: dict | str | None) -> dict:
    if name not in TOOLS:
        return {"error": f"Unknown tool {name}"}
    if isinstance(arguments, str):
        arguments = json.loads(arguments or "{}")
    arguments = {k: v for k, v in (arguments or {}).items() if v is not None}
    try:
        return TOOLS[name](**arguments)
    except TypeError as e:
        return {"error": f"Bad arguments for {name}: {e}"}
    except Exception as e:  # surface as data so the agent can report it honestly
        return {"error": f"{type(e).__name__}: {e}"}
