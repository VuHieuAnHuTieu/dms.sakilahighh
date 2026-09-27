"""Grade the LIVE agent (Groq) on the team's question bank.

    python scripts/run_testbank.py              # all questions (uses your Groq quota)
    python scripts/run_testbank.py --limit 10   # first 10

Writes docs/testbank_results.md. Grading is a heuristic screen, not a replacement for reading the answers:
  tools   - did the agent call at least one expected tool?
  must    - share of expected keywords present (case-insensitive)
  avoid   - none of the forbidden claims present
  grounded- no numbers outside tool results (grounding check)
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.testbank import TESTBANK  # noqa: E402
from src.agent import llm_available, run_agent  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=len(TESTBANK))
ap.add_argument("--sleep", type=float, default=2.0, help="seconds between questions (rate limits)")
a = ap.parse_args()
if not llm_available():
    sys.exit("Set GROQ_API_KEY and GROQ_MODEL in .env first.")

rows, passed = [], 0
for i, e in enumerate(TESTBANK[: a.limit], 1):
    res = run_agent(e["q"], context={})
    ans = res.answer.lower()
    used = {c["tool"] for c in res.tool_calls}
    tools_ok = (not e["tools"]) or bool(used & set(e["tools"]))
    must = [m for m in e["must"] if m.lower() in ans]
    must_ok = (not e["must"]) or len(must) >= max(1, len(e["must"]) // 2)
    bad = [x for x in e["avoid"] if x.lower() in ans]
    ok = tools_ok and must_ok and not bad and not res.unverified and res.mode == "llm"
    passed += ok
    rows.append((i, e["q"], ok, sorted(used), tools_ok, must, bad, res.unverified, res.mode, res.answer))
    print(f"{i:3d} {'PASS' if ok else 'FAIL'}  {e['q'][:70]}")
    time.sleep(a.sleep)

out = ROOT / "docs" / "testbank_results.md"
lines = [f"# Question-bank results: {passed}/{len(rows)} passed\n"]
for i, q, ok, used, t_ok, must, bad, unv, mode, ans in rows:
    lines += [f"## {i}. {'✅' if ok else '❌'} {q}", f"- mode: {mode}; tools: {', '.join(used) or '-'} (expected tool used: {t_ok})",
              f"- keywords found: {must}; forbidden claims: {bad}; unverified numbers: {unv}", "", ans, ""]
out.write_text("\n".join(lines), encoding="utf-8")
print(f"\n{passed}/{len(rows)} passed -> {out}")
