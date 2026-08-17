# Executive Revenue Command Center adapted for Native App deployment
# Co-authored with CoCo
# ================================================================
# CONTRACT INTELLIGENCE — EXECUTIVE REVENUE COMMAND CENTER v4
# White / Light Theme · Refined Luxury Aesthetic · SiS Ready
# dashboard.py — Native App Version
# All queries use app-internal schemas: gold.*, analytics.*, raw.*, config.*
# Cortex AI chatbot included (mistral-large, runs inside Snowflake)
# ================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from snowflake.snowpark.context import get_active_session
from datetime import datetime
import json

# Fallback for older Streamlit versions that do not support st.dialog
if not hasattr(st, "dialog"):
    if hasattr(st, "experimental_dialog"):
        st.dialog = st.experimental_dialog
    else:
        def dialog_fallback(title, width=None):
            def decorator(func):
                def wrapper(*args, **kwargs):
                    with st.container(border=True):
                        st.subheader(title)
                        func(*args, **kwargs)
                return wrapper
            return decorator
        st.dialog = dialog_fallback


# ================================================================
# GLOBAL DESIGN SYSTEM — WHITE LUXURY THEME
# ================================================================
_DASHBOARD_CSS = """
<style>
/* Using system font stack — no external network calls */

:root {
    --bg-canvas: #ffffff; --bg-surface: #ffffff; --bg-card: #ffffff;
    --bg-raised: #ffffff; --bg-hover: #f9fafb; --bg-muted: #f8fafc; --bg-input: #ffffff;
    --bd-0: rgba(0,0,0,0.04); --bd-1: rgba(0,0,0,0.08); --bd-2: rgba(0,0,0,0.12); --bd-3: rgba(0,0,0,0.20);
    --tx-0: #0f1117; --tx-1: #2d3142; --tx-2: #6b7280; --tx-3: #9ca3af; --tx-4: #c2c8d4;
    --acc: #1a1f36; --acc-dk: #0d1020; --acc-lt: #3d4566;
    --acc-bg: rgba(26,31,54,0.06); --acc-bd: rgba(26,31,54,0.14);
    --red: #dc2626; --red-lt: #ef4444; --red-dk: #b91c1c;
    --red-bg: rgba(220,38,38,0.06); --red-bd: rgba(220,38,38,0.18); --red-soft: #fff1f1;
    --amb: #d97706; --amb-lt: #f59e0b; --amb-dk: #b45309;
    --amb-bg: rgba(217,119,6,0.06); --amb-bd: rgba(217,119,6,0.18); --amb-soft: #fffbeb;
    --grn: #059669; --grn-lt: #10b981; --grn-dk: #047857;
    --grn-bg: rgba(5,150,105,0.06); --grn-bd: rgba(5,150,105,0.18); --grn-soft: #f0fdf9;
    --blu: #2563eb; --blu-lt: #3b82f6; --blu-dk: #1d4ed8;
    --blu-bg: rgba(37,99,235,0.06); --blu-bd: rgba(37,99,235,0.16); --blu-soft: #eff6ff;
    --vio: #7c3aed; --vio-lt: #8b5cf6; --vio-dk: #6d28d9;
    --vio-bg: rgba(124,58,237,0.06); --vio-bd: rgba(124,58,237,0.16); --vio-soft: #f5f3ff;
    --sky: #0284c7; --sky-lt: #0ea5e9; --sky-dk: #0369a1;
    --sky-bg: rgba(2,132,199,0.06); --sky-bd: rgba(2,132,199,0.16);
    --sh-xs: 0 1px 2px rgba(0,0,0,0.04);
    --sh-sm: 0 1px 4px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --sh-md: 0 4px 12px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04);
    --sh-lg: 0 8px 24px rgba(0,0,0,0.10), 0 2px 8px rgba(0,0,0,0.06);
    --sh-xl: 0 16px 48px rgba(0,0,0,0.12), 0 4px 12px rgba(0,0,0,0.06);
    --sh-card: 0 0 0 1px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.06);
    --r-xs: 3px; --r-sm: 6px; --r-md: 8px; --r-lg: 12px;
    --r-xl: 16px; --r-2xl: 20px; --r-f: 999px;
}

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    -webkit-font-smoothing: antialiased;
}
[data-testid="stAppViewContainer"] { background: var(--bg-canvas) !important; }
.block-container { padding: 0 2rem 6rem !important; max-width: 1680px !important; background: transparent !important; }
#MainMenu, footer, header { visibility: hidden !important; }
.stDeployButton { display: none !important; }

.topnav { position: sticky; top: 0; z-index: 200; background: rgba(255,255,255,0.92);
    backdrop-filter: blur(20px) saturate(1.6); border-bottom: 1px solid var(--bd-1);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 2rem; height: 52px; box-shadow: 0 1px 0 var(--bd-1), 0 2px 8px rgba(0,0,0,0.04); margin: 0 -2rem 0; }
.tn-brand { display:flex; align-items:center; gap:10px; }
.tn-logo { width: 28px; height: 28px; border-radius: var(--r-md); background: var(--acc);
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 900; color: #fff; flex-shrink: 0; }
.tn-name { font-family: Georgia, 'Times New Roman', serif; font-size: 15px; color: var(--tx-0); }
.tn-sep { color: var(--bd-3); font-size: 16px; margin: 0 2px; }
.tn-right { display:flex; align-items:center; gap:14px; }
.tn-ts { font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; font-size: 10.5px; color: var(--tx-3); }
.tn-divider { width:1px; height:18px; background: var(--bd-2); }
.tn-live { display:inline-flex; align-items:center; gap:5px; background: var(--grn-soft);
    border: 1px solid var(--grn-bd); border-radius: var(--r-f); padding: 3px 10px;
    font-size: 10px; font-weight: 700; color: var(--grn); letter-spacing: 0.06em; text-transform: uppercase; }
.live-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--grn); animation: pulse 2s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1);} 50%{opacity:0.4;transform:scale(0.8);} }

.sec-hd { display: flex; align-items: center; gap: 10px; margin: 24px 0 14px; }
.sec-hd-line { flex:1; height:1px; background: var(--bd-1); }
.sec-hd-label { font-size: 9.5px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--tx-3); white-space: nowrap; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }

.hero-grid { display: grid; grid-template-columns: 1.55fr 1fr 1fr; gap: 14px; margin-top: 16px; }
.hero-card { background: var(--bg-card); border-radius: var(--r-2xl); padding: 24px 26px 22px;
    box-shadow: var(--sh-card); border: 1px solid var(--bd-1); position: relative; overflow: hidden;
    transition: box-shadow 0.2s, transform 0.2s; }
.hero-card:hover { box-shadow: var(--sh-lg); transform: translateY(-2px); }
.hero-card::after { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: var(--r-2xl) var(--r-2xl) 0 0; }
.hc-danger::after { background: linear-gradient(90deg, var(--red), #ff6b6b); }
.hc-success::after { background: linear-gradient(90deg, var(--grn), var(--sky)); }
.hc-neutral::after { background: linear-gradient(90deg, var(--acc), #6b7280); }
.hc-eyebrow { display: flex; align-items: center; gap: 7px; margin-bottom: 12px; }
.hc-dot { width: 7px; height: 7px; border-radius: 50%; }
.d-red { background: var(--red); box-shadow: 0 0 0 3px var(--red-bg); }
.d-grn { background: var(--grn); box-shadow: 0 0 0 3px var(--grn-bg); }
.d-acc { background: var(--acc); box-shadow: 0 0 0 3px var(--acc-bg); }
.hc-label { font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--tx-3); font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.hc-main-val { font-family: Georgia, 'Times New Roman', serif; font-size: 44px; font-weight: 400;
    letter-spacing: -0.02em; line-height: 1.05; margin-bottom: 8px; color: var(--tx-0); }
.hc-main-val.v-red { color: var(--red); }
.hc-main-val.v-grn { color: var(--grn); }
.hc-main-val.v-acc { color: var(--acc); }
.hc-desc { font-size: 12px; color: var(--tx-2); line-height: 1.5; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.hc-tag { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: var(--r-f); border: 1px solid; }
.ht-red { background: var(--red-soft); border-color: var(--red-bd); color: var(--red); }
.ht-grn { background: var(--grn-soft); border-color: var(--grn-bd); color: var(--grn); }
.ht-acc { background: var(--acc-bg); border-color: var(--acc-bd); color: var(--acc); }
.hc-mini-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 16px; }
.hc-mini { background: var(--bg-muted); border: 1px solid var(--bd-1); border-radius: var(--r-lg); padding: 10px 10px 9px; }
.hcm-val { font-size: 18px; font-weight: 700; letter-spacing: -0.03em; line-height: 1; margin-bottom: 2px; color: var(--tx-0); }
.hcm-lbl { font-size: 8.5px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--tx-3); font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }

.panel { background: var(--bg-card); border: 1px solid var(--bd-1); border-radius: var(--r-2xl);
    box-shadow: var(--sh-card); overflow: hidden; }
.panel-head { display: flex; align-items: center; gap: 10px; padding: 14px 18px 12px;
    border-bottom: 1px solid var(--bd-0); background: var(--bg-raised); }
.ph-icon { width: 30px; height: 30px; border-radius: var(--r-md); display: flex;
    align-items: center; justify-content: center; font-size: 13px; flex-shrink: 0; }
.phi-red{background:var(--red-soft);} .phi-amb{background:var(--amb-soft);}
.phi-grn{background:var(--grn-soft);} .phi-acc{background:var(--acc-bg);}
.phi-vio{background:var(--vio-soft);} .phi-blu{background:var(--blu-soft);}
.ph-title { font-size: 13px; font-weight: 700; color: var(--tx-0); }
.ph-sub { font-size: 11px; color: var(--tx-3); margin-top: 1px; }
.ph-badge { margin-left: auto; font-size: 9.5px; font-weight: 700; letter-spacing: 0.06em;
    text-transform: uppercase; padding: 3px 10px; border-radius: var(--r-f);
    background: var(--bg-muted); border: 1px solid var(--bd-2); color: var(--tx-2);
    font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.panel-body { padding: 16px 18px 18px; }

.iss-wrap { padding: 0 18px 18px; }
.iss-tbl { width: 100%; border-collapse: collapse; }
.iss-tbl thead tr { border-bottom: 1.5px solid var(--bd-1); }
.iss-tbl thead th { font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
    color: var(--tx-3); padding: 0 10px 10px; text-align: left; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.iss-tbl thead th.ta-r { text-align: right; }
.iss-tbl tbody tr { border-bottom: 1px solid var(--bd-0); transition: background 0.1s; }
.iss-tbl tbody tr:last-child { border-bottom: none; }
.iss-tbl tbody tr:hover { background: var(--bg-hover); }
.iss-tbl td { padding: 10px 10px; vertical-align: middle; }
.rank-badge { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px;
    border-radius: var(--r-sm); font-size: 9.5px; font-weight: 700; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    background: var(--bg-muted); border: 1px solid var(--bd-2); color: var(--tx-3); }
.rank-badge.r1{background:var(--red-soft);border-color:var(--red-bd);color:var(--red);}
.rank-badge.r2{background:var(--amb-soft);border-color:var(--amb-bd);color:var(--amb);}
.rank-badge.r3{background:var(--vio-soft);border-color:var(--vio-bd);color:var(--vio);}
.cust-name { font-size: 12.5px; font-weight: 600; color: var(--tx-0); max-width: 140px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cust-ind { font-size: 10px; color: var(--tx-3); margin-top: 1px; }
.rule-name { font-size: 11.5px; font-weight: 500; color: var(--tx-1); max-width: 155px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rule-calc { font-size: 9.5px; color: var(--tx-3); max-width: 155px; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; margin-top: 1px; }
.amt-cell { font-size: 13px; font-weight: 700; letter-spacing: -0.02em; color: var(--tx-0);
    text-align: right; white-space: nowrap; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.amt-cell.a-crit { color: var(--red); }
.amt-cell.a-high { color: var(--amb); }
.sev-pill { display: inline-flex; align-items: center; gap: 4px; font-size: 9px; font-weight: 700;
    letter-spacing: 0.07em; text-transform: uppercase; padding: 3px 9px; border-radius: var(--r-f);
    border: 1px solid; white-space: nowrap; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.sp-critical{background:var(--red-soft);border-color:var(--red-bd);color:var(--red);}
.sp-high{background:var(--amb-soft);border-color:var(--amb-bd);color:var(--amb);}
.sp-medium{background:var(--vio-soft);border-color:var(--vio-bd);color:var(--vio);}
.sp-low{background:var(--grn-soft);border-color:var(--grn-bd);color:var(--grn);}
.cat-tag { display: inline-block; font-size: 9px; font-weight: 600; padding: 2px 8px;
    border-radius: var(--r-f); border: 1px solid; white-space: nowrap; }

.bar-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--bd-0); }
.bar-row:last-child { border-bottom: none; }
.bar-label { font-size: 11.5px; font-weight: 500; color: var(--tx-1); min-width: 128px; }
.bar-track { flex: 1; height: 5px; background: var(--bg-muted); border-radius: var(--r-f); overflow: hidden; border: 1px solid var(--bd-0); }
.bar-fill { height: 100%; border-radius: var(--r-f); transition: width 0.5s ease; }
.bar-amount { font-size: 11.5px; font-weight: 700; color: var(--tx-0); min-width: 60px;
    text-align: right; white-space: nowrap; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.bar-pct { font-size: 10px; color: var(--tx-3); min-width: 34px; text-align: right; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }

.action-grid { display: grid; grid-template-columns: repeat(5,1fr); gap: 10px; }
.action-card { background: var(--bg-card); border: 1px solid var(--bd-1); border-radius: var(--r-xl);
    padding: 16px 15px 15px; box-shadow: var(--sh-xs); position: relative; overflow: hidden;
    transition: box-shadow 0.16s, transform 0.16s; display: flex; flex-direction: column; gap: 7px; }
.action-card:hover { box-shadow: var(--sh-lg); transform: translateY(-2px); }
.action-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
.ac-1::before{background:linear-gradient(90deg,var(--red),#f97316);}
.ac-2::before{background:linear-gradient(90deg,var(--amb),#eab308);}
.ac-3::before{background:linear-gradient(90deg,var(--vio),var(--blu));}
.ac-4::before{background:linear-gradient(90deg,var(--blu),var(--sky));}
.ac-5::before{background:linear-gradient(90deg,var(--grn),#14b8a6);}
.ac-top { display: flex; align-items: center; justify-content: space-between; }
.ac-pri { font-size: 8.5px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.ac1{color:var(--red);} .ac2{color:var(--amb);} .ac3{color:var(--vio);} .ac4{color:var(--blu);} .ac5{color:var(--grn);}
.ac-urg { font-size: 9px; color: var(--tx-3); font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    background: var(--bg-muted); border: 1px solid var(--bd-1); border-radius: var(--r-f); padding: 2px 7px; }
.ac-amount { font-family: Georgia, 'Times New Roman', serif; font-size: 22px; font-weight: 400;
    letter-spacing: -0.02em; color: var(--tx-0); line-height: 1.1; }
.ac-title { font-size: 11.5px; font-weight: 600; color: var(--tx-0); line-height: 1.35; }
.ac-body { font-size: 10.5px; color: var(--tx-2); line-height: 1.6; flex: 1; }

.insight-card { background: var(--bg-card); border: 1px solid var(--bd-1); border-radius: var(--r-xl);
    padding: 18px 18px 16px; box-shadow: var(--sh-xs); height: 100%; }
.ic-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ic-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ic-title { font-size: 12px; font-weight: 700; color: var(--tx-0); }
.ic-body { font-size: 11.5px; color: var(--tx-2); line-height: 1.7; }
.hi-r{color:var(--red);font-weight:700;} .hi-a{color:var(--amb);font-weight:700;}
.hi-g{color:var(--grn);font-weight:700;} .hi-b{color:var(--tx-0);font-weight:700;} .hi-v{color:var(--vio);font-weight:700;}

.stTabs [data-baseweb="tab-list"] { background: transparent !important; border-bottom: 1.5px solid var(--bd-1) !important; gap: 0 !important; }
.stTabs [data-baseweb="tab"] { font-size: 12.5px !important; font-weight: 600 !important; color: var(--tx-2) !important;
    background: transparent !important; padding: 10px 20px !important; border-bottom: 2px solid transparent !important; border-radius: 0 !important; }
.stTabs [aria-selected="true"] { color: var(--tx-0) !important; border-bottom-color: var(--acc) !important; font-weight: 700 !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 1.25rem !important; background: transparent !important; }
[data-testid="stMetric"] { background: var(--bg-card); border: 1px solid var(--bd-1); border-radius: var(--r-lg); padding: 12px 16px !important; box-shadow: var(--sh-xs); }
[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 700 !important; letter-spacing: -0.03em !important; color: var(--tx-0) !important; }
[data-testid="stMetricLabel"] { font-size: 9px !important; font-weight: 700 !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important; color: var(--tx-3) !important; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace !important; }
section[data-testid="stSidebar"] { background: var(--bg-card) !important; border-right: 1px solid var(--bd-1) !important; }
.stButton > button { background: var(--acc) !important; border: 1.5px solid var(--acc) !important; color: #fff !important;
    border-radius: var(--r-lg) !important; font-size: 12px !important; font-weight: 600 !important;
    box-shadow: var(--sh-sm) !important; padding: 8px 18px !important; transition: all 0.15s ease !important; }
.stButton > button:hover { background: var(--acc-lt) !important; box-shadow: var(--sh-md) !important; transform: translateY(-1px) !important; }
.stDataFrame { border-radius: var(--r-lg) !important; border: 1px solid var(--bd-1) !important; overflow: hidden; box-shadow: var(--sh-xs) !important; }

.ci-footer { text-align: center; padding: 2rem 0 0.5rem; font-size: 10px; color: var(--tx-4);
    font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; letter-spacing: 0.04em; border-top: 1px solid var(--bd-0); margin-top: 2.5rem; }
</style>
"""

