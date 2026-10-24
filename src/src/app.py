"""
app.py
Streamlit front end for the AI Multi-Agent System (Business Intelligence Team).

Layout: left navigation sidebar, main workspace, right "power of agents" panel.
Pages: Home, Investigate, Analytics, Products, Settings (all wired up).

Requires: streamlit >= 1.40 (keyed containers + button icons).

Run with:
    streamlit run src/app.py
"""

import html
import sys
import textwrap
from collections import Counter
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.orchestrator import run_team
from src.tools import build_database

st.set_page_config(page_title="AI Multi-Agent System", page_icon="✦", layout="wide",
                   initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# Theme: light, indigo-to-violet accent, soft panels
# ---------------------------------------------------------------------------
FONTS_URL = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800"
             "&family=JetBrains+Mono:wght@400;500&display=swap")

CSS = """
:root { --bg: #F6F8FF; --panel: #FFFFFF; --border: #E6EAF6; --text: #0F1B3D; --muted: #6B7592;
        --primary: #3D5AF1; --primary2: #6D4AF2; --soft: #EEF1FF; --green: #10B981;
        color-scheme: light; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { visibility: hidden; height: 0; }
[data-testid="stHeader"] { background: transparent; }
.stApp { background: radial-gradient(1100px 480px at 75% -10%, #E9EEFF 0%, rgba(246,248,255,0) 60%), var(--bg); }
.stApp, .stApp p, .stApp label, .stApp li, .stApp button, .stApp textarea, .stApp input,
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { font-family: 'Inter', sans-serif; }
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
[data-testid="stMarkdownContainer"] { color: var(--text) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--muted) !important; }
.stApp h2 { font-size: 1.15rem; font-weight: 700; margin-top: 1.1rem; }
.stApp h3 { font-size: 1.02rem; font-weight: 700; }
.block-container { max-width: 1320px; padding-top: 2rem; padding-bottom: 4rem; }

[data-testid="stSidebar"] { background: linear-gradient(180deg, #FFFFFF, #F7F8FE); border-right: 1px solid var(--border);
    min-width: 280px !important; width: 280px !important; }
.bi-brand { display: flex; align-items: center; gap: 0.7rem; padding: 0.6rem 0.4rem 1.4rem 0.4rem; }
.bi-brand-title { font-size: 1.02rem; font-weight: 700; color: var(--text); line-height: 1.15; }
.bi-brand-sub { font-size: 0.74rem; color: var(--muted); margin-top: 2px; }
.bi-promo { margin-top: 3.2rem; border: 1px solid var(--border); border-radius: 16px; padding: 1rem; background: linear-gradient(180deg, #FFFFFF, #F1F3FF); }
.bi-promo-top { display: flex; gap: 0.6rem; align-items: flex-start; color: var(--primary); }
.bi-promo-k { font-size: 0.72rem; color: var(--muted); }
.bi-promo-t { font-size: 0.92rem; font-weight: 600; color: var(--text); }
.bi-promo-d { font-size: 0.78rem; color: var(--muted); margin-top: 0.6rem; line-height: 1.5; }

.bi-topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; gap: 1rem; }
.bi-hero { display: flex; align-items: center; gap: 1rem; }
.bi-logo { width: 56px; height: 56px; border-radius: 16px; display: flex; align-items: center; justify-content: center; color: #fff;
    background: linear-gradient(135deg, var(--primary), var(--primary2)); box-shadow: 0 10px 24px rgba(79,70,229,0.28); flex: 0 0 56px; }
.bi-h1 { font-size: 1.75rem; font-weight: 700; line-height: 1.15; letter-spacing: -0.01em; color: var(--text); }
.bi-sub { font-size: 0.92rem; color: var(--muted); margin-top: 0.2rem; }
.bi-right { display: flex; align-items: center; gap: 0.9rem; }
.bi-pill { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; font-weight: 500; color: var(--text);
    background: var(--panel); border: 1px solid var(--border); border-radius: 999px; padding: 0.55rem 1rem; white-space: nowrap; }
.bi-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--green); display: inline-block; }
.bi-avatar { width: 44px; height: 44px; border-radius: 50%; background: #E9ECF5; display: flex; align-items: center; justify-content: center; }

[class*="st-key-excard"] { position: relative; background: var(--panel); border: 1px solid var(--border); border-radius: 18px;
    padding: 1.1rem 1.2rem; box-shadow: 0 4px 18px rgba(61,90,241,0.05); transition: border-color .15s, box-shadow .15s, transform .15s; }
[class*="st-key-excard"]:hover { border-color: #C3CDFF; box-shadow: 0 10px 28px rgba(61,90,241,0.12); transform: translateY(-2px); }
[class*="st-key-cardbtn"] { position: absolute !important; inset: 0; width: 100% !important; height: 100% !important; z-index: 3; margin: 0 !important; }
[class*="st-key-cardbtn"] [data-testid="stButton"], [class*="st-key-cardbtn"] button { width: 100% !important; height: 100% !important;
    min-height: 100% !important; opacity: 0; cursor: pointer; }
.bi-ac { display: flex; gap: 0.9rem; align-items: flex-start; }
.bi-ic { width: 48px; height: 48px; flex: 0 0 48px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.bi-act-title { display: flex; justify-content: space-between; align-items: center; font-weight: 600; font-size: 0.95rem; color: var(--text); }
.bi-arrow { color: var(--primary); display: inline-flex; }
.bi-act-desc { font-size: 0.8rem; color: var(--muted); margin-top: 0.35rem; line-height: 1.5; }

.st-key-inputcard { background: var(--panel); border: 1px solid var(--border); border-radius: 20px; padding: 1.2rem 1.4rem;
    box-shadow: 0 8px 30px rgba(61,90,241,0.07); }
.bi-input-label { display: flex; align-items: center; gap: 0.5rem; color: var(--primary); font-size: 0.85rem; font-weight: 600; }
.st-key-inputcard [data-baseweb="textarea"], .st-key-inputcard [data-baseweb="base-input"] { border: none !important; background: transparent !important; }
.st-key-inputcard textarea { font-size: 1rem; min-height: 190px; }
.stTextArea textarea, .stTextInput input { background: var(--panel) !important; color: var(--text) !important;
    -webkit-text-fill-color: var(--text) !important; }
.stTextInput input { border: 1px solid var(--border) !important; border-radius: 10px !important; }
.stTextArea textarea::placeholder, .stTextInput input::placeholder { color: var(--muted) !important; -webkit-text-fill-color: var(--muted) !important; opacity: 1; }
.st-key-inputcard textarea:focus { box-shadow: none !important; }

div[data-testid="stButton"] button[kind="primary"] { background: linear-gradient(135deg, var(--primary), var(--primary2)) !important; color: #fff !important;
    border: none !important; font-weight: 600 !important; border-radius: 10px !important; padding: 0.55rem 1.2rem !important;
    box-shadow: 0 8px 18px rgba(61,90,241,0.28) !important; }
div[data-testid="stButton"] button[kind="primary"] p { color: #fff !important; }
div[data-testid="stButton"] button:not([kind="primary"]), [data-testid="stDownloadButton"] button { background: var(--panel) !important;
    border: 1px solid var(--border) !important; border-radius: 999px !important; padding: 0.3rem 1rem !important; }
div[data-testid="stButton"] button:not([kind="primary"]) p, [data-testid="stDownloadButton"] button p { color: var(--text) !important; font-size: 0.82rem; }
div[data-testid="stButton"] button:not([kind="primary"]):hover, [data-testid="stDownloadButton"] button:hover { border-color: var(--primary) !important; }
div[data-testid="stButton"] button:disabled { opacity: 0.5; }

.bi-panel { background: linear-gradient(180deg, #EEF2FF, #FFFFFF 70%); border: 1px solid var(--border); border-radius: 22px; padding: 1.2rem; }
.bi-illus { position: relative; height: 270px; overflow: hidden; }
.bi-glow { position: absolute; left: 50%; top: 110px; width: 230px; height: 130px; margin-left: -115px; border-radius: 50%;
    background: radial-gradient(closest-side, rgba(109,138,255,0.35), rgba(109,138,255,0)); }
.bi-tile { position: absolute; border-radius: 16px; display: flex; align-items: center; justify-content: center; color: #fff;
    box-shadow: 0 14px 28px rgba(61,90,241,0.25); }
.bi-panel-title { font-size: 1.02rem; font-weight: 700; color: var(--text); margin: 0.4rem 0 0.9rem 0; }
.bi-check { display: flex; align-items: center; gap: 0.7rem; font-size: 0.88rem; color: var(--muted); margin-bottom: 0.75rem; }
.bi-check-ic { width: 22px; height: 22px; border-radius: 50%; background: #D5F5E8; color: #059669; display: flex; align-items: center; justify-content: center; flex: 0 0 22px; }
.bi-built { margin-top: 1.1rem; display: flex; align-items: center; gap: 0.8rem; background: var(--panel); border: 1px solid var(--border);
    border-radius: 14px; padding: 0.8rem 1rem; font-size: 0.82rem; color: var(--muted); }
.bi-built-ic { width: 40px; height: 40px; border-radius: 12px; color: #fff; background: linear-gradient(135deg, var(--primary), var(--primary2));
    display: flex; align-items: center; justify-content: center; flex: 0 0 40px; }

.bi-sec { font-size: 1.05rem; font-weight: 700; margin: 1.2rem 0 0.6rem 0; color: var(--text); }
.bi-card { border: 1px solid var(--border); border-radius: 16px; background: var(--panel); padding: 0.9rem 1.1rem; margin: 1.2rem 0 0.4rem 0; }
.bi-question { font-size: 1.05rem; font-weight: 600; margin-top: 0.55rem; color: var(--text); }
.bi-badge { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; font-weight: 500;
    border-radius: 999px; padding: 0.15rem 0.65rem; color: #fff; }
.bi-chip { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; border-radius: 999px;
    padding: 0.1rem 0.55rem; margin-right: 0.3rem; border: 1px solid; background: var(--panel); }
[data-testid="stExpander"] { border: 1px solid var(--border) !important; border-radius: 12px !important; background: var(--panel) !important; }
[data-testid="stExpander"] summary p, [data-testid="stExpander"] li, [data-testid="stExpander"] p { color: var(--text) !important; }
[data-testid="stMetric"] { background: var(--panel); border: 1px solid var(--border); border-radius: 16px; padding: 1rem 1.1rem; }
[data-testid="stMetricLabel"] p { color: var(--muted) !important; }

.bi-kpi { display: flex; align-items: center; gap: 1rem; background: var(--panel); border: 1px solid var(--border); border-radius: 18px;
    padding: 1.1rem 1.2rem; box-shadow: 0 4px 18px rgba(61,90,241,0.05); transition: transform .15s, box-shadow .15s, border-color .15s; }
.bi-kpi:hover { transform: translateY(-2px); border-color: #C3CDFF; box-shadow: 0 10px 28px rgba(61,90,241,0.12); }
.bi-kpi-ic { width: 48px; height: 48px; flex: 0 0 48px; border-radius: 14px; display: flex; align-items: center; justify-content: center; }
.bi-kpi-l { font-size: 0.8rem; color: var(--muted); font-weight: 500; }
.bi-kpi-v { font-size: 1.7rem; font-weight: 700; line-height: 1.15; color: var(--text); letter-spacing: -0.01em; }
.bi-kpi-h { font-size: 0.74rem; color: var(--muted); margin-top: 2px; }
.bi-chart { background: var(--panel); border: 1px solid var(--border); border-radius: 18px; padding: 1.1rem 1.3rem 1.2rem; margin-bottom: 0.6rem;
    min-height: 300px; box-shadow: 0 4px 18px rgba(61,90,241,0.05); transition: box-shadow .15s, border-color .15s; }
.bi-chart:hover { border-color: #D3DAFF; box-shadow: 0 10px 28px rgba(61,90,241,0.10); }
.bi-chart-t { font-size: 1rem; font-weight: 700; color: var(--text); }
.bi-chart-s { font-size: 0.78rem; color: var(--muted); margin: 2px 0 1.1rem 0; }
.bi-row { display: grid; grid-template-columns: 120px 1fr 74px; align-items: center; gap: 0.8rem; margin-bottom: 1rem; }
.bi-row-l { font-size: 0.86rem; font-weight: 500; color: var(--text); text-transform: capitalize; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bi-track { height: 12px; background: #EEF1FB; border-radius: 999px; overflow: hidden; }
.bi-fill { height: 100%; border-radius: 999px; }
.bi-row-v { font-size: 0.86rem; font-weight: 700; color: var(--text); text-align: right; }
.bi-row-v span { font-weight: 500; color: var(--muted); margin-left: 0.4rem; font-size: 0.74rem; }
.bi-empty { font-size: 0.85rem; color: var(--muted); padding: 1rem 0; }

.stApp [data-testid="stSidebar"] [data-testid="stButton"] button { width: 100%; justify-content: flex-start !important; gap: 0.6rem; text-align: left;
    background: transparent !important; border: none !important; box-shadow: none !important; border-radius: 12px !important;
    padding: 0.7rem 0.9rem !important; color: var(--muted) !important; }
.stApp [data-testid="stSidebar"] [data-testid="stButton"] button p { color: inherit !important; font-size: 0.95rem; font-weight: 500; text-align: left; }
.stApp [data-testid="stSidebar"] [data-testid="stButton"] button:hover { background: var(--soft) !important; color: var(--primary) !important; }
.stApp [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] { background: var(--soft) !important; color: var(--primary) !important;
    box-shadow: none !important; }
.stApp [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] p { color: var(--primary) !important; font-weight: 600; }
"""


