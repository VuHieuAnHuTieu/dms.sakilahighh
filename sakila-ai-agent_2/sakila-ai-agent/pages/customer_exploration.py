import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import analytics as an
from src import ui

ui.setup("Customer Exploration",
         "Do customers come back — and when they do, do they stay in the same category?", step="STEP 1–2")

# ---------------- STEP 1: return ----------------
st.subheader("Step 1 · Do customers return?")
rs = an.customer_return_stats()
c = st.columns(4)
ui.kpi(c[0], "Customers who rent again", f"{rs['pct_customers_returning']:.0f}%", f"{rs['customers_with_2plus_rentals']} of {rs['customers_with_rentals']}")
ui.kpi(c[1], "Rentals per customer", f"{rs['rentals_per_customer_median']:.0f}", f"median · range {rs['rentals_per_customer_min']}–{rs['rentals_per_customer_max']}")
ui.kpi(c[2], "Visit days per customer", f"{rs['visit_days_per_customer_median']:.0f}", "median distinct rental dates")
ui.kpi(c[3], "Active in every month", f"{rs['pct_active_in_all_months']:.1f}%", f"of customers, {rs['months_in_window']} months in window")
ui.box(f"Every one of the {rs['customers_with_rentals']} customers returns: the lightest customer still has "
       f"{rs['rentals_per_customer_min']} rentals. Retention is not the question in Sakila — the question is "
       "<b>what they choose when they come back</b>.")

# ---------------- STEP 2: repeat vs switch ----------------
st.subheader("Step 2 · Category loyalty vs category exploration")
rp = an.repetition_stats()
dv = an.category_diversity()
c = st.columns(4)
ui.kpi(c[0], "Next rental switches category", f"{rp['switch_pct']:.2f}%", f"{rp['switched_category']:,} of {rp['transitions']:,} transitions")
ui.kpi(c[1], "Next rental repeats category", f"{rp['repeat_pct']:.2f}%", f"{rp['same_category']:,} transitions")
ui.kpi(c[2], "Categories explored", f"{dv['median_distinct_categories']:.0f} / {dv['total_categories']}", "median per customer")
ui.kpi(c[3], "Top category share", f"{dv['median_top_category_share_pct']:.0f}%", "median share of a customer's favourite")

left, right = st.columns(2)
with left:
    comp = pd.DataFrame({
        "benchmark": ["Observed in Sakila", "Shuffled own history", "Random choice (Σp²)"],
        "repeat_pct": [rp["repeat_pct"], rp["shuffled_sequence_repeat_pct"], rp["random_choice_repeat_pct"]],
    })
    fig = px.bar(comp, x="benchmark", y="repeat_pct", text="repeat_pct",
                 title="Same-category repeat rate: observed vs chance benchmarks")
    fig.update_traces(marker_color=[ui.BLUE, ui.GRAY, ui.GRAY], texttemplate="%{text:.2f}%", textposition="outside",
                      hovertemplate="%{x}<br>%{y:.2f}% repeat<extra></extra>")
    fig.update_yaxes(title="% of consecutive rentals in same category", range=[0, max(comp["repeat_pct"]) * 1.3])
    fig.update_xaxes(title=None)
    st.plotly_chart(ui.style(fig), width="stretch")
with right:
    dist = pd.Series(dv["distribution"]).rename_axis("categories").reset_index(name="customers")
    fig = px.bar(dist, x="categories", y="customers", text="customers",
                 title="Customers by number of distinct categories rented")
    fig.update_traces(marker_color=ui.BLUE, textposition="outside",
                      hovertemplate="%{x} categories<br>%{y} customers<extra></extra>")
    fig.update_xaxes(dtick=1, title="distinct categories rented (of 16)")
    st.plotly_chart(ui.style(fig), width="stretch")

ui.box(f"<b>{rp['switch_pct']:.1f}%</b> of consecutive rentals move to a different category, and "
       f"{dv['pct_customers_10plus_categories']:.0f}% of customers have rented 10+ of the 16 categories. "
       f"Customers clearly <b>return and explore</b>.")
