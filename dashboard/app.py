"""
OCP Bionic Judge — Dashboard (DEPRECATED)
Author: Mounir Sanbouli

╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠  DÉPRÉCIÉ — Ce dashboard Streamlit était le prototype de validation.     ║
║     Le frontend officiel est désormais l'application React (frontend/).      ║
║                                                                              ║
║     Pour lancer le frontend React :                                          ║
║       cd frontend && npm install && npm run dev    →  http://localhost:5173  ║
║                                                                              ║
║     Ce fichier sera supprimé dans une version future.                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations  # MUST be the first statement after the docstring

import warnings
warnings.warn(
    "\n\n⚠  dashboard/app.py est DÉPRÉCIÉ.\n"
    "   Utilisez le frontend React : cd frontend && npm run dev\n",
    DeprecationWarning,
    stacklevel=1,
)
import base64, sqlite3, logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

try:
    from streamlit_autorefresh import st_autorefresh
    _HAS_AUTOREFRESH = True
except ImportError:
    _HAS_AUTOREFRESH = False

load_dotenv()

BASE_DIR  = Path(__file__).parent.parent
DB_PATH   = BASE_DIR / "data" / "ocp_bionic.db"
LOGO_PATH = Path(__file__).parent / "assets" / "ocp_logo.png"

st.set_page_config(
    page_title="OCP Bionic Judge",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

def _b64(p) -> str:
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""

LOGO_B64 = _b64(LOGO_PATH)

# ─── Design tokens ────────────────────────────────────────────────────────────
# Inspired by Grafana / Linear dark theme
C_BG      = "#111318"   # main background
C_SURF    = "#1A1D27"   # sidebar, elevated surfaces
C_CARD    = "#1E2130"   # cards
C_CARD_HV = "#242840"   # card hover
C_BORDER  = "#2A2E3F"   # borders
C_BORDER2 = "#353A52"   # stronger border
C_GREEN   = "#00D37F"   # primary accent
C_GREEN_D = "#00A362"   # darker green
C_GREEN_L = "#4DFFA9"   # light green
C_AMBER   = "#FFB020"   # warning
C_RED     = "#F04438"   # critical
C_BLUE    = "#4F7CF6"   # info
C_TEAL    = "#06B6D4"   # secondary
C_TEXT    = "#E8ECF1"   # primary text
C_TEXT2   = "#8B92A9"   # secondary text
C_TEXT3   = "#525870"   # muted text

SEV = {"NORMAL": C_GREEN, "WARNING": C_AMBER, "CRITICAL": C_RED}
MACHINES = ["BROYEUR_01","POMPE_02","CONVOYEUR_03","REACTEUR_04","COMPRESSEUR_05"]
M_NAMES  = {
    "BROYEUR_01":    "Broyeur à Boulets",
    "POMPE_02":      "Pompe Centrifuge",
    "CONVOYEUR_03":  "Convoyeur à Courroie",
    "REACTEUR_04":   "Réacteur d'Attaque",
    "COMPRESSEUR_05":"Compresseur Industriel",
}
M_SITE = {
    "BROYEUR_01":"Khouribga","POMPE_02":"Benguerir",
    "CONVOYEUR_03":"Jorf Lasfar","REACTEUR_04":"Youssoufia","COMPRESSEUR_05":"Safi",
}
S_UNITS = {"temperature":"°C","vibration":"mm/s","pression":"bar","courant":"A","rpm":"tr/min"}

LOGO_TAG = (
    f'<img src="data:image/png;base64,{LOGO_B64}" style="width:36px;height:36px;object-fit:contain;display:block;"/>'
    if LOGO_B64 else
    '<span style="font-size:13px;font-weight:900;color:#00D37F;letter-spacing:1px;">OCP</span>'
)


# ─── CSS ──────────────────────────────────────────────────────────────────────
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Reset ── */
*, *::before, *::after { box-sizing: border-box; }
#MainMenu, footer, header, .stDeployButton, [data-testid="stToolbar"] {
    visibility: hidden !important;
    display: none !important;
}

/* ── Keyframes ── */
@keyframes pulse-dot {
    0%, 100% { box-shadow: 0 0 0 2px rgba(0,211,127,.25); }
    50%       { box-shadow: 0 0 0 6px rgba(0,211,127,.06); }
}
@keyframes gradient-sweep {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes card-glow-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes spin-ring {
    to { transform: rotate(360deg); }
}

/* ── App shell — dot-grid background ── */
.stApp {
    background-color: #0C0E14 !important;
    background-image: radial-gradient(circle, #1E2240 1px, transparent 1px) !important;
    background-size: 28px 28px !important;
    color: #E8ECF1 !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
.main .block-container {
    padding: 0 28px 40px !important;
    max-width: 100% !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] > div:first-child {
    background: linear-gradient(180deg, #141622 0%, #111320 100%) !important;
    border-right: 1px solid #252840 !important;
    box-shadow: 4px 0 24px rgba(0,0,0,.35) !important;
}
[data-testid="stSidebar"] * { color: #E8ECF1 !important; }

/* Sidebar logo block */
.sb-logo {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 24px 20px 20px;
    border-bottom: 1px solid #252840;
    margin-bottom: 8px;
    position: relative;
}
.sb-logo::after {
    content: '';
    position: absolute; bottom: 0; left: 20px; right: 20px;
    height: 1px;
    background: linear-gradient(90deg, transparent, #00D37F44, transparent);
}
.sb-logo-icon {
    width: 44px; height: 44px;
    background: linear-gradient(135deg, rgba(0,211,127,.18), rgba(0,211,127,.06));
    border: 1px solid rgba(0,211,127,.3);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 0 16px rgba(0,211,127,.15), inset 0 1px 0 rgba(255,255,255,.06);
}
.sb-logo-text-main {
    font-size: 15px; font-weight: 700;
    color: #E8ECF1 !important;
    letter-spacing: -0.2px;
    -webkit-text-fill-color: #E8ECF1 !important;
}
.sb-logo-text-sub {
    font-size: 10px;
    color: #525870 !important;
    -webkit-text-fill-color: #525870 !important;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-top: 2px;
}
.sb-section-label {
    font-size: 10px; font-weight: 600;
    color: #525870 !important;
    -webkit-text-fill-color: #525870 !important;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding: 16px 20px 8px;
}

/* Sidebar radio nav */
[data-testid="stSidebar"] [data-testid="stRadio"] > div { gap: 2px !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    background: transparent !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 9px 16px !important;
    margin: 1px 8px !important;
    cursor: pointer;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #6B7280 !important;
    transition: all 0.18s ease !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: rgba(79,124,246,.08) !important;
    color: #E8ECF1 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
[data-testid="stSidebar"] [data-testid="stRadio"] label[aria-checked="true"] {
    background: rgba(0,211,127,.1) !important;
    color: #00D37F !important;
    font-weight: 600 !important;
    box-shadow: inset 2px 0 0 #00D37F !important;
}

/* Sidebar refresh button */
[data-testid="stSidebar"] .stButton button {
    background: rgba(30,33,48,.6) !important;
    color: #8B92A9 !important;
    border: 1px solid #2A2E3F !important;
    border-radius: 8px !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    transition: all 0.18s ease !important;
    width: calc(100% - 24px) !important;
    margin: 0 12px !important;
    backdrop-filter: blur(4px) !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    border-color: rgba(0,211,127,.4) !important;
    color: #00D37F !important;
    background: rgba(0,211,127,.06) !important;
    box-shadow: 0 0 12px rgba(0,211,127,.1) !important;
}

/* Sidebar status panel */
.sb-status {
    margin: 12px;
    background: rgba(12,14,20,.7);
    border: 1px solid #252840;
    border-radius: 12px;
    padding: 14px 16px;
    backdrop-filter: blur(8px);
    box-shadow: 0 4px 16px rgba(0,0,0,.2);
}
.sb-status-title {
    font-size: 10px; font-weight: 600;
    color: #525870 !important;
    -webkit-text-fill-color: #525870 !important;
    text-transform: uppercase; letter-spacing: 1.5px;
    margin-bottom: 10px;
}
.sb-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid rgba(37,40,64,.8);
    font-size: 12px;
}
.sb-row:last-child { border: none; padding-bottom: 0; }
.sb-key { color: #8B92A9 !important; -webkit-text-fill-color: #8B92A9 !important; }
.sb-val { color: #E8ECF1 !important; -webkit-text-fill-color: #E8ECF1 !important; font-weight: 500; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.sb-online {
    display: inline-flex; align-items: center; gap: 5px;
    color: #00D37F !important; -webkit-text-fill-color: #00D37F !important;
    font-weight: 600; font-size: 11px;
}
.sb-dot {
    width: 7px; height: 7px; background: #00D37F;
    border-radius: 50%; flex-shrink: 0;
    animation: pulse-dot 2.5s ease-in-out infinite;
}
.sb-footer {
    padding: 16px 20px;
    font-size: 10px;
    color: #525870 !important;
    -webkit-text-fill-color: #525870 !important;
    line-height: 1.7;
}
.sb-sep {
    height: 1px;
    background: linear-gradient(90deg, transparent, #252840, transparent);
    margin: 12px 0;
}

/* ── Page header ── */
.page-header {
    padding: 28px 0 22px;
    margin-bottom: 24px;
    border-bottom: 1px solid #1E2240;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    position: relative;
}
.page-header::after {
    content: '';
    position: absolute; bottom: -1px; left: 0;
    width: 120px; height: 1px;
    background: linear-gradient(90deg, #00D37F, transparent);
}
.page-breadcrumb {
    font-size: 11px; font-weight: 500;
    color: #525870;
    text-transform: uppercase; letter-spacing: 1px;
    margin-bottom: 8px;
    display: flex; align-items: center; gap: 8px;
}
.page-breadcrumb span { color: #353A52; }
.page-title {
    font-size: 26px; font-weight: 800;
    color: #E8ECF1;
    letter-spacing: -0.8px; line-height: 1.15;
    background: linear-gradient(135deg, #E8ECF1 60%, #8B92A9);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.page-subtitle {
    font-size: 13px; color: #6B7280; margin-top: 5px; font-weight: 400;
    -webkit-text-fill-color: #6B7280;
}
.page-header-right {
    display: flex; align-items: center; gap: 8px;
}
.status-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(0,211,127,.08);
    border: 1px solid rgba(0,211,127,.25);
    color: #00D37F;
    font-size: 11px; font-weight: 600;
    padding: 5px 12px; border-radius: 6px;
    box-shadow: 0 0 12px rgba(0,211,127,.1);
}
.status-badge-dot {
    width: 5px; height: 5px; background: #00D37F;
    border-radius: 50%; animation: pulse-dot 2.5s infinite;
}
.time-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: #525870;
    background: rgba(30,33,48,.8); border: 1px solid #252840;
    padding: 5px 12px; border-radius: 6px;
    backdrop-filter: blur(4px);
}

/* ── Metric cards ── */
.metrics-grid {
    display: grid;
    gap: 14px;
    margin-bottom: 28px;
}
.metric-card {
    background: linear-gradient(145deg, rgba(30,33,48,.95), rgba(24,27,42,.95));
    border: 1px solid #252840;
    border-radius: 14px;
    padding: 22px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.25s ease, transform 0.25s ease, box-shadow 0.25s ease;
    animation: card-glow-in 0.4s ease forwards;
    backdrop-filter: blur(8px);
}
.metric-card::before {
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(ellipse at 50% 0%, rgba(var(--accent-rgb),.06) 0%, transparent 65%);
    pointer-events: none;
}
.metric-card:hover {
    border-color: rgba(var(--accent-rgb),.35);
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0,0,0,.25), 0 0 0 1px rgba(var(--accent-rgb),.1);
}
.metric-card .accent-line {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, rgba(var(--accent-rgb),1), transparent);
    opacity: 0.7;
}
.metric-label {
    font-size: 10px; font-weight: 700;
    color: #6B7280; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 12px;
    display: flex; align-items: center; gap: 6px;
}
.metric-value {
    font-size: 32px; font-weight: 800;
    color: #E8ECF1; letter-spacing: -1px; line-height: 1;
    font-variant-numeric: tabular-nums;
}
.metric-sub {
    font-size: 11px; color: #525870; margin-top: 6px;
    font-family: 'JetBrains Mono', monospace;
}
.m-green  { --accent: #00D37F; --accent-rgb: 0,211,127; }
.m-red    { --accent: #F04438; --accent-rgb: 240,68,56; }
.m-amber  { --accent: #FFB020; --accent-rgb: 255,176,32; }
.m-blue   { --accent: #4F7CF6; --accent-rgb: 79,124,246; }
.m-teal   { --accent: #06B6D4; --accent-rgb: 6,182,212; }

/* ── Section heading ── */
.section-head {
    font-size: 11px; font-weight: 700;
    color: #6B7280; text-transform: uppercase;
    letter-spacing: 1.2px;
    margin: 28px 0 14px;
    display: flex; align-items: center; gap: 10px;
}
.section-head::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, #252840, transparent);
}

/* ── Status pills ── */
.pill {
    display: inline-flex; align-items: center;
    font-size: 10px; font-weight: 700;
    padding: 3px 10px; border-radius: 4px;
    text-transform: uppercase; letter-spacing: 0.6px;
}
.pill-ok   { background: rgba(0,211,127,.1); color: #00D37F; border: 1px solid rgba(0,211,127,.25); }
.pill-warn { background: rgba(255,176,32,.1); color: #FFB020; border: 1px solid rgba(255,176,32,.25); }
.pill-crit { background: rgba(240,68,56,.1);  color: #F04438; border: 1px solid rgba(240,68,56,.25); }

/* ── Alert ── */
.alert-box {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 13px 16px; border-radius: 10px;
    font-size: 13px; line-height: 1.55; margin: 10px 0;
    backdrop-filter: blur(4px);
}
.alert-ok   { background: rgba(0,211,127,.06);  border: 1px solid rgba(0,211,127,.2);  color: #4DFFA9; }
.alert-warn { background: rgba(255,176,32,.06); border: 1px solid rgba(255,176,32,.2); color: #FFD166; }
.alert-info { background: rgba(79,124,246,.06); border: 1px solid rgba(79,124,246,.2); color: #93B4F8; }

/* ── Widgets override ── */
.stSelectbox label {
    font-size: 11px !important; font-weight: 700 !important;
    color: #6B7280 !important; text-transform: uppercase !important;
    letter-spacing: 0.9px !important;
}
.stSelectbox > div > div {
    background: rgba(30,33,48,.9) !important;
    border: 1px solid #252840 !important;
    border-radius: 8px !important;
    color: #E8ECF1 !important;
    font-size: 13px !important;
    backdrop-filter: blur(4px) !important;
}
.stSelectbox > div > div:focus-within {
    border-color: rgba(0,211,127,.4) !important;
    box-shadow: 0 0 0 3px rgba(0,211,127,.08), 0 0 16px rgba(0,211,127,.08) !important;
}

/* Data table */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 1px solid #252840 !important;
    box-shadow: 0 4px 20px rgba(0,0,0,.2) !important;
}
[data-testid="stDataFrame"] thead tr th {
    background: rgba(36,40,64,.95) !important;
    color: #6B7280 !important;
    font-size: 10px !important; font-weight: 700 !important;
    text-transform: uppercase !important; letter-spacing: 0.9px !important;
    border-bottom: 1px solid #252840 !important;
    padding: 10px 14px !important;
}
[data-testid="stDataFrame"] tbody tr td {
    background: rgba(30,33,48,.9) !important;
    color: #C8CDD8 !important;
    border-bottom: 1px solid rgba(37,40,64,.6) !important;
    font-size: 12px !important;
}
[data-testid="stDataFrame"] tbody tr:hover td {
    background: rgba(36,40,64,.95) !important;
}

/* Download button */
.stDownloadButton button {
    background: rgba(30,33,48,.8) !important; color: #8B92A9 !important;
    border: 1px solid #252840 !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 12px !important;
    transition: all 0.18s ease !important;
    backdrop-filter: blur(4px) !important;
}
.stDownloadButton button:hover {
    border-color: rgba(0,211,127,.4) !important; color: #00D37F !important;
    background: rgba(0,211,127,.06) !important;
    box-shadow: 0 0 16px rgba(0,211,127,.1) !important;
}

/* Column spacing */
[data-testid="column"] { padding: 0 6px !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #252840; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #353A52; }

/* Chart container card */
[data-testid="stPlotlyChart"] {
    background: rgba(24,27,42,.6) !important;
    border: 1px solid #1E2240 !important;
    border-radius: 12px !important;
    padding: 8px !important;
    box-shadow: 0 4px 20px rgba(0,0,0,.15) !important;
}
"""