def inject_css(css: str) -> None:
    """Inject CSS as ONE line, with the fonts pulled in by @import.

    Streamlit renders st.markdown as Markdown, and a Markdown HTML block ends at the first blank line. A
    multi-line stylesheet with blank lines in it is therefore cut in two, and everything after the first blank
    line is printed on the page as plain text. One line has no blank lines to cut at."""
    one_line = " ".join(line.strip() for line in css.splitlines() if line.strip())
    st.markdown(f"<style>@import url('{FONTS_URL}'); {one_line}</style>", unsafe_allow_html=True)


inject_css(CSS)


def render_html(fragment: str) -> None:
    """Collapse to single-line HTML: Streamlit's markdown parser turns an indented multi-line fragment into a code block."""
    st.markdown(" ".join(line.strip() for line in textwrap.dedent(fragment).splitlines()), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Icons (inline SVG, lucide-style) and constants
# ---------------------------------------------------------------------------
ICONS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "bulb": '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/>'
            '<path d="M9 18h6"/><path d="M10 22h4"/>',
    "box": '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
           '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    "sparkle": '<path d="M12 2.5l2.2 6.3 6.3 2.2-6.3 2.2L12 19.5l-2.2-6.3L3.5 11l6.3-2.2z" fill="currentColor"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M8 17v-5"/><path d="M13 17V8"/><path d="M18 17v-9"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
}