ui.box(f"But the repeat rate ({rp['repeat_pct']:.2f}%) is close to what pure chance produces "
       f"({rp['random_choice_repeat_pct']:.2f}% if categories were picked at random; {rp['shuffled_sequence_repeat_pct']:.2f}% "
       f"when each customer's own history is shuffled, p = {rp['shuffled_repeat_p_value']}). So switching is the "
       "<i>default outcome of choosing among 16 evenly-demanded categories</i>, not evidence of a special craving for novelty. "
       f"The result is robust: counting only rentals on different days gives {rp['different_day_repeat_pct']:.2f}% repeats.",
       "caveat")
ui.sql_expander("category_transitions.sql", "repeat_vs_switch")

# ---------------- Discovery curve ----------------
st.subheader("How fast do customers discover new categories?")
dc = an.discovery_curve()
fig = go.Figure()
fig.add_trace(go.Scatter(x=dc["rental_number"], y=dc["observed_new_category_pct"], name="Observed",
                         mode="lines+markers", line=dict(color=ui.BLUE, width=2), marker=dict(size=7),
                         hovertemplate="Rental #%{x}<br>%{y:.1f}% in a new category<extra>Observed</extra>"))
fig.add_trace(go.Scatter(x=dc["rental_number"], y=dc["shuffled_baseline_pct"], name="Shuffled baseline",
                         mode="lines", line=dict(color=ui.GRAY, width=2, dash="dot"),
                         hovertemplate="Rental #%{x}<br>%{y:.1f}%<extra>Shuffled</extra>"))
fig.update_xaxes(title="rental number in customer's history")
fig.update_yaxes(title="% of rentals in a never-rented-before category", range=[0, 105])
st.plotly_chart(ui.style(fig, 360, legend=True), width="stretch")
r2 = dc.set_index("rental_number")
ui.box(f"At rental #2, {r2.loc[2, 'observed_new_category_pct']:.1f}% of customers pick a category they have not tried; "
       f"by rental #10 it is still {r2.loc[10, 'observed_new_category_pct']:.1f}%. The decline is what happens naturally as "
       "customers run out of untried categories — the observed curve tracks the shuffled baseline closely.", "neutral")

# ---------------- Journey examples ----------------
st.subheader("Customer journey examples")
cs = an.customer_summary()
default = int(st.session_state.get("selected_customer", 42))
cid = st.selectbox("Customer", cs["customer_id"].tolist(), index=cs["customer_id"].tolist().index(default),
                   key="explore_customer")
j = an.customer_journey(int(cid))
row = cs.set_index("customer_id").loc[int(cid)]
st.markdown(ui.journey_chips(j["category"].tolist(), 12), unsafe_allow_html=True)
st.caption(f"{int(row['rentals'])} rentals · {int(row['distinct_categories'])} categories · repeat rate "
           f"{100*row['repeat_rate']:.1f}% · favourite: {row['top_category']} ({100*row['top_category_share']:.0f}%)")
order = sorted(j["category"].unique())
fig = go.Figure()
fig.add_trace(go.Scatter(x=j["rental_number"], y=j["category"], mode="lines", line=dict(color="#d9d8d3", width=1.5),
                         hoverinfo="skip", showlegend=False))
for label, color in [("switch", ui.BLUE), ("repeat", ui.ORANGE), ("first rental", ui.GRAY)]:
    s = j[j["transition"] == label]
    fig.add_trace(go.Scatter(x=s["rental_number"], y=s["category"], mode="markers", name=label,
                             marker=dict(size=11, color=color, line=dict(color="white", width=2)),
                             customdata=s[["title", "rental_date"]].astype(str).values,
                             hovertemplate="#%{x} · %{y}<br>%{customdata[0]}<br>%{customdata[1]}<extra>" + label + "</extra>"))
fig.update_yaxes(categoryorder="array", categoryarray=order, title=None)
fig.update_xaxes(title="rental number")
st.plotly_chart(ui.style(fig, 420, legend=True), width="stretch")
st.caption("Rentals made at the same timestamp are ordered by rental_id (deterministic tie-breaker).")
