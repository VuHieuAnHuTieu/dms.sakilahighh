"""Database access layer. Works with the bundled SQLite copy or a live MySQL Sakila.

All SQL lives in `sql/*.sql`. Files may contain several named queries separated by
`-- name: <query_name>` headers. Queries use only portable SQL (standard joins and
window functions supported by MySQL 8 / MariaDB 10.2+ / SQLite 3.25+).
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import ROOT, get_settings

SQL_DIR = ROOT / "sql"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    s = get_settings()
    if s.db_backend == "mysql":
        url = f"mysql+pymysql://{s.mysql_user}:{s.mysql_password}@{s.mysql_host}:{s.mysql_port}/{s.mysql_db}"
        return create_engine(url, pool_pre_ping=True)
    path = Path(s.sqlite_path)
    if not path.exists():
        raise FileNotFoundError(
            f"SQLite database not found at {path}. Either keep data/sakila.db in the project, "
            "or set DB_BACKEND=mysql in .env."
        )
    # read-only connection: the app (and the agent's SQL tool) can never modify the data
    return create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true")


def backend_label() -> str:
    s = get_settings()
    return f"MySQL · {s.mysql_db}@{s.mysql_host}" if s.db_backend == "mysql" else "SQLite · data/sakila.db"


@lru_cache(maxsize=None)
def load_sql(file: str, name: str | None = None) -> str:
    """Return a query from sql/<file>. If `name` is given, return that named block."""
    raw = (SQL_DIR / file).read_text(encoding="utf-8")
    if name is None:
        return raw
    parts = re.split(r"^--\s*name:\s*(\w+)\s*$", raw, flags=re.M)
    blocks = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}
    if name not in blocks:
        raise KeyError(f"Query '{name}' not found in {file}. Available: {sorted(blocks)}")
    return blocks[name]


def _strip_comments(sql: str) -> str:
    """Remove `-- ...` line comments so documentation like ':end_date' is not parsed as a bind."""
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines()).strip()


def query(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(_strip_comments(sql)), conn, params=params or {})


def run(file: str, name: str | None = None, **params: Any) -> pd.DataFrame:
    return query(load_sql(file, name), params)


def window_params() -> dict[str, str]:
    """Bind parameter for the analysis window. '9999-12-31' = no upper cut."""
    end = get_settings().analysis_end_date.strip()
    return {"end_date": end or "9999-12-31"}