def svg(name: str, size: int = 20, color: str = "currentColor", stroke: float = 2) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">{ICONS[name]}</svg>')


MARK_SVG = (
    '<svg width="36" height="36" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<circle cx="16" cy="16" r="12.5" stroke="#D5DBE3" stroke-width="1.4" stroke-dasharray="3 5"/>'
    '<line x1="16" y1="16" x2="8" y2="8" stroke="#2563EB" stroke-width="2"/>'
    '<line x1="16" y1="16" x2="24" y2="8" stroke="#D97706" stroke-width="2"/>'
    '<line x1="16" y1="16" x2="8" y2="24" stroke="#E11D48" stroke-width="2"/>'
    '<line x1="16" y1="16" x2="24" y2="24" stroke="#7C3AED" stroke-width="2"/>'
    '<circle cx="8" cy="8" r="3.4" fill="#2563EB"/><circle cx="24" cy="8" r="3.4" fill="#D97706"/>'
    '<circle cx="8" cy="24" r="3.4" fill="#E11D48"/><circle cx="24" cy="24" r="3.4" fill="#7C3AED"/>'
    '<circle cx="16" cy="16" r="5" fill="#0F1B3D"/><circle cx="16" cy="16" r="1.8" fill="#10B981"/></svg>'
)

STATUS_COLORS = {
    "verified": "#059669", "not_fully_verified": "#D97706", "partial": "#D97706", "findings_only": "#2563EB",
    "insufficient_evidence": "#6B7592", "needs_clarification": "#2563EB", "error": "#DC2626",
    "internal_only": "#D97706",
}
AGENT_COLORS = {"research": "#2563EB", "analyst": "#D97706", "strategy": "#E11D48", "critic": "#7C3AED", "revise": "#E11D48"}

