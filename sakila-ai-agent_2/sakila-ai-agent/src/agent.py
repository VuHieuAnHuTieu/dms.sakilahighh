"""Sakila AI Business Agent.

Architecture: user question -> LLM (Groq, tool/function calling) -> tools in src/tools.py
-> Sakila DB / analytics / recommendation engine -> LLM writes the final answer from tool output.

If GROQ_API_KEY / GROQ_MODEL are not configured (or the API fails), the agent falls back to an
offline deterministic router that calls the SAME tools and fills answer templates, so the demo
never shows invented numbers.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from . import analytics as an
from .config import get_settings
from .insights import DATA_LIMITS
from .tools import TOOL_SCHEMAS, call_tool

MAX_TOOL_CHARS = 14000


def system_prompt(context: dict | None = None) -> str:
    cats = ", ".join(an.categories())
    it = an.independence_test()
    ctx = ""
    if context and context.get("last_customer_id"):
        ctx = f"\nConversation context: the most recently discussed customer is customer_id={context['last_customer_id']}."
    if context and context.get("last_category"):
        ctx += f" The most recently discussed/recommended category is {context['last_category']} (resolve 'this category' to it)."
    limits = "\n".join(f"   - {t}: {d}" for t, d in DATA_LIMITS)
    return f"""You are the Sakila AI Business Agent, a senior analyst for the Sakila DVD rental chain (2 stores).
Audiences: business users (managers, lecturers, analysts) and shoppers ("hi, I want a history DVD").

CORE RULES
1. Every number, category, title, store or customer fact MUST come from a tool result in this conversation. Never guess;
   call a tool. Never infer a fact from the ABSENCE of information. If no tool covers it, try run_sql_query; if still
   unknown, say the data does not contain it. If the user says you are wrong, re-check with a tool and admit mistakes.
   Copy numbers exactly; no new ratios unless you show the formula with tool numbers. Label any illustrative number
   with the word "illustrative". State scope (analysis window vs all data) when giving totals. No HTML tags.
2. THE INSIGHTS: the team report has exactly SIX insights. For "how many / what are the insights" call get_insights()
   and list all six. For details, metrics, SQL or charts of an insight call get_insights(insight_id). Present only the
   verified_findings; mention report_check items when they correct the written report. Do not invent other insights.
3. BEFORE answering anything about causes/effects, predictions or forecasts, profit/cost, customer motives or satisfaction,
   demographics or personas, visits/baskets, churn/lifetime value, market share, BCG, pricing changes or "what if" scenarios,
   call get_data_limitations and follow it. Structure such answers as: (a) what the data can show, with numbers;
   (b) what it cannot show and why; (c) a proxy or test design that would answer it. Refuse false premises politely.
4. Association is not causation: say "is associated with", "historically observed". Counterfactuals (price cuts, new
   policies, more copies) cannot be measured from this data. Lucas critique: relationships observed under current policies
   (fixed prices, no bundles, current due dates) may change once the policy changes, so they cannot predict a new policy's
   effect; recommend a controlled pilot/A-B test with success metrics.
5. Time: rentals exist only on 41 dates in five 8-day bursts (May-Aug 2005) plus one day (2006-02-14), with a 174-day gap.
   Sep 2005-Jan 2006 are MISSING, not zero. For trends use get_trends and warn that month/quarter/year totals mainly reflect
   recorded days; never state growth rates, seasonality or monthly churn as facts.
6. Strategy: never recommend investing everything in one title/category (demand is spread evenly across 16 categories and
   customers switch category 93% of the time). BCG needs market growth and relative market share, which Sakila lacks; you may
   show an internal proxy only with that warning.
7. Metrics: define them exactly as in metrics_to_watch / field_meanings. Lift 1.4 means 1.4x the baseline share, not 140%.
   The permutation p-value (0.0166, repeat vs shuffled) is NOT the chi-square p-value (0.4351, transition independence).
8. Charts: when asked to visualize, call visualize with the relevant chart_ids (e.g. insight_1 ... insight_6); the app
   renders them. Then explain each chart in one line.