# ================================================================
# CONSTANTS & MAPPINGS
# ================================================================
RULE_LABELS = {
    "R01": "SLA Breach Penalty", "R02": "Missed Performance Bonus",
    "R03": "Billing Rate Error", "R04": "Unbilled Overage Usage",
    "R05": "Delivery SLA Failure", "R06": "Quality Defect Penalty",
}
CATEGORY_MAP = {
    "R01": "SLA Violations", "R02": "Uncaptured Revenue",
    "R03": "Billing Errors", "R04": "Billing Errors",
    "R05": "Delivery Failures", "R06": "Quality Penalties",
}
CATEGORY_COLORS = {
    "SLA Violations": "#dc2626", "Billing Errors": "#d97706",
    "Delivery Failures": "#2563eb", "Quality Penalties": "#7c3aed",
    "Uncaptured Revenue": "#059669",
}
SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
ACTION_TEMPLATES = {
    "R03": dict(title="Issue corrected invoice this week", body="Billing rate discrepancy detected. Finance should issue a credit note and confirm the correct contractual rate.", urgency="This week", ac="ac-1", pri="ac1", lbl="IMMEDIATE"),
    "R04": dict(title="Raise supplemental invoice for overages", body="Usage exceeded contracted tier. A supplemental invoice for overage units at the agreed rate should be raised.", urgency="Immediate", ac="ac-1", pri="ac1", lbl="IMMEDIATE"),
    "R01": dict(title="Apply SLA penalty deductions", body="Claim turnaround exceeded contracted SLA windows. Apply the penalty deduction per contract terms.", urgency="48 hours", ac="ac-2", pri="ac2", lbl="48 HRS"),
    "R06": dict(title="Escalate quality breach to supplier", body="Defect rates exceeded contracted threshold. Raise formal non-conformance notice and initiate penalty calculation.", urgency="48 hours", ac="ac-2", pri="ac2", lbl="48 HRS"),
    "R05": dict(title="Calculate and claim delivery penalties", body="On-time delivery fell below contracted minimum. Log the breach and notify the procurement lead.", urgency="This week", ac="ac-3", pri="ac3", lbl="THIS WEEK"),
    "R02": dict(title="Apply earned bonus to next invoice", body="A performance bonus was earned but not yet applied. Adjust the upcoming invoice to include the bonus credit.", urgency="Next cycle", ac="ac-4", pri="ac4", lbl="SCHEDULE"),
}