# (title, description, icon, circle background, icon colour, question sent to the team)
EXAMPLES = [
    ("Full investigation", "Get a complete analysis with all agents working together.", "search", "#E4EAFF", "#3D5AF1",
     "Analyze our sales, research the market, and recommend what to do next."),
    ("Why did revenue drop?", "Understand the root cause with evidence and insights.", "bulb", "#D9F6EA", "#059669",
     "Why did our revenue drop this month, and what should we do next?"),
    ("Top products", "Discover the best performing and most promising products.", "box", "#EDE2FF", "#7C3AED",
     "What are our top products in June?"),
]

PRODUCT_QUESTIONS = [
    ("Top products", "See which products sold best in June.", "What are our top products in June?"),
    ("Declining products", "Find products losing sales and the reasons why.", "Which products are declining in sales, and why?"),
    ("Growth opportunities", "Spot products with the most room to grow.", "Which products have the best growth potential, and what should we do next?"),
    ("Revenue risks", "Check which products or categories put revenue at risk.", "Which products or categories put our revenue at risk, and what should we do about it?"),
]

NAV = [
    ("home", "Home", ":material/home:"),
    ("investigate", "Investigate", ":material/search:"),
    ("analytics", "Analytics", ":material/bar_chart:"),
    ("products", "Products", ":material/inventory_2:"),
    ("settings", "Settings", ":material/settings:"),
]


@st.cache_resource
def _prepare_data() -> bool:
    build_database()
    return True


# ---------------------------------------------------------------------------
# Session state, password gate
# ---------------------------------------------------------------------------
for _k, _v in {"history": [], "runs": 0, "draft": "", "page": "home", "pending": None,
               "run_id": 0, "pref_expand": False}.items():
    st.session_state.setdefault(_k, _v)

if config.APP_PASSWORD and not st.session_state.get("authed"):
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        render_html(f'<div class="bi-brand">{MARK_SVG}<div><div class="bi-brand-title">AI Multi-Agent System</div>'
                    f'<div class="bi-brand-sub">Enter the password to continue</div></div></div>')
        entered = st.text_input("Password", type="password")
        if entered:
            if entered == config.APP_PASSWORD:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Wrong password.")
    st.stop()

with st.spinner("Preparing business data…"):
    _prepare_data()

