"""Reusable analytics layer: customer return, category repetition vs switching,
category transitions, high-transition categories and statistical checks.

Every number shown in the dashboard or returned to the AI agent comes from these
functions, which read the live Sakila database through `src.database`.
Results are cached per process (the data is static during a session).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, norm

from . import database as db
from .config import get_settings

N_PERMUTATIONS = 300


# ---------------------------------------------------------------------------
# Base data
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def rental_events() -> pd.DataFrame:
    """One row per rental (inside the analysis window) with category and amount,
    sorted by customer, rental_date, rental_id, plus sequence columns."""
    df = db.run("rental_events.sql", **db.window_params())
    df["rental_date"] = pd.to_datetime(df["rental_date"])
    df["return_date"] = pd.to_datetime(df["return_date"])
    df = df.sort_values(["customer_id", "rental_date", "rental_id"]).reset_index(drop=True)
    g = df.groupby("customer_id", sort=False)
    df["rental_number"] = g.cumcount() + 1
    df["prev_category"] = g["category"].shift()
    df["prev_rental_date"] = g["rental_date"].shift()
    return df


@lru_cache(maxsize=1)
def film_catalog() -> pd.DataFrame:
    return db.run("film_catalog.sql", **db.window_params())


@lru_cache(maxsize=1)
def categories() -> tuple[str, ...]:
    return tuple(sorted(db.query("SELECT name FROM category")["name"]))


def transitions_df() -> pd.DataFrame:
    """Consecutive-rental pairs (A -> B) per customer."""
    ev = rental_events()
    t = ev.dropna(subset=["prev_category"]).copy()
    t["same_day"] = t["rental_date"].dt.date == t["prev_rental_date"].dt.date
    t["is_repeat"] = t["category"] == t["prev_category"]
    return t


# ---------------------------------------------------------------------------
# Executive overview
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def headline_metrics() -> dict:
    h = db.run("business_metrics.sql", "headline", **db.window_params()).iloc[0].to_dict()
    cat = category_performance()
    h["most_rented_category"] = cat.iloc[0]["category"]
    h["most_rented_category_rentals"] = int(cat.iloc[0]["rentals"])
    h["avg_payment_per_rental"] = float(rental_events()["amount"].mean())
    h["analysis_end_date"] = get_settings().analysis_end_date or "none (all data)"
    h["scope_note"] = (f"Figures cover rentals before {h['analysis_end_date']} ({h['total_rentals']:,} rentals). The database holds "
                       f"{h['all_time_rentals']:,} rentals in total; {h['rentals_excluded_from_window']:,} rentals from a single "
                       "anomalous batch on 2006-02-14 are excluded (team convention).")
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in h.items()}


@lru_cache(maxsize=1)
def category_performance() -> pd.DataFrame:
    df = db.run("business_metrics.sql", "category_performance", **db.window_params())
    df["rental_share_pct"] = 100 * df["rentals"] / df["rentals"].sum()
    df["revenue_share_pct"] = 100 * df["revenue"] / df["revenue"].sum()
    return df


@lru_cache(maxsize=1)
def monthly_trend() -> pd.DataFrame:
    ev = rental_events()
    rentals = ev.groupby(ev["rental_date"].dt.to_period("M")).agg(
        rentals=("rental_id", "count"), active_customers=("customer_id", "nunique"))
    pay = db.run("business_metrics.sql", "payments", **db.window_params())
    pay["payment_date"] = pd.to_datetime(pay["payment_date"])
    revenue = pay.groupby(pay["payment_date"].dt.to_period("M"))["amount"].sum().rename("revenue")
    out = rentals.join(revenue, how="outer").fillna(0).reset_index(names="month")
    out["month"] = out["month"].astype(str)
    return out


@lru_cache(maxsize=1)
def daily_trend() -> pd.DataFrame:
    ev = rental_events()
    d = ev.groupby(ev["rental_date"].dt.date).agg(rentals=("rental_id", "count"), revenue=("amount", "sum"))
    return d.reset_index(names="date")


# ---------------------------------------------------------------------------
# STEP 1 - Customer return
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def customer_return_stats() -> dict:
    ev = rental_events()
    per_cust = ev.groupby("customer_id").agg(
        rentals=("rental_id", "count"),
        first=("rental_date", "min"),
        last=("rental_date", "max"),
        active_months=("rental_date", lambda s: s.dt.to_period("M").nunique()),
        visit_days=("rental_date", lambda s: s.dt.date.nunique()),
    )
    gaps = ev.groupby("customer_id")["rental_date"].apply(lambda s: s.dt.normalize().drop_duplicates().diff().dt.days.dropna())
    total_customers = int(db.query("SELECT COUNT(*) AS n FROM customer")["n"].iloc[0])
    return {
        "customers_in_database": total_customers,
        "customers_with_rentals": int(len(per_cust)),
        "customers_with_2plus_rentals": int((per_cust["rentals"] >= 2).sum()),
        "pct_customers_returning": round(100 * float((per_cust["rentals"] >= 2).mean()), 2),
        "customers_with_2plus_visit_days": int((per_cust["visit_days"] >= 2).sum()),
        "rentals_per_customer_min": int(per_cust["rentals"].min()),
        "rentals_per_customer_median": float(per_cust["rentals"].median()),
        "rentals_per_customer_mean": round(float(per_cust["rentals"].mean()), 2),
        "rentals_per_customer_max": int(per_cust["rentals"].max()),
        "visit_days_per_customer_median": float(per_cust["visit_days"].median()),
        "active_months_median": float(per_cust["active_months"].median()),
        "pct_active_in_all_months": round(100 * float((per_cust["active_months"] == per_cust["active_months"].max()).mean()), 2),
        "months_in_window": int(ev["rental_date"].dt.to_period("M").nunique()),
        "median_days_between_visits": float(gaps.median()),
        "distinct_rental_dates_in_window": int(ev["rental_date"].dt.date.nunique()),
    }


@lru_cache(maxsize=1)
def customer_summary() -> pd.DataFrame:
    """Per-customer rentals, distinct categories, repeat share and top category."""
    ev = rental_events()
    t = transitions_df()
    per = ev.groupby("customer_id").agg(
        rentals=("rental_id", "count"),
        distinct_categories=("category", "nunique"),
        revenue=("amount", "sum"),
        last_rental=("rental_date", "max"),
    )
    top = ev.groupby("customer_id")["category"].agg(lambda s: s.value_counts().index[0]).rename("top_category")
    top_share = ev.groupby("customer_id")["category"].agg(lambda s: s.value_counts(normalize=True).iloc[0]).rename("top_category_share")
    rep = t.groupby("customer_id")["is_repeat"].mean().rename("repeat_rate")
    return per.join([top, top_share, rep]).reset_index()


# ---------------------------------------------------------------------------
# STEP 2 - Category loyalty vs exploration
# ---------------------------------------------------------------------------
def _within_customer_permutations(n: int = N_PERMUTATIONS) -> np.ndarray:
    """Shuffle each customer's category sequence (keeps each customer's category mix,
    destroys ordering). Returns simulated repeat rates."""
    ev = rental_events()
    cust = ev["customer_id"].to_numpy()
    cat = pd.Categorical(ev["category"]).codes
    rng = np.random.default_rng(get_settings().random_seed)
    same_cust = cust[1:] == cust[:-1]
    out = np.empty(n)
    for k in range(n):
        order = np.lexsort((rng.random(len(cust)), cust))
        c = cat[order]
        out[k] = (c[1:] == c[:-1])[same_cust].mean()
    return out


@lru_cache(maxsize=1)
def repetition_stats() -> dict:
    t = transitions_df()
    ev = rental_events()
    share = ev["category"].value_counts(normalize=True)
    sims = _within_customer_permutations()
    observed = float(t["is_repeat"].mean())
    diff_day = t[~t["same_day"]]
    by_n = t.groupby("rental_number")["is_repeat"].mean()
    return {
        "transitions": int(len(t)),
        "same_category": int(t["is_repeat"].sum()),
        "switched_category": int((~t["is_repeat"]).sum()),
        "repeat_pct": round(100 * observed, 2),
        "switch_pct": round(100 * (1 - observed), 2),
        "random_choice_repeat_pct": round(100 * float((share ** 2).sum()), 2),
        "shuffled_sequence_repeat_pct": round(100 * float(sims.mean()), 2),
        "shuffled_repeat_p_value": round(float((np.sum(sims >= observed) + 1) / (len(sims) + 1)), 4),
        "n_permutations": int(len(sims)),
        "different_day_transitions": int(len(diff_day)),
        "different_day_repeat_pct": round(100 * float(diff_day["is_repeat"].mean()), 2),
        "second_rental_same_category_pct": round(100 * float(by_n.get(2, np.nan)), 2),
        "customers_never_repeating_consecutively": int((t.groupby("customer_id")["is_repeat"].sum() == 0).sum()),
    }


@lru_cache(maxsize=1)
def category_diversity() -> dict:
    cs = customer_summary()
    n_cat = len(categories())
    return {
        "total_categories": n_cat,
        "mean_distinct_categories": round(float(cs["distinct_categories"].mean()), 2),
        "median_distinct_categories": float(cs["distinct_categories"].median()),
        "min_distinct_categories": int(cs["distinct_categories"].min()),
        "max_distinct_categories": int(cs["distinct_categories"].max()),
        "pct_customers_10plus_categories": round(100 * float((cs["distinct_categories"] >= 10).mean()), 2),
        "median_top_category_share_pct": round(100 * float(cs["top_category_share"].median()), 2),
        "distribution": cs["distinct_categories"].value_counts().sort_index().to_dict(),
    }


@lru_cache(maxsize=1)
def discovery_curve(max_n: int = 30) -> pd.DataFrame:
    """Share of rentals at position k that are in a category the customer had never
    rented before, observed vs. a within-customer shuffle baseline."""
    ev = rental_events()

    def first_time(df: pd.DataFrame, col: str) -> pd.Series:
        return ~df.duplicated(["customer_id", col])

    obs = ev.assign(new=first_time(ev, "category")).groupby("rental_number")["new"].mean()
    rng = np.random.default_rng(get_settings().random_seed)
    sims = []
    for _ in range(50):
        order = np.lexsort((rng.random(len(ev)), ev["customer_id"].to_numpy()))
        sh = ev[["customer_id", "rental_number"]].copy()
        sh["cat"] = ev["category"].to_numpy()[order]
        sims.append(sh.assign(new=first_time(sh, "cat")).groupby("rental_number")["new"].mean())
    base = pd.concat(sims, axis=1).mean(axis=1)
    counts = ev.groupby("rental_number").size()
    out = pd.DataFrame({"observed_new_category_pct": 100 * obs, "shuffled_baseline_pct": 100 * base, "customers": counts})
    return out.loc[out.index <= max_n].reset_index(names="rental_number")


# ---------------------------------------------------------------------------
# STEP 3 - Category transitions
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def transition_counts() -> pd.DataFrame:
    """16x16 count matrix computed by SQL (sql/category_transitions.sql)."""
    long = db.run("category_transitions.sql", "transition_counts", **db.window_params())
    cats = list(categories())
    m = long.pivot(index="from_category", columns="to_category", values="transitions")
    return m.reindex(index=cats, columns=cats).fillna(0).astype(int)


@lru_cache(maxsize=1)
def transition_long() -> pd.DataFrame:
    """Long table: from, to, count, customers, P(B|A), baseline share of B, lift,
    adjusted standardized residual (z) vs independence."""
    long = db.run("category_transitions.sql", "transition_counts", **db.window_params())
    counts = transition_counts()
    n = counts.values.sum()
    row = counts.sum(axis=1)
    col = counts.sum(axis=0)
    long["outgoing_total"] = long["from_category"].map(row)
    long["probability"] = long["transitions"] / long["outgoing_total"]
    long["baseline_share"] = long["to_category"].map(col / n)
    long["lift"] = long["probability"] / long["baseline_share"]
    expected = long["outgoing_total"] * long["baseline_share"]
    rp = long["outgoing_total"] / n
    long["expected"] = expected
    long["z_residual"] = (long["transitions"] - expected) / np.sqrt(expected * (1 - rp) * (1 - long["baseline_share"]))
    long["is_self"] = long["from_category"] == long["to_category"]
    return long


def probability_matrix() -> pd.DataFrame:
    c = transition_counts()
    return c.div(c.sum(axis=1), axis=0)


def lift_matrix() -> pd.DataFrame:
    c = transition_counts()
    base = c.sum(axis=0) / c.values.sum()
    return probability_matrix().div(base, axis=1)


@lru_cache(maxsize=1)
def independence_test() -> dict:
    """Chi-square test: is the next category independent of the previous category?"""
    c = transition_counts()
    chi2, p, dof, _ = chi2_contingency(c.values)
    n = c.values.sum()
    v = float(np.sqrt(chi2 / (n * (min(c.shape) - 1))))
    long = transition_long()
    k = len(long)
    bonf_z = round(float(norm.ppf(1 - 0.05 / (2 * k))), 2)  # two-sided, alpha=0.05 / k cells
    return {
        "chi2": round(float(chi2), 2),
        "dof": int(dof),
        "p_value": round(float(p), 4),
        "cramers_v": round(v, 4),
        "n_transitions": int(n),
        "cells": int(k),
        "cells_abs_z_gt_1_96": int((long["z_residual"].abs() > 1.96).sum()),
        "cells_expected_by_chance_at_5pct": round(0.05 * k, 1),
        "bonferroni_z_threshold": bonf_z,
        "cells_significant_after_bonferroni": int((long["z_residual"].abs() > bonf_z).sum()),
        "max_probability": round(float(long.loc[~long["is_self"], "probability"].max()), 4),
        "uniform_probability": round(1 / c.shape[1], 4),
        "lift_min": round(float(long["lift"].min()), 3),
        "lift_max": round(float(long["lift"].max()), 3),
        "interpretation": (
            "No evidence that the previous category changes the next-category distribution"
            if p >= 0.05 else "The next category depends on the previous category (statistically)"
        ) + f" (chi2 p={p:.3f}, Cramer's V={v:.3f}; V<0.1 is a negligible association).",
    }


def top_transitions(n: int = 15, include_self: bool = False, sort_by: str = "transitions") -> pd.DataFrame:
    long = transition_long()
    if not include_self:
        long = long[~long["is_self"]]
    return long.sort_values([sort_by, "transitions"], ascending=False).head(n).reset_index(drop=True)


def category_transition_profile(category: str, top_n: int = 5) -> dict:
    cats = {c.lower(): c for c in categories()}
    key = category.strip().lower()
    if key not in cats:
        raise ValueError(f"Unknown category '{category}'. Valid: {', '.join(categories())}")
    cat = cats[key]
    long = transition_long()
    out = long[long["from_category"] == cat].sort_values("probability", ascending=False)
    inc = long[long["to_category"] == cat]
    return {
        "category": cat,
        "outgoing_transitions": int(out["transitions"].sum()),
        "incoming_transitions": int(inc["transitions"].sum()),
        "unique_destination_categories": int((out.loc[~out["is_self"], "transitions"] > 0).sum()),
        "self_transition_probability": round(float(out.loc[out["is_self"], "probability"].sum()), 4),
        "top_destinations": [
            {
                "to_category": r.to_category,
                "transitions": int(r.transitions),
                "customers": int(r.customers),
                "probability": round(float(r.probability), 4),
                "baseline_share": round(float(r.baseline_share), 4),
                "lift": round(float(r.lift), 3),
                "z_residual": round(float(r.z_residual), 2),
            }
            for r in out[~out["is_self"]].head(top_n).itertuples()
        ],
        "top_sources_into_category": [
            {"from_category": r.from_category, "transitions": int(r.transitions), "probability": round(float(r.probability), 4)}
            for r in inc[~inc["is_self"]].sort_values("probability", ascending=False).head(3).itertuples()
        ],
    }


@lru_cache(maxsize=1)
def high_transition_table() -> pd.DataFrame:
    """Candidate 'gateway' metrics per category.

    - outgoing / incoming transitions
    - unique destinations (excluding self)
    - normalized entropy of the outgoing distribution (1.0 = perfectly even spread)
    - strongest outgoing transition, its probability, lift and z-residual
    - count of outgoing cells with |z| > 1.96

    A category would qualify as a *gateway* only if it spreads customers to many
    categories MORE evenly or MORE strongly than other categories do, i.e. it must
    stand out on entropy / significant cells, not just on volume.
    """
    long = transition_long()
    rows = []
    for cat in categories():
        out = long[long["from_category"] == cat]
        off = out[~out["is_self"]]
        p = out["probability"].to_numpy()
        p = p[p > 0]
        entropy = float(-(p * np.log(p)).sum() / np.log(len(categories())))
        best = off.sort_values("probability", ascending=False).iloc[0]
        rows.append({
            "category": cat,
            "outgoing_transitions": int(out["transitions"].sum()),
            "incoming_transitions": int(long.loc[long["to_category"] == cat, "transitions"].sum()),
            "unique_destinations": int((off["transitions"] > 0).sum()),
            "outgoing_entropy": round(entropy, 4),
            "switch_out_rate": round(float(off["transitions"].sum() / out["transitions"].sum()), 4),
            "strongest_destination": best["to_category"],
            "strongest_probability": round(float(best["probability"]), 4),
            "strongest_lift": round(float(best["lift"]), 3),
            "strongest_z": round(float(best["z_residual"]), 2),
            "cells_abs_z_gt_1_96": int((out["z_residual"].abs() > 1.96).sum()),
        })
    return pd.DataFrame(rows).sort_values("outgoing_transitions", ascending=False).reset_index(drop=True)


def gateway_assessment() -> dict:
    ht = high_transition_table()
    it = independence_test()
    ent_range = (float(ht["outgoing_entropy"].min()), float(ht["outgoing_entropy"].max()))
    supported = it["p_value"] < 0.05 and it["cells_significant_after_bonferroni"] > 0
    return {
        "gateway_supported": bool(supported),
        "label_used": "gateway category" if supported else "high-transition category",
        "entropy_range": [round(ent_range[0], 4), round(ent_range[1], 4)],
        "unique_destinations_range": [int(ht["unique_destinations"].min()), int(ht["unique_destinations"].max())],
        "highest_outgoing_volume": ht.iloc[0]["category"],
        "highest_outgoing_transitions": int(ht.iloc[0]["outgoing_transitions"]),
        "explanation": (
            "Every category sends customers to all 15 other categories with a near-uniform spread "
            f"(normalized entropy {ent_range[0]:.3f}-{ent_range[1]:.3f}), and no single transition is "
            "statistically distinguishable from chance after multiple-comparison correction. Differences in "
            "outgoing volume simply mirror each category's rental volume. The data therefore does not support "
            "calling any category a 'gateway'; the neutral term 'high-transition category' is used for the "
            "categories with the most outgoing transitions."
        ) if not supported else "Some categories show statistically distinguishable outgoing patterns.",
    }


# ---------------------------------------------------------------------------
# Customer journey
# ---------------------------------------------------------------------------
def customer_journey(customer_id: int) -> pd.DataFrame:
    ev = rental_events()
    j = ev[ev["customer_id"] == customer_id][
        ["rental_number", "rental_id", "rental_date", "title", "category", "rating", "amount", "prev_category"]
    ].copy()
    j["transition"] = np.where(j["prev_category"].isna(), "first rental",
                               np.where(j["category"] == j["prev_category"], "repeat", "switch"))
    return j.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Honest evaluation of next-category prediction (hold-out backtest)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def next_category_backtest() -> dict:
    """Hide each customer's LAST rental; learn transitions & popularity from all other
    rentals; predict the hidden rental's category. Reports hit@1 and hit@3."""
    from .recommendation import score_categories  # local import to avoid cycle

    ev = rental_events()
    last_idx = ev.groupby("customer_id").tail(1).index
    train = ev.drop(last_idx)
    tt = train.dropna(subset=["prev_category"])
    cats = list(categories())
    P = pd.crosstab(tt["prev_category"], tt["category"]).reindex(index=cats, columns=cats, fill_value=0)
    P = P.div(P.sum(axis=1), axis=0)
    pop = train["category"].value_counts(normalize=True).reindex(cats, fill_value=0)
    s = get_settings()
    hits = {"popularity": [0, 0], "transition_only": [0, 0], "app_blend": [0, 0]}
    for cid, truth in ev.loc[last_idx, ["customer_id", "category"]].itertuples(index=False):
        hist = train.loc[train["customer_id"] == cid, "category"]
        ranks = {
            "popularity": pop.sort_values(ascending=False).index.tolist(),
            "transition_only": P.loc[hist.iloc[-1]].sort_values(ascending=False).index.tolist(),
            "app_blend": score_categories(hist.tolist(), P, cats, s.w_transition, s.w_affinity)["category"].tolist(),
        }
        for k, r in ranks.items():
            hits[k][0] += truth == r[0]
            hits[k][1] += truth in r[:3]
    n = len(last_idx)
    res = {"customers_tested": int(n), "random_hit@1_pct": round(100 / len(cats), 2), "random_hit@3_pct": round(300 / len(cats), 2)}
    for k, (h1, h3) in hits.items():
        res[f"{k}_hit@1_pct"] = round(100 * h1 / n, 2)
        res[f"{k}_hit@3_pct"] = round(100 * h3 / n, 2)
    res["standard_error_hit@3_pp"] = round(100 * float(np.sqrt(0.1875 * 0.8125 / n)), 2)
    return res