st.markdown("<style>" + _CSS + "</style>", unsafe_allow_html=True)

# ─── Non-blocking auto-refresh (top-level, runs before any widget) ────────────
if _HAS_AUTOREFRESH:
    _refresh_count = st_autorefresh(interval=30_000, limit=None, key="ocp_autorefresh_top")


# ─── Plotly theme ─────────────────────────────────────────────────────────────
PLOT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", size=11, color="#8B92A9"),
    xaxis=dict(gridcolor="#2A2E3F", showgrid=True, zeroline=False,
               linecolor="#2A2E3F", tickfont=dict(size=10, color="#525870"),
               tickcolor="#2A2E3F"),
    yaxis=dict(gridcolor="#2A2E3F", showgrid=True, zeroline=False,
               linecolor="#2A2E3F", tickfont=dict(size=10, color="#525870")),
    margin=dict(l=4, r=4, t=36, b=4),
    legend=dict(bgcolor="rgba(30,33,48,0.9)", font=dict(size=10, color="#8B92A9"),
                bordercolor="#2A2E3F", borderwidth=1),
    title_font=dict(size=12, color="#8B92A9", family="Inter"),
    hoverlabel=dict(bgcolor="#242840", font_size=12, font_family="Inter",
                    bordercolor="#353A52", font_color="#E8ECF1"),
)