have_key = bool(config.OPENAI_API_KEY)
limit_reached = st.session_state.runs >= config.MAX_RUNS_PER_SESSION


# ---------------------------------------------------------------------------
# Callbacks and helpers
# ---------------------------------------------------------------------------
def go(page: str) -> None:
    st.session_state.page = page


def use_example(text: str) -> None:
    """Fill the question box (does not run, so the person can edit first)."""
    st.session_state.draft = text
    st.session_state["question_w"] = text
    st.toast("Question added. Press Run the team when you are ready.", icon="✅")


def queue_run(question: str) -> None:
    """Send the person to Home and run this question straight away."""
    st.session_state.pending = question
    st.session_state.page = "home"


def clear_history() -> None:
    st.session_state.history = []


def log_out() -> None:
    st.session_state["authed"] = False


def execute(question: str) -> None:
    with st.spinner("The agents are working…"):
        try:
            result = run_team(question, save=config.SAVE_RUNS)
        except Exception as exc:  # keep the UI alive if a run crashes
            result = {"status": "error", "report": f"The run failed: {exc}", "log": {}}
    st.session_state.runs += 1
    st.session_state.run_id += 1
    st.session_state.history.insert(0, {"id": st.session_state.run_id, "question": question, "result": result})


def topbar(title: str, subtitle: str) -> None:
    render_html(
        f"""
        <div class="bi-topbar">
            <div class="bi-hero"><div class="bi-logo">{svg("sparkle", 28)}</div>
                <div><div class="bi-h1">{html.escape(title)}</div><div class="bi-sub">{html.escape(subtitle)}</div></div></div>
            <div class="bi-right">
                <span class="bi-pill"><span class="bi-dot"></span>{st.session_state.runs}/{config.MAX_RUNS_PER_SESSION} runs</span>
                <span class="bi-avatar">{svg("user", 22, "#6B7592")}</span>
            </div>
        </div>
        """
    )


def section(title: str) -> None:
    render_html(f'<div class="bi-sec">{html.escape(title)}</div>')


def action_card(key: str, icon: str, bg: str, fg: str, title: str, desc: str, on_click, args: tuple) -> None:
    """A whole card that is clickable: an invisible button is stretched over the card by the CSS."""
    with st.container(key=f"excard_{key}"):
        render_html(
            f"""
            <div class="bi-ac"><div class="bi-ic" style="background:{bg};color:{fg}">{svg(icon, 22)}</div>
                <div style="flex:1"><div class="bi-act-title"><span>{html.escape(title)}</span>
                <span class="bi-arrow">{svg("arrow", 16)}</span></div>
                <div class="bi-act-desc">{html.escape(desc)}</div></div></div>
            """
        )
        st.button(title, key=f"cardbtn_{key}", on_click=on_click, args=args)


def render_result(item: dict, ctx: str) -> None:
    result = item["result"]
    status = result["status"]
    log = result.get("log", {})
    badge = (f'<span class="bi-badge" style="background:{STATUS_COLORS.get(status, "#6B7592")}">'
             f'{html.escape(status.replace("_", " "))}</span>')
    counts = Counter(log.get("calls", []))
    chips = "".join(f'<span class="bi-chip" style="color:{AGENT_COLORS.get(n, "#6B7592")};'
                    f'border-color:{AGENT_COLORS.get(n, "#6B7592")}">{html.escape(n)} ×{c}</span>'
                    for n, c in counts.items())
    render_html(f'<div class="bi-card">{badge} {chips}<div class="bi-question">{html.escape(item["question"])}</div></div>')

    if status == "error":
        st.error(result["report"])
    else:
        st.markdown(result["report"])

    with st.expander("Run details (plan, agent statuses, calls, tokens)", expanded=st.session_state.pref_expand):
        scope_bits = [f"focus: {log['focus'].replace('_', ' ')}" if log.get("focus") else "",
                      f"month: {log['month']}" if log.get("month") else ""]
        scope_text = " · ".join(b for b in scope_bits if b)
        st.caption(f"Agents chosen by the router: {', '.join(log.get('steps', [])) or 'none'}"
                   + (f" · {scope_text}" if scope_text else ""))
        for tid, info in log.get("tasks", {}).items():
            detail = info.get("error") or info.get("reason") or ""
            st.markdown(f"- **{tid}**: {info['status']} in {info.get('seconds', 0)}s {detail}")
        if log.get("handoffs"):
            st.caption("Handoffs: " + ", ".join(f"{h['from_task']} → {h['to_task']}" for h in log["handoffs"]))
        llm = log.get("llm") or {}
        st.caption(f"{len(log.get('calls', []))} agent calls · {llm.get('calls', 0)} LLM calls · "
                   f"{llm.get('prompt_tokens', 0)} prompt + {llm.get('completion_tokens', 0)} completion tokens · "
                   f"{log.get('seconds', 0)}s total · {log.get('revisions', 0)} revision(s)")
        if log.get("saved_to"):
            st.caption(f"Run saved to {log['saved_to']}")

    st.download_button("Download report (.md)", data=f"# {item['question']}\n\n{result['report']}",
                       file_name=f"report_{item['id']}.md", mime="text/markdown", key=f"dl_{ctx}_{item['id']}")
    st.markdown("---")