@lru_cache(maxsize=1)
def store_summary() -> pd.DataFrame:
    """One row per store (branch) with location, manager, customers, inventory, rentals and revenue."""
    df = db.run("business_metrics.sql", "stores", **db.window_params())
    df.insert(3, "manager", df.pop("manager_first_name") + " " + df.pop("manager_last_name"))
    df["rental_share_pct"] = 100 * df["rentals"] / df["rentals"].sum()
    df["revenue_share_pct"] = 100 * df["revenue"] / df["revenue"].sum()
    return df


@lru_cache(maxsize=1)
def revenue_breakdown() -> dict:
    """Split revenue into base rental fees (film.rental_rate) and late fees (amount above the rate)."""
    d = db.run("business_metrics.sql", "payment_components", **db.window_params())
    d["extra"] = (d["amount"] - d["rental_rate"]).round(2)
    rd, rt = pd.to_datetime(d["rental_date"]), pd.to_datetime(d["return_date"])
    days_late = ((rt - rd).dt.total_seconds() / 86400 - d["rental_duration"]).clip(lower=0)
    late = d["extra"] > 0
    total = float(d["amount"].sum())
    return {
        "payments": int(len(d)),
        "total_revenue": round(total, 2),
        "base_rental_fees": round(float(d["amount"].where(~late, d["rental_rate"]).sum()), 2),
        "late_fees": round(float(d.loc[late, "extra"].sum()), 2),
        "late_fee_share_of_revenue_pct": round(100 * float(d.loc[late, "extra"].sum()) / total, 2),
        "payments_with_late_fee_pct": round(100 * float(late.mean()), 2),
        "avg_payment": round(float(d["amount"].mean()), 4),
        "avg_rental_rate_per_rental": round(float(d["rental_rate"].mean()), 4),
        "correlation_extra_vs_days_late": round(float(d["extra"].corr(days_late)), 3),
        "note": "Extra = amount - rental_rate, a PROXY for late fees: payment rows have no charge-type field. It tracks days late (~$1/day) but does not always equal them. No damage fee exists in the data.",
    }


