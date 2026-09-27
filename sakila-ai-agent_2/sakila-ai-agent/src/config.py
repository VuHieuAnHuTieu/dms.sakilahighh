"""Central configuration. Every value can be overridden in `.env` (see `.env.example`)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _secret(name: str, default: str = "") -> str:
    """Read a setting from the environment / .env first, then from Streamlit secrets
    (Streamlit Community Cloud stores the Groq key there, hidden on the server)."""
    v = os.getenv(name)
    if v:
        return v
    try:
        import streamlit as st
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # ---- Database -------------------------------------------------------
    db_backend: str = os.getenv("DB_BACKEND", "sqlite").strip().lower()  # "sqlite" | "mysql"
    sqlite_path: str = os.getenv("SQLITE_PATH") or str(ROOT / "data" / "sakila.db")
    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_db: str = os.getenv("MYSQL_BUSINESS_DB", "sakila")
    mysql_user: str = os.getenv("MYSQL_READ_USER", "bi_reader")
    mysql_password: str = os.getenv("MYSQL_READ_PASSWORD", "")

    # ---- Analysis window (CONFIGURABLE) --------------------------------
    # The team's SQL excludes the anomalous 2006-02-14 batch (182 rentals, 1 day,
    # almost all never returned) with `rental_date < '2006-01-01'`. Set to "" to use all rentals.
    analysis_end_date: str = os.getenv("ANALYSIS_END_DATE", "2006-01-01")

    # ---- Recommendation weights (CONFIGURABLE, must be >= 0) -----------
    w_transition: float = _f("REC_WEIGHT_TRANSITION", 0.7)  # P(next = B | last category)
    w_affinity: float = _f("REC_WEIGHT_AFFINITY", 0.3)      # customer's own smoothed share of B
    min_transition_support: int = int(os.getenv("MIN_TRANSITION_SUPPORT", "30"))

    # ---- LLM (Groq) -----------------------------------------------------
    groq_api_key: str = _secret("GROQ_API_KEY")
    groq_model: str = _secret("GROQ_MODEL")
    agent_max_tool_rounds: int = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "6"))

    random_seed: int = int(os.getenv("RANDOM_SEED", "42"))


def get_settings() -> Settings:
    return Settings()
