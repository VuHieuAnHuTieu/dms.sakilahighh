import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import analytics as an
from src import ui
from src.config import get_settings
from src.recommendation import recommend_for_customer

ui.setup("Next-Category Recommendation",
         "Transparent, data-driven recommendation: historical transitions + the customer's own history → category → movies.",
         step="STEP 4")

ids = an.customer_summary()["customer_id"].tolist()
c1, c2, c3 = st.columns([2, 2, 2])
default = int(st.session_state.get("selected_customer", 42))
cid = c1.selectbox("Customer ID", ids, index=ids.index(default))
explore = c2.toggle("Exploration mode", value=False, help="Exclude the customer's current category, "
                    "so the recommendation always suggests a different category.")
avail = c3.toggle("Only in-stock movies", value=True)
st.session_state["selected_customer"] = int(cid)

r = recommend_for_customer(int(cid), n_categories=5, n_movies=6, available_only=avail, exclude_current_category=explore)
st.session_state["last_recommendation"] = {"customer_id": r["customer_id"], "category": r["recommended_category"]}
s = get_settings()

# ---- Step 1-2: history ----
st.markdown("#### Customer journey (most recent on the right)")
j = an.customer_journey(int(cid))
st.markdown(ui.journey_chips(j["category"].tolist(), 10), unsafe_allow_html=True)
with st.expander(f"Full rental history ({len(j)} rentals)"):
    st.dataframe(j[["rental_number", "rental_date", "title", "category", "rating", "amount", "transition"]],
                 hide_index=True, width="stretch")

# ---- Result cards ----
k = st.columns(4)
ui.kpi(k[0], "Current category", r["current_category"], f"last rental {r['last_rental_date'][:10]}")
ui.kpi(k[1], "Recommended next category", r["recommended_category"], r["mode"])
ui.kpi(k[2], "Transition probability", f"{100*r['transition_probability']:.2f}%",
       f"{r['transitions_observed']} of {r['outgoing_transitions_from_current']} · lift {r['lift_vs_baseline']:.2f}")
ui.kpi(k[3], "Signal strength", r["signal_strength"].title(), f"z = {r['z_residual']:.2f} · matrix p = {r['global_signal']['chi2_p_value']:.2f}")

# ---- Explanation ----
st.markdown("#### Why this category?")
ui.box(
    f"The customer's most recent rental was <b>{r['current_category']}</b>. Across all Sakila rental sequences, "
    f"<b>{r['transitions_observed']}</b> of the {r['outgoing_transitions_from_current']} rentals that followed a "
    f"{r['current_category']} rental were <b>{r['recommended_category']}</b> "
    f"(P = {100*r['transition_probability']:.2f}%, lift {r['lift_vs_baseline']:.2f}). "
    f"This customer has rented {r['customer_rentals_in_recommended_category']} {r['recommended_category']} film(s) out of "
    f"{r['rentals_in_window']} (smoothed affinity {100*r['customer_affinity']:.1f}%). Combining both "
    f"(score = {s.w_transition} × transition + {s.w_affinity} × affinity), <b>{r['recommended_category']}</b> ranks first "
    f"with score {r['score']:.4f}.")
ui.box(f"Signal strength is <b>{r['signal_strength']}</b>: category-to-category transitions in Sakila are close to chance "
       f"(χ² p = {r['global_signal']['chi2_p_value']:.2f}, Cramér's V = {r['global_signal']['cramers_v']:.3f}). "
       "Treat the category as a data-informed suggestion; the movie ranking (popular, in stock, not seen before) carries most of "
       "the practical value.", "caveat")

# ---- Score breakdown ----
rk = pd.DataFrame(recommend_for_customer(int(cid), n_categories=8, n_movies=1, available_only=avail,
                                         exclude_current_category=explore)["ranked_categories"])
