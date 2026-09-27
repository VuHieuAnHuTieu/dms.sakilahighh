"""Shared Streamlit UI helpers: styling, KPI cards, insight boxes, chart theme."""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from . import database as db

# Validated reference palette (dataviz skill): categorical slots 1-2, sequential blue, diverging blue<->red.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GRAY = "#8a8985"
TEXT, TEXT2, MUTED = "#0b0b0b", "#52514e", "#8a8985"
SEQ_BLUE = [[0, "#f3f7fd"], [0.25, "#cde2fb"], [0.5, "#86b6ef"], [0.75, "#2a78d6"], [1, "#104281"]]
DIVERGING = [[0, "#1c5cab"], [0.25, "#86b6ef"], [0.5, "#f0efec"], [0.75, "#f09a92"], [1, "#b8322f"]]

CSS = """
<style>
.block-container {padding-top: 3.5rem; max-width: 1250px;}
.kpi {background:#fff;border:1px solid #e6e5e1;border-radius:12px;padding:14px 16px;height:100%;}
.kpi .l {font-size:.78rem;color:#52514e;text-transform:uppercase;letter-spacing:.04em;}
.kpi .v {font-size:1.6rem;font-weight:700;color:#0b0b0b;line-height:1.25;margin-top:2px;}
.kpi .s {font-size:.8rem;color:#8a8985;}
.box {border-radius:10px;padding:12px 16px;margin:6px 0 14px 0;font-size:.95rem;line-height:1.5;}
.box.finding {background:#eef5fd;border-left:4px solid #2a78d6;}
.box.caveat {background:#fdf3ee;border-left:4px solid #eb6834;}
.box.neutral {background:#f3f3f1;border-left:4px solid #8a8985;}
.step {display:inline-block;background:#2a78d6;color:#fff;border-radius:999px;padding:2px 10px;font-size:.75rem;font-weight:600;margin-bottom:4px;}
.chip {display:inline-block;padding:3px 10px;border-radius:999px;margin:2px;font-size:.85rem;border:1px solid #d9d8d3;background:#fff;}
.chip.last {background:#2a78d6;color:#fff;border-color:#2a78d6;}
.arrow {color:#8a8985;margin:0 2px;}
</style>
"""


def setup(title: str, subtitle: str = "", step: str | None = None) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)
    badge = f'<span class="step">{step}</span> ' if step else ""
    if subtitle or step:
        st.markdown(f'{badge}<span style="color:#52514e;font-size:.9rem">{subtitle}</span>', unsafe_allow_html=True)


def kpi(col, label: str, value: str, sub: str = "") -> None:
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>',
                 unsafe_allow_html=True)


def box(text: str, kind: str = "finding") -> None:
    icon = {"finding": "📊 <b>Finding.</b> ", "caveat": "⚠️ <b>Caution.</b> ", "neutral": ""}[kind]
    st.markdown(f'<div class="box {kind}">{icon}{text}</div>', unsafe_allow_html=True)


def sql_expander(file: str, name: str | None = None, label: str = "Show SQL used") -> None:
    with st.expander(label):
        st.code(db.load_sql(file, name), language="sql")


def style(fig: go.Figure, height: int = 380, legend: bool = False) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=10, r=10, t=50, b=10),
        font=dict(family="Inter, system-ui, sans-serif", size=13, color=TEXT2),
        title_font=dict(size=15, color=TEXT), showlegend=legend,
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0, traceorder="normal"),
        hoverlabel=dict(bgcolor="white", font_size=12),
        plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
    )
    fig.update_xaxes(gridcolor="#ecebe7", zeroline=False, linecolor="#d9d8d3")
    fig.update_yaxes(gridcolor="#ecebe7", zeroline=False, linecolor="#d9d8d3")
    fig.update_traces(selector=dict(type="bar"), marker_cornerradius=4)
    return fig


def journey_chips(categories: list[str], max_items: int = 10) -> str:
    items = categories[-max_items:]
    prefix = '<span class="chip">…</span><span class="arrow">→</span>' if len(categories) > max_items else ""
    html = '<span class="arrow">→</span>'.join(
        f'<span class="chip{" last" if i == len(items) - 1 else ""}">{c}</span>' for i, c in enumerate(items))
    return prefix + html