@lru_cache(maxsize=1)
def inventory_utilization() -> dict:
    u = db.run("business_metrics.sql", "film_utilization", **db.window_params())
    stocked = u[u["copies"] > 0].copy()
    stocked["rentals_per_copy"] = stocked["rentals"] / stocked["copies"]
    q = stocked["rentals_per_copy"].quantile([0.25, 0.5, 0.75])
    return {
        "films_in_catalog": int(len(u)),
        "films_with_no_copies": int((u["copies"] == 0).sum()),
        "stocked_films": int(len(stocked)),
        "stocked_films_with_zero_rentals": int((stocked["rentals"] == 0).sum()),
        "stocked_films_with_under_5_rentals": int((stocked["rentals"] < 5).sum()),
        "films_with_3plus_copies_and_under_5_rentals": int(((stocked["copies"] >= 3) & (stocked["rentals"] < 5)).sum()),
        "rentals_per_copy_p25_median_p75": [round(float(v), 2) for v in q],
        "lowest_rentals_per_copy": stocked.nsmallest(5, "rentals_per_copy")[["title", "category", "copies", "rentals"]].to_dict(orient="records"),
        "highest_rentals_per_copy": stocked.nlargest(5, "rentals_per_copy")[["title", "category", "copies", "rentals"]].to_dict(orient="records"),
    }