tot = s.w_transition + s.w_affinity
rk["transition part"] = s.w_transition / tot * rk["transition_probability"]
rk["affinity part"] = s.w_affinity / tot * rk["affinity"]
rk = rk.iloc[::-1]
fig = go.Figure()
fig.add_trace(go.Bar(y=rk["category"], x=rk["transition part"], name="Transition probability part", orientation="h",
                     marker_color=ui.BLUE, customdata=rk[["transition_probability", "transitions_from_last"]].values,
                     hovertemplate="%{y}<br>P = %{customdata[0]:.2%} (%{customdata[1]} transitions)<br>contributes %{x:.4f}<extra></extra>"))
fig.add_trace(go.Bar(y=rk["category"], x=rk["affinity part"], name="Customer affinity part", orientation="h",
                     marker_color=ui.ORANGE, customdata=rk[["affinity", "customer_rentals_in_category"]].values,
                     hovertemplate="%{y}<br>affinity %{customdata[0]:.2%} (%{customdata[1]} rentals)<br>contributes %{x:.4f}<extra></extra>"))
fig.update_layout(barmode="stack", title="Category score breakdown (top 8)", bargap=0.3)
fig.update_xaxes(title="score")
st.plotly_chart(ui.style(fig, 400, legend=True), width="stretch")

# ---- Movies ----
st.markdown(f"#### Recommended {r['recommended_category']} movies")
st.caption("Rule: films in the recommended category that this customer has never rented, "
           + ("with at least one copy in stock, " if avail else "")
           + "ranked by number of rentals in the analysis window (popularity), then copies available.")
mv = pd.DataFrame(r["recommended_movies"])
if mv.empty:
    st.info("No eligible movies found for this category.")
else:
    cols = st.columns(min(3, len(mv)))
    for i, m in mv.head(3).iterrows():
        ui.kpi(cols[i], f"#{i+1} · {m['rating']} · ${m['rental_rate']}", m["title"].title(),
               f"{m['rentals_in_window']} rentals · {m['available_copies']}/{m['copies']} copies in stock")
    st.dataframe(mv, hide_index=True, width="stretch")
alt = r["alternative_category_movies"]
if alt:
    st.markdown("**Alternatives from the next-ranked categories:** " +
                " · ".join(f"*{c}*: {', '.join(t.title() for t in titles)}" for c, titles in alt.items()))

# ---- Evaluation ----
with st.expander("How well does next-category prediction work? (hold-out test)"):
    bt = an.next_category_backtest()
    ev = pd.DataFrame({
        "method": ["Random guess", "Most popular categories", "Transition only", "This app (blend)"],
        "hit@1": [bt["random_hit@1_pct"], bt["popularity_hit@1_pct"], bt["transition_only_hit@1_pct"], bt["app_blend_hit@1_pct"]],
        "hit@3": [bt["random_hit@3_pct"], bt["popularity_hit@3_pct"], bt["transition_only_hit@3_pct"], bt["app_blend_hit@3_pct"]],
    })
    fig = go.Figure(go.Bar(x=ev["method"], y=ev["hit@3"], marker_color=[ui.GRAY, ui.BLUE, ui.BLUE, ui.BLUE],
                           text=ev["hit@3"], texttemplate="%{text:.2f}%", textposition="outside",
                           hovertemplate="%{x}<br>hit@3 = %{y:.2f}%<extra></extra>"))
    fig.update_layout(title="Hit@3: true next category among the top-3 suggestions")
    fig.update_yaxes(range=[0, 30], title="%")
    st.plotly_chart(ui.style(fig, 340), width="stretch")
    st.dataframe(ev, hide_index=True, width="stretch")
    st.caption(f"Each of the {bt['customers_tested']} customers' last rental is hidden; transitions and popularity are learned "
               f"from the remaining rentals. Standard error ≈ ±{bt['standard_error_hit@3_pp']} pp, so all methods perform "
               "about as well as a random guess — consistent with the independence test.")