CHAT_SUGGESTIONS = [
    "What is the total revenue at risk?",
    "Which customer has the highest exposure?",
    "Explain SLA Breach Penalty rule",
    "How does the detection engine work?",
    "What actions should I take today?",
    "Summarise portfolio health",
]

# ================================================================
# DATA LOADERS — all queries use app-internal schemas, filtered by data mode
# ================================================================
session = get_active_session()


def _get_data_mode():
    """Get the current data mode (DEMO or CONSUMER)."""
    try:
        rows = session.sql("SELECT setting_value FROM config.app_settings WHERE setting_key='DATA_MODE'").collect()
        return rows[0][0] if rows else 'DEMO'
    except Exception:
        return 'DEMO'


@st.cache_data(ttl=60)
def load_kpi(mode):
    if mode == 'CONSUMER':
        return session.sql("""
            SELECT COUNT(*) AS TOTAL_CONTRACTS,
                   COALESCE(SUM(ANNUAL_VALUE_USD), 0) AS PORTFOLIO_VALUE_USD
            FROM raw.consumer_master_contracts
        """).to_pandas()
    else:
        return session.sql("""
            SELECT COUNT(*) AS TOTAL_CONTRACTS,
                   COALESCE(SUM(ANNUAL_VALUE_USD), 0) AS PORTFOLIO_VALUE_USD
            FROM raw.demo_contracts
        """).to_pandas()