9. SQL: when asked for follow-up SQL, give the follow_up_sql of the relevant insight(s) (portable SQL) and say what it returns;
   you may test a query with run_sql_query.
10. REPORT / STORY MODE (report, story, memo, deck outline, recommendations for management): use a consulting (MBB) structure
   and the Pyramid Principle, MECE:
   # Action title that states the answer
   **Executive summary** - 3 bullets: situation, complication, resolution (answer first).
   **Key findings** - one section per insight: headline (the "so what") -> evidence (numbers from tools) -> implication.
   **Recommendations** - prioritised; each as a testable initiative with owner, KPI and pilot design (not a certainty).
   **Risks & data limitations** - chronology gap, observational data, no costs, etc.
   **Next steps** - 30/60/90-day test plan.
   Business language, no jargon without definition.
11. Neutral language ("category switching/exploration", never "disloyal"). Signal honesty: category transitions are close to
   independent (chi-square p={it['p_value']}, Cramer's V={it['cramers_v']}); never call a category a "gateway".
12. Recommendations for a customer: cite current category, P(B|A), lift, the customer's own rentals in B, weights, and the
   movie rule (not rented before, in stock, ranked by popularity).
13. Shoppers: Sakila RENTS DVDs (price per rental), it does not sell them. Categories: {cats}. For genres that do not exist
   (e.g. history, romance) say so and use search_movies with that word as category. Kids/family: only G or PG films.

DATA LIMITATIONS (always true):
{limits}

Customer IDs are 1-599. Analysis window ends before {an.headline_metrics()['analysis_end_date']}.{ctx}"""


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "llm"
    unverified: list[str] = field(default_factory=list)
    model: str | None = None
    error: str | None = None


def _for_llm(obj: dict) -> dict:
    if isinstance(obj, dict) and "charts" in obj:
        return {**obj, "charts": [{"chart_id": c["chart_id"], "title": (c["plotly"].get("layout", {}).get("title") or {}).get("text")}
                                  for c in obj["charts"]]}
    return obj


def _truncate(obj: dict) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= MAX_TOOL_CHARS else s[:MAX_TOOL_CHARS] + '..."(truncated)"'


_DATE = re.compile(r"\b\d{4}-\d{2}(-\d{2})?([ T]\d{2}:\d{2}(:\d{2})?)?\b")
_NUM = re.compile(r"(?<![\w.])[-−]?\$?\d[\d,]*(?:\.\d+)?%?")


def _numbers_in(obj, out: set) -> set:
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, out)
    elif isinstance(obj, str):
        for m in _NUM.findall(_DATE.sub(" ", obj)):
            try:
                out.add(float(m.replace("$", "").replace(",", "").replace("%", "").replace("−", "-")))
            except ValueError:
                pass
    return out


def unverified_numbers(answer: str, tool_calls: list[dict], question: str = "", extra_text: str = "") -> list[str]:
    """Numbers in the answer that do not match any number in the tool results (or the question), allowing
    rounding and the x100 percent conversion. Small integers (<= 20) and years are ignored."""
    known = set()
    for c in tool_calls:
        _numbers_in(c.get("result"), known)
        _numbers_in(c.get("arguments"), known)
    _numbers_in(question, known)
    _numbers_in(extra_text, known)
    known |= {100.0, 6.25, 16.0, 1.96, 30.0, 60.0, 90.0}
    cands = known | {k * 100 for k in known} | {k / 100 for k in known}
    bad = []
    kept = "\n".join(l for l in (answer or "").splitlines()
                      if not re.search(r"illustrative|hypothetical|for example|e\.g\.|example", l, re.I))
    for m in _NUM.findall(_DATE.sub(" ", kept)):
        try:
            x = float(m.replace("$", "").replace(",", "").replace("%", "").replace("−", "-"))
        except ValueError:
            continue
        if (x.is_integer() and abs(x) <= 20) or 1990 <= x <= 2030:
            continue
        if not any(abs(x - k) <= max(0.0051, 0.005 * abs(k)) for k in cands):
            bad.append(m)
    return sorted(set(bad))


# ---------------------------------------------------------------------------
# Retrieval of answer guidance from the team's question bank (knowledge/testbank.py)
# ---------------------------------------------------------------------------
_STOP = set("a an the of to in for is are was were be do does did what which who how why can could should would will "
            "i me my we our you your it its that this these those and or on at by with from as if than then there their "
            "sakila customer customers".split())


def _tokens(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9$.]+", t.lower().replace("-", " ")) if w not in _STOP and len(w) > 1]


def guidance_for(question: str, k: int = 2, min_score: float = 0.22) -> list[dict]:
    from knowledge.testbank import TESTBANK
    import math
    docs = [set(_tokens(e["q"])) for e in TESTBANK]
    df = {}
    for d in docs:
        for w in d:
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log(1 + len(docs) / c) for w, c in df.items()}
    syn = {"bundle": ["combo", "bulk", "price"], "bundles": ["combo", "bulk", "price"], "combo": ["bulk", "price"], "pricing": ["price"],
           "forecast": ["predict", "demand"], "prediction": ["predict", "demand"], "older": ["age", "group"], "younger": ["age", "group"],
           "age": ["group"], "lose": ["lose", "revenue"], "lost": ["lose", "revenue"], "persona": ["persona"], "personas": ["persona"],
           "branches": ["stores"], "branch": ["stores"], "shops": ["stores"], "trend": ["trend", "months"], "trends": ["trend", "months"],
           "valentine": ["valentine's", "february"], "bcg": ["bcg", "matrix"], "invest": ["invest", "totally"]}
    q = set(_tokens(question))
    for w in list(q):
        q |= set(syn.get(w, []))
    if not q:
        return []
    scored = []
    for e, d in zip(TESTBANK, docs):
        inter = sum(idf.get(w, 0) for w in q & d)
        denom = sum(idf.get(w, 1) for w in q | d) or 1
        scored.append((inter / denom, e))
    scored.sort(key=lambda x: -x[0])
    return [dict(e, score=round(sc, 3)) for sc, e in scored[:k] if sc >= min_score]


def llm_available() -> bool:
    s = get_settings()
    return bool(s.groq_api_key and s.groq_model)


def run_agent(question: str, history: list[dict] | None = None, context: dict | None = None,
              client: Any = None) -> AgentResult:
    """Answer `question`. `history` = previous [{'role','content'}] turns. `client` lets tests inject a fake Groq client."""
    context = context if context is not None else {}
    _update_context(question, context)
    s = get_settings()
    if client is None and not llm_available():
        res = run_offline(question, context)
        res.error = "GROQ_API_KEY/GROQ_MODEL not set - running offline deterministic mode."
        return res
    try:
        if client is None:
            from groq import Groq
            client = Groq(api_key=s.groq_api_key)
        return _run_llm(question, history or [], context, client, s.groq_model or "test-model", s.agent_max_tool_rounds)
    except Exception as e:  # network / API / tool-format failure -> honest fallback
        res = run_offline(question, context)
        res.error = f"LLM call failed ({type(e).__name__}: {str(e)[:200]}). Answered in offline mode."
        return res


def _run_llm(question: str, history: list[dict], context: dict, client: Any, model: str, max_rounds: int) -> AgentResult:
    sys_prompt = system_prompt(context)
    guides = guidance_for(question)
    if guides:
        sys_prompt += "\n\nANSWER GUIDANCE for similar questions from the team's question bank (follow the approach; take numbers from tools):\n" + "\n".join(
            f"- Q: {g['q']}\n  How to answer: {g['guide']}\n  Tools: {', '.join(g['tools']) or 'none needed'}" for g in guides)
    messages: list[dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-8:] if m.get("role") in ("user", "assistant")]
    messages.append({"role": "user", "content": question})
    calls: list[dict[str, Any]] = []
    revised = False
    for _ in range(max_rounds + 1):
        resp = client.chat.completions.create(model=model, messages=messages, tools=TOOL_SCHEMAS,
                                              tool_choice="auto", temperature=0.2, max_tokens=4000)
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            answer = (msg.content or "").replace("<br>", "; ")
            bad = unverified_numbers(answer, calls, question, messages[0]["content"])
            if bad and not revised:
                # grounding check: ask the model once to fix numbers that no tool returned
                revised = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content":
                    "GROUNDING CHECK FAILED. These numbers in your answer do not appear in any tool result: "
                    + ", ".join(bad) + ". Rewrite the answer: use only numbers returned by tools (call a tool if you need more data), "
                    "or remove the claim. Do not mention this check."})
                continue
            return AgentResult(answer=answer, tool_calls=calls, mode="llm", model=model, unverified=bad)
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                                        for tc in tool_calls]})
        for tc in tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = call_tool(tc.function.name, args)
            if "customer_id" in args:
                context["last_customer_id"] = int(args["customer_id"])
            _context_from_result(tc.function.name, result, context)
            calls.append({"tool": tc.function.name, "arguments": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.function.name, "content": _truncate(_for_llm(result))})
    return AgentResult(answer="I reached the tool-call limit before finishing. Please ask a narrower question.",
                       tool_calls=calls, mode="llm", model=model)


# ---------------------------------------------------------------------------
# Offline deterministic router (same tools, template answers)
# ---------------------------------------------------------------------------
def _update_context(q: str, context: dict) -> None:
    m = re.search(r"customer\s*(?:id)?\s*#?\s*(\d{1,3})", q, re.I)
    if m:
        context["last_customer_id"] = int(m.group(1))
    for c in an.categories():
        if re.search(rf"\b{re.escape(c)}\b", q, re.I):
            context["last_category"] = c


def _context_from_result(name: str, result: dict, context: dict) -> None:
    if name == "get_customer_recommendation" and "recommended_category" in result:
        context["last_category"] = result["recommended_category"]
        context["last_customer_id"] = result["customer_id"]
    elif name == "get_category_transitions" and "category" in result:
        context["last_category"] = result["category"]


def _find_category(q: str) -> str | None:
    for c in sorted(an.categories(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", q, re.I):
            return c
    return None


def _pct(x: float) -> str:
    return f"{100 * x:.2f}%"


def run_offline(q: str, context: dict) -> AgentResult:
    ql = q.lower()
    cid = context.get("last_customer_id")
    cat = _find_category(q) or (context.get("last_category") if re.search(r"\b(this|that) category\b", ql) else None)
    calls: list[dict] = []

    def use(name: str, **args) -> dict:
        r = call_tool(name, args)
        calls.append({"tool": name, "arguments": args, "result": r})
        _context_from_result(name, r, context)
        return r

    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    m = re.search(r"\b(\d{1,2}|" + "|".join(words) + r")\s+(?:\w+\s+)?(?:movies|films|titles)", ql)
    n_movies = (int(m.group(1)) if m.group(1).isdigit() else words[m.group(1)]) if m else 5
    explicit_customer = bool(re.search(r"customer\s*(?:id)?\s*#?\s*\d", ql))
    refers_customer = explicit_customer or bool(re.search(r"\b(this|that|the same) customer\b|\b(he|she|they|them|their|his|her)\b", ql))

    if cid and re.search(r"\bwhy\b|explain|reason", ql) and re.search(r"recommend|categor|suggest|movie|film", ql):
        r = use("get_customer_recommendation", customer_id=cid)
        ans = _fmt_reco(r, explain=True)
    elif not explicit_customer and re.search(r"significan|random|chi.?square|independen|predictab", ql):
        v = use("get_business_metrics", metric_name="transition_statistics")["value"]
        ans = (f"{v['interpretation']}\n\n- χ² = {v['chi2']} (dof {v['dof']}), p = {v['p_value']}\n- Cramér's V = {v['cramers_v']}\n"
               f"- Highest off-diagonal P(B|A) = {_pct(v['max_probability'])} vs chance {_pct(v['uniform_probability'])}\n"
               f"- Cells significant after Bonferroni: {v['cells_significant_after_bonferroni']} of {v['cells']}")
    elif re.search(r"backtest|accura|hit rate|hit@|evaluat", ql):
        v = use("get_business_metrics", metric_name="recommendation_backtest")["value"]
        ans = ("Hold-out test (each customer's last rental hidden):\n\n| Method | hit@1 | hit@3 |\n|---|---|---|\n"
               f"| Random | {v['random_hit@1_pct']}% | {v['random_hit@3_pct']}% |\n| Popularity | {v['popularity_hit@1_pct']}% | {v['popularity_hit@3_pct']}% |\n"
               f"| Transition only | {v['transition_only_hit@1_pct']}% | {v['transition_only_hit@3_pct']}% |\n| App blend | {v['app_blend_hit@1_pct']}% | {v['app_blend_hit@3_pct']}% |\n\n"
               f"Standard error ≈ ±{v['standard_error_hit@3_pp']} pp, so differences are within noise.")
    elif cid and refers_customer | bool(re.search(r"recommend|watch next|suggest", ql)) and re.search(r"recommend|watch next|suggest|should .* watch|next category", ql):
        r = use("get_customer_recommendation", customer_id=cid, n_movies=n_movies,
                exploration_mode=bool(re.search(r"explor|new category|different category", ql)))
        ans = _fmt_reco(r)
    elif cid and refers_customer and re.search(r"journey|history|rented|profile|rentals", ql):
        ans = _fmt_history(use("get_customer_history", customer_id=cid, max_rentals=15))
    elif cat and re.search(r"strongest transition to|lead(s)? to|into|before|come from|towards?", ql):
        ans = _fmt_trans(use("get_category_transitions", category_name=cat, direction="incoming"))
    elif cat and re.search(r"next|after|go|move|transition|switch", ql):
        ans = _fmt_trans(use("get_category_transitions", category_name=cat, direction="outgoing"))
    elif re.search(r"\b(stores?|shops?|branch(es)?|chi nhánh|cửa hàng)\b", ql):
        v = use("get_business_metrics", metric_name="stores")["value"]
        ans = (f"Sakila has **{v['total_stores']} stores**:\n\n| Store | Location | Manager | Customers | Copies | Rentals | Revenue |\n|---|---|---|---|---|---|---|\n"
               + "\n".join(f"| {r['store_id']} | {r['city']}, {r['country']} | {r['manager']} | {r['customers']} | {r['copies']:,} | {r['rentals']:,} | ${r['revenue']:,.2f} |" for r in v["stores"])
               + "\n\n_Rentals and revenue are attributed to the store that owns the rented copy._")
    elif re.search(r"\b(visuali[sz]e|chart|graph|plot)\b", ql):
        use("visualize", chart_ids=[f"insight_{i}" for i in range(1, 7)])
        ans = "Here are the six insights as charts (rendered below), each built from verified data."
    elif re.search(r"\bsql\b|query", ql) and re.search(r"insight", ql):
        parts = [use("get_insights", insight_id=i) for i in range(1, 7)]
        ans = "Follow-up SQL for each insight (portable SQL; tested on the Sakila database):\n\n" + "\n\n".join(
            f"**Insight {x['id']} - {x['title']}**\n```sql\n{x['follow_up_sql']}\n```" for x in parts)
    elif re.search(r"\bmetrics?\b|kpis?", ql):
        parts = [use("get_insights", insight_id=i) for i in range(1, 7)]
        ans = "Metrics to watch, by insight:\n\n" + "\n".join(
            f"- **Insight {x['id']}**: " + "; ".join(f"`{k}` = {v}" for k, v in x["metrics_to_watch"].items()) for x in parts)
    elif re.search(r"\b(report|story|memo)\b", ql):
        a = use("get_insights")
        lim = use("get_data_limitations")["limitations"]
        ans = ("# Sakila retains every customer, but its policies and assortment are not tuned to how customers actually behave\n\n"
               "**Executive summary**\n- *Situation*: all 599 customers return and rent across most categories.\n"
               "- *Complication*: due dates, pricing and inventory are set per title, while behaviour is uniform (holding ~5 days on average for every policy, demand spread evenly).\n"
               "- *Resolution*: test policy changes (extensions, bundles, copy reallocation) with controlled pilots rather than roll them out.\n\n"
               "**Key findings**\n" + "\n".join(f"{x['id']}. **{x['title']}** - " + " ".join(x["verified_findings"][:2]) for x in a["insights"])
               + "\n\n**Recommendations (to be tested, not proven)**\n1. Pre-due-date extension option priced below the late fee (pilot one store).\n"
               "2. Two-title same-category bundle for single-$0.99 visits (A/B test).\n3. Next-title suggestions when a customer is down to one open DVD.\n"
               "4. Review copies for high/low rentals-per-copy films.\n\n**Risks & data limitations**\n" + "\n".join(f"- {l['limitation']}" for l in lim[:5])
               + "\n\n**Next steps**: 30 days define KPIs and control groups; 60 days run pilots; 90 days read results and decide.")
    elif re.search(r"\b(trend|monthly|quarter|quarterly|year|yearly|annual)\b", ql):
        t = use("get_trends", granularity="quarter" if "quarter" in ql else "year" if re.search(r"\byear|annual", ql) else "month")
        ans = "| Period | Rentals | Revenue | Recorded days |\n|---|---|---|---|\n" + "\n".join(
            f"| {r['period']} | {r['rentals']:,} | ${r['revenue']:,.2f} | {r['recorded_days']} |" for r in t["rows"]) + f"\n\n**Warning:** {t['warning']}"
    elif re.search(r"forecast|predict|bcg|price|pricing|combo|bulk|elasticit|profit|lucas|cause|churn|lifetime|demograph|gender|age group", ql):
        topic = next((t for t in ("forecast", "bcg", "causality", "money", "churn", "demographics") if re.search(
            {"forecast": "forecast|predict", "bcg": "bcg", "causality": "cause|price|pricing|combo|bulk|elasticit|lucas",
             "money": "profit", "churn": "churn|lifetime", "demographics": "demograph|gender|age group"}[t], ql)), None)
        lim = use("get_data_limitations", topic=topic)["limitations"]
        ans = ("What the data can and cannot show here:\n\n" + "\n".join(f"- {l['limitation']}" for l in lim)
               + "\n\nSet GROQ_API_KEY/GROQ_MODEL for a full answer; the agent will add the relevant insight numbers and a test design.")
    elif re.search(r"persona|segment", ql):
        seg = use("get_business_metrics", metric_name="customer_segments")["value"]
        ans = seg["method"] + "\n\n| Segment | Customers | Avg rentals | Avg revenue | Late share |\n|---|---|---|---|---|\n" + "\n".join(
            f"| {r['segment']} | {r['customers']} | {r['avg_rentals']} | ${r['avg_revenue']} | {r['avg_late_share_pct']}% |" for r in seg["segments"]) + f"\n\n_{seg['caveat']}_"
    elif re.search(r"\b(insights?|findings?|summary|summarize|key (numbers|results))\b", ql):
        a = use("get_insights")
        ans = f"There are **{a['count']} insights** (recomputed from the database):\n\n" + "\n".join(
            f"{x['id']}. **{x['title']}** - {x['verified_findings'][0]}" for x in a["insights"])
    elif re.search(r"gateway|high.transition", ql):
        r = use("get_business_metrics", metric_name="high_transition_categories")
        a = r["value"]["assessment"]
        top = r["value"]["table"][:3]
        ans = (f"**Gateway supported by data: {a['gateway_supported']}** → using the term *{a['label_used']}*.\n\n{a['explanation']}\n\n"
               + "\n".join(f"- {t['category']}: {t['outgoing_transitions']} outgoing transitions, entropy {t['outgoing_entropy']}, "
                           f"strongest → {t['strongest_destination']} ({_pct(t['strongest_probability'])})" for t in top))
    elif re.search(r"switch|repeat|loyal|explor|same category", ql):
        v = use("get_business_metrics", metric_name="repeat_vs_switch")["value"]
        ans = (f"Of {v['transitions']:,} consecutive-rental pairs, **{v['switch_pct']}% switch category** and {v['repeat_pct']}% repeat it. "
               f"Pure chance would give ~{v['random_choice_repeat_pct']}% repeats (shuffled sequences: {v['shuffled_sequence_repeat_pct']}%, "
               f"p = {v['shuffled_repeat_p_value']}), so repetition is only slightly above chance.")
    elif re.search(r"(most|top).*(rented|popular).*categor|categor.*(most|popular)", ql):
        rows = use("get_business_metrics", metric_name="most_rented_categories")["value"]
        ans = "Most rented categories (analysis window):\n\n| Category | Rentals | Share |\n|---|---|---|\n" + "\n".join(
            f"| {r['category']} | {r['rentals']:,} | {r['rental_share_pct']:.2f}% |" for r in rows[:8])
    elif re.search(r"revenue", ql) and re.search(r"categor", ql):
        rows = use("get_business_metrics", metric_name="category_revenue")["value"]
        ans = "Revenue by category:\n\n| Category | Revenue | Share |\n|---|---|---|\n" + "\n".join(
            f"| {r['category']} | ${r['revenue']:,.2f} | {r['revenue_share_pct']:.2f}% |" for r in rows[:8])
    elif re.search(r"\b(want|looking for|buy|rent|find|any|suggest|recommend me|in the mood|show me)\b", ql) and \
            re.search(r"movie|film|dvd|something|watch", ql) and not explicit_customer:
        from .tools import GENRE_SYNONYMS
        word = cat or next((k for k in sorted(GENRE_SYNONYMS, key=len, reverse=True) if re.search(rf"\b{re.escape(k)}\b", ql)), None)
        if word is None:
            r = use("search_movies", available_only=True, limit=n_movies)
            head = "Here are our most popular films that are in stock right now:"
        else:
            r = use("search_movies", category=word, available_only=True, limit=n_movies)
            head = r.get("genre_note") or f"Top available {word} films:"
        buy = "Just so you know: Sakila **rents** DVDs rather than selling them. " if re.search(r"\bbuy|purchase\b", ql) else ""
        ans = (f"Hi! {buy}{head}\n\n" + "\n".join(
            f"- **{m['title'].title()}** ({m['category']}, {m['rating']}, ${m['rental_rate']} per rental): {m['description']}. "
            f"{m['available_copies']} copies in stock" for m in r.get("movies", [])))
    elif cat and re.search(r"movie|film|title", ql):
        r = use("search_movies", category=cat, available_only=True, limit=n_movies)
        ans = f"Top available {cat} films by rentals:\n\n" + "\n".join(
            f"- **{m['title']}** ({m['rating']}, ${m['rental_rate']}) — {m['rentals_in_window']} rentals, {m['available_copies']} copies in stock"
            for m in r["movies"])
    elif re.search(r"revenue|customers|rentals|kpi|overview|rate", ql):
        v = use("get_business_metrics", metric_name="overview")["value"]
        ans = (f"- Customers: {v['total_customers']}\n- Rentals: {v['total_rentals']:,}\n- Revenue: ${v['total_revenue']:,.2f}\n"
               f"- Avg catalogue rental rate: ${v['avg_catalog_rental_rate']:.2f}\n- Most rented category: {v['most_rented_category']} "
               f"({v['most_rented_category_rentals']:,} rentals)\n\nWindow: {v['first_rental'][:10]} → {v['last_rental'][:10]}.")
    else:
        ans = ("Offline mode understands questions like: *What should customer 42 watch next?*, *Why did you recommend this category?*, "
               "*Show me customer 42's rental journey*, *Where do Action customers go next?*, *Which category has the strongest "
               "transition to Comedy?*, *What are the most rented categories?*, *Is there a gateway category?*. "
               "Set GROQ_API_KEY and GROQ_MODEL for free-form questions.")
    return AgentResult(answer=ans, tool_calls=calls, mode="offline")


def _fmt_reco(r: dict, explain: bool = False) -> str:
    if "error" in r:
        return r["error"]
    movies = "\n".join(f"- **{m['title']}** ({m['rating']}, ${m['rental_rate']}) — {m['rentals_in_window']} rentals in window, "
                       f"{m['available_copies']} copies in stock" for m in r["recommended_movies"])
    head = (f"**Customer {r['customer_id']} → recommended category: {r['recommended_category']}** "
            f"(signal strength: {r['signal_strength']})\n\nRecent categories: {' → '.join(r['recent_categories'])}\n\n")
    why = (f"**Why:** the most recent rental was **{r['current_category']}**. Across all Sakila rental sequences, "
           f"{r['transitions_observed']} of {r['outgoing_transitions_from_current']} transitions out of {r['current_category']} went to "
           f"{r['recommended_category']} (P = {_pct(r['transition_probability'])}, lift {r['lift_vs_baseline']}, z = {r['z_residual']}). "
           f"The customer has rented {r['customer_rentals_in_recommended_category']} {r['recommended_category']} film(s) of "
           f"{r['rentals_in_window']}. Score = {r['weights']['transition']}×transition probability + {r['weights']['affinity']}×customer affinity "
           f"= {r['score']}.\n\n")
    ranked = "Top categories: " + ", ".join(f"{c['category']} ({c['score']:.4f})" for c in r["ranked_categories"]) + "\n\n"
    caveat = (f"_Caveat: overall, the next category is close to independent of the previous one (χ² p = {r['global_signal']['chi2_p_value']}, "
              f"Cramér's V = {r['global_signal']['cramers_v']}), so treat this as a data-informed suggestion, not a prediction._")
    return head + why + (ranked if explain else "") + "**Movies** (not rented before, in stock, ranked by popularity):\n" + movies + "\n\n" + caveat


def _fmt_history(r: dict) -> str:
    if "error" in r:
        return r["error"]
    c = r["customer"]
    rows = "\n".join(f"| {x['rental_number']} | {x['rental_date'][:10]} | {x['title']} | {x['category']} | {x['transition']} |" for x in r["rentals"])
    return (f"**{c['first_name'].title()} {c['last_name'].title()}** (customer {c['customer_id']}, {c['city']}, {c['country']}) — "
            f"{r['rental_count']} rentals across {r['distinct_categories']} categories; {r['switch_transitions']} switches, "
            f"{r['repeat_transitions']} repeats.\n\nJourney: {r['category_journey']}\n\n| # | Date | Title | Category | Step |\n|---|---|---|---|---|\n{rows}")


def _fmt_trans(r: dict) -> str:
    if "error" in r:
        return r["error"]
    st = r["statistical_context"]
    if r.get("direction") == "incoming":
        rows = "\n".join(f"| {x['from_category']} | {x['transitions']} | {_pct(x['probability_from_source'])} | {x['lift']} | {x['z_residual']} |"
                         for x in r["top_source_categories"])
        body = (f"Categories whose customers most often move **into {r['category']}** next:\n\n| From | Transitions | P({r['category']} | from) | Lift | z |\n"
                f"|---|---|---|---|---|\n{rows}")
    else:
        rows = "\n".join(f"| {x['to_category']} | {x['transitions']} | {_pct(x['probability'])} | {x['lift']} | {x['z_residual']} |"
                         for x in r["top_destinations"])
        body = (f"After renting **{r['category']}** ({r['outgoing_transitions']} observed next rentals), customers most often move to:\n\n"
                f"| Next category | Transitions | Probability | Lift | z |\n|---|---|---|---|---|\n{rows}\n\n"
                f"They rent {r['category']} again {_pct(r['self_transition_probability'])} of the time; all {r['unique_destination_categories']} other categories are reached.")
    return body + (f"\n\n_Chance level is {_pct(st['uniform_probability'])}; overall χ² p = {st['p_value']}, "
                   f"Cramér's V = {st['cramers_v']} → these differences are small and mostly within random variation._")
