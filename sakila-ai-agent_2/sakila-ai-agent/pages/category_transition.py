import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import analytics as an
from src import ui

ui.setup("Category Transition",
         "After a customer rents a movie from category A, which category do they rent next?", step="STEP 3")

it = an.independence_test()
c = st.columns(4)
ui.kpi(c[0], "Transitions analysed", f"{it['n_transitions']:,}", "consecutive rental pairs")
ui.kpi(c[1], "Highest P(B | A)", f"{100*it['max_probability']:.2f}%", f"chance level = {100*it['uniform_probability']:.2f}%")
ui.kpi(c[2], "Independence test", f"p = {it['p_value']:.2f}", f"χ² = {it['chi2']:.0f}, dof {it['dof']}")
ui.kpi(c[3], "Association strength", f"V = {it['cramers_v']:.3f}", "Cramér's V (<0.1 = negligible)")

ui.box("<b>Key result:</b> the previous category tells us very little about the next one. " + it["interpretation"] +
       f" Only {it['cells_abs_z_gt_1_96']} of {it['cells']} cells deviate at |z|>1.96 (≈{it['cells_expected_by_chance_at_5pct']:.0f} expected by "
       f"chance) and <b>{it['cells_significant_after_bonferroni']}</b> survive a Bonferroni correction (|z|>{it['bonferroni_z_threshold']}).",
       "caveat")

# ---------------- Heatmap ----------------
st.subheader("Transition heatmap")
view = st.radio("Show", ["Probability P(next = B | previous = A)", "Lift vs baseline (P ÷ share of B)", "Counts"],
                horizontal=True)
cats = list(an.categories())
counts = an.transition_counts()
if view.startswith("Probability"):
    z = 100 * an.probability_matrix()
    fig = go.Figure(go.Heatmap(z=z.values, x=cats, y=cats, colorscale=ui.SEQ_BLUE, customdata=counts.values,
                               zmin=0, zmax=max(15.0, float(z.values.max())),  # anchored at 0 so the scale is not exaggerated
                               colorbar=dict(title="%"), xgap=2, ygap=2,
                               hovertemplate="%{y} → %{x}<br>P = %{z:.2f}%<br>%{customdata} transitions<extra></extra>"))
elif view.startswith("Lift"):
    z = an.lift_matrix()
    dev = float(np.abs(z.values - 1).max())
    fig = go.Figure(go.Heatmap(z=z.values, x=cats, y=cats, colorscale=ui.DIVERGING, zmid=1, zmin=1 - dev, zmax=1 + dev,
                               customdata=counts.values, colorbar=dict(title="lift"), xgap=2, ygap=2,
                               hovertemplate="%{y} → %{x}<br>lift = %{z:.2f}<br>%{customdata} transitions<extra></extra>"))
else:
    fig = go.Figure(go.Heatmap(z=counts.values, x=cats, y=cats, colorscale=ui.SEQ_BLUE, colorbar=dict(title="n"),
                               xgap=2, ygap=2, hovertemplate="%{y} → %{x}<br>%{z} transitions<extra></extra>"))
fig.update_xaxes(title="next category (B)", side="bottom", tickangle=-40)
fig.update_yaxes(title="previous category (A)", autorange="reversed")
if view.startswith("Probability"):
    st.caption("Colour scale anchored at 0–15% so small differences are not visually exaggerated; hover for exact values.")
st.plotly_chart(ui.style(fig, 620), width="stretch")
pm = 100 * an.probability_matrix()
ui.box(f"Read across a row: every cell lies between <b>{pm.values.min():.2f}%</b> and <b>{pm.values.max():.2f}%</b> — "
       f"a narrow band around the 6.25% you would get by picking one of 16 categories at random. "
       "The heatmap is visually 'flat', which is itself the finding.", "neutral")
ui.sql_expander("category_transitions.sql", "transition_counts")