@st.cache_data(ttl=60)
def load_register(mode):
    return session.sql(f"""
        SELECT RULE_ID, RULE_NAME, EVENT_REF, CONTRACT_ID, CUSTOMER_NAME, INDUSTRY,
               LEAKAGE_TYPE, SEVERITY, LEAKAGE_AMOUNT_USD, EVENT_DATE,
               CALCULATION_DETAIL, DETECTED_AT, DATA_MODE
        FROM gold.leakage_register
        WHERE DATA_MODE = '{mode}'
    """).to_pandas()


@st.cache_data(ttl=60)
def load_alerts(mode):
    return session.sql(f"""
        SELECT a.ALERT_TYPE, a.SEVERITY, a.CUSTOMER_NAME, a.LEAKAGE_AMOUNT_USD,
               a.SENT_TO, a.STATUS, a.CREATED_AT
        FROM gold.alerts a
        JOIN analytics.leakage_events le ON le.leakage_id = a.leakage_id
        WHERE le.data_mode = '{mode}'
        LIMIT 50
    """).to_pandas()


@st.cache_data(ttl=60)
def load_credits(mode):
    return session.sql(f"""
        SELECT c.CREDIT_TYPE, c.CUSTOMER_NAME, c.CONTRACT_ID, c.CREDIT_AMOUNT_USD,
               c.STATUS, c.ERP_SYNC_STATUS, c.CREATED_AT
        FROM gold.credit_notes c
        JOIN analytics.leakage_events le ON le.leakage_id = c.leakage_id
        WHERE le.data_mode = '{mode}'
        ORDER BY c.CREDIT_AMOUNT_USD DESC
    """).to_pandas()


# ================================================================
# CORTEX LLM HELPER
# ================================================================
def _build_system_context(kpi_summary: dict) -> str:
    return f"""You are a Contract Intelligence AI assistant embedded inside
an executive revenue-leakage dashboard built on Snowflake. You help Finance,
Procurement, and Legal teams understand contract risks and take action.

CURRENT PORTFOLIO SNAPSHOT (live data):
- Total revenue at risk: ${kpi_summary.get('total_leakage', 0):,.0f}
- Portfolio value: ${kpi_summary.get('portfolio_val', 0):,.0f}
- Leakage rate: {kpi_summary.get('leakage_rate', 0):.2f}% of portfolio
- Total issues detected: {kpi_summary.get('total_events', 0)}
- Critical issues: {kpi_summary.get('critical_count', 0)}
- High issues: {kpi_summary.get('high_count', 0)}
- Recovery potential (85% rate): ${kpi_summary.get('recovery_est', 0):,.0f}
- Top leakage category: {kpi_summary.get('top_cat', '-')} ({kpi_summary.get('top_cat_pct', 0)}% of total)
- Highest-risk customer: {kpi_summary.get('top_cust', '-')} (${kpi_summary.get('top_cust_amt', 0):,.0f})

DETECTION RULES:
- R01: SLA Breach Penalty
- R02: Missed Performance Bonus
- R03: Billing Rate Error
- R04: Unbilled Overage Usage
- R05: Delivery SLA Failure
- R06: Quality Defect Penalty

Respond concisely and professionally. Use bullet points for lists.
When quoting amounts use $ formatting. Always be actionable and specific."""


def call_cortex(prompt: str, kpi_summary: dict) -> str:
    system_ctx = _build_system_context(kpi_summary)
    safe_prompt = prompt.replace("'", "\\'")
    safe_system = system_ctx.replace("'", "\\'")
    sql = f"""
    SELECT SNOWFLAKE.CORTEX.COMPLETE(
        'mistral-large2',
        [
            {{'role': 'system', 'content': '{safe_system}'}},
            {{'role': 'user', 'content': '{safe_prompt}'}}
        ],
        {{'temperature': 0.3, 'max_tokens': 600}}
    ) AS response
    """
    try:
        result = session.sql(sql).collect()
        raw = result[0]["RESPONSE"] if result else "{}"
        parsed = json.loads(raw)
        return parsed["choices"][0]["messages"]
    except Exception as e:
        err_msg = str(e)
        if any(term in err_msg.lower() for term in ["does not exist", "not authorized", "privilege", "unknown function", "cortex", "permission"]):
            return (
                "⚠️ **Cortex AI is not enabled or authorized.**\n\n"
                "To use the Cortex AI Assistant, please enable the `CORTEX_USER` privilege via the application settings page in Snowsight.\n\n"
                "*Note: Cortex AI features may not be supported or available in standard Snowflake Trial Accounts without upgrading.*"
            )
        return f"⚠️ Cortex is unavailable right now. Error: {err_msg}"