def side_panel() -> None:
    checks = "".join(f'<div class="bi-check"><span class="bi-check-ic">{svg("check", 13, "#059669", 3)}</span>{t}</div>'
                     for t in ("Specialized agents", "Shared evidence", "One verified report", "Better decisions"))
    render_html(
        f"""
        <div class="bi-panel">
            <div class="bi-illus">
                <div class="bi-glow"></div>
                <div class="bi-tile" style="left:50%;top:70px;width:100px;height:100px;margin-left:-50px;border-radius:24px;background:linear-gradient(135deg,#3D5AF1,#7FA0FF)">{svg("sparkle", 46)}</div>
                <div class="bi-tile" style="left:8%;top:18px;width:58px;height:58px;background:linear-gradient(135deg,#3D6BF1,#6D9BFF)">{svg("search", 26)}</div>
                <div class="bi-tile" style="right:6%;top:36px;width:56px;height:56px;background:linear-gradient(135deg,#34D399,#A7F3D0)">{svg("chart", 26)}</div>
                <div class="bi-tile" style="left:4%;top:150px;width:56px;height:56px;background:linear-gradient(135deg,#8B5CF6,#C4B5FD)">{svg("box", 26)}</div>
                <div class="bi-tile" style="right:10%;top:178px;width:56px;height:56px;background:linear-gradient(135deg,#3B82F6,#93C5FD)">{svg("bulb", 26)}</div>
            </div>
            <div class="bi-panel-title">The Power of Multiple Agents</div>
            {checks}
            <div class="bi-built"><span class="bi-built-ic">{svg("zap", 20)}</span><span>Built for smarter business intelligence.</span></div>
        </div>
        """
    )


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
with st.sidebar:
    render_html(f'<div class="bi-brand">{MARK_SVG}<div><div class="bi-brand-title">AI Multi-Agent System</div>'
                f'<div class="bi-brand-sub">Smarter agents. Better decisions.</div></div></div>')
    for key, label, icon in NAV:
        st.button(label, key=f"nav_{key}", icon=icon, use_container_width=True, on_click=go, args=(key,),
                  type="primary" if st.session_state.page == key else "secondary")
    render_html(
        f"""
        <div class="bi-promo"><div class="bi-promo-top">{svg("sparkle", 20)}
            <div><div class="bi-promo-k">Powered by</div><div class="bi-promo-t">Multi-Agent Intelligence</div></div></div>
            <div class="bi-promo-d">Collaborative agents for deeper insights and smarter business decisions.</div></div>
        """
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_home() -> None:
    topbar("AI Multi-Agent System", "Business Intelligence Team • Specialist agents, shared evidence, one verified report")
    left, right = st.columns([3.3, 1.25], gap="large")

    with left:
        cols = st.columns(3, gap="medium")
        for i, (col, ex) in enumerate(zip(cols, EXAMPLES)):
            title, desc, icon, bg, fg, question = ex
            with col:
                action_card(f"ex{i}", icon, bg, fg, title, desc, use_example, (question,))

        st.write("")
        if "question_w" not in st.session_state:  # restore the draft after coming back from another page
            st.session_state["question_w"] = st.session_state.draft

        with st.container(key="inputcard"):
            render_html(f'<div class="bi-input-label">{svg("sparkle", 18)}Ask the team</div>')
            st.text_area("Business question", key="question_w", height=200, label_visibility="collapsed",
                         placeholder="Ask a business question, e.g. which problems matter most and what to do next.",
                         on_change=lambda: st.session_state.update(draft=st.session_state.question_w))
            c1, c2 = st.columns([3, 1.3])
            with c1:
                st.caption("Tip: mention a month, metric or product to get a sharper answer.")
            with c2:
                clicked = st.button("Run the team", type="primary", icon=":material/play_arrow:", key="run_btn",
                                    use_container_width=True, disabled=(not have_key or limit_reached))

        if not have_key:
            st.warning("No OPENAI_API_KEY is configured, so the team cannot run. Set it in .env or in the host's secrets.")
        if limit_reached:
            st.info("This session has used all of its runs. Reload the page to start a new session.")

        if clicked:
            question = st.session_state.question_w.strip()
            if question:
                execute(question)
                st.rerun()
            else:
                st.warning("Type a question first, or pick one of the cards above.")

        pending = st.session_state.pending
        st.session_state.pending = None
        if pending:
            if have_key and not limit_reached:
                execute(pending)
                st.rerun()
            else:
                st.warning("Cannot run this question: the API key is missing or the session run limit is reached.")

        for item in st.session_state.history:
            render_result(item, "home")

    with right:
        side_panel()


def page_investigate() -> None:
    topbar("Investigate", "Every run with its evidence, details and a downloadable report")
    history = st.session_state.history
    if not history:
        st.info("No investigations yet. Run the team from Home and every report will be listed here.")
        st.button("Go to Home", on_click=go, args=("home",), key="inv_home")
        return
    term = st.text_input("Filter", placeholder="Filter past runs by question…", label_visibility="collapsed", key="inv_filter")
    items = [h for h in history if term.lower() in h["question"].lower()]
    if not items:
        st.info("No runs match that filter.")
    for item in items:
        render_result(item, "inv")
        st.button("Run this question again", key=f"again_{item['id']}", on_click=queue_run, args=(item["question"],),
                  disabled=(not have_key or limit_reached))


STATUS_DISPLAY = {k.replace("_", " "): v for k, v in STATUS_COLORS.items()}


def kpi(icon: str, bg: str, fg: str, label: str, value: str, hint: str) -> None:
    render_html(
        f"""
        <div class="bi-kpi"><div class="bi-kpi-ic" style="background:{bg};color:{fg}">{svg(icon, 22)}</div>
            <div><div class="bi-kpi-l">{html.escape(label)}</div><div class="bi-kpi-v">{html.escape(value)}</div>
            <div class="bi-kpi-h">{html.escape(hint)}</div></div></div>
        """
    )


def chart_card(title: str, subtitle: str, body: str) -> None:
    render_html(f'<div class="bi-chart"><div class="bi-chart-t">{html.escape(title)}</div>'
                f'<div class="bi-chart-s">{html.escape(subtitle)}</div>{body}</div>')


def bar_rows(data: dict, colors: dict) -> str:
    """Horizontal bars drawn with plain HTML/CSS, so they always match the app's light theme."""
    if not data:
        return '<div class="bi-empty">No data yet.</div>'
    top = max(data.values()) or 1
    total = sum(data.values()) or 1
    rows = ""
    for name, val in sorted(data.items(), key=lambda kv: -kv[1]):
        color = colors.get(name, "#6B7592")
        rows += (f'<div class="bi-row"><div class="bi-row-l">{html.escape(str(name))}</div>'
                 f'<div class="bi-track"><div class="bi-fill" style="width:{max(4, 100 * val / top):.0f}%;background:{color}"></div></div>'
                 f'<div class="bi-row-v">{val}<span>{100 * val / total:.0f}%</span></div></div>')
    return rows


def svg_series(values: list, color: str, labels: list, kind: str = "area") -> str:
    """Area or bar chart as inline SVG: light grid, value labels, rounded bars."""
    if not values:
        return '<div class="bi-empty">No data yet.</div>'
    W, H, L, R, T, B = 640, 240, 54, 16, 22, 36
    ymax = (max(values) or 1) * 1.2
    base = H - B
    plot_h = base - T
    n = len(values)
    slot = (W - L - R) / n
    xs = [L + slot * (i + 0.5) for i in range(n)]

    def fmt(v: float) -> str:
        return f"{v:,.0f}" if ymax >= 20 else f"{v:.1f}"

    def y_of(v: float) -> float:
        return base - plot_h * v / ymax

    parts = []
    for k in range(5):
        v = ymax * k / 4
        y = y_of(v)
        parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="#E6EAF6" stroke-width="1"/>')
        parts.append(f'<text x="{L - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#6B7592">{fmt(v)}</text>')

    if kind == "bars":
        bw = min(56, slot * 0.55)
        for x, v in zip(xs, values):
            y = y_of(v)
            parts.append(f'<rect x="{x - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(base - y, 1):.1f}" rx="6" fill="{color}"/>')
            if n <= 12:
                parts.append(f'<text x="{x:.1f}" y="{y - 7:.1f}" text-anchor="middle" font-size="11" font-weight="600" fill="#0F1B3D">{fmt(v)}</text>')
    else:
        pts = " ".join(f"{x:.1f},{y_of(v):.1f}" for x, v in zip(xs, values))
        if n > 1:
            parts.append(f'<polygon points="{xs[0]:.1f},{base} {pts} {xs[-1]:.1f},{base}" fill="{color}" fill-opacity="0.12"/>')
            parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>')
        for x, v in zip(xs, values):
            y = y_of(v)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#FFFFFF" stroke="{color}" stroke-width="2.5"/>')
            if n <= 12:
                parts.append(f'<text x="{x:.1f}" y="{y - 11:.1f}" text-anchor="middle" font-size="11" font-weight="600" fill="#0F1B3D">{fmt(v)}</text>')

    for i, (x, lab) in enumerate(zip(xs, labels)):
        if n <= 12 or i % 2 == 0:
            parts.append(f'<text x="{x:.1f}" y="{H - 12}" text-anchor="middle" font-size="11" fill="#6B7592">{html.escape(lab)}</text>')

    return (f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Inter, sans-serif" '
            f'style="display:block;max-width:100%;height:auto">{"".join(parts)}</svg>')


def page_analytics() -> None:
    topbar("Analytics", "How the team performed in this session")
    history = st.session_state.history
    if not history:
        st.info("No data yet. Run the team from Home and the charts will fill in here.")
        st.button("Go to Home", on_click=go, args=("home",), key="an_home")
        return

    chron = list(reversed(history))  # oldest first, for time-based charts
    logs = [h["result"].get("log", {}) for h in chron]
    labels = [f"#{h['id']}" for h in chron]
    n = len(chron)
    verified = sum(1 for h in chron if h["result"]["status"] == "verified")
    seconds = [float(lg.get("seconds", 0) or 0) for lg in logs]
    token_list = [int((lg.get("llm") or {}).get("prompt_tokens", 0) + (lg.get("llm") or {}).get("completion_tokens", 0)) for lg in logs]
    tokens = sum(token_list)

    k = st.columns(4, gap="medium")
    with k[0]:
        kpi("chart", "#E4EAFF", "#3D5AF1", "Runs", str(n), "This session")
    with k[1]:
        kpi("check", "#D9F6EA", "#059669", "Verified reports", f"{round(100 * verified / n)}%", f"{verified} of {n} reports")
    with k[2]:
        kpi("zap", "#FFF1D6", "#D97706", "Average time", f"{sum(seconds) / n:.1f}s", f"Fastest {min(seconds):.1f}s, slowest {max(seconds):.1f}s")
    with k[3]:
        kpi("sparkle", "#EDE2FF", "#7C3AED", "Tokens used", f"{tokens:,}", f"{tokens // n:,} per run")

    st.write("")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        status_counts = Counter(h["result"]["status"].replace("_", " ") for h in chron)
        chart_card("Reports by status", "How each run ended", bar_rows(dict(status_counts), STATUS_DISPLAY))
    with c2:
        agent_calls = Counter(name for lg in logs for name in lg.get("calls", []))
        chart_card("Agent calls", "Which specialists did the work", bar_rows(dict(agent_calls), AGENT_COLORS))

    c3, c4 = st.columns(2, gap="medium")
    with c3:
        chart_card("Time per run", "Seconds, oldest to newest", svg_series(seconds, "#3D5AF1", labels, "area"))
    with c4:
        chart_card("Tokens per run", "Prompt plus completion tokens", svg_series(token_list, "#7C3AED", labels, "bars"))


def page_products() -> None:
    topbar("Products", "One click sends a product question to the whole team")
    cols = st.columns(2, gap="medium")
    colors = [("#EDE2FF", "#7C3AED"), ("#FFE4EA", "#E11D48"), ("#D9F6EA", "#059669"), ("#FFF1D6", "#D97706")]
    for i, (title, desc, question) in enumerate(PRODUCT_QUESTIONS):
        bg, fg = colors[i % len(colors)]
        with cols[i % 2]:
            action_card(f"pr{i}", "box", bg, fg, title, desc, queue_run, (question,))
            st.write("")
    if not have_key or limit_reached:
        st.warning("The team cannot run right now: the API key is missing or this session's run limit is reached.")


def page_settings() -> None:
    topbar("Settings", "Configuration status and session preferences")
    section("Configuration")
    if have_key:
        st.success("OpenAI API key is configured.")
    else:
        st.error("OpenAI API key is missing. Set OPENAI_API_KEY in .env or in the host's secrets.")
    st.markdown(f"- **Runs per session:** {config.MAX_RUNS_PER_SESSION} ({st.session_state.runs} used)\n"
                f"- **Save runs to disk:** {'yes' if config.SAVE_RUNS else 'no'}\n"
                f"- **Password protection:** {'on' if config.APP_PASSWORD else 'off'}")

    section("Preferences")
    if "_w_expand" not in st.session_state:
        st.session_state["_w_expand"] = st.session_state.pref_expand
    st.toggle("Open run details automatically", key="_w_expand",
              on_change=lambda: st.session_state.update(pref_expand=st.session_state["_w_expand"]))

    section("Session")
    c1, c2, _ = st.columns([1, 1, 2])
    c1.button("Clear history", on_click=clear_history, key="clear_hist", disabled=not st.session_state.history)
    if config.APP_PASSWORD:
        c2.button("Log out", on_click=log_out, key="logout")
    st.caption("Clearing history removes the reports from this page. The run counter is not reset.")


PAGES = {"home": page_home, "investigate": page_investigate, "analytics": page_analytics,
         "products": page_products, "settings": page_settings}
PAGES[st.session_state.page]()