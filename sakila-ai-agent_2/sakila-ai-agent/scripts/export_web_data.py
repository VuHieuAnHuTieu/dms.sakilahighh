"""Export every number the web (artifact) version needs into web/data.json.
Heavy statistics (permutation tests, chi-square, backtest) are computed here in Python;
the web page recomputes recommendations live from the exported matrix + histories."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import analytics as an  # noqa: E402
from src import database as db  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.tools import GENRE_SYNONYMS, KID_WORDS, THEME_KEYWORDS, _clean  # noqa: E402
from src import insights as ins  # noqa: E402
from knowledge.testbank import TESTBANK  # noqa: E402

cats = list(an.categories())
ci = {c: i for i, c in enumerate(cats)}
ev = an.rental_events()
fc = an.film_catalog()
films = {int(r.film_id): [r.title, ci[r.category], r.rating, float(r.rental_rate), int(r.length),
                          int(r.rentals_in_window), int(r.copies), int(r.available_copies), r.description] for r in fc.itertuples()}
prof = db.query("""SELECT cu.customer_id, cu.first_name, cu.last_name, ci.city, co.country
FROM customer cu JOIN address a ON a.address_id=cu.address_id JOIN city ci ON ci.city_id=a.city_id
JOIN country co ON co.country_id=ci.country_id""")
seen_all = db.query("SELECT r.customer_id, i.film_id FROM rental r JOIN inventory i ON i.inventory_id=r.inventory_id")
customers = {}
for cid, g in ev.groupby("customer_id"):
    p = prof[prof.customer_id == cid].iloc[0]
    in_window = set(g.film_id)
    extra = sorted(set(seen_all[seen_all.customer_id == cid].film_id) - in_window)
    customers[int(cid)] = {
        "n": f"{p.first_name.title()} {p.last_name.title()}", "loc": f"{p.city}, {p.country}",
        "r": [[int(f), d.strftime("%Y-%m-%d %H:%M"), round(float(a), 2)] for f, d, a in zip(g.film_id, g.rental_date, g.amount)],
        "x": [int(x) for x in extra],
    }
cs = an.customer_summary().set_index("customer_id")
data = {
    "categories": cats,
    "settings": {"end": get_settings().analysis_end_date, "w_t": get_settings().w_transition, "w_a": get_settings().w_affinity},
    "headline": an.headline_metrics(),
    "monthly": an.monthly_trend(),
    "daily": an.daily_trend(),
    "category_perf": an.category_performance(),
    "return": an.customer_return_stats(),
    "repetition": an.repetition_stats(),
    "diversity": an.category_diversity(),
    "discovery": an.discovery_curve(),
    "counts": an.transition_counts().values.tolist(),
    "independence": an.independence_test(),
    "high_transition": an.high_transition_table(),
    "gateway": an.gateway_assessment(),
    "backtest": an.next_category_backtest(),
    "films": films,
    "customers": customers,
    "stores": an.store_summary(),
    "team_insights": [ins.INSIGHTS[i]() for i in range(1, 7)],
    "limits": [{"topic": t, "limitation": d} for t, d in ins.DATA_LIMITS],
    "trends": {g: ins.trends(g) for g in ("month", "quarter", "year")},
    "chronology": ins.chronology(),
    "segments": ins.customer_segments(),
    "misc": ins.misc_facts(),
    "cat_burst": ins.category_by_burst(),
    "testbank": [{"q": e["q"], "guide": e["guide"], "tools": e["tools"]} for e in TESTBANK],
    "revenue_breakdown": an.revenue_breakdown(),
    "inventory_utilization": an.inventory_utilization(),
    "key_insights": an.key_insights(),
    "outside_window": db.query("""SELECT (SELECT COUNT(*) FROM rental WHERE rental_date >= :d) AS rentals,
        (SELECT ROUND(SUM(amount), 2) FROM payment WHERE payment_date >= :d) AS revenue,
        (SELECT MIN(DATE(rental_date)) FROM rental WHERE rental_date >= :d) AS first_date,
        (SELECT ROUND(SUM(amount), 2) FROM payment) AS all_time_revenue""", {"d": db.window_params()["end_date"]}).iloc[0].to_dict(),
    "genre": {"synonyms": GENRE_SYNONYMS, "themes": THEME_KEYWORDS, "kid_words": sorted(KID_WORDS)},
    "summary": {int(k): [int(v.distinct_categories), round(float(v.repeat_rate), 4), v.top_category, round(float(v.top_category_share), 4)]
                for k, v in cs.iterrows()},
}
out = ROOT / "web" / "data.json"
out.write_text(json.dumps(_clean(data), separators=(",", ":")), encoding="utf-8")
print(out, round(out.stat().st_size / 1024), "KB")
# reference recommendations for parity testing of the JS engine
from src.recommendation import recommend_for_customer  # noqa: E402
ref = {cid: [recommend_for_customer(cid)["recommended_category"], [m["film_id"] for m in recommend_for_customer(cid)["recommended_movies"]],
             recommend_for_customer(cid, exclude_current_category=True)["recommended_category"]] for cid in customers}
(ROOT / "web" / "reference_recs.json").write_text(json.dumps(ref))