# ─── DB helpers ───────────────────────────────────────────────────────────────
_log = logging.getLogger("ocp_dashboard")

@st.cache_data(ttl=30)
def q(sql: str, params=None) -> pd.DataFrame:
    """Execute a read-only SQL query; returns empty DataFrame on failure."""
    if not DB_PATH.exists():
        _log.warning("DB not found: %s", DB_PATH)
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5, check_same_thread=False)
        df = pd.read_sql(sql, conn, params=params or [])
        conn.close()
        return df
    except sqlite3.OperationalError as exc:
        _log.error("DB query failed (%s): %s", type(exc).__name__, exc)
        return pd.DataFrame()
    except Exception as exc:
        _log.error("Unexpected DB error: %s", exc)
        return pd.DataFrame()

def sensor_data(mid, limit=720):
    df = q("SELECT * FROM sensor_readings WHERE machine_id=? ORDER BY timestamp DESC LIMIT ?",
           [mid, limit])
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df

def decisions(limit=1000, severity="ALL"):
    sql = "SELECT * FROM ml_decisions WHERE 1=1"
    p: list = []
    if severity != "ALL":
        sql += " AND severity=?"; p.append(severity)
    sql += " ORDER BY created_at DESC LIMIT ?"
    p.append(int(limit))
    return q(sql, p)

