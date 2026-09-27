"""Chart builders used by the agent's `visualize` tool. Every chart is built from verified data
(src/analytics.py and src/insights.py) and returned as a Plotly JSON spec for the UI to render."""
from __future__ import annotations

import plotly.graph_objects as go

from . import analytics as an
from . import insights as ins

BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#9aa1ac"


def _layout(fig: go.Figure, title: str, ytitle: str = "", xtitle: str = "") -> dict:
    fig.update_layout(title=title, template="plotly_white", height=380, margin=dict(l=10, r=10, t=50, b=10),
                      yaxis_title=ytitle, xaxis_title=xtitle, showlegend=len(fig.data) > 1,
                      legend=dict(orientation="h", y=-0.2))
    fig.update_traces(selector=dict(type="bar"), marker_cornerradius=4)
    return fig.to_plotly_json()


def _bar(x, y, title, ytitle="", xtitle="", color=BLUE, text_fmt="{:,.2f}", horizontal=False) -> dict:
    fig = go.Figure(go.Bar(x=y if horizontal else x, y=x if horizontal else y, orientation="h" if horizontal else "v",
                           marker_color=color, text=[text_fmt.format(v) for v in y], textposition="outside"))
    return _layout(fig, title, ytitle, xtitle)


def insight_1() -> dict:
    t = ins.insight_1()["table"]
    fig = go.Figure()
    fig.add_bar(x=[f"{r['rental_duration']}-day" for r in t], y=[r["pct_late_exact_time"] for r in t], name="% returned late", marker_color=ORANGE)
    fig.add_bar(x=[f"{r['rental_duration']}-day" for r in t], y=[r["pct_early_exact_time"] for r in t], name="% returned early", marker_color=BLUE)
    return _layout(fig, "Insight 1 · Late vs early returns by rental-duration policy (avg hold ~5 days for all)", "% of completed rentals", "policy")


def hold_days() -> dict:
    d = ins.insight_1()["hold_day_distribution"]
    return _bar([f"{k} d" for k in d], list(d.values()), "Insight 1 · Days kept before return (flat 1-9 days)", "rentals", "calendar days held", text_fmt="{:,.0f}")


def insight_2() -> dict:
    rp = an.repetition_stats()
    return _bar(["Observed", "Shuffled own history", "Random choice"], [rp["repeat_pct"], rp["shuffled_sequence_repeat_pct"], rp["random_choice_repeat_pct"]],
                "Insight 2 · Same-category repeat rate vs chance", "% of consecutive rentals", color=[BLUE, GRAY, GRAY])


def insight_3() -> dict:
    x = ins.insight_3()
    fig = go.Figure(go.Bar(x=list(x["calendar_buckets_pct"].keys()), y=list(x["calendar_buckets_pct"].values()), marker_color=BLUE,
                           text=[f"{v:.1f}%" for v in x["calendar_buckets_pct"].values()], textposition="outside"))
    return _layout(fig, "Insight 3 · Time from zero holdings to next rental (calendar clock; 7-14 d reflects 2-week data gaps)", "% of reactivations")


def prior_open() -> dict:
    d = ins.insight_3()["prior_open_distribution"]
    return _bar([k if k != "5" else "5+" for k in d], list(d.values()), "Insight 3 · DVDs already held at checkout", "checkouts", "DVDs held", text_fmt="{:,.0f}")


def insight_4() -> dict:
    t = an.top_transitions(10, sort_by="lift").iloc[::-1]
    return _bar([f"{a} → {b}" for a, b in zip(t["from_category"], t["to_category"])], t["lift"].round(3).tolist(),
                "Insight 4 · Top 10 category transitions by lift (none significant after correction)", "", "lift", horizontal=True)


def heatmap() -> dict:
    cats = list(an.categories())
    z = (100 * an.probability_matrix()).round(2).values
    fig = go.Figure(go.Heatmap(z=z, x=cats, y=cats, zmin=0, zmax=15, colorscale="Blues", colorbar=dict(title="%")))
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, "P(next category | previous category), %", "previous", "next")


def insight_5() -> dict:
    b = ins.insight_5()["basket_table"]
    return _bar([f"{r['discs']} disc(s)" for r in b], [r["pct"] for r in b], "Insight 5 · Same-day visits with a $0.99 title, by number of discs", "% of visits")


def price_tiers() -> dict:
    t = ins.insight_5()["price_tiers"]
    return _bar([f"${r['rental_rate']}" for r in t], [r["rentals_per_title"] for r in t], "Insight 5 · Rentals per title by price tier", "rentals per title")


def insight_6() -> dict:
    q = ins.insight_6()["quartiles"]
    return _bar([r["quartile"] for r in q], [r["rentals_per_copy"] for r in q], "Insight 6 · Rentals per copy by productivity quartile", "rentals per copy")


def monthly_gap() -> dict:
    rows = ins.trends("month")["rows"]
    return _bar([r["period"] for r in rows], [r["rentals"] for r in rows], "Rentals by month (Sep 2005-Jan 2006: NO DATA, not zero demand)", "rentals",
                color=[BLUE if r["has_data"] else GRAY for r in rows], text_fmt="{:,.0f}")


def categories() -> dict:
    cp = an.category_performance().sort_values("rentals")
    return _bar(cp["category"].tolist(), cp["rental_share_pct"].round(2).tolist(), "Rental share by category (equal split = 6.25%)", "", "% of rentals", horizontal=True)


def stores() -> dict:
    s = an.store_summary()
    return _bar([f"Store {i} ({c})" for i, c in zip(s["store_id"], s["city"])], s["revenue"].tolist(), "Revenue by store", "$", text_fmt="${:,.2f}")


def segments() -> dict:
    s = ins.customer_segments()["segments"]
    return _bar([r["segment"] for r in s], [r["customers"] for r in s], "Behavioural customer segments (no demographic data)", "customers", text_fmt="{:,.0f}")


CHARTS = {
    "insight_1": insight_1, "hold_days": hold_days, "insight_2": insight_2, "insight_3": insight_3, "prior_open": prior_open,
    "insight_4": insight_4, "transition_heatmap": heatmap, "insight_5": insight_5, "price_tiers": price_tiers, "insight_6": insight_6,
    "monthly_trend_with_gap": monthly_gap, "category_share": categories, "stores": stores, "customer_segments": segments,
}
