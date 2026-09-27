"""Ground truth for the team's six insights and the question bank."""
import json
from types import SimpleNamespace

import pytest

from knowledge.testbank import TESTBANK
from src import charts as ch
from src import insights as ins
from src.agent import _for_llm, guidance_for, run_agent
from src.tools import TOOLS, call_tool, run_sql_query


def test_six_insights_and_key_numbers():
    a = ins.all_insights()
    assert a["count"] == 6
    i1, i3, i6 = ins.insight_1(), ins.insight_3(), ins.insight_6()
    t = {r["rental_duration"]: r for r in i1["table"]}
    assert t[3]["pct_late_exact_time"] == 72.07 and t[7]["pct_late_exact_time"] == 29.06
    assert all(4.9 < r["avg_actual_hold_days"] < 5.1 for r in i1["table"])
    assert "UNIFORMLY" in " ".join(i1["verified_findings"])
    assert "2.44" in i3["verified_findings"][0] and "3,208" in i3["verified_findings"][1]
    assert i3["calendar_buckets_pct"]["7-14 days"] == 67.93
    assert "0.935" in i6["verified_findings"][1] and i6["verified_findings"][0].startswith("958 of 1000")


def test_chronology_gap():
    c = ins.chronology()
    assert c["distinct_rental_dates"] == 41 and c["gap_days"] == 174
    assert c["months_with_no_rentals"] == ["2005-09", "2005-10", "2005-11", "2005-12", "2006-01"]
    assert c["feb_2006_batch"]["rentals"] == 182 == c["feb_2006_batch"]["unreturned"]
    assert "MISSING" in ins.trends("month")["warning"].upper() or "NO rentals" in ins.trends("month")["warning"]


def test_follow_up_sql_runs():
    for i in range(1, 7):
        r = run_sql_query(ins.INSIGHTS[i]()["follow_up_sql"], max_rows=2)
        assert "error" not in r and r["row_count"] > 0, (i, r)


def test_all_charts_build_and_are_stripped_for_llm():
    ids = list(ch.CHARTS)
    for part in (ids[:7], ids[7:]):
        r = call_tool("visualize", {"chart_ids": part})
        assert r["rendered"] == part
    slim = _for_llm(r)
    assert len(json.dumps(slim)) < 3000 and "plotly" not in json.dumps(slim)


def test_question_bank_is_retrievable_and_tools_exist():
    for e in TESTBANK:
        top = guidance_for(e["q"])
        assert top and top[0]["q"] == e["q"], e["q"]
        assert set(e["tools"]) <= set(TOOLS), e


def test_trap_facts():
    m = ins.misc_facts()
    assert 45 < m["store_attribution"]["pct_rentals_inventory_store_differs_from_customer_store"] < 55
    assert abs(m["film_length_vs_holding_days_correlation"]) < 0.05
    rb = call_tool("get_business_metrics", {"metric_name": "revenue_breakdown"})["value"]
    assert "PROXY" in rb["note"]


@pytest.mark.parametrize("q,must", [
    ("How many insights are there?", "6 insights"),
    ("Analyze any trend in months, quarters and year?", "174-day gap"),
    ("What are the customer persona for Sakila?", "NO age"),
    ("Use the BCG matrix to actually categorize the customer segments and titles/categories.", "market growth"),
    ("Give me the follow-up SQL query with the insights", "```sql"),
])
def test_offline_answers_for_core_questions(q, must):
    assert must in run_agent(q, context={}).answer


class _SpyGroq:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="It is not supported by the data.", tool_calls=None))])


def test_guidance_injected_into_llm_prompt():
    spy = _SpyGroq()
    run_agent("Was the February 14, 2006 rental spike caused by Valentine's Day demand?", context={}, client=spy)
    sys_msg = spy.calls[0]["messages"][0]["content"]
    assert "ANSWER GUIDANCE" in sys_msg and "anomalous" in sys_msg and "SIX insights" in sys_msg
