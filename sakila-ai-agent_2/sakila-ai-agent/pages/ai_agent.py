import json

import streamlit as st

from src import ui
from src.agent import _for_llm, llm_available, run_agent
from src.config import get_settings

ui.setup("🤖 Sakila AI Business Agent",
         "Ask about customer behaviour, category transitions, recommendations, movies or business metrics. "
         "The agent answers by calling tools that query the Sakila database.", step="STEP 5")

s = get_settings()
if llm_available():
    st.caption(f"Mode: **LLM with tool calling** · Groq · `{s.groq_model}`")
else:
    st.caption("Mode: **offline** — deterministic router calling the same tools (set `GROQ_API_KEY` and `GROQ_MODEL` in `.env` "
               "for free-form questions).")

if "chat" not in st.session_state:
    st.session_state.chat = []  # list of {"role","content","tool_calls","mode","error"}
if "agent_context" not in st.session_state:
    st.session_state.agent_context = {}
# carry the customer/category selected on the Recommendation page into the conversation
last = st.session_state.get("last_recommendation")
if last and st.session_state.get("_synced_reco") != last:
    st.session_state.agent_context.update(last_customer_id=last["customer_id"], last_category=last["category"])
    st.session_state["_synced_reco"] = dict(last)

examples = [
    f"What should customer {st.session_state.agent_context.get('last_customer_id', 42)} watch next?",
    "Why did you recommend this category?",
    "Which categories do customers most often move to after this category?",
    "Show me customer 42's rental journey",
    "Which category has the strongest transition to Comedy?",
    "Is the next category predictable, or close to random?",
    "Is there a gateway category?",
    "What are the most rented categories?",
]
with st.expander("Example questions", expanded=not st.session_state.chat):
    cols = st.columns(2)
    for i, q in enumerate(examples):
        if cols[i % 2].button(q, key=f"ex{i}", width="stretch"):
            st.session_state.pending = q

top = st.columns([6, 1])
if top[1].button("Clear chat"):
    st.session_state.chat, st.session_state.agent_context = [], {}
    st.rerun()


def show_charts(calls):
    import plotly.graph_objects as go
    for c in calls or []:
        if c.get("tool") == "visualize":
            for chart in (c.get("result") or {}).get("charts", []):
                st.session_state["_chart_n"] = st.session_state.get("_chart_n", 0) + 1
                st.plotly_chart(go.Figure(chart["plotly"]), width="stretch", key=f"chart-{st.session_state['_chart_n']}")


def show_tools(calls, mode, error):
    show_charts(calls)
    if error:
        st.caption(f"ℹ️ {error}")
    if calls:
        with st.expander(f"🔧 {len(calls)} tool call(s) · {mode} mode — data used for this answer"):
            for c in calls:
                st.markdown(f"**{c['tool']}** `{json.dumps(c['arguments'])}`")
                st.json(_for_llm(c["result"]), expanded=False)


for m in st.session_state.chat:
    with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "🤖"):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            if m.get("unverified"):
                st.warning("Grounding check: unmatched numbers: " + ", ".join(m["unverified"]), icon="⚠️")
            show_tools(m.get("tool_calls"), m.get("mode"), m.get("error"))

MAX_Q = int(__import__("os").getenv("AGENT_MAX_QUESTIONS_PER_SESSION", "40"))  # protects the Groq key on a public deploy
question = st.chat_input("Ask a question…") or st.session_state.pop("pending", None)
asked = sum(1 for m in st.session_state.chat if m["role"] == "user")
if question and asked >= MAX_Q:
    st.warning(f"This demo allows {MAX_Q} questions per session. Refresh the page to start a new session.")
    question = None
if question:
    with st.chat_message("user", avatar="🧑"):
        st.markdown(question)
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat]
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Querying Sakila…"):
            res = run_agent(question, history=history, context=st.session_state.agent_context)
        st.markdown(res.answer)
        if res.unverified:
            st.warning("Grounding check: these numbers could not be matched to any tool result: " + ", ".join(res.unverified)
                       + ". Treat them with caution.", icon="⚠️")
        show_tools(res.tool_calls, res.mode, res.error)
    st.session_state.chat += [
        {"role": "user", "content": question},
        {"role": "assistant", "content": res.answer, "tool_calls": res.tool_calls, "mode": res.mode, "error": res.error,
         "unverified": res.unverified},
    ]
