"""Sakila Next-Category Intelligence — Streamlit entry point.

Run:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Sakila Next-Category Intelligence", page_icon="🎬", layout="wide")

from src import analytics as an  # noqa: E402
from src.agent import llm_available  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.database import backend_label  # noqa: E402

pages = [
    st.Page("pages/overview.py", title="1 · Executive Overview", icon="📈", default=True),
    st.Page("pages/customer_exploration.py", title="2 · Customer Exploration", icon="🧭"),
    st.Page("pages/category_transition.py", title="3 · Category Transition", icon="🔀"),
    st.Page("pages/recommendation.py", title="4 · Recommendation", icon="🎯"),
    st.Page("pages/ai_agent.py", title="5 · AI Agent", icon="🤖"),
]
nav = st.navigation(pages)

with st.sidebar:
    st.markdown("### 🎬 Sakila BI")
    st.caption("Beyond Category Loyalty: customer exploration & next-category recommendation")
    try:
        h = an.headline_metrics()
        st.success(f"Database connected\n\n{backend_label()}", icon="✅")
        st.caption(f"Analysis window: {h['first_rental'][:10]} → {h['last_rental'][:10]} "
                   f"(rentals before {get_settings().analysis_end_date or 'end of data'})")
    except Exception as e:  # show a clear message instead of a stack trace
        st.error(f"Database error: {e}")
        st.stop()
    s = get_settings()
    if llm_available():
        st.info(f"AI Agent: Groq · `{s.groq_model}`", icon="🧠")
    else:
        st.warning("AI Agent: offline mode (set GROQ_API_KEY + GROQ_MODEL in .env)", icon="🔌")

nav.run()
