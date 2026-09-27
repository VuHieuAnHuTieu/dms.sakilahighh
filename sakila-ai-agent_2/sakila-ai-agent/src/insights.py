"""The team's six report insights, recomputed from the database (never copied from the report).

Each insight returns: title, business question, verified findings (numbers computed here),
check of the written report's claims, metrics to watch (with definitions), caveats,
recommendations (labelled as hypotheses), follow-up SQL, and data for a chart.

Also: chronology (the 174-day gap), trends by month/quarter/year, behavioural customer
segments, and a fixed list of data limitations used by the AI agent.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import analytics as an
from . import database as db

END = pd.Timestamp("2006-01-01")


@lru_cache(maxsize=1)
def _rentals_all() -> pd.DataFrame:
    """All rentals (no window) with film attributes and payment amount."""
    df = db.query("""
        SELECT r.rental_id, r.customer_id, r.rental_date, r.return_date, r.staff_id, i.store_id,
               f.film_id, f.title, f.rental_duration, f.rental_rate, f.length, f.rating, c.name AS category,
               p.amount
        FROM rental r
        JOIN inventory i ON i.inventory_id = r.inventory_id
        JOIN film f ON f.film_id = i.film_id
        JOIN film_category fc ON fc.film_id = f.film_id
        JOIN category c ON c.category_id = fc.category_id
        LEFT JOIN (SELECT rental_id, SUM(amount) AS amount FROM payment GROUP BY rental_id) p ON p.rental_id = r.rental_id""")
    df["rd"] = pd.to_datetime(df["rental_date"])
    df["rt"] = pd.to_datetime(df["return_date"])
    return df.sort_values(["customer_id", "rd", "rental_id"]).reset_index(drop=True)


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


# ---------------------------------------------------------------------------
# Chronology and trends
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def chronology() -> dict:
    R = _rentals_all()
    days = sorted(R["rd"].dt.normalize().unique())
    bursts, start = [], days[0]
    for a, b in zip(days, days[1:] + [None]):
        if b is None or (b - a).days > 1:
            bursts.append({"from": str(start.date()), "to": str(a.date()), "recorded_days": int((a - start).days) + 1})
            start = b
    win = R[R["rd"] < END]
    after = R[R["rd"] >= END]
    gap = after["rd"].min() - win["rd"].max()
    months = R.groupby(R["rd"].dt.to_period("M")).agg(rentals=("rental_id", "size"),
                                                         recorded_days=("rd", lambda s: s.dt.normalize().nunique()))
    all_months = pd.period_range(months.index.min(), months.index.max(), freq="M")
    missing = [str(m) for m in all_months if m not in months.index]
    return {
        "first_rental": str(R["rd"].min()), "last_rental": str(R["rd"].max()),
        "distinct_rental_dates": len(days),
        "rental_bursts": bursts,
        "pattern": "Rentals are recorded in 8-day bursts separated by ~2-week gaps (May, June, early July, late July/early Aug, mid Aug 2005), then one day in Feb 2006.",
        "gap_days": int(gap.days), "gap_from": str(win["rd"].max()), "gap_to": str(after["rd"].min()),
        "months_with_no_rentals": missing,
        "feb_2006_batch": {"date": str(after["rd"].min().date()), "rentals": int(len(after)),
                           "unreturned": int(after["rt"].isna().sum()),
                           "note": "All rentals of this single day were never returned; treated as an anomalous batch and excluded from behavioural analysis. Its cause (e.g. Valentine's Day) cannot be inferred."},
        "last_return_recorded": str(R["rt"].max()),
    }


def trends(granularity: str = "month") -> dict:
    R = _rentals_all()
    per = {"month": "M", "quarter": "Q", "year": "Y"}.get(granularity, "M")
    g = R.groupby(R["rd"].dt.to_period(per)).agg(rentals=("rental_id", "size"), revenue=("amount", "sum"),
                                                     active_customers=("customer_id", "nunique"),
                                                     recorded_days=("rd", lambda s: s.dt.normalize().nunique()))
    full = pd.period_range(g.index.min(), g.index.max(), freq=per)
    g = g.reindex(full).fillna(0)
    g["rentals_per_recorded_day"] = (g["rentals"] / g["recorded_days"].replace(0, np.nan)).round(1)
    rows = [{"period": str(p), "rentals": int(r.rentals), "revenue": round(float(r.revenue), 2),
             "active_customers": int(r.active_customers), "recorded_days": int(r.recorded_days),
             "rentals_per_recorded_day": None if np.isnan(r.rentals_per_recorded_day) else float(r.rentals_per_recorded_day),
             "has_data": bool(r.recorded_days > 0)} for p, r in g.iterrows()]
    ch = chronology()
    return {"granularity": granularity, "rows": rows,
            "warning": (f"Data covers only {ch['distinct_rental_dates']} recorded dates. There is a {ch['gap_days']}-day gap "
                        f"({ch['gap_from'][:10]} to {ch['gap_to'][:10]}); months {', '.join(ch['months_with_no_rentals'])} have NO rentals "
                        "(missing data, not zero demand). Month totals mostly reflect how many days were recorded, so growth rates, "
                        "seasonality, quarterly/yearly trends and churn by month cannot be measured reliably. Feb 2006 is a single anomalous day."),
            "chronology": {k: ch[k] for k in ("rental_bursts", "gap_days", "months_with_no_rentals")}}


# ---------------------------------------------------------------------------
# Insight 1 — rental-duration policy vs actual return behaviour
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def insight_1() -> dict:
    R = _rentals_all()
    c = R[R["rt"].notna()].copy()
    c["hold"] = (c["rt"] - c["rd"]).dt.total_seconds() / 86400
    c["cal"] = (c["rt"].dt.normalize() - c["rd"].dt.normalize()).dt.days
    c["late_exact"] = c["hold"] > c["rental_duration"]
    c["gap_cal"] = c["cal"] - c["rental_duration"]
    rows = []
    for d, g in c.groupby("rental_duration"):
        rows.append({"rental_duration": int(d), "completed_rentals": int(len(g)), "avg_actual_hold_days": _r(g["hold"].mean()),
                     "pct_late_exact_time": _r(100 * g["late_exact"].mean()), "pct_early_exact_time": _r(100 * (g["hold"] < d).mean()),
                     "pct_late_calendar_days": _r(100 * (g["gap_cal"] > 0).mean()),
                     "pct_returned_day_4_to_6": _r(100 * g["cal"].between(4, 6).mean()),
                     "late_copy_days": int(g.loc[g["gap_cal"] > 0, "gap_cal"].sum()),
                     "unused_allowance_days": int(-g.loc[g["gap_cal"] < 0, "gap_cal"].sum())})
    dist = c["cal"].value_counts().sort_index()
    by_policy = ", ".join("%d-day %s" % (r["rental_duration"], r["avg_actual_hold_days"]) for r in rows)
    return {
        "id": 1, "title": "Rental-duration policy does not match actual holding time",
        "business_question": "Does the contractual rental duration (3-7 days) match how long customers actually keep DVDs?",
        "verified_findings": [
            f"{len(c):,} completed rentals (all data; {int(R['rt'].isna().sum())} never returned) are kept {c['hold'].mean():.2f} days on average.",
            f"Average holding time is ~5 days for every policy: {by_policy}.",
            f"Holding time is statistically unrelated to the policy (correlation {c[['hold', 'rental_duration']].corr().iloc[0, 1]:.4f}).",
            f"Late share (exact time) falls from {rows[0]['pct_late_exact_time']}% (3-day) to {rows[-1]['pct_late_exact_time']}% (7-day); using calendar days it is {rows[0]['pct_late_calendar_days']}% to {rows[-1]['pct_late_calendar_days']}%.",
            f"Holding days are spread almost UNIFORMLY from 1 to 9 days (each ~{100 * dist.loc[1:9].mean() / len(c):.0f}% of rentals); only ~{100 * c['cal'].between(4, 6).mean():.0f}% are returned on day 4-6. The ~5-day average is the middle of a flat distribution, not a peak.",
            f"Late copy-days beyond contract: {int(c.loc[c['gap_cal'] > 0, 'gap_cal'].sum()):,}; unused allowance days: {int(-c.loc[c['gap_cal'] < 0, 'gap_cal'].sum()):,} (calendar-day basis).",
        ],
        "report_check": [
            "Report's late rates (72.07% for 3-day ... 29.06% for 7-day) are reproduced with the exact-time definition; they are lower with calendar days. Always state the definition.",
            "Report says customers have a 'stable ~5-day rental horizon'. The AVERAGE is ~5 for every policy, but the distribution is flat (1-9 days), so '5 days' is not a typical behaviour; the policy mainly decides who is labelled late.",
            "Why customers return late (e.g. treating late fees as an extension fee) is not observable; it is a hypothesis.",
        ],
        "metrics_to_watch": {"avg_actual_hold_days": "mean (return_date - rental_date) in days", "pct_late": "share of rentals kept longer than rental_duration (state exact-time or calendar-day definition)",
                             "late_copy_days": "sum of days beyond contract = inventory time locked by late rentals", "unused_allowance_days": "contract days not used by early returns",
                             "pct_returned_day_4_to_6": "concentration around 5 days (tests the '5-day horizon' claim)"},
        "caveats": ["A customer is 'late' because the policy threshold is exceeded: the same holding time is late under 3 days and early under 7 days (policy exposure, not worse behaviour).",
                    "Changing all durations to 5 days would change the labels, but the effect on real returns is a counterfactual that the data cannot show (Lucas critique: behaviour may change under a new policy).",
                    "Lost revenue from late returns is not observed (no record of customers who could not rent)."],
        "recommendations_hypotheses": ["Test (A/B, one store or a subset of titles) a pre-due-date extension option priced below the late fee, and measure late_copy_days and availability.",
                                       "Track actual holding time alongside the contract, by title demand level."],
        "follow_up_sql": """SELECT f.rental_duration,
       COUNT(*) AS completed_rentals,
       AVG((julianday(r.return_date) - julianday(r.rental_date))) AS avg_hold_days,   -- MySQL: TIMESTAMPDIFF(SECOND, r.rental_date, r.return_date)/86400
       100.0 * SUM(CASE WHEN julianday(r.return_date) - julianday(r.rental_date) > f.rental_duration THEN 1 ELSE 0 END) / COUNT(*) AS pct_late
FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id JOIN film f ON f.film_id = i.film_id
WHERE r.return_date IS NOT NULL
GROUP BY f.rental_duration ORDER BY f.rental_duration;""",
        "table": rows,
        "hold_day_distribution": {int(k): int(v) for k, v in dist.items()},
    }


# ---------------------------------------------------------------------------
# Insight 2 — customer loyalty does not translate into category loyalty
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def insight_2() -> dict:
    rp, dv, rs = an.repetition_stats(), an.category_diversity(), an.customer_return_stats()
    ev = an.rental_events()
    seqs = ev.groupby("customer_id")["category"].apply(list)
    first_two = [s for s in seqs if len(s) >= 3 and s[0] == s[1]]
    third_same = sum(s[2] == s[1] for s in first_two)
    return {
        "id": 2, "title": "Customer loyalty (returning) does not translate into category loyalty",
        "business_question": "When customers come back, do they stay in the same category?",
        "verified_findings": [
            f"All {rs['customers_with_rentals']} customers return (min {rs['rentals_per_customer_min']}, median {rs['rentals_per_customer_median']:.0f} rentals).",
            f"{rp['switch_pct']}% of {rp['transitions']:,} consecutive rentals switch category; {rp['repeat_pct']}% repeat.",
            f"Rental 2 repeats rental 1's category in {rp['second_rental_same_category_pct']}% of customers; of the {len(first_two)} customers whose first two rentals share a category, {third_same} continue on rental 3.",
            f"Median customer has rented {dv['median_distinct_categories']:.0f} of 16 categories; {dv['pct_customers_10plus_categories']:.0f}% have rented 10+.",
            f"Chance benchmark: random choice gives {rp['random_choice_repeat_pct']}% repeats; shuffling each customer's own history gives {rp['shuffled_sequence_repeat_pct']}% (permutation p = {rp['shuffled_repeat_p_value']}). Repetition is only slightly above chance.",
        ],
        "report_check": ["'Customers want exploration' is an interpretation: the switching rate is close to what random choice among 16 evenly-demanded categories produces.",
                         "Loyalty must be defined: store loyalty (returning) is 100%; category loyalty (repeat) is low."],
        "metrics_to_watch": {"repeat_pct": "consecutive rentals in the same category", "switch_pct": "consecutive rentals changing category",
                             "distinct_categories_per_customer": "category diversity", "random_choice_repeat_pct": "chance benchmark"},
        "caveats": ["Low repetition does not mean categories have no value; it means the previous category is a weak predictor.",
                    "Same-timestamp rentals are ordered by rental_id (tie-breaker)."],
        "recommendations_hypotheses": ["Promote discovery across categories rather than 'more of the same' genre.", "Define loyalty KPIs separately: store retention vs category affinity."],
        "follow_up_sql": """WITH seq AS (
  SELECT r.customer_id, c.name AS category,
         LAG(c.name) OVER (PARTITION BY r.customer_id ORDER BY r.rental_date, r.rental_id) AS prev_category
  FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id
  JOIN film_category fc ON fc.film_id = i.film_id JOIN category c ON c.category_id = fc.category_id
  WHERE r.rental_date < '2006-01-01')