def key_insights() -> list[dict]:
    """Pre-verified insights: every number is computed here from the database, with its caveat."""
    h, rp, dv, it = headline_metrics(), repetition_stats(), category_diversity(), independence_test()
    rs, cp, rb, iu, bt = customer_return_stats(), category_performance(), revenue_breakdown(), inventory_utilization(), next_category_backtest()
    st = store_summary()
    lo, hi = cp.iloc[-1], cp.iloc[0]
    return [
        {"insight": "Every customer returns", "evidence": f"{rs['pct_customers_returning']:.0f}% of {rs['customers_with_rentals']} customers rent more than once (min {rs['rentals_per_customer_min']}, median {rs['rentals_per_customer_median']:.0f} rentals).",
         "caveat": "Sakila is a sample database; retention is not the problem to solve."},
        {"insight": "Customers switch category on almost every rental", "evidence": f"{rp['switch_pct']}% of {rp['transitions']:,} consecutive-rental pairs change category; {rp['repeat_pct']}% repeat. Median customer rents {dv['median_distinct_categories']:.0f} of 16 categories.",
         "caveat": f"Random choice would give {rp['random_choice_repeat_pct']}% repeats (shuffled history {rp['shuffled_sequence_repeat_pct']}%, permutation p = {rp['shuffled_repeat_p_value']}): switching is close to what chance produces, so it is not evidence of a special 'exploration habit'."},
        {"insight": "The previous category does not predict the next one", "evidence": f"Chi-square independence test p = {it['p_value']}, Cramér's V = {it['cramers_v']}; P(B|A) ranges up to {100*it['max_probability']:.2f}% vs a 6.25% chance level; {it['cells_significant_after_bonferroni']} of 256 cells significant after Bonferroni.",
         "caveat": f"Hold-out test: transition-based hit@3 = {bt['transition_only_hit@3_pct']}% vs random {bt['random_hit@3_pct']}%. No 'gateway' category is supported."},
        {"insight": "Demand is spread almost evenly across categories", "evidence": f"Category shares run from {lo['rental_share_pct']:.2f}% ({lo['category']}) to {hi['rental_share_pct']:.2f}% ({hi['category']}) vs 6.25% for an equal split.",
         "caveat": "No category dominates; Sports is the largest by only a small margin."},
        {"insight": "Charges above the rental rate (a late-fee proxy) are a large part of revenue", "evidence": f"Payments above the film's rental rate total ${rb['late_fees']:,.2f} = {rb['late_fee_share_of_revenue_pct']}% of revenue; {rb['payments_with_late_fee_pct']}% of payments include such an extra. The extra correlates {rb['correlation_extra_vs_days_late']} with days late.",
         "caveat": "Payments have no charge-type field, so amount - rental_rate is only a proxy for late fees (it is not always equal to the late days); no damage fee exists in the data."},
        {"insight": "The two stores are almost identical in size", "evidence": f"Store 1 ({st.iloc[0]['city']}): {int(st.iloc[0]['rentals']):,} rentals, ${st.iloc[0]['revenue']:,.2f}; Store 2 ({st.iloc[1]['city']}): {int(st.iloc[1]['rentals']):,} rentals, ${st.iloc[1]['revenue']:,.2f}.",
         "caveat": "Rentals attributed to the store owning the rented copy."},
        {"insight": "Inventory gaps are about unstocked titles, not idle copies", "evidence": f"{iu['films_with_no_copies']} of {iu['films_in_catalog']} films have no copies at all; {iu['films_with_3plus_copies_and_under_5_rentals']} films have 3+ copies with under 5 rentals; median {iu['rentals_per_copy_p25_median_p75'][1]} rentals per copy.",
         "caveat": "4-month window; the team's Insight #6 (Spearman copies vs rentals) covers allocation in more depth."},
        {"insight": "Scope of the numbers", "evidence": h["scope_note"], "caveat": ""},
    ]