def judge_evals(limit=300):
    return q("SELECT * FROM judge_evaluations ORDER BY timestamp DESC LIMIT ?", [limit])

def audit_log(limit=300):
    return q("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", [limit])

# ─── Component helpers ────────────────────────────────────────────────────────
def metric(value, label, sub="", color_cls="m-green", icon="") -> str:
    ico = f'<span style="margin-right:4px">{icon}</span>' if icon else ""
    return f"""<div class="metric-card {color_cls}">
  <div class="accent-line"></div>
  <div class="metric-label">{ico}{label}</div>
  <div class="metric-value">{value}</div>
  {"" if not sub else f'<div class="metric-sub">{sub}</div>'}
</div>"""

def section(title, icon="") -> str:
    i = f"{icon} " if icon else ""
    return f'<div class="section-head">{i}{title}</div>'

def page_header(title, subtitle, section_name, badge_text="") -> str:
    now = datetime.now().strftime("%d %b %Y · %H:%M")
    badge = f'<span class="status-badge"><span class="status-badge-dot"></span>{badge_text}</span>' if badge_text else ""
    return f"""<div class="page-header">
  <div class="page-header-left">
    <div class="page-breadcrumb">OCP Bionic Judge <span>›</span> {section_name}</div>
    <div class="page-title">{title}</div>
    <div class="page-subtitle">{subtitle}</div>
  </div>
  <div class="page-header-right">
    {badge}
    <span class="time-badge">{now}</span>
  </div>
</div>"""

def alert(msg, kind="info") -> str:
    icons = {"ok": "✓", "warn": "⚠", "info": "ℹ"}
    classes = {"ok": "alert-ok", "warn": "alert-warn", "info": "alert-info"}
    return (f'<div class="alert-box {classes.get(kind,"alert-info")}">'
            f'<span>{icons.get(kind,"ℹ")}</span><div>{msg}</div></div>')