# ---------------- Top transitions ----------------
st.subheader("Most frequent category transitions (A ≠ B)")
left, right = st.columns([3, 2])
with left:
    sort_by = st.radio("Rank by", ["transitions", "probability", "lift"], horizontal=True)
    tt = an.top_transitions(15, sort_by=sort_by).iloc[::-1]
    tt["pair"] = tt["from_category"] + " → " + tt["to_category"]
    fig = px.bar(tt, x=sort_by, y="pair", orientation="h",
                 custom_data=["transitions", "probability", "lift", "z_residual"])
    fig.update_traces(marker_color=ui.BLUE, hovertemplate="%{y}<br>%{customdata[0]} transitions · P = %{customdata[1]:.2%}"
                      "<br>lift %{customdata[2]:.2f} · z = %{customdata[3]:.2f}<extra></extra>")
    fig.update_yaxes(title=None)
    st.plotly_chart(ui.style(fig, 520), width="stretch")
with right:
    top = an.top_transitions(1).iloc[0]
    topp = an.top_transitions(1, sort_by="probability").iloc[0]
    ui.box(f"The most frequent switch is <b>{top['from_category']} → {top['to_category']}</b> "
           f"({int(top['transitions'])} times, P = {100*top['probability']:.2f}%). The highest conditional probability is "
           f"<b>{topp['from_category']} → {topp['to_category']}</b> ({100*topp['probability']:.2f}%, lift {topp['lift']:.2f}, "
           f"z = {topp['z_residual']:.2f}).")
    ui.box("Frequency rankings mostly mirror category size (Sports and Animation are the biggest categories, so they "
           "appear in the most pairs). None of these pairs is statistically distinguishable from chance after correcting "
           "for 256 comparisons — present them as <i>historically observed</i>, not as reliable routes.", "caveat")

# ---------------- Explore one category ----------------
st.subheader("Where do customers go after …")
cat = st.selectbox("Category A", cats, index=cats.index("Action"))
prof = an.category_transition_profile(cat, top_n=16)
d = pd.DataFrame(prof["top_destinations"]).sort_values("probability")
fig = px.bar(d, x="probability", y="to_category", orientation="h", custom_data=["transitions", "lift", "z_residual"],
             title=f"P(next = B | previous = {cat}) · {prof['outgoing_transitions']} transitions")
fig.update_traces(marker_color=ui.BLUE, hovertemplate="%{y}<br>P = %{x:.2%}<br>%{customdata[0]} transitions · lift %{customdata[1]:.2f}"
                  " · z %{customdata[2]:.2f}<extra></extra>")
fig.add_vline(x=1 / 16, line_dash="dot", line_color=ui.GRAY, annotation_text="chance 6.25%")
fig.update_xaxes(tickformat=".0%")
fig.update_yaxes(title=None)
st.plotly_chart(ui.style(fig, 480), width="stretch")
st.caption(f"{cat} is followed by {cat} again {100*prof['self_transition_probability']:.2f}% of the time. "
           f"It reaches all {prof['unique_destination_categories']} other categories.")

# ---------------- Gateway ----------------
st.subheader("Gateway or 'high-transition' categories?")
ga = an.gateway_assessment()
st.markdown(
    "**Definition used.** A *gateway category* would need to (1) send customers to many destinations, (2) do so in a way that "
    "differs from other categories — e.g. unusually concentrated strong routes (significant cells) or unusually broad spread "
    "(outgoing entropy) — and not simply (3) have high rental volume.")
ht = an.high_transition_table()
left, right = st.columns([2, 3])
with left:
    fig = px.scatter(ht, x="outgoing_transitions", y="outgoing_entropy", custom_data=["category"],
                     title="Outgoing volume vs spread of destinations")
    fig.update_traces(marker=dict(size=11, color=ui.BLUE, line=dict(color="white", width=2)),
                      hovertemplate="%{customdata[0]}<br>%{x} outgoing<br>entropy %{y:.4f}<extra></extra>")
    fig.update_yaxes(title="normalized entropy (1 = perfectly even)", range=[0.9, 1.0])
    fig.update_xaxes(title="outgoing transitions")
    st.plotly_chart(ui.style(fig, 420), width="stretch")
with right:
    st.dataframe(ht.rename(columns={"outgoing_transitions": "out", "incoming_transitions": "in",
                                    "unique_destinations": "destinations", "outgoing_entropy": "entropy",
                                    "cells_abs_z_gt_1_96": "cells |z|>1.96"}),
                 hide_index=True, width="stretch", height=420)
ui.box(f"<b>Verdict: gateway supported = {ga['gateway_supported']}.</b> {ga['explanation']}",
       "caveat" if not ga["gateway_supported"] else "finding")
