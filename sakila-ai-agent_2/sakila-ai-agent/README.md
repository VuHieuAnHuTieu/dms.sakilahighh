# Beyond Category Loyalty — Sakila Next-Category Intelligence

An end-to-end business-intelligence system on the **Sakila DVD rental database**:
SQL analytics → category-transition analysis → transparent recommendation engine →
Streamlit dashboard → tool-calling AI agent (Groq).

> **Central question:** *After a customer rents a movie from category A, which category do they explore next?*
>
> **What the data says:** customers always return and explore widely (93% of next rentals switch category),
> but the previous category barely predicts the next one (χ² p ≈ 0.44, Cramér's V ≈ 0.03).
> See [`docs/FINDINGS.md`](docs/FINDINGS.md). It is generated from the database, so every number in it is real.

---

## 1. Quick start

```bash
cd sakila-ai-agent
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # Windows: copy .env.example .env
# edit .env -> set GROQ_API_KEY (and GROQ_MODEL if you want a different model)
streamlit run app.py
```

Open http://localhost:8501. The app works straight away with the bundled `data/sakila.db`.
Without a Groq key, the AI agent runs in **offline mode**: a rule-based router calls the same tools
and fills in answer templates, so it never makes up numbers.

Run the tests:

```bash
python -m pytest -q tests
```

Regenerate the findings report (after changing the database or the window):

```bash
python scripts/generate_findings.py
```

## 2. Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `GROQ_API_KEY` | for LLM mode | Groq API key (never commit it) |
| `GROQ_MODEL` | for LLM mode | Any Groq model that supports tool calling (the example value can be changed) |
| `DB_BACKEND` | no | `sqlite` (default, bundled file) or `mysql` |
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_BUSINESS_DB`, `MYSQL_READ_USER`, `MYSQL_READ_PASSWORD` | if mysql | Same names as the team's existing project; a read-only user is enough |
| `ANALYSIS_END_DATE` | no | Only rentals before this date are analysed (default `2006-01-01`). This drops the anomalous 2006-02-14 batch, the same rule as the team's SQL. Leave it empty to use all data |
| `REC_WEIGHT_TRANSITION`, `REC_WEIGHT_AFFINITY` | no | Weights in the recommendation score (default 0.7 / 0.3) |
| `AGENT_MAX_TOOL_ROUNDS`, `RANDOM_SEED` | no | Agent loop limit and seed for the permutation tests |

### Using your MySQL Sakila instead of SQLite

```env
DB_BACKEND=mysql
MYSQL_BUSINESS_DB=sakila
MYSQL_READ_USER=bi_reader
MYSQL_READ_PASSWORD=...
```

All SQL is portable (MySQL 8 / MariaDB 10.2+ / SQLite 3.25+). The test suite checks that MySQL and
SQLite give identical results.
To rebuild the SQLite file from MySQL, run `python scripts/build_sqlite_from_mysql.py --user ... --password ...`.

> ⚠️ The team's `sakila_extended` database contains extra, AI-generated records. If you point the app at it,
> every number is recalculated, and you must say in the report that the data is partly synthetic.

## 3. Project structure

```
sakila-ai-agent/
├── app.py                      Streamlit entry point + navigation
├── pages/                      the 5 dashboard pages
│   ├── overview.py             1 · Executive Overview
│   ├── customer_exploration.py 2 · Customer return, repeat vs switch, diversity, journeys
│   ├── category_transition.py  3 · Heatmap, top transitions, significance, gateway test
│   ├── recommendation.py       4 · Customer → next category → movies (+ hold-out test)
│   └── ai_agent.py             5 · Chat with the tool-calling agent
├── src/
│   ├── config.py               .env settings
│   ├── database.py             SQLite/MySQL engine + named-SQL loader
│   ├── analytics.py            all metrics, transitions, statistical tests, backtest
│   ├── recommendation.py       transparent scoring engine
│   ├── tools.py                5 agent tools + JSON schemas
│   ├── agent.py                Groq tool-calling loop + offline fallback
│   └── ui.py                   styling, KPI cards, chart theme
├── sql/                        rental_events, category_transitions, customer_history, film_catalog, business_metrics
├── data/sakila.db              SQLite copy of the official Sakila dump (16,044 rentals)
├── scripts/                    build_sqlite_from_mysql.py, generate_findings.py
├── docs/FINDINGS.md            auto-generated findings with values + queries
└── tests/test_system.py        14 end-to-end tests
```

## 4. Method

**Sequences.** For each customer, rentals are sorted by `rental_date`, with `rental_id` breaking ties
(`LAG(...) OVER (PARTITION BY customer_id ORDER BY rental_date, rental_id)`, as in team SQL #2).
Each rental maps to one category through inventory → film → film_category → category. Every Sakila film has exactly one category.

**Transitions.** `P(B|A) = count(A→B) / count(A→any)`. The app also reports:

- lift = P(B|A) ÷ B's overall share
- the adjusted standardized residual *z*
- a χ² independence test with Cramér's V
- a Bonferroni check across all 256 cells

**Chance benchmarks.** Observed repetition is compared with two baselines. The first is random choice (Σp²). The second shuffles each customer's own history, 300 times.

**Gateway test.** A category counts as a gateway only if its outgoing pattern stands out statistically: significant cells, or an unusual spread of destinations (normalized entropy). High volume alone does not count. The data does not support a gateway, so the app uses the neutral term **"high-transition category"**.

**Recommendation.**
```
score(B) = w_t · P(next = B | customer's most recent category)
         + w_a · (customer's rentals in B + 1) / (customer's rentals + 16)
```
Movies come from the top category and must meet three rules:

1. The customer has never rented the film.
2. At least one copy is in stock. A copy counts as out while it has an unreturned rental.
3. Films are ranked by rentals in the window, then by copies available.

Exploration mode leaves out the customer's current category.

**Evaluation.** In a hold-out test, each customer's last rental is hidden and predicted. The test reports hit@1 and hit@3 against random guessing and a popularity baseline.

## 5. AI agent tools

| Tool | Purpose |
|---|---|
| `get_customer_history(customer_id)` | profile, rental count, chronological journey with categories, repeat/switch flags |
| `get_category_transitions(category_name, direction)` | where customers go after a category (outgoing) or which categories lead into it (incoming), with counts, probabilities, lift, z |
| `get_customer_recommendation(customer_id, n_movies, exploration_mode)` | next category, score parts, signal strength, movies, explanation inputs |
| `search_movies(category, title, rating, available_only)` | catalogue search with popularity and stock |
| `get_business_metrics(metric_name)` | KPIs, category performance, trends, repeat vs switch, diversity, transition statistics, high-transition table, backtest |

The system prompt requires the agent to:

- take every number from a tool result
- use neutral wording, and never call customers "disloyal"
- make no causal claims
- report how strong the signal is

## 6. Demo script (≈5 min)

1. **Executive Overview**: KPIs, and category demand that is almost evenly spread.
2. **Customer Exploration**: 100% of customers return, 93% of next rentals switch, and the repeat rate is close to chance.
3. **Category Transition**: the heatmap is flat, the χ² test is not significant, and no gateway is supported.
4. **Recommendation**: pick customer 42. Show the journey, the recommended category, the score breakdown and the movies. Then turn on exploration mode.
5. **AI Agent**: "Why did you recommend this category?", then "Which categories do customers most often move to after this category?"

## 7. Limitations

- Sakila is a sample database. The window has 4 months and rentals fall on only 40 distinct dates. Several rentals often share a timestamp, so the order within one visit comes from `rental_id`. The conclusions still hold when you count only transitions between different days.
- The data is observational: transitions describe what happened, not what caused it.
- "Available" means in stock at the dataset snapshot, not in real time.
- The transition matrix is built from all customers, including the customer being scored. The effect on one customer is negligible, and the hold-out test removes it.
- Category-level prediction is about as good as chance on this data. Accuracy figures come only from the hold-out test and are not claimed anywhere else.

## 8. Web version (hosted link)

`web/` contains a single-file web version of the dashboard, hosted as a claude.ai artifact:

- `scripts/export_web_data.py` exports all computed statistics to `web/data.json`.
- `web/engine.js` re-implements the recommendation engine in JavaScript. Its results match the Python engine for all 599 customers.
- `python web/build.py` builds `web/dist/index.html`.

In the web version, the AI agent uses Claude (on the viewer's own account) with the same 5 tools, and falls back to the offline router when Claude isn't available. Groq is not used there because an API key can't be hidden inside a public page.

## 9. Public deploy with no login (Streamlit Community Cloud)

The Groq key stays on the server as a secret. Visitors never see it and don't need to sign in to anything.

1. Push this folder to a GitHub repository. `.env` is ignored, so the key is never uploaded.
2. Go to https://share.streamlit.io, sign in with GitHub, and click **Create app**. Pick the repository, branch `main` and main file `app.py`.
3. Under **Advanced settings → Secrets**, paste the lines from `.streamlit/secrets.toml.example` with your real Groq key.
4. Click **Deploy**. You get a public `https://<name>.streamlit.app` link.

Each browser session can ask at most `AGENT_MAX_QUESTIONS_PER_SESSION` questions (default 40). This protects your Groq quota.

## 10. The six team insights and the question bank

- `src/insights.py` recomputes the team report's **six insights** from the database. Nothing is copied from the report. Each insight includes:
  - verified findings
  - a check of the written report
  - metrics to watch
  - caveats
  - recommendations, labelled as hypotheses
  - runnable follow-up SQL
- It also computes the chronology (41 recorded dates, a 174-day gap), trends, behavioural customer segments and a list of **data limitations**.
- `knowledge/testbank.py` holds the team's question bank (117 questions). For each question it records the tools to call, how to answer, the keywords a good answer contains, and the claims it must avoid. For every question, the agent pulls the closest guidance into its prompt.
- Agent tools added: `get_insights`, `get_data_limitations`, `get_trends`, `visualize` (charts drawn in the chat). There are also metrics `chronology`, `customer_segments`, `category_share_by_burst` and `misc_facts`.
- Report requests follow a consulting (MBB) structure: action title, executive summary in SCR form, findings, testable recommendations, limitations, and next steps.
- `python scripts/run_testbank.py` grades the live agent (Groq) on the question bank and writes `docs/testbank_results.md`.
- `python scripts/generate_insights_doc.py` writes `docs/INSIGHTS_VERIFIED.md`.