# ─── Model metrics (dynamic — read from bundle, cached 5 min) ─────────────────
@st.cache_data(ttl=300)
def _model_metrics() -> dict:
    """Load metrics from the saved model bundle. Returns {} if no model trained."""
    try:
        import joblib as _jl
        bundle = _jl.load(str(BASE_DIR / "models" / "best_model.joblib"))
        return bundle.get("metrics", {})
    except Exception:
        return {}


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    dec_all  = decisions(limit=200)
    mdl_name = dec_all["model_version"].iloc[0] if not dec_all.empty else "—"
    _metrics = _model_metrics()
    _auc_str = f"{_metrics['auc_roc']:.4f}" if "auc_roc" in _metrics else "N/A"
    _feat_n  = str(len(_metrics.get("feature_cols", [])) or 24)  # fallback 24

    st.markdown(f"""
<div class="sb-logo">
  <div class="sb-logo-icon">{LOGO_TAG}</div>
  <div>
    <div class="sb-logo-text-main">Bionic Judge</div>
    <div class="sb-logo-text-sub">OCP · Programme Bionic</div>
  </div>
</div>
<div class="sb-section-label">Navigation</div>""", unsafe_allow_html=True)

    # ── Legacy notice ─────────────────────────────────────────────────────────
    st.markdown("""
<div style="margin:4px 12px 8px;padding:8px 12px;border-radius:8px;
            background:rgba(79,124,246,.07);border:1px solid rgba(79,124,246,.2);
            font-size:11px;color:#93B4F8;line-height:1.5;">
  ℹ Interface legacy.<br>
  Frontend principal → <b>localhost:5173</b>
</div>""", unsafe_allow_html=True)

    page = st.radio("", [
        "Capteurs & Détection",
        "Judge Agent",
        "Gouvernance & Audit",
    ], label_visibility="collapsed")

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    if st.button("Actualiser les données", use_container_width=False):
        st.cache_data.clear()
        st.rerun()

    st.markdown(f"""
<div class="sb-sep"></div>
<div class="sb-status">
  <div class="sb-status-title">Système</div>
  <div class="sb-row">
    <span class="sb-key">Statut</span>
    <span class="sb-online"><span class="sb-dot"></span>Opérationnel</span>
  </div>
  <div class="sb-row">
    <span class="sb-key">Modèle</span>
    <span class="sb-val">{mdl_name}</span>
  </div>
  <div class="sb-row">
    <span class="sb-key">AUC-ROC</span>
    <span class="sb-val">{_auc_str}</span>
  </div>
  <div class="sb-row">
    <span class="sb-key">Features</span>
    <span class="sb-val">{_feat_n}</span>
  </div>
  <div class="sb-row">
    <span class="sb-key">Machines</span>
    <span class="sb-val">5 actives</span>
  </div>
  <div class="sb-row">
    <span class="sb-key">Sync</span>
    <span class="sb-val">{datetime.now().strftime('%H:%M:%S')}</span>
  </div>
</div>
<div class="sb-sep"></div>
<div class="sb-footer">
  OCP Bionic Judge v1.2.0<br>
  © 2026 OCP Group — Tous droits réservés
</div>""", unsafe_allow_html=True)


