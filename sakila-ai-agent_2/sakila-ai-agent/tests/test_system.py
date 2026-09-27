"""End-to-end checks: SQL vs pandas consistency, recommendation rules, tools and agent loop."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src import analytics as an
from src import database as db
from src.agent import run_agent
from src.recommendation import recommend_for_customer
from src.tools import TOOL_SCHEMAS, TOOLS, call_tool

ROOT = Path(__file__).resolve().parents[1]


def test_schema_relationships():
    # every film has exactly one category -> each rental maps to one category
    fc = db.query("SELECT film_id, COUNT(*) n FROM film_category GROUP BY film_id")
    assert (fc["n"] == 1).all()
    assert len(an.rental_events()) == int(db.query(
        "SELECT COUNT(*) n FROM rental WHERE rental_date < :d", {"d": db.window_params()["end_date"]})["n"].iloc[0])


def test_sql_transitions_match_pandas():
    t = an.transitions_df()
    pandas_counts = pd.crosstab(t["prev_category"], t["category"]).reindex(
        index=an.categories(), columns=an.categories(), fill_value=0)
    sql_counts = an.transition_counts()
    assert (pandas_counts.values == sql_counts.values).all()
    rs = db.run("category_transitions.sql", "repeat_vs_switch", **db.window_params()).iloc[0]
    st = an.repetition_stats()
    assert int(rs["same_category"]) == st["same_category"]
    assert int(rs["total_transitions"]) == st["transitions"] == len(t)
    # transitions = rentals - customers
    assert st["transitions"] == len(an.rental_events()) - an.rental_events()["customer_id"].nunique()


def test_probability_matrix_rows_sum_to_one():
    assert np.allclose(an.probability_matrix().sum(axis=1).values, 1.0)
    long = an.transition_long()
    assert np.allclose(long.groupby("from_category")["probability"].sum(), 1.0)


def test_independence_test_consistent():
    it = an.independence_test()
    assert it["dof"] == (len(an.categories()) - 1) ** 2
    assert 0 <= it["p_value"] <= 1 and 0 <= it["cramers_v"] <= 1


@pytest.mark.parametrize("cid", [1, 42, 130, 599])
def test_recommendation_rules(cid):
    r = recommend_for_customer(cid)
    seen = set(db.run("customer_history.sql", "customer_all_film_ids", customer_id=cid)["film_id"])
    assert r["recommended_movies"], "should return movies"
    for m in r["recommended_movies"]:
        assert m["category"] == r["recommended_category"]
        assert m["film_id"] not in seen
        assert m["available_copies"] > 0
    scores = [c["score"] for c in r["ranked_categories"]]
    assert scores == sorted(scores, reverse=True)
    assert r["current_category"] == an.customer_journey(cid)["category"].iloc[-1]
    P = an.probability_matrix()
    assert abs(r["transition_probability"] - P.loc[r["current_category"], r["recommended_category"]]) < 1e-4


def test_exploration_mode_excludes_current():
    r = recommend_for_customer(42, exclude_current_category=True)
    assert r["recommended_category"] != r["current_category"]


def test_tools_are_json_serialisable_and_validate_inputs():
    assert {s["function"]["name"] for s in TOOL_SCHEMAS} == set(TOOLS)
    for name, args in [("get_customer_history", {"customer_id": 42}),
                       ("get_category_transitions", {"category_name": "action"}),
                       ("get_category_transitions", {"category_name": "Comedy", "direction": "incoming"}),
                       ("get_customer_recommendation", {"customer_id": 42}),
                       ("search_movies", {"category": "Comedy", "available_only": True}),
                       ("get_business_metrics", {"metric_name": "high_transition_categories"}),
                       ("get_business_metrics", {"metric_name": "recommendation_backtest"})]:
        out = call_tool(name, args)
        json.dumps(out)
        assert "error" not in out, (name, out)
    assert "error" in call_tool("get_customer_history", {"customer_id": 9999})
    assert "error" in call_tool("get_category_transitions", {"category_name": "Western"})
    assert "error" in call_tool("get_business_metrics", {"metric_name": "nope"})


class _FakeGroq:
    """Mimics groq.Groq().chat.completions.create: first asks for a tool, then answers."""
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            tc = SimpleNamespace(id="call_1", function=SimpleNamespace(
                name="get_customer_recommendation", arguments=json.dumps({"customer_id": 42})))
            msg = SimpleNamespace(content="", tool_calls=[tc])
        else:
            tool_msg = kw["messages"][-1]
            assert tool_msg["role"] == "tool"
            data = json.loads(tool_msg["content"])
            msg = SimpleNamespace(content=f"Recommend {data['recommended_category']}", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_llm_tool_loop_with_fake_client():
    ctx = {}
    fake = _FakeGroq()
    res = run_agent("What should customer 42 watch next?", context=ctx, client=fake)
    expected = recommend_for_customer(42)["recommended_category"]
    assert res.mode == "llm" and res.answer == f"Recommend {expected}"
    assert res.tool_calls[0]["tool"] == "get_customer_recommendation"
    assert ctx["last_customer_id"] == 42 and ctx["last_category"] == expected
    assert fake.calls[0]["tools"] == TOOL_SCHEMAS


def test_llm_failure_falls_back_offline():
    class Broken:
        chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))))
    res = run_agent("Where do Action customers usually go next?", context={}, client=Broken())
    assert res.mode == "offline" and "boom" in res.error and res.tool_calls


def test_offline_demo_questions_route_to_tools():
    ctx = {}
    expect = [
        ("What should customer 42 watch next?", "get_customer_recommendation"),
        ("Why did you recommend this category?", "get_customer_recommendation"),
        ("Which categories do customers most often move to after this category?", "get_category_transitions"),
        ("Show me customer 42's rental journey", "get_customer_history"),
        ("Which category has the strongest transition to Comedy?", "get_category_transitions"),
        ("What are the most rented categories?", "get_business_metrics"),
    ]
    os.environ.pop("GROQ_API_KEY", None)
    for q, tool in expect:
        res = run_agent(q, context=ctx) if not os.getenv("GROQ_API_KEY") else None
        if res is None:
            pytest.skip("GROQ key set; offline routing test skipped")
        assert res.tool_calls and res.tool_calls[0]["tool"] == tool, (q, res.tool_calls)


def _mysql_up() -> bool:
    try:
        import pymysql
        pymysql.connect(host="127.0.0.1", user="bi_reader", password="readonly_pw", database="sakila").close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _mysql_up(), reason="local MySQL/MariaDB sakila not available")
def test_mysql_backend_gives_identical_results():
    code = ("import sys,json; sys.path.insert(0,'.'); from src import analytics as an;"
            "print(json.dumps([an.headline_metrics()['total_rentals'], an.transition_counts().values.tolist(),"
            " an.repetition_stats()['repeat_pct']]))")
    env = dict(os.environ, DB_BACKEND="mysql", MYSQL_READ_USER="bi_reader", MYSQL_READ_PASSWORD="readonly_pw",
               MYSQL_BUSINESS_DB="sakila")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    mysql_res = json.loads(out.stdout.strip().splitlines()[-1])
    assert mysql_res == [an.headline_metrics()["total_rentals"], an.transition_counts().values.tolist(),
                         an.repetition_stats()["repeat_pct"]]


def test_shopper_questions_are_answered_honestly():
    from src.tools import search_movies
    r = search_movies(category="history", available_only=True)
    assert "no 'history' category" in r["genre_note"] and {m["category"] for m in r["movies"]} <= {"Documentary", "Classics"}
    kids = search_movies(category="kids")
    assert kids["movies"] and all(m["rating"] in ("G", "PG") for m in kids["movies"])
    res = run_agent("hi, I want to buy history DVD", context={})
    assert res.tool_calls and res.tool_calls[0]["tool"] == "search_movies" and "rents" in res.answer


def test_stores_and_readonly_sql():
    from src.tools import run_sql_query
    assert call_tool("get_business_metrics", {"metric_name": "stores"})["value"]["total_stores"] == 2
    assert run_sql_query("SELECT COUNT(*) AS n FROM store")["rows"][0]["n"] == 2
    for bad in ["DELETE FROM store", "select 1; drop table store", "UPDATE film SET title='x'"]:
        assert "error" in run_sql_query(bad)
    with pytest.raises(Exception):  # the engine itself is read-only
        db.query("CREATE TABLE hack (x INT)")
    res = run_agent("how many stores are there", context={})
    assert "2 stores" in res.answer


def test_grounding_checker_flags_invented_numbers():
    from src.agent import unverified_numbers
    calls = [{"tool": "get_business_metrics", "arguments": {"metric_name": "verified_facts"},
              "result": call_tool("get_business_metrics", {"metric_name": "verified_facts"})}]
    good = "93.19% switch, chi-square p = 0.4351, late fees $20,195.00 = 30.19% of revenue, 16,044 rentals in total."
    assert unverified_numbers(good, calls) == []
    bad = "Average payment exceeds rental rate by ~41%; about 4,321 idle copies."
    assert set(unverified_numbers(bad, calls)) == {"41%", "4,321"}


class _FakeGroqFabricating:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        n = len(self.calls)
        if n == 1:
            tc = SimpleNamespace(id="c1", function=SimpleNamespace(name="get_business_metrics",
                                                                  arguments=json.dumps({"metric_name": "overview"})))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[tc]))])
        text = "Sakila has 12,345 rentals." if n == 2 else "Sakila has 15,862 rentals in the analysis window."
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))])


def test_agent_revises_fabricated_numbers():
    fake = _FakeGroqFabricating()
    res = run_agent("how many rentals?", context={}, client=fake)
    assert "15,862" in res.answer and res.unverified == []
    assert "12,345" in fake.calls[2]["messages"][-1]["content"]   # the revision request named the invented number