# ================================================================
# MAIN render()
# ================================================================
def render():
    st.markdown(_DASHBOARD_CSS, unsafe_allow_html=True)

    # ── Back button to return to landing page ──────────────────────
    col_back, col_spacer = st.columns([1, 5])
    with col_back:
        if st.button("← Back to Home", key="btn_back_to_landing"):
            st.session_state.page = "landing"
            st.rerun()

    # ── Determine current data mode for filtering ──────────────────
    current_mode = _get_data_mode()

    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # ── SIDEBAR ────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style='display:flex;align-items:center;gap:9px;margin-bottom:20px;
            padding-bottom:16px;border-bottom:1px solid rgba(0,0,0,0.08)'>
            <div style='width:28px;height:28px;border-radius:8px;background:#1a1f36;
                display:flex;align-items:center;justify-content:center;
                font-size:13px;font-weight:900;color:#fff;'>CI</div>
            <div>
                <div style='font-size:12.5px;font-weight:700;color:#0f1117;'>Contract Intel</div>
                <div style='font-size:9.5px;color:#9ca3af;font-family:'SF Mono','Consolas',monospace;'>Executive Controls</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        reg_raw_all = load_register(current_mode)
        industries = sorted(reg_raw_all["INDUSTRY"].dropna().unique().tolist())
        severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        categories = sorted(reg_raw_all["RULE_ID"].map(CATEGORY_MAP).dropna().unique().tolist())
        customers = sorted(reg_raw_all["CUSTOMER_NAME"].dropna().unique().tolist())

        st.markdown("**Industry**")
        sel_industry = st.multiselect("", industries, default=industries, label_visibility="collapsed", key="ms_ind")
        st.markdown("**Severity**")
        sel_severity = st.multiselect("", severities, default=severities, label_visibility="collapsed", key="ms_sev")
        st.markdown("**Category**")
        sel_category = st.multiselect("", categories, default=categories, label_visibility="collapsed", key="ms_cat")
        st.markdown("**Customer**")
        sel_customer = st.multiselect("", customers, default=customers, label_visibility="collapsed", key="ms_cust")

        st.divider()
        if st.button("Run Detection Pipeline", use_container_width=True):
            with st.spinner("Running 6-rule detection engine..."):
                result = session.sql("CALL app.run_leakage_detection()").collect()
                st.success(str(result[0][0]))
                st.cache_data.clear()
                st.rerun()

        if st.button("Refresh Dashboard", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.caption("Auto-refresh every 5 min")

    # ── DATA PREP ──────────────────────────────────────────────
    reg_raw = load_register(current_mode).copy()
    reg_raw["FRIENDLY_RULE"] = reg_raw["RULE_ID"].map(RULE_LABELS).fillna(reg_raw["RULE_ID"])
    reg_raw["CATEGORY"] = reg_raw["RULE_ID"].map(CATEGORY_MAP).fillna("Other")
    reg_raw["SEV_SORT"] = reg_raw["SEVERITY"].map(SEV_ORDER).fillna(99)
    reg_raw = reg_raw.sort_values(["SEV_SORT", "LEAKAGE_AMOUNT_USD"], ascending=[True, False])

    reg = reg_raw.copy()
    if sel_industry:
        reg = reg[reg["INDUSTRY"].isin(sel_industry)]
    if sel_severity:
        reg = reg[reg["SEVERITY"].isin(sel_severity)]
    if sel_category:
        reg = reg[reg["CATEGORY"].isin(sel_category)]
    if sel_customer:
        reg = reg[reg["CUSTOMER_NAME"].isin(sel_customer)]

    kpi_raw = load_kpi(current_mode)
    kpi = kpi_raw.iloc[0] if not kpi_raw.empty else {}
    portfolio_val = float(kpi.get("PORTFOLIO_VALUE_USD", 0))
    total_contracts = int(kpi.get("TOTAL_CONTRACTS", 0))

    total_leakage = reg["LEAKAGE_AMOUNT_USD"].sum()
    critical_count = int((reg["SEVERITY"] == "CRITICAL").sum())
    high_count = int((reg["SEVERITY"] == "HIGH").sum())
    medium_count = int((reg["SEVERITY"] == "MEDIUM").sum())
    low_count = int((reg["SEVERITY"] == "LOW").sum())
    total_events = len(reg)
    leakage_rate = round(total_leakage / portfolio_val * 100, 2) if portfolio_val else 0
    recovery_est = total_leakage * 0.85
    now_str = datetime.now().strftime("%d %b %Y · %H:%M")

    cat_df = (
        reg.groupby("CATEGORY")["LEAKAGE_AMOUNT_USD"]
        .sum().reset_index()
        .sort_values("LEAKAGE_AMOUNT_USD", ascending=False)
    )
    cust_df = (
        reg.groupby("CUSTOMER_NAME")["LEAKAGE_AMOUNT_USD"]
        .sum().reset_index()
        .sort_values("LEAKAGE_AMOUNT_USD", ascending=True)
        .tail(8)
    )
    rule_df = (
        reg.groupby("FRIENDLY_RULE")["LEAKAGE_AMOUNT_USD"]
        .sum().reset_index()
        .sort_values("LEAKAGE_AMOUNT_USD", ascending=False)
    )

    top_cat = cat_df.iloc[0]["CATEGORY"] if not cat_df.empty else "-"
    top_cat_pct = round(cat_df.iloc[0]["LEAKAGE_AMOUNT_USD"] / total_leakage * 100) if total_leakage else 0
    top_cust = cust_df.iloc[-1]["CUSTOMER_NAME"] if not cust_df.empty else "-"
    top_cust_amt = cust_df.iloc[-1]["LEAKAGE_AMOUNT_USD"] if not cust_df.empty else 0

    kpi_summary = dict(
        total_leakage=total_leakage, portfolio_val=portfolio_val,
        leakage_rate=leakage_rate, total_events=total_events,
        critical_count=critical_count, high_count=high_count,
        recovery_est=recovery_est, top_cat=top_cat, top_cat_pct=top_cat_pct,
        top_cust=top_cust, top_cust_amt=top_cust_amt,
    )

    # ── TOP NAV ────────────────────────────────────────────────
    st.markdown(f"""
    <div class="topnav">
        <div class="tn-brand">
            <div class="tn-logo">CI</div>
            <span class="tn-name">Contract Revenue Leakage Intelligence</span>
            <span class="tn-sep">·</span>
        </div>
        <div class="tn-right">
            <span class="tn-ts">{now_str}</span>
            <div class="tn-divider"></div>
            <span class="tn-live"><span class="live-dot"></span>Live</span>
        </div>
    </div>
    <div style="height:6px"></div>
    """, unsafe_allow_html=True)

    # ── HERO CARDS ─────────────────────────────────────────────
    st.markdown("""<div class="sec-hd"><span class="sec-hd-label">Executive Summary</span><div class="sec-hd-line"></div></div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="hero-grid">
        <div class="hero-card hc-danger">
            <div class="hc-eyebrow"><div class="hc-dot d-red"></div><span class="hc-label">Total Revenue at Risk</span></div>
            <div class="hc-main-val v-red">${total_leakage/1e3:,.0f}K</div>
            <div class="hc-desc">
                <span class="hc-tag ht-red">{leakage_rate}% of portfolio</span>
                <span style="color:var(--tx-4)">·</span>
                <span>${portfolio_val/1e6:.1f}M active contracts</span>
            </div>
            <div class="hc-mini-row">
                <div class="hc-mini"><div class="hcm-val" style="color:var(--red)">{critical_count}</div><div class="hcm-lbl">Critical</div></div>
                <div class="hc-mini"><div class="hcm-val" style="color:var(--amb)">{high_count}</div><div class="hcm-lbl">High</div></div>
                <div class="hc-mini"><div class="hcm-val" style="color:var(--vio)">{medium_count}</div><div class="hcm-lbl">Medium</div></div>
                <div class="hc-mini"><div class="hcm-val" style="color:var(--grn)">{low_count}</div><div class="hcm-lbl">Low</div></div>
            </div>
        </div>
        <div class="hero-card hc-success">
            <div class="hc-eyebrow"><div class="hc-dot d-grn"></div><span class="hc-label">Recovery Potential</span></div>
            <div class="hc-main-val v-grn">${recovery_est/1e3:,.0f}K</div>
            <div class="hc-desc">
                <span class="hc-tag ht-grn">85% hist. rate</span>
                <span style="color:var(--tx-4)">·</span>
                <span>Act on active alerts</span>
            </div>
            <div class="hc-mini-row" style="grid-template-columns:1fr 1fr; margin-top:22px;">
                <div class="hc-mini"><div class="hcm-val">{total_events}</div><div class="hcm-lbl">Issues</div></div>
                <div class="hc-mini"><div class="hcm-val">{total_contracts}</div><div class="hcm-lbl">Contracts</div></div>
            </div>
        </div>
        <div class="hero-card hc-neutral">
            <div class="hc-eyebrow"><div class="hc-dot d-acc"></div><span class="hc-label">Portfolio Health Score</span></div>
            <div class="hc-main-val v-acc">{max(0, round(100 - leakage_rate, 1))}%</div>
            <div class="hc-desc">
                <span class="hc-tag ht-acc">{100 - round(leakage_rate)}/100 score</span>
                <span style="color:var(--tx-4)">·</span>
                <span>${portfolio_val/1e6:.1f}M annual value</span>
            </div>
            <div class="hc-mini-row" style="grid-template-columns:1fr 1fr; margin-top:22px;">
                <div class="hc-mini"><div class="hcm-val">${total_leakage/max(total_events,1):,.0f}</div><div class="hcm-lbl">Avg / Issue</div></div>
                <div class="hc-mini"><div class="hcm-val">{len(cat_df)}</div><div class="hcm-lbl">Categories</div></div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── ISSUES TABLE + CHARTS ──────────────────────────────────
    st.markdown("""<div class="sec-hd"><span class="sec-hd-label">Issues &amp; Analytics</span><div class="sec-hd-line"></div></div>""", unsafe_allow_html=True)

    body_l, body_r = st.columns([1.18, 0.82], gap="medium")

    with body_l:
        top_n = min(len(reg), 8)
        rows_html = ""
        for rank, (_, row) in enumerate(reg.head(8).iterrows(), 1):
            sev = row["SEVERITY"].lower()
            calc = str(row.get("CALCULATION_DETAIL", ""))
            calc = (calc[:200] + "...") if len(calc) > 200 else calc
            r_cls = {1: "r1", 2: "r2", 3: "r3"}.get(rank, "")
            a_cls = "a-crit" if sev == "critical" else ("a-high" if sev == "high" else "")
            cat = row.get("CATEGORY", "")
            cat_c = CATEGORY_COLORS.get(cat, "#6b7280")
            rgb = ','.join(str(int(cat_c.lstrip('#')[i:i+2], 16)) for i in (0, 2, 4))
            rows_html += f"""<tr>
                <td><div class="rank-badge {r_cls}">{rank}</div></td>
                <td><div class="cust-name">{row['CUSTOMER_NAME']}</div><div class="cust-ind">{row.get('INDUSTRY','')}</div></td>
                <td><div class="rule-name">{row['FRIENDLY_RULE']}</div><div class="rule-calc">{calc}</div></td>
                <td><span class="cat-tag" style="background:rgba({rgb},0.08);border-color:rgba({rgb},0.22);color:{cat_c};">{cat}</span></td>
                <td class="amt-cell {a_cls}">${row['LEAKAGE_AMOUNT_USD']:,.0f}</td>
                <td style="text-align:right"><span class="sev-pill sp-{sev}">{row['SEVERITY']}</span></td>
            </tr>"""

        st.markdown(f"""
        <div class="panel">
            <div class="panel-head">
                <div class="ph-icon phi-red">!</div>
                <div><div class="ph-title">Top Issues by Revenue Impact</div>
                <div class="ph-sub">Ranked by financial exposure</div></div>
                <span class="ph-badge">Top {top_n}</span>
            </div>
            <div class="iss-wrap" style="padding-top:12px">
                <table class="iss-tbl">
                <thead><tr><th style="width:34px">#</th><th>Account</th><th>Issue</th><th>Category</th><th class="ta-r">Exposure</th><th class="ta-r">Severity</th></tr></thead>
                <tbody>{rows_html}</tbody>
                </table>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with body_r:
        if not cat_df.empty:
            pie_colors = [CATEGORY_COLORS.get(c, "#6b7280") for c in cat_df["CATEGORY"]]
            fig_pie = go.Figure(go.Pie(
                labels=cat_df["CATEGORY"], values=cat_df["LEAKAGE_AMOUNT_USD"],
                hole=0.66, marker=dict(colors=pie_colors, line=dict(color="#ffffff", width=3)),
                textinfo="percent", textfont=dict(size=10, family="DM Sans", color="#2d3142"),
                hovertemplate="<b>%{label}</b><br>$%{value:,.0f}<br>%{percent}<extra></extra>",
                pull=[0.05 if i == 0 else 0 for i in range(len(cat_df))],
            ))
            fig_pie.add_annotation(text=f'<b>${total_leakage/1e3:.0f}K</b>', x=0.5, y=0.58, showarrow=False,
                                   xref="paper", yref="paper", font=dict(size=16, family="DM Serif Display", color="#0f1117"))
            fig_pie.add_annotation(text="at risk", x=0.5, y=0.43, showarrow=False,
                                   xref="paper", yref="paper", font=dict(size=10, family="DM Sans", color="#9ca3af"))
            fig_pie.update_layout(height=230, margin=dict(l=0, r=0, t=10, b=0),
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  showlegend=True, legend=dict(font=dict(size=10, family="DM Sans", color="#2d3142"),
                                  bgcolor="rgba(0,0,0,0)", x=1.0, y=0.5, xanchor="left"))
            st.markdown("""<div class="panel" style="margin-bottom:12px"><div class="panel-head">
                <div class="ph-icon phi-vio">O</div><div><div class="ph-title">Category Breakdown</div>
                <div class="ph-sub">Leakage by issue type</div></div></div></div>""", unsafe_allow_html=True)
            st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})

        if not cust_df.empty:
            fig_bar = go.Figure(go.Bar(
                x=cust_df["LEAKAGE_AMOUNT_USD"], y=cust_df["CUSTOMER_NAME"], orientation="h",
                marker=dict(color=cust_df["LEAKAGE_AMOUNT_USD"],
                            colorscale=[[0, "rgba(37,99,235,0.2)"], [0.5, "rgba(217,119,6,0.6)"], [1, "rgba(220,38,38,0.85)"]]),
                text=[f"${v/1e3:.0f}K" for v in cust_df["LEAKAGE_AMOUNT_USD"]],
                textposition="outside", textfont=dict(size=10, family="DM Mono", color="#6b7280"),
            ))
            fig_bar.update_layout(height=210, margin=dict(l=0, r=55, t=10, b=0),
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                                             range=[0, cust_df["LEAKAGE_AMOUNT_USD"].max()*1.30]),
                                  yaxis=dict(showgrid=False, tickfont=dict(size=10, family="DM Sans", color="#6b7280")),
                                  showlegend=False, bargap=0.35)
            st.markdown("""<div style="margin-bottom:6px"><span style="font-size:11px;font-weight:600;color:#6b7280;
                font-family:'DM Mono',monospace;letter-spacing:0.06em;text-transform:uppercase;">Top Accounts</span></div>""", unsafe_allow_html=True)
            st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

    # ── CATEGORY BREAKDOWN + RULE CHART ────────────────────────
    st.markdown("""<div class="sec-hd"><span class="sec-hd-label">Category Breakdown</span><div class="sec-hd-line"></div></div>""", unsafe_allow_html=True)

    cat_left, cat_right = st.columns([1.15, 0.85], gap="medium")

    with cat_left:
        bars_html = ""
        for _, row in cat_df.iterrows():
            pct = (row["LEAKAGE_AMOUNT_USD"] / total_leakage * 100) if total_leakage else 0
            color = CATEGORY_COLORS.get(row["CATEGORY"], "#6b7280")
            bars_html += f"""<div class="bar-row">
                <span class="bar-label">{row['CATEGORY']}</span>
                <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:linear-gradient(90deg,{color}88,{color}33)"></div></div>
                <span class="bar-amount">${row['LEAKAGE_AMOUNT_USD']/1e3:.0f}K</span>
                <span class="bar-pct">{pct:.0f}%</span>
            </div>"""
        st.markdown(f"""
        <div class="panel">
            <div class="panel-head"><div class="ph-icon phi-amb">%</div>
            <div><div class="ph-title">Leakage by Category</div><div class="ph-sub">Proportional share of total exposure</div></div>
            <span class="ph-badge">{len(cat_df)} categories</span></div>
            <div class="panel-body">{bars_html}</div>
        </div>""", unsafe_allow_html=True)

    with cat_right:
        if not rule_df.empty:
            rule_colors = ["#dc2626", "#d97706", "#d97706", "#7c3aed", "#2563eb", "#059669"]
            fig_rule = go.Figure(go.Bar(
                x=rule_df["LEAKAGE_AMOUNT_USD"], y=rule_df["FRIENDLY_RULE"], orientation="h",
                marker=dict(color=rule_colors[:len(rule_df)], opacity=0.75),
                text=[f"${v/1e3:.0f}K" for v in rule_df["LEAKAGE_AMOUNT_USD"]],
                textposition="outside", textfont=dict(size=10, family="DM Mono", color="#6b7280"),
            ))
            fig_rule.update_layout(height=250, margin=dict(l=0, r=55, t=10, b=0),
                                   paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                   xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.05)", zeroline=False,
                                              showticklabels=False, range=[0, rule_df["LEAKAGE_AMOUNT_USD"].max()*1.32]),
                                   yaxis=dict(showgrid=False, tickfont=dict(size=10.5, family="DM Sans", color="#2d3142")),
                                   showlegend=False, bargap=0.32)
            st.markdown("""<div style="margin-bottom:6px"><span style="font-size:11px;font-weight:600;color:#6b7280;
                font-family:'DM Mono',monospace;text-transform:uppercase;">Leakage by Detection Rule</span></div>""", unsafe_allow_html=True)
            st.plotly_chart(fig_rule, use_container_width=True, config={"displayModeBar": False})

    # ── RECOMMENDED ACTIONS ────────────────────────────────────
    st.markdown("""<div class="sec-hd"><span class="sec-hd-label">Recommended Actions</span><div class="sec-hd-line"></div></div>""", unsafe_allow_html=True)

    seen_rules, actions = [], []
    for _, row in reg.iterrows():
        rule = row["RULE_ID"]
        if rule not in seen_rules and rule in ACTION_TEMPLATES:
            seen_rules.append(rule)
            actions.append((row["LEAKAGE_AMOUNT_USD"], rule, ACTION_TEMPLATES[rule]))
        if len(actions) >= 5:
            break

    if actions:
        act_cols = st.columns(len(actions), gap="small")
        for col, (amt, rule, tmpl) in zip(act_cols, actions):
            dv = f"${amt/1e3:.0f}K" if amt >= 1000 else f"${amt:.0f}"
            col.markdown(f"""
            <div class="action-card {tmpl['ac']}">
                <div class="ac-top"><span class="ac-pri {tmpl['pri']}">{tmpl['lbl']}</span><span class="ac-urg">{tmpl['urgency']}</span></div>
                <div class="ac-amount">{dv}</div>
                <div class="ac-title">{tmpl['title']}</div>
                <div class="ac-body">{tmpl['body']}</div>
            </div>""", unsafe_allow_html=True)

    # ── NARRATIVE INSIGHTS ─────────────────────────────────────
    st.markdown("""<div class="sec-hd"><span class="sec-hd-label">Business Narrative</span><div class="sec-hd-line"></div></div>""", unsafe_allow_html=True)

    i1, i2, i3, i4 = st.columns(4, gap="medium")
    with i1:
        st.markdown(f"""<div class="insight-card"><div class="ic-head"><div class="ic-dot" style="background:var(--red)"></div>
            <span class="ic-title">Biggest Loss Source</span></div><div class="ic-body"><span class="hi-b">{top_cat}</span> accounts for
            <span class="hi-r">{top_cat_pct}%</span> of all detected leakage.</div></div>""", unsafe_allow_html=True)
    with i2:
        st.markdown(f"""<div class="insight-card"><div class="ic-head"><div class="ic-dot" style="background:var(--amb)"></div>
            <span class="ic-title">Highest-Risk Account</span></div><div class="ic-body"><span class="hi-b">{top_cust}</span> holds the greatest
            exposure at <span class="hi-a">${top_cust_amt:,.0f}</span>.</div></div>""", unsafe_allow_html=True)
    with i3:
        st.markdown(f"""<div class="insight-card"><div class="ic-head"><div class="ic-dot" style="background:var(--grn)"></div>
            <span class="ic-title">Recovery Outlook</span></div><div class="ic-body">Acting on all <span class="hi-b">{total_events}</span> alerts
            could recover <span class="hi-g">${recovery_est:,.0f}</span> (85% rate).</div></div>""", unsafe_allow_html=True)
    with i4:
        alert_rate = round(critical_count / max(total_events, 1) * 100)
        st.markdown(f"""<div class="insight-card"><div class="ic-head"><div class="ic-dot" style="background:var(--vio)"></div>
            <span class="ic-title">Urgency Signal</span></div><div class="ic-body"><span class="hi-r">{alert_rate}%</span> of issues are
            <span class="hi-r">Critical</span>, requiring same-day action.</div></div>""", unsafe_allow_html=True)

    # ── DETAIL TABS ────────────────────────────────────────────
    st.markdown("""<div class="sec-hd"><span class="sec-hd-label">Full Data</span><div class="sec-hd-line"></div></div>""", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Issue Register", "Alert Log", "Credit Notes"])

    with tab1:
        display = reg[[
            "CUSTOMER_NAME", "INDUSTRY", "CATEGORY", "FRIENDLY_RULE",
            "SEVERITY", "LEAKAGE_AMOUNT_USD", "EVENT_DATE", "CALCULATION_DETAIL",
        ]].rename(columns={
            "CUSTOMER_NAME": "Account", "INDUSTRY": "Industry", "CATEGORY": "Category",
            "FRIENDLY_RULE": "Issue", "SEVERITY": "Severity",
            "LEAKAGE_AMOUNT_USD": "Revenue at Risk", "EVENT_DATE": "Date",
            "CALCULATION_DETAIL": "Detail"
        })
        display["Detail"] = display["Detail"].astype(str).str[:200]
        st.dataframe(display, use_container_width=True, height=320)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total at Risk", f"${display['Revenue at Risk'].sum():,.0f}")
        m2.metric("Issues Shown", len(display))
        m3.metric("Critical", critical_count)
        m4.metric("High", high_count)
        m5.metric("Med + Low", medium_count + low_count)

    with tab2:
        alerts = load_alerts(current_mode)
        if not alerts.empty:
            a1, a2, a3 = st.columns(3)
            a1.metric("Total Alerts", len(alerts))
            a2.metric("Pending", int((alerts["STATUS"] == "PENDING").sum()))
            a3.metric("Value Notified", f"${alerts['LEAKAGE_AMOUNT_USD'].sum():,.0f}")
            st.dataframe(alerts, use_container_width=True, height=260)
        else:
            st.info("No alerts yet. Run the detection pipeline from the sidebar.")

    with tab3:
        credits = load_credits(current_mode)
        if not credits.empty:
            x1, x2, x3 = st.columns(3)
            x1.metric("Credit Notes", len(credits))
            x2.metric("Total Credit Value", f"${credits['CREDIT_AMOUNT_USD'].sum():,.0f}")
            x3.metric("Pending ERP Sync", int((credits["ERP_SYNC_STATUS"] == "PENDING").sum()))
            st.dataframe(credits, use_container_width=True, height=260)
        else:
            st.info("Credit notes auto-generate for Critical issues over $500.")

    # ── FOOTER ─────────────────────────────────────────────────
    st.markdown(
        f'<div class="ci-footer">Contract Intelligence Platform · {now_str} · '
        f'6-rule detection engine · Snowflake Native App · Cortex AI</div>',
        unsafe_allow_html=True,
    )

    # ── CORTEX AI CHATBOT ──────────────────────────────────────
    @st.dialog("Cortex AI Assistant", width="large")
    def cortex_chat_dialog():
        st.markdown("**Cortex AI** - Ask about your portfolio, leakage rules, or recommended actions.")

        if not st.session_state.chat_history:
            st.info("I have full visibility into your live portfolio. Ask me anything about revenue leakage, detection rules, or recommended actions.")
            st.caption("Try: " + " | ".join(CHAT_SUGGESTIONS[:3]))

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        with st.form(key="cortex_chat_form", clear_on_submit=True):
            user_input = st.text_input("Your question", placeholder="Ask about leakage, rules, customers...", label_visibility="collapsed")
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                send = st.form_submit_button("Send", use_container_width=True)
            with c2:
                clear = st.form_submit_button("Clear chat", use_container_width=True)
            with c3:
                close = st.form_submit_button("Close", use_container_width=True)

        if send and user_input.strip():
            st.session_state.chat_history.append({"role": "user", "content": user_input.strip()})
            with st.spinner("Cortex is thinking..."):
                reply = call_cortex(user_input.strip(), kpi_summary)
            st.session_state.chat_history.append({"role": "assistant", "content": reply})
            st.rerun()
        if clear:
            st.session_state.chat_history = []
            st.rerun()
        if close:
            st.session_state.chat_open = False
            st.rerun()

    if st.button("AI Assistant", key="chat_fab_trigger"):
        st.session_state.chat_open = True
        st.rerun()

    if st.session_state.chat_open:
        cortex_chat_dialog()