# ─── PAGE 1 · Capteurs & Détection ───────────────────────────────────────────
if page == "Capteurs & Détection":
    dec = decisions(limit=1000)
    n_t = len(dec)
    n_m = dec["machine_id"].nunique() if not dec.empty else 0
    n_a = int(dec["is_anomaly"].sum()) if not dec.empty else 0
    n_c = int((dec["severity"] == "CRITICAL").sum()) if not dec.empty else 0
    n_n = int((dec["severity"] == "NORMAL").sum()) if not dec.empty else 0
    pct = f"{n_a/n_t*100:.1f} %" if n_t else "—"

    st.markdown(page_header(
        "Surveillance Capteurs",
        "Détection d'anomalies en temps réel · 5 machines · OCP Khouribga",
        "Capteurs & Détection",
        badge_text="En direct"
    ), unsafe_allow_html=True)

    st.markdown(
        '<div class="metrics-grid" style="grid-template-columns:repeat(5,1fr)">'
        + metric(str(n_m),    "Machines actives",   "sites OCP",                 "m-teal",  "▣")
        + metric(f"{n_t:,}",  "Lectures analysées", "par le modèle ML",          "m-blue",  "◈")
        + metric(f"{n_a:,}",  "Anomalies",          pct,                         "m-amber", "◆")
        + metric(f"{n_c:,}",  "Alertes critiques",  "intervention requise",      "m-red",   "◉")
        + metric(f"{n_n:,}",  "Lectures normales",  "fonctionnement nominal",    "m-green", "◎")
        + '</div>',
        unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        sel = st.selectbox("Machine", MACHINES,
            format_func=lambda m: f"{m}  ·  {M_NAMES.get(m, '')}")
    with c2:
        sen = st.selectbox("Capteur",
            ["temperature", "vibration", "pression", "courant", "rpm"],
            format_func=lambda s: f"{s.capitalize()}  ({S_UNITS.get(s, '')})")
    with c3:
        lim = st.selectbox("Période", [360, 720, 1440], index=1,
            format_func=lambda n: f"Dernières {n//2}h")

    df = sensor_data(sel, limit=lim)
    if df.empty:
        st.markdown(alert("Aucune donnée disponible pour cette machine.", "info"),
                    unsafe_allow_html=True)
    else:
        if not dec.empty:
            dm = dec[dec["machine_id"] == sel].copy()
            dm["timestamp"] = dm["timestamp"].astype(str)
            dj = df[["timestamp", sen]].copy()
            dj["timestamp"] = dj["timestamp"].astype(str)
            mg = pd.merge(dj, dm[["timestamp", "severity", "anomaly_score"]],
                          on="timestamp", how="left")
            mg["severity"]      = mg["severity"].fillna("NORMAL")
            mg["timestamp"]     = pd.to_datetime(df["timestamp"].values)
        else:
            mg = df[["timestamp", sen]].copy()
            mg["severity"] = "NORMAL"
            mg["anomaly_score"] = 0.0

        col_chart, col_gauge = st.columns([4, 1])
        with col_chart:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=mg["timestamp"], y=mg[sen],
                mode="lines", name=sen.capitalize(),
                line=dict(color=C_GREEN, width=1.5),
                fill="tozeroy", fillcolor="rgba(0,211,127,0.05)",
                hovertemplate=f"<b>%{{y:.2f}} {S_UNITS.get(sen,'')}</b><br>%{{x}}<extra></extra>"))
            anom = mg[mg["severity"] != "NORMAL"]
            for sev_t, col, sym, sz in [("WARNING", C_AMBER, "diamond", 8),
                                         ("CRITICAL", C_RED,   "x",       10)]:
                sub = anom[anom["severity"] == sev_t] if not anom.empty else pd.DataFrame()
                if not sub.empty:
                    fig.add_trace(go.Scatter(
                        x=sub["timestamp"], y=sub[sen],
                        mode="markers", name=sev_t,
                        marker=dict(color=col, size=sz, symbol=sym,
                                    line=dict(width=1.5, color=col))))
            fig.update_layout(
                title=f"{M_NAMES.get(sel, sel)}  ·  {sen.capitalize()} ({S_UNITS.get(sen, '')})",
                height=300, xaxis_title="", yaxis_title=S_UNITS.get(sen, ""), **PLOT)
            st.plotly_chart(fig, use_container_width=True)

        with col_gauge:
            score  = float(mg["anomaly_score"].iloc[-1]) if not mg.empty else 0.0
            sev_lv = str(mg["severity"].iloc[-1]) if not mg.empty else "NORMAL"
            gc     = SEV.get(sev_lv, C_GREEN)
            gauge  = go.Figure(go.Indicator(
                mode="gauge+number", value=round(score * 100, 1),
                number={"suffix": "%", "font": {"size": 22, "color": gc, "family": "Inter"}},
                title={"text": "Score anomalie", "font": {"size": 10, "color": "#525870", "family": "Inter"}},
                gauge={
                    "axis": {"range": [0, 100], "tickcolor": "#2A2E3F",
                             "tickfont": {"size": 9, "color": "#525870"}},
                    "bar": {"color": gc, "thickness": 0.25},
                    "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
                    "steps": [{"range": [0, 30], "color": "rgba(0,211,127,0.06)"},
                               {"range": [30, 70], "color": "rgba(255,176,32,0.06)"},
                               {"range": [70, 100], "color": "rgba(240,68,56,0.06)"}],
                    "threshold": {"line": {"color": gc, "width": 2},
                                  "thickness": 0.75, "value": score * 100}}))
            gauge.update_layout(height=220, paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=30, b=0))
            st.plotly_chart(gauge, use_container_width=True)
            p_cls = {"CRITICAL": "pill-crit", "WARNING": "pill-warn"}.get(sev_lv, "pill-ok")
            st.markdown(f'<div style="text-align:center;margin-top:-8px">'
                        f'<span class="pill {p_cls}">{sev_lv}</span></div>',
                        unsafe_allow_html=True)

        st.markdown(section("Sévérités par machine"), unsafe_allow_html=True)
        if not dec.empty:
            sv = dec.groupby(["machine_id", "severity"]).size().reset_index(name="n")
            fb = px.bar(sv, x="machine_id", y="n", color="severity",
                color_discrete_map=SEV, barmode="stack",
                category_orders={"severity": ["NORMAL", "WARNING", "CRITICAL"]})
            fb.update_traces(marker_line_width=0)
            fb.update_layout(height=240, xaxis_title="", yaxis_title="", **PLOT)
            st.plotly_chart(fb, use_container_width=True)

    st.markdown(section("Alertes critiques récentes"), unsafe_allow_html=True)
    crit = decisions(limit=50, severity="CRITICAL")
    if crit.empty:
        st.markdown(alert("Aucune alerte critique enregistrée.", "ok"), unsafe_allow_html=True)
    else:
        d = crit[["machine_id","timestamp","anomaly_score","severity","model_version"]].copy()
        d["anomaly_score"] = d["anomaly_score"].round(4)
        d["machine_id"]    = d["machine_id"].map(lambda m: f"{m}  ·  {M_NAMES.get(m,'')}")
        st.dataframe(d.head(20), use_container_width=True, hide_index=True,
            column_config={"anomaly_score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=1, format="%.4f")})


# ─── PAGE 2 · Judge Agent ─────────────────────────────────────────────────────
elif page == "Judge Agent":
    ev = judge_evals(limit=500)

    st.markdown(page_header(
        "Judge Agent",
        "Évaluation indépendante des décisions IA · 5 critères pondérés · Gemini 2.0 Flash",
        "Judge Agent",
        badge_text="Gouvernance IA"
    ), unsafe_allow_html=True)

    if ev.empty:
        st.markdown(alert("Aucune évaluation disponible. Lancez <code>POST /analyze</code> avec <code>run_judge: true</code>.", "info"),
                    unsafe_allow_html=True)
    else:
        ev["timestamp"] = pd.to_datetime(ev["timestamp"])
        ms = ev["global_score"].mean()
        ar = ev["agreement"].mean() * 100
        ne = len(ev)
        nd = int((ev["agreement"] == 0).sum())

        st.markdown(
            '<div class="metrics-grid" style="grid-template-columns:repeat(4,1fr)">'
            + metric(str(ne),        "Évaluations",    "enregistrées",     "m-blue",            "◈")
            + metric(f"{ms:.1f}/10", "Score moyen",    "Judge global",     "m-green" if ms>=6 else "m-amber", "◎")
            + metric(f"{ar:.0f} %",  "Taux d'accord",  "Agent ↔ Judge",    "m-green" if ar>=70 else "m-amber","◆")
            + metric(str(nd),        "Désaccords",     "score < 6.0",      "m-red" if nd>0 else "m-green",    "◉")
            + '</div>',
            unsafe_allow_html=True)

        cl, cr = st.columns(2)
        cmap = {
            "relevance_score":   "Pertinence (25%)",
            "history_score":     "Historique (20%)",
            "confidence_score":  "Confiance (20%)",
            "compliance_score":  "Conformité OCP (20%)",
            "feasibility_score": "Faisabilité (15%)",
        }
        av = [c for c in cmap if c in ev.columns]

        with cl:
            st.markdown(section("Distribution des scores"), unsafe_allow_html=True)
            fh = go.Figure()
            fh.add_trace(go.Histogram(
                x=ev["global_score"], nbinsx=20,
                marker=dict(color=C_GREEN, opacity=0.8, line=dict(color=C_GREEN_D, width=0.5))))
            fh.add_vline(x=6.0, line_dash="dash", line_color=C_RED, line_width=1.5,
                annotation_text="  Seuil 6.0",
                annotation_font=dict(color=C_RED, size=10))
            fh.update_layout(xaxis_title="Score /10", yaxis_title="",
                height=280, showlegend=False, **PLOT)
            st.plotly_chart(fh, use_container_width=True)

        with cr:
            st.markdown(section("Profil multi-critères"), unsafe_allow_html=True)
            if av:
                mn = ev[av].mean().tolist()
                ct = [cmap[c] for c in av]
                fr = go.Figure(go.Scatterpolar(
                    r=mn + [mn[0]], theta=ct + [ct[0]],
                    fill="toself",
                    fillcolor="rgba(0,211,127,0.08)",
                    line=dict(color=C_GREEN, width=2),
                    marker=dict(size=6, color=C_GREEN)))
                fr.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 10],
                            gridcolor="#2A2E3F",
                            tickfont=dict(size=9, color="#525870"),
                            tickmode="linear", tick0=0, dtick=2),
                        angularaxis=dict(gridcolor="#2A2E3F",
                            tickfont=dict(size=10, color="#8B92A9")),
                        bgcolor="rgba(0,0,0,0)"),
                    height=280, paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=False, margin=dict(l=55, r=55, t=20, b=20))
                st.plotly_chart(fr, use_container_width=True)

        st.markdown(section("Évolution temporelle des scores"), unsafe_allow_html=True)
        evs = ev.sort_values("timestamp")
        ft  = go.Figure()
        colors_c = [C_GREEN, C_AMBER, C_BLUE, "#A78BFA", C_TEAL]
        if "machine_id" in evs.columns:
            for i, mid in enumerate(evs["machine_id"].unique()):
                sub = evs[evs["machine_id"] == mid]
                ft.add_trace(go.Scatter(
                    x=sub["timestamp"], y=sub["global_score"],
                    mode="lines+markers", name=mid,
                    line=dict(width=1.5, color=colors_c[i % len(colors_c)]),
                    marker=dict(size=3, color=colors_c[i % len(colors_c)])))
        ft.add_hrect(y0=0, y1=6, fillcolor="rgba(240,68,56,0.03)", line_width=0)
        ft.add_hline(y=6.0, line_dash="dash", line_color=C_RED, line_width=1,
            annotation_text="  Seuil 6.0",
            annotation_font=dict(color=C_RED, size=10))
        ft.update_layout(yaxis=dict(range=[0, 10.5]),
            xaxis_title="", yaxis_title="Score /10", height=260, **PLOT)
        st.plotly_chart(ft, use_container_width=True)

        if av and "machine_id" in ev.columns:
            st.markdown(section("Heatmap — Conformité OCP par machine"), unsafe_allow_html=True)
            pivot = ev.groupby("machine_id")[av].mean().round(2)
            pivot.columns = [cmap[c] for c in pivot.columns]
            fhm = px.imshow(
                pivot.T, text_auto=True, aspect="auto",
                color_continuous_scale=[
                    [0, "#F04438"], [0.4, "#FFB020"],
                    [0.7, "#00D37F55"], [1, "#00D37F"]
                ], zmin=0, zmax=10)
            fhm.update_layout(height=240,
                coloraxis_colorbar=dict(
                    tickfont=dict(size=9, color="#525870"),
                    title=dict(text="/10", font=dict(size=10, color="#8B92A9"))),
                **PLOT)
            fhm.update_traces(textfont=dict(size=10, color="white"))
            st.plotly_chart(fhm, use_container_width=True)