SELECT 100.0 * SUM(CASE WHEN category = prev_category THEN 1 ELSE 0 END) / COUNT(*) AS repeat_pct
FROM seq WHERE prev_category IS NOT NULL;""",
    }


# ---------------------------------------------------------------------------
# Insight 3 — holdings, zero state and reactivation
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def insight_3() -> dict:
    R = _rentals_all()
    rec_dates = np.array(sorted(R.loc[R["rd"] < END, "rd"].dt.normalize().unique()))
    prior, episodes = [], []
    for cid, g in R.groupby("customer_id", sort=False):
        rd, rt = g["rd"].to_numpy(), g["rt"].to_numpy()
        ids = g["rental_id"].to_numpy()
        rt_open = np.where(pd.isna(rt), np.datetime64("2100-01-01"), rt)
        win = rd < np.datetime64(END)
        # DVDs already held at each checkout (other rentals started before and not yet returned)
        held = (rd[None, :] < rd[:, None]) & (rt_open[None, :] > rd[:, None]) & (ids[None, :] != ids[:, None])
        prior.extend(held.sum(axis=1)[win].tolist())
        # zero-state entries: return events after which nothing is held
        for t in np.unique(rt[~pd.isna(rt) & (rt < np.datetime64(END))]):
            if ((rd < t) & (rt_open > t)).any():
                continue
            nxt = rd[(rd > t) & win]
            episodes.append((cid, t, nxt.min() if len(nxt) else None))
    pr = pd.Series(prior)
    E = pd.DataFrame(episodes, columns=["customer_id", "zero_time", "next_rental"])
    E["zero_time"] = pd.to_datetime(E["zero_time"])
    E["next_rental"] = pd.to_datetime(E["next_rental"])
    r = E[E["next_rental"].notna()].copy()
    r["days"] = (r["next_rental"] - r["zero_time"]).dt.total_seconds() / 86400
    zd, nd = r["zero_time"].dt.normalize().to_numpy(), r["next_rental"].dt.normalize().to_numpy()
    r["recorded_step"] = [int(((rec_dates > a) & (rec_dates <= b)).sum()) for a, b in zip(zd, nd)]
    buckets = pd.cut(r["days"], [-1, 1, 3, 7, 14, 30, 1e9], labels=["<=1 day", "1-3 days", "3-7 days", "7-14 days", "14-30 days", ">30 days"])
    cal = (buckets.value_counts(normalize=True).sort_index() * 100).round(2)
    cum = {f"by_{k}_recorded_date": _r(100 * (r["recorded_step"] <= k).mean()) for k in (1, 2, 3, 4)}
    disagree = r[(r["recorded_step"] <= 4) != (r["days"] <= 14)]
    return {
        "id": 3, "title": "Customers rent while still holding DVDs; zero holdings are a repeated pause, not churn",
        "business_question": "How many DVDs do customers hold when they rent again, and how quickly do they come back after returning everything?",
        "verified_findings": [
            f"At {len(pr):,} checkouts (window) customers already hold {pr.mean():.2f} DVDs on average; {100 * (pr > 0).mean():.2f}% of checkouts happen while holding at least one (0: {100 * (pr == 0).mean():.2f}%, 1: {100 * (pr == 1).mean():.2f}%, 2: {100 * (pr == 2).mean():.2f}%, 3+: {100 * (pr >= 3).mean():.2f}%).",
            f"{len(E):,} zero-holding episodes across {E['customer_id'].nunique()} customers; {len(r):,} are followed by another rental inside the window and {int(E['next_rental'].isna().sum())} are censored (no later data), not churn.",
            f"Calendar clock: {cal.get('7-14 days', 0)}% of reactivations happen 7-14 days later.",
            f"Recorded-date clock (counting only dates with any rental): {cum['by_1_recorded_date']}% by the 1st, {cum['by_2_recorded_date']}% by the 2nd, {cum['by_3_recorded_date']}% by the 3rd, {cum['by_4_recorded_date']}% by the 4th recorded date.",
            f"The two clocks classify {len(disagree)} episodes ({disagree['customer_id'].nunique()} customers) differently (early = within 4 recorded dates vs within 14 calendar days).",
        ],
        "report_check": ["Report's 2.44 average, 3,208 episodes and 67.93% (7-14 days) are reproduced.",
                         "The 7-14 day 'wait' is largely an artefact of the data: rentals were recorded in 8-day bursts separated by ~2-week gaps, so a return near the end of a burst can only be followed by a rental in the next burst.",
                         "Holding 3 DVDs does not CAUSE more visits; the association is observational. The mean (2.44) is not an optimal target."],
        "metrics_to_watch": {"avg_prior_open_rentals": "DVDs already held at checkout (interval reconstruction)", "zero_state_episodes": "returns that leave the customer holding nothing",
                             "reactivation_by_recorded_date": "share of reactivations within k recorded dates", "censored_episodes": "zero states with no later observation (not churn)"},
        "caveats": ["Zero holdings is not churn; churn cannot be observed in a finite, censored dataset.",
                    "Episodes are not unique customers (a customer can have many episodes).",
                    "The 174-day gap and 2-week gaps between bursts distort calendar-day measures."],
        "recommendations_hypotheses": ["When a customer is down to 1 open DVD, show 2-3 next-title suggestions at return; test with a control group."],
        "follow_up_sql": """-- DVDs held at each checkout (interval reconstruction)
SELECT cur.rental_id, COUNT(prev.rental_id) AS prior_open_rentals
FROM rental cur
LEFT JOIN rental prev ON prev.customer_id = cur.customer_id AND prev.rental_id <> cur.rental_id
     AND prev.rental_date < cur.rental_date AND (prev.return_date IS NULL OR prev.return_date > cur.rental_date)
WHERE cur.rental_date < '2006-01-01'
GROUP BY cur.rental_id;""",
        "prior_open_distribution": {str(k): int(v) for k, v in pr.clip(upper=5).value_counts().sort_index().items()},
        "calendar_buckets_pct": {str(k): float(v) for k, v in cal.items()},
        "recorded_date_cumulative_pct": cum,
    }


# ---------------------------------------------------------------------------
# Insight 4 — customer journey and category transitions
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def insight_4() -> dict:
    it = an.independence_test()
    top = an.top_transitions(5, sort_by="lift")
    t = an.transitions_df()
    sw = t[~t["is_repeat"]]
    base = an.rental_events()["category"].value_counts(normalize=True)
    ct = pd.crosstab(sw["prev_category"], sw["category"])
    lift_sw = ct.div(ct.sum(axis=1), axis=0).div(base, axis=1).stack().sort_values(ascending=False).head(5)
    bt = an.next_category_backtest()
    return {
        "id": 4, "title": "Category transitions: the strongest routes are weak signals",
        "business_question": "After category A, is category B disproportionately likely next (lift), and is it usable for bundles/recommendations?",
        "verified_findings": [
            "Top lifts (all next rentals as denominator): " + "; ".join(f"{r.from_category}->{r.to_category} lift {r.lift:.2f} ({int(r.transitions)} transitions, z {r.z_residual:.2f})" for r in top.itertuples()) + ".",
            "Report's definition (switches only as denominator) gives: " + "; ".join(f"{a}->{b} {v:.2f}" for (a, b), v in lift_sw.items()) + ". Same pairs, higher values because repeats are removed from the denominator.",
            f"Whole matrix: chi-square p = {it['p_value']}, Cramer's V = {it['cramers_v']}; {it['cells_abs_z_gt_1_96']} of 256 pairs exceed |z| 1.96 (~13 expected by chance); {it['cells_significant_after_bonferroni']} survive Bonferroni.",
            f"Hold-out test: transition-based top-3 hit rate {bt['transition_only_hit@3_pct']}% vs random {bt['random_hit@3_pct']}%.",
        ],
        "report_check": ["Games->Action lift ~1.4 is reproduced under the report's definition, but it is not statistically distinguishable from chance after multiple-comparison correction.",
                         "Lift 1.4 means B is 1.4 times as likely as its baseline share, NOT that 140% of customers rent B.",
                         "Lift is association, not causation (A does not make customers want B).",
                         "Each Sakila film has exactly one category (film_category is one-to-one here)."],
        "metrics_to_watch": {"transition_probability": "P(B|A) = count(A->B)/count(A->any)", "lift": "P(B|A) / share of B (controls for B's popularity)",
                             "z_residual": "deviation from independence; judge against multiple comparisons", "hit@3": "hold-out predictive accuracy"},
        "caveats": ["Use lift, not raw counts (raw counts favour big categories).", "With 256 pairs some high lifts appear by chance."],
        "recommendations_hypotheses": ["Treat high-lift pairs as candidates for a small bundle/placement test, not as proven demand routes."],
        "follow_up_sql": """WITH seq AS (
  SELECT r.customer_id, c.name AS category,
         LAG(c.name) OVER (PARTITION BY r.customer_id ORDER BY r.rental_date, r.rental_id) AS prev_category
  FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id
  JOIN film_category fc ON fc.film_id = i.film_id JOIN category c ON c.category_id = fc.category_id
  WHERE r.rental_date < '2006-01-01'),
pairs AS (SELECT prev_category AS a, category AS b, COUNT(*) AS n FROM seq WHERE prev_category IS NOT NULL GROUP BY prev_category, category),
out_a AS (SELECT a, SUM(n) AS n_a FROM pairs GROUP BY a),
share_b AS (SELECT b, 1.0 * SUM(n) / (SELECT SUM(n) FROM pairs) AS share FROM pairs GROUP BY b)
SELECT p.a AS from_category, p.b AS to_category, p.n AS transitions,
       1.0 * p.n / o.n_a AS p_b_given_a, (1.0 * p.n / o.n_a) / s.share AS lift
FROM pairs p JOIN out_a o ON o.a = p.a JOIN share_b s ON s.b = p.b
WHERE p.a <> p.b
ORDER BY lift DESC;""",
    }


# ---------------------------------------------------------------------------
# Insight 5 — price tiers, hybrid buyers, baskets, bundling
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def insight_5() -> dict:
    R = _rentals_all()
    seg = R.groupby("customer_id")["rental_rate"].apply(lambda s: "pure_0.99" if (s == 0.99).all() else ("hybrid" if (s == 0.99).any() else "no_0.99"))
    R = R.assign(day=R["rd"].dt.date)
    V = R.groupby(["customer_id", "day"]).agg(discs=("rental_id", "size"), value=("rental_rate", "sum"), n099=("rental_rate", lambda s: (s == 0.99).sum()))
    v = V[V["n099"] > 0]
    bask = v.groupby("discs").agg(visits=("value", "size"), avg_value=("value", "mean"))
    bask["pct"] = 100 * bask["visits"] / bask["visits"].sum()
    tiers = R.groupby("rental_rate").agg(rentals=("rental_id", "size"), titles=("film_id", "nunique"))
    tiers["rentals_per_title"] = tiers["rentals"] / tiers["titles"]
    single = bask.loc[1]
    return {
        "id": 5, "title": "Every customer is a hybrid buyer; demand per title is similar across price tiers",
        "business_question": "Are $0.99 renters bargain hunters, and is there room to bundle single $0.99 'visits' into bigger baskets?",
        "verified_findings": [
            f"Customer segments by price tiers used: {seg.value_counts().to_dict()} (all customers mix $0.99 with $2.99/$4.99 titles).",
            f"Same-day 'visits' containing a $0.99 title: {int(bask['visits'].sum()):,}; {single['pct']:.2f}% are a single $0.99 disc; 2-disc visits average ${bask.loc[2, 'avg_value']:.2f} list value.",
            "Rentals per title by price: " + ", ".join(f"${p}: {r.rentals_per_title:.2f}" for p, r in tiers.iterrows()) + " (nearly equal).",
        ],
        "report_check": ["A 'visit' is approximated as customer + calendar date; Sakila has no visit/basket id, so basket figures are a heuristic.",
                         "Report text says 48.67% of visits have 'three or more' rentals; it is two or more.",
                         "Equal demand across fixed price tiers is NOT a price-elasticity estimate: each title has one fixed price, and price is confounded with the title.",
                         "The $250 bundle upside in the report is an assumption-based illustration, not a forecast."],
        "metrics_to_watch": {"single_0.99_visit_share": "same-day visits with only one $0.99 disc", "avg_visit_value": "sum of rental_rate per same-day visit",
                             "rentals_per_title_by_tier": "demand per title at each fixed price"},
        "caveats": ["Lucas critique: behaviour observed under today's fixed prices and no bundles may change once bundles/combos exist, so historical ratios cannot predict the effect of a new pricing policy.",
                    "No cost data: profit/margin of a bundle cannot be computed; replacement_cost is not acquisition cost."],
        "recommendations_hypotheses": ["Pilot a combo (e.g. 2 same-category $0.99 titles priced between $0.99 and $1.98, the report's example is $1.49) in one store or period; compare basket size, revenue per visit and availability with a control group before rollout."],
        "follow_up_sql": """SELECT customer_id, DATE(rental_date) AS visit_day, COUNT(*) AS discs,
       SUM(f.rental_rate) AS visit_value
FROM rental r JOIN inventory i ON i.inventory_id = r.inventory_id JOIN film f ON f.film_id = i.film_id
GROUP BY customer_id, DATE(rental_date);""",
        "basket_table": [{"discs": int(k), "visits": int(r.visits), "pct": _r(r.pct), "avg_value": _r(r.avg_value)} for k, r in bask.iterrows()],
        "price_tiers": [{"rental_rate": float(p), "rentals": int(r.rentals), "titles": int(r.titles), "rentals_per_title": _r(r.rentals_per_title)} for p, r in tiers.iterrows()],
    }


# ---------------------------------------------------------------------------
# Insight 6 — inventory availability and productivity
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def insight_6() -> dict:
    R = _rentals_all()
    films = db.query("SELECT f.film_id, f.title, c.name AS category, COUNT(i.inventory_id) AS copies FROM film f "
                     "JOIN film_category fc ON fc.film_id = f.film_id JOIN category c ON c.category_id = fc.category_id "
                     "LEFT JOIN inventory i ON i.film_id = f.film_id GROUP BY f.film_id, f.title, c.name")
    agg = R.groupby("film_id").agg(rentals=("rental_id", "size"), revenue=("amount", "sum"))
    F = films.merge(agg, on="film_id", how="left").fillna({"rentals": 0, "revenue": 0})
    S = F[F["copies"] > 0].copy()
    S["productivity"] = S["rentals"] / S["copies"]
    rho, p = spearmanr(S["copies"], S["rentals"])
    S["quartile"] = pd.qcut(S["productivity"].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
    q = S.groupby("quartile", observed=True).agg(films=("film_id", "size"), copies=("copies", "sum"), rentals=("rentals", "sum"), revenue=("revenue", "sum"))
    q["rentals_per_copy"] = q["rentals"] / q["copies"]
    by_copies = S.groupby("copies")["productivity"].mean()
    cat = S.groupby("category").agg(copies=("copies", "sum"), rentals=("rentals", "sum"))
    cat["rentals_per_copy"] = cat["rentals"] / cat["copies"]
    cat = cat.sort_values("rentals_per_copy", ascending=False)
    return {
        "id": 6, "title": "Rentals track the number of copies; productivity differs by film",
        "business_question": "Do films with more copies get more rentals, and are copies used equally productively?",
        "verified_findings": [
            f"{len(S)} of {len(F)} films have copies ({int((F['copies'] == 0).sum())} have none, so their zero rentals mean 'not stocked', not 'unpopular').",
            f"Spearman correlation copies vs rentals: rho = {rho:.3f} (p < 0.001) - strong association.",
            "Productivity quartiles (rentals per copy): " + "; ".join(f"{k}: {r.rentals_per_copy:.2f} ({int(r.copies)} copies, {int(r.rentals)} rentals)" for k, r in q.iterrows()) + ".",
            "Average rentals per copy barely changes with the number of copies: " + ", ".join(f"{int(k)} copies {v:.2f}" for k, v in by_copies.items()) + " - rentals rise almost proportionally with copies.",
            f"Rentals per copy by category range from {cat['rentals_per_copy'].min():.2f} ({cat.index[-1]}) to {cat['rentals_per_copy'].max():.2f} ({cat.index[0]}).",
        ],
        "report_check": ["Report's rho 0.935 is reproduced; quartile totals differ slightly because of tie handling.",
                         "Association, not causation: films with more demand may have been given more copies; adding copies is not proven to add rentals.",
                         "Rentals per copy is a utilisation proxy; unmet demand, costs and profit are not in the data, so 'which category to buy more of' cannot be concluded from it alone."],
        "metrics_to_watch": {"rentals_per_copy": "rentals / physical copies (utilisation proxy)", "films_with_no_copies": "catalogue titles that cannot be rented",
                             "spearman_rho": "rank association copies vs rentals"},
        "caveats": ["A film with zero rentals may simply have no copies or short observation.", "Removal/purchase decisions need costs and unmet demand, which are not recorded."],
        "recommendations_hypotheses": ["Review high-productivity/low-copy films for a small copy increase and measure the change; review low-productivity/high-copy films before any reduction."],
        "follow_up_sql": """SELECT f.film_id, f.title, COUNT(DISTINCT i.inventory_id) AS copies, COUNT(r.rental_id) AS rentals,
       1.0 * COUNT(r.rental_id) / NULLIF(COUNT(DISTINCT i.inventory_id), 0) AS rentals_per_copy
