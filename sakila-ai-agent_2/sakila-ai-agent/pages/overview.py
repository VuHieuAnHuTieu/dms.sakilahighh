import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import analytics as an
from src import ui

ui.setup("Executive Overview",
         "Sakila DVD rental business — headline KPIs for the analysis window. Every number is computed live from the database.")

h = an.headline_metrics()
c = st.columns(5)
ui.kpi(c[0], "Total customers", f"{h['total_customers']:,}", f"{h['renting_customers']:,} rented in window")
ui.kpi(c[1], "Total rentals", f"{h['total_rentals']:,}", f"{h['first_rental'][:10]} → {h['last_rental'][:10]}")
ui.kpi(c[2], "Total revenue", f"${h['total_revenue']:,.2f}", "sum of payments in window")
ui.kpi(c[3], "Avg rental rate", f"${h['avg_catalog_rental_rate']:.2f}", f"catalogue avg · ${h['avg_payment_per_rental']:.2f} paid / rental")
ui.kpi(c[4], "Most rented category", h["most_rented_category"], f"{h['most_rented_category_rentals']:,} rentals")

st.markdown("#### The storyline")
st.markdown(
    "**1 · Do customers return?** → **2 · Do they stay in one category?** → **3 · Where do they go next?** → "
    "**4 · What should we recommend?** → **5 · Ask the AI agent to explain it.**")

mt = an.monthly_trend()
left, right = st.columns(2)
with left:
    fig = px.bar(mt, x="month", y="rentals", title="Rentals per month", text="rentals")
    fig.update_traces(marker_color=ui.BLUE, texttemplate="%{text:,}", textposition="outside",
                      hovertemplate="%{x}<br>%{y:,} rentals<extra></extra>")
    st.plotly_chart(ui.style(fig), width="stretch")
with right:
    fig = px.bar(mt, x="month", y="revenue", title="Revenue per month (payments)", text="revenue")
    fig.update_traces(marker_color=ui.BLUE, texttemplate="$%{text:,.0f}", textposition="outside",
                      hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>")
    st.plotly_chart(ui.style(fig), width="stretch")

rs = an.customer_return_stats()
peak = mt.loc[mt["rentals"].idxmax()]
ui.box(f"Activity peaks in <b>{peak['month']}</b> ({int(peak['rentals']):,} rentals). Rentals are recorded on only "
       f"<b>{rs['distinct_rental_dates_in_window']} distinct dates</b> in the window, so Sakila behaves like a series of "
       "busy rental 'waves' rather than a continuous daily stream — month-to-month trends should be read with that in mind.",
       "neutral")

dt = an.daily_trend()
fig = px.bar(dt, x="date", y="rentals", title="Daily rentals (only dates with recorded rentals appear)")
fig.update_traces(marker_color=ui.BLUE, hovertemplate="%{x}<br>%{y:,} rentals<extra></extra>")
st.plotly_chart(ui.style(fig, 300), width="stretch")

cp = an.category_performance().sort_values("rentals")
left, right = st.columns([3, 2])
with left:
    fig = px.bar(cp, x="rentals", y="category", orientation="h", title="Rentals by category",
                 custom_data=["rental_share_pct", "revenue"])
    fig.update_traces(marker_color=ui.BLUE,
                      hovertemplate="%{y}<br>%{x:,} rentals (%{customdata[0]:.2f}%)<br>$%{customdata[1]:,.2f} revenue<extra></extra>")
    even = cp["rentals"].sum() / len(cp)
    fig.add_vline(x=even, line_dash="dot", line_color=ui.GRAY,
                  annotation_text=f"equal share = {even:,.0f}", annotation_position="top")
    st.plotly_chart(ui.style(fig, 520), width="stretch")
with right:
    lo, hi = cp.iloc[0], cp.iloc[-1]
    ui.box(f"Demand is spread <b>almost evenly</b> across the {len(cp)} categories: from "
           f"{lo['rental_share_pct']:.2f}% ({lo['category']}) to {hi['rental_share_pct']:.2f}% ({hi['category']}) of rentals, "
           f"versus {100/len(cp):.2f}% for a perfectly equal split. No single genre dominates the business.")
    st.dataframe(cp.sort_values("rentals", ascending=False)[["category", "rentals", "rental_share_pct", "revenue", "customers"]]
                 .rename(columns={"rental_share_pct": "share %"}).round(2),
                 hide_index=True, width="stretch", height=380)
ui.sql_expander("business_metrics.sql", "category_performance")