# ─── PAGE 3 · Gouvernance & Audit ─────────────────────────────────────────────
elif page == "Gouvernance & Audit":
    st.markdown(page_header(
        "Gouvernance & Audit",
        "Conformité ISO 55000 · Traçabilité complète · Surveillance dérive modèle",
        "Gouvernance & Audit",
        badge_text="Conformité"
    ), unsafe_allow_html=True)

    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR))
        from src.governance.governance import compute_metrics
        gov   = compute_metrics(window="24h")
        conf  = gov.get("mean_judge_confidence", 0) * 100
        disr  = gov.get("disagreement_rate", 0) * 100
        comp  = gov.get("ocp_compliance_rate", 0) * 100
        crit_ = gov.get("critical_unresolved", 0)
        st.markdown(
            '<div class="metrics-grid" style="grid-template-columns:repeat(4,1fr)">'
            + metric(f"{conf:.1f} %", "Confiance moyenne",    "Judge 24h",   "m-green" if conf>=70 else "m-amber", "◎")
            + metric(f"{disr:.1f} %", "Taux de désaccord",    "Agent ↔ Judge","m-red" if disr>30 else "m-green",   "◆")
            + metric(f"{comp:.1f} %", "Conformité OCP",       "ISO 55000",   "m-green" if comp>=70 else "m-amber", "◈")
            + metric(str(crit_),      "Critiques non résolus","24 h",        "m-red" if crit_>0 else "m-green",    "◉")
            + '</div>', unsafe_allow_html=True)
        for a in gov.get("alerts", []):
            st.markdown(alert(a.get("message", str(a)), "warn"), unsafe_allow_html=True)
    except Exception as e:
        st.markdown(alert(f"Métriques non disponibles : {e}", "info"), unsafe_allow_html=True)

    dec2 = decisions(limit=2000)
    if not dec2.empty:
        st.markdown(section("Distribution temporelle des anomalies"), unsafe_allow_html=True)
        dec2["timestamp"] = pd.to_datetime(dec2["timestamp"])
        samp = dec2.sample(min(600, len(dec2)), random_state=42).sort_values("timestamp")
        fs = px.scatter(samp, x="timestamp", y="anomaly_score",
            color="severity", color_discrete_map=SEV, opacity=0.7)
        fs.update_traces(marker=dict(size=4, line=dict(width=0.5, color="#111318")))
        fs.update_layout(xaxis_title="", yaxis_title="Score d'anomalie", height=260, **PLOT)
        st.plotly_chart(fs, use_container_width=True)

    st.markdown(section("Journal d'audit"), unsafe_allow_html=True)

    f1, f2, f3 = st.columns(3)
    with f1:
        mf = st.selectbox("Machine", ["Toutes"] + MACHINES,
            format_func=lambda m: "Toutes les machines" if m == "Toutes"
            else f"{m}  ·  {M_NAMES.get(m, '')}")
    with f2:
        sf = st.selectbox("Sévérité", ["Toutes", "INFO", "WARNING", "CRITICAL"])
    with f3:
        ef = st.selectbox("Type d'événement",
            ["Tous", "JUDGE_EVALUATION", "DRIFT_CHECK", "PREDICTION"])

    al = audit_log(limit=500)
    if not al.empty:
        fa = al.copy()
        if mf != "Toutes": fa = fa[fa["machine_id"] == mf]
        if sf != "Toutes": fa = fa[fa["severity"]   == sf]
        if ef != "Tous":   fa = fa[fa["event_type"] == ef]

        tc, pc = st.columns([3, 1])
        with pc:
            sd = fa["severity"].value_counts().reset_index()
            sd.columns = ["severity", "n"]
            fp = px.pie(sd, values="n", names="severity", color="severity",
                color_discrete_map={"INFO": C_BLUE, "WARNING": C_AMBER, "CRITICAL": C_RED},
                hole=0.65)
            fp.update_layout(
                height=240, paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=10, b=0),
                font=dict(size=9, family="Inter", color="#8B92A9"),
                legend=dict(font=dict(size=9), bgcolor="rgba(0,0,0,0)"))
            fp.update_traces(textfont_size=9,
                marker=dict(line=dict(color="#0C0E14", width=2)))
            st.plotly_chart(fp, use_container_width=True)
        with tc:
            cols = [c for c in ["timestamp","event_type","machine_id","action","severity"]
                    if c in fa.columns]
            st.dataframe(fa[cols].head(50), use_container_width=True,
                         hide_index=True, height=240)

        csv = fa.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Exporter en CSV",
            csv,
            f"audit_ocp_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            "text/csv")
    else:
        st.markdown(alert("Aucun log d'audit disponible.", "info"), unsafe_allow_html=True)


# ── Fallback notice when streamlit-autorefresh is not installed ───────────────
if not _HAS_AUTOREFRESH:
    st.markdown(
        '<div style="text-align:right;font-size:10px;color:#525870;'
        'font-family:JetBrains Mono,monospace;padding:8px 4px 0">'
        'Installez streamlit-autorefresh pour le rafraichissement auto'
        '</div>',
        unsafe_allow_html=True,
    )