FROM film f LEFT JOIN inventory i ON i.film_id = f.film_id LEFT JOIN rental r ON r.inventory_id = i.inventory_id
GROUP BY f.film_id, f.title ORDER BY rentals_per_copy DESC;""",
        "quartiles": [{"quartile": str(k), "films": int(r.films), "copies": int(r.copies), "rentals": int(r.rentals), "revenue": _r(r.revenue), "rentals_per_copy": _r(r.rentals_per_copy)} for k, r in q.iterrows()],
        "category_utilisation": [{"category": k, "copies": int(r.copies), "rentals": int(r.rentals), "rentals_per_copy": _r(r.rentals_per_copy)} for k, r in cat.iterrows()],
    }


INSIGHTS = {1: insight_1, 2: insight_2, 3: insight_3, 4: insight_4, 5: insight_5, 6: insight_6}


def all_insights(detail: bool = False) -> dict:
    items = [INSIGHTS[i]() for i in sorted(INSIGHTS)]
    if not detail:
        items = [{k: v for k, v in x.items() if k in ("id", "title", "business_question", "verified_findings")} for x in items]
    return {"count": len(items), "insights": items,
            "note": "Six insights from the team report, recomputed from the database. Ask for one insight_id for metrics, caveats, SQL and report checks."}


# ---------------------------------------------------------------------------
# Behavioural customer segments (no demographics exist in Sakila)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def customer_segments() -> dict:
    R = _rentals_all()
    W = R[R["rd"] < END].copy()
    W["late"] = ((W["rt"] - W["rd"]).dt.total_seconds() / 86400) > W["rental_duration"]
    c = W.groupby("customer_id").agg(rentals=("rental_id", "size"), revenue=("amount", "sum"), late_share=("late", "mean"),
                                      categories=("category", "nunique"))
    hi_f, hi_l = c["rentals"] >= c["rentals"].median(), c["late_share"] >= c["late_share"].median()
    names = {(True, False): "Frequent & punctual", (True, True): "Frequent & often late",
             (False, False): "Occasional & punctual", (False, True): "Occasional & often late"}
    c["segment"] = [names[(a, b)] for a, b in zip(hi_f, hi_l)]
    s = c.groupby("segment").agg(customers=("rentals", "size"), avg_rentals=("rentals", "mean"), avg_revenue=("revenue", "mean"),
                                 avg_late_share_pct=("late_share", lambda x: 100 * x.mean()), avg_categories=("categories", "mean"))
    return {"method": f"Behavioural 2x2 split at the medians: rentals (median {c['rentals'].median():.0f}) and share of rentals returned late (median {100 * c['late_share'].median():.1f}%).",
            "segments": [{"segment": k, **{kk: _r(vv) if kk != "customers" else int(vv) for kk, vv in r.items()}} for k, r in s.iterrows()],
            "caveat": "Sakila has NO age, gender, income or lifestyle data, so these are behavioural segments, not demographic personas. Any persona name or story beyond these numbers is illustrative."}


# ---------------------------------------------------------------------------
# Data limitations the agent must respect (mapped to the question bank)
# ---------------------------------------------------------------------------
DATA_LIMITS = [
    ("chronology", "Rentals exist only on 41 dates: five 8-day bursts in May-Aug 2005 plus one day (2006-02-14). There is a 174-day gap (Aug 24 2005 - Feb 13 2006); Sep 2005-Jan 2006 have no data. Month/quarter/year growth, seasonality, churn by month and forecasts are unreliable; Feb 14 cannot be attributed to Valentine's Day."),
    ("visits", "No visit, basket, session, browsing, search, store-entry or display data. Same customer + same date is only a heuristic for a visit."),
    ("demographics", "No age, gender, income, wealth, tourist status or acquisition channel. Customer address is not a demand location. No demographic personas or LTV by demographic."),
    ("causality", "All data is observational: no experiments. Correlations (price, length, copies, lift, staff, holdings) cannot prove causes; counterfactuals (price cuts, policy changes, more copies) cannot be measured. Lucas critique: behaviour under current policies may change when policies change."),
    ("unobserved_demand", "Failed rentals, unavailable-copy events, substitutions, abandonment and unmet demand are not recorded, so lost sales and lost revenue cannot be measured."),
    ("money", "No acquisition cost, operating cost, commissions or profit. replacement_cost is a replacement charge attribute, not purchase cost. payment rows have no charge-type field; amount - rental_rate is only a late-fee proxy (matches days late exactly in ~72% of rentals, and 852 late rentals have no extra charge)."),
    ("ratings", "film.rating is an MPAA content classification (G/PG/PG-13/R/NC-17), not a customer review score. No satisfaction or service-quality data."),
    ("staff_store", "Two stores and two staff. A rental can be linked to the customer's store, the inventory's store or the staff member's store; state which. Store 'efficiency', market share, closures and new locations need data Sakila does not have."),
    ("actors", "A film has several actors; attributing a film's full revenue to each actor double-counts. Renting a film with an actor does not prove preference for that actor."),
    ("churn", "Churn and lifetime value cannot be observed in a short, censored window; zero holdings is not churn."),
    ("forecast", "No reliable demand forecast: 4 months of bursty, partly synthetic data with a large gap. Offer scenario methods and what data is needed, not point forecasts."),
    ("bcg", "A true BCG matrix needs market growth and relative market share against competitors; Sakila has neither. Only an internal proxy (share of Sakila rentals vs change between bursts) is possible, and it must not justify betting on one category: demand is spread evenly and customers switch 93% of the time."),
]


def data_limitations(topic: str | None = None) -> dict:
    items = [{"topic": t, "limitation": d} for t, d in DATA_LIMITS if not topic or topic.lower() in t or topic.lower() in d.lower()]
    return {"limitations": items or [{"topic": t, "limitation": d} for t, d in DATA_LIMITS]}


@lru_cache(maxsize=1)
def category_by_burst() -> dict:
    """Category share of rentals in each 8-day recording burst (for trend / BCG-proxy questions)."""
    R = _rentals_all()
    R = R[R["rd"] < END]
    bursts = chronology()["rental_bursts"][:-1]
    rows = {}
    for i, b in enumerate(bursts, 1):
        m = (R["rd"] >= pd.Timestamp(b["from"])) & (R["rd"] < pd.Timestamp(b["to"]) + pd.Timedelta(days=1))
        rows[f"burst_{i} ({b['from']}..{b['to']})"] = (100 * R.loc[m, "category"].value_counts(normalize=True)).round(2)
    df = pd.DataFrame(rows).fillna(0)
    first, last = df.columns[0], df.columns[-1]
    df["share_all"] = (100 * R["category"].value_counts(normalize=True)).round(2)
    df["change_first_to_last_burst_pp"] = (df[last] - df[first]).round(2)
    return {"table": df.reset_index(names="category").sort_values("share_all", ascending=False).to_dict(orient="records"),
            "note": "Shares per 8-day burst are comparable (same number of recorded days); absolute totals are not. Changes of +/-1 percentage point are within normal noise for ~1,000-4,000 rentals per burst. This is NOT market growth, so a real BCG matrix cannot be built."}


@lru_cache(maxsize=1)
def misc_facts() -> dict:
    """Facts that answer common trap questions (store attribution, visits, film length, cities, actors, ratings)."""
    d = db.query("""SELECT cu.store_id AS cust_store, i.store_id AS inv_store, s.store_id AS staff_store
                    FROM rental r JOIN customer cu ON cu.customer_id = r.customer_id
                    JOIN inventory i ON i.inventory_id = r.inventory_id JOIN staff s ON s.staff_id = r.staff_id""")
    v = db.query("SELECT customer_id, DATE(rental_date) AS d, COUNT(*) AS n FROM rental GROUP BY customer_id, DATE(rental_date)")
    R = _rentals_all()
    c = R[R["rt"].notna()]
    hold = (c["rt"] - c["rd"]).dt.total_seconds() / 86400
    cities = db.query("SELECT COUNT(DISTINCT a.city_id) AS n FROM customer cu JOIN address a ON a.address_id = cu.address_id")["n"].iloc[0]
    fa = db.query("SELECT COUNT(*) AS n, COUNT(DISTINCT film_id) AS films FROM film_actor").iloc[0]
    rc = db.query("SELECT MIN(replacement_cost) AS lo, MAX(replacement_cost) AS hi FROM film").iloc[0]
    return {
        "store_attribution": {"pct_rentals_inventory_store_differs_from_customer_store": _r(100 * (d.inv_store != d.cust_store).mean()),
                              "pct_inventory_store_differs_from_staff_store": _r(100 * (d.inv_store != d.staff_store).mean()),
                              "note": "Three possible store links (customer.store_id, inventory.store_id, staff.store_id) disagree for about half of rentals, so always state which one is used. Dashboard uses inventory.store_id (where the copy is)."},
        "visits_heuristic": {"same_day_customer_groups": int(len(v)), "avg_rentals_per_same_day_group": _r(v["n"].mean(), 3),
                             "note": "No visit/basket id exists; customer + calendar date is only an approximation of a visit."},
        "film_length_vs_holding_days_correlation": _r(hold.corr(c["length"]), 4),
        "customer_cities": int(cities), "customers": 599,
        "city_note": "Customers live in almost as many different cities as there are customers, so 'demand by city' is not meaningful; address is not where rentals happen.",
        "film_actor_links": int(fa["n"]), "films_with_actors": int(fa["films"]),
        "actor_note": "Films have several actors; crediting a film's full revenue to each actor double-counts. Rentals do not show preference for an actor.",
        "replacement_cost_range": [float(rc["lo"]), float(rc["hi"])],
        "replacement_cost_note": "replacement_cost is the amount charged if a DVD is lost/damaged, not what Sakila paid to acquire it.",
        "rating_note": "film.rating (G, PG, PG-13, R, NC-17) is a content classification, not a customer review score.",
    }
