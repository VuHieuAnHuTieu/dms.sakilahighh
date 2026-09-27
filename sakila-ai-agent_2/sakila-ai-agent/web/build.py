"""Build the single-file web version: web/dist/index.html (engine + data + app inlined)."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from src.database import load_sql  # noqa: E402

def safe(s: str) -> str:
    return s.replace("</", "<\\/")

sql = {"transition_counts": load_sql("category_transitions.sql", "transition_counts"),
       "repeat_vs_switch": load_sql("category_transitions.sql", "repeat_vs_switch")}
html = (HERE / "template.html").read_text(encoding="utf-8")
html = html.replace("/*__ENGINE__*/", safe((HERE / "engine.js").read_text(encoding="utf-8")))
html = html.replace("/*__DATA__*/", safe((HERE / "data.json").read_text(encoding="utf-8")) + ";window.SAKILA_SQL=" + safe(json.dumps(sql)))
html = html.replace("/*__APP__*/", safe((HERE / "app.js").read_text(encoding="utf-8")))
out = HERE / "dist" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(html, encoding="utf-8")
print(out, round(out.stat().st_size / 1024), "KB")
