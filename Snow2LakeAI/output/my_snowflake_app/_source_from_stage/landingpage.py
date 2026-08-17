# Contract Intelligence Native App landing page with Permissions SDK integration
# Co-authored with CoCo
# ================================================================
# CONTRACT INTELLIGENCE — LANDING PAGE (Premium Enterprise Redesign)
# Supports 3 data modes:
#   DEMO → provider's pre-extracted sample contracts
#   CONSUMER_TABLES → consumer binds their own structured tables
#   CONSUMER_PDF → consumer uploads PDFs, app runs AI pipeline
# Includes: Permissions SDK flows, column mapping UI
# ================================================================

import streamlit as st
import snowflake.permissions as permissions
from snowflake.snowpark.context import get_active_session

# ================================================================
# DESIGN SYSTEM — PREMIUM ENTERPRISE LIGHT THEME
# ================================================================
_CSS = """
<style>
/* Using system font stack — no external network calls */

:root {
    --bg-page:     #F7F9FC;
    --bg-card:     #FFFFFF;
    --bg-elevated: #FFFFFF;
    --bg-muted:    #F1F5F9;
    --bg-hover:    #F8FAFC;

    --primary:    #29B5E8;
    --primary-dk: #1A9FD0;
    --primary-lt: #E8F7FD;
    --primary-bg: rgba(41,181,232,0.08);
    --primary-bd: rgba(41,181,232,0.25);

    --secondary:    #2563EB;
    --secondary-lt: #EFF6FF;
    --secondary-bg: rgba(37,99,235,0.08);
    --secondary-bd: rgba(37,99,235,0.20);

    --accent:    #6D5EF5;
    --accent-lt: #F5F3FF;
    --accent-bg: rgba(109,94,245,0.08);
    --accent-bd: rgba(109,94,245,0.20);

    --success:    #10B981;
    --success-lt: #ECFDF5;
    --success-bg: rgba(16,185,129,0.08);
    --success-bd: rgba(16,185,129,0.20);

    --warning:    #F59E0B;
    --warning-lt: #FFFBEB;
    --warning-bg: rgba(245,158,11,0.08);
    --warning-bd: rgba(245,158,11,0.20);

    --critical:    #EF4444;
    --critical-lt: #FEF2F2;
    --critical-bg: rgba(239,68,68,0.08);
    --critical-bd: rgba(239,68,68,0.20);

    --tx-0: #1F2937;
    --tx-1: #374151;
    --tx-2: #6B7280;
    --tx-3: #9CA3AF;
    --tx-4: #D1D5DB;

    --bd-0: rgba(0,0,0,0.04);
    --bd-1: #E5E7EB;
    --bd-2: rgba(0,0,0,0.10);

    --sh-xs: 0 1px 3px rgba(0,0,0,0.05);
    --sh-sm: 0 2px 8px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.04);
    --sh-md: 0 4px 16px rgba(0,0,0,0.08), 0 2px 6px rgba(0,0,0,0.04);
    --sh-lg: 0 8px 32px rgba(0,0,0,0.10), 0 2px 10px rgba(0,0,0,0.05);
    --sh-xl: 0 16px 48px rgba(0,0,0,0.12), 0 4px 16px rgba(0,0,0,0.06);

    --r-sm:  6px;
    --r-md:  10px;
    --r-lg:  14px;
    --r-xl:  18px;
    --r-2xl: 24px;
    --r-full: 999px;
}

*, *::before, *::after { box-sizing: border-box; }

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: var(--bg-page) !important;
}

.block-container {
    padding: 0 3rem 6rem !important;
    max-width: 1280px !important;
    margin: 0 auto !important;
}

#MainMenu, footer, header { visibility: hidden !important; }
.stDeployButton { display: none !important; }

/* ── TOP NAV BAR ─────────────────────────────────────────── */
.lp-nav {
    position: sticky;
    top: 0;
    z-index: 200;
    background: rgba(247,249,252,0.92);
    backdrop-filter: blur(20px) saturate(1.8);
    border-bottom: 1px solid var(--bd-1);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 3rem;
    height: 58px;
    margin: 0 -3rem;
    box-shadow: 0 1px 0 var(--bd-1), 0 2px 8px rgba(0,0,0,0.04);
}
.lp-nav-brand {
    display: flex;
    align-items: center;
    gap: 12px;
}
.lp-nav-logo {
    width: 34px;
    height: 34px;
    border-radius: var(--r-md);
    background: linear-gradient(135deg, var(--secondary) 0%, var(--primary) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    color: #fff;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(41,181,232,0.35);
}
.lp-nav-name {
    font-size: 15px;
    font-weight: 700;
    color: var(--tx-0);
    letter-spacing: -0.01em;
}
.lp-nav-sub {
    font-size: 11px;
    color: var(--tx-3);
    font-weight: 400;
    margin-left: 2px;
}
.lp-nav-right {
    display: flex;
    align-items: center;
    gap: 16px;
}
.lp-nav-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--accent-lt);
    border: 1px solid var(--accent-bd);
    border-radius: var(--r-full);
    padding: 4px 12px;
    font-size: 10.5px;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
.lp-nav-badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    animation: pulse-dot 2s ease-in-out infinite;
}
@keyframes pulse-dot {
    0%,100% { opacity:1; transform:scale(1); }
    50%      { opacity:0.4; transform:scale(0.75); }
}
.lp-nav-powered {
    font-size: 11px;
    color: var(--tx-3);
    display: flex;
    align-items: center;
    gap: 6px;
}
.lp-nav-sf-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: var(--primary-lt);
    border: 1px solid var(--primary-bd);
    border-radius: var(--r-full);
    padding: 3px 10px;
    font-size: 10px;
    font-weight: 700;
    color: var(--primary-dk);
    letter-spacing: 0.04em;
}

/* ── HERO SECTION ────────────────────────────────────────── */
.lp-hero {
    text-align: center;
    padding: 5rem 2rem 3.5rem;
    position: relative;
}
.lp-hero::before {
    content: '';
    position: absolute;
    top: 0; left: 50%;
    transform: translateX(-50%);
    width: 900px;
    height: 480px;
    background: radial-gradient(ellipse 70% 50% at 50% 0%,
        rgba(41,181,232,0.10) 0%,
        rgba(109,94,245,0.06) 50%,
        transparent 100%);
    pointer-events: none;
}
.lp-hero-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--secondary-lt);
    border: 1px solid var(--secondary-bd);
    border-radius: var(--r-full);
    padding: 6px 16px;
    font-size: 11px;
    font-weight: 700;
    color: var(--secondary);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: 1.75rem;
}
.lp-hero-eyebrow-icon { font-size: 13px; }
.lp-hero-title {
    font-size: clamp(2.6rem, 5.5vw, 4rem);
    font-weight: 800;
    color: var(--tx-0);
    letter-spacing: -0.03em;
    line-height: 1.08;
    margin: 0 0 0.6rem;
}
.lp-hero-title span {
    background: linear-gradient(135deg, var(--secondary) 0%, var(--primary) 55%, var(--accent) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.lp-hero-subtitle {
    font-size: 1.2rem;
    font-weight: 500;
    color: var(--tx-2);
    line-height: 1.55;
    margin: 0 auto 0.9rem;
    max-width: 620px;
}
.lp-hero-desc {
    font-size: 0.97rem;
    color: var(--tx-3);
    line-height: 1.7;
    max-width: 580px;
    margin: 0 auto 2.5rem;
}
.lp-hero-cta {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background: linear-gradient(135deg, var(--secondary) 0%, var(--primary) 100%);
    color: #ffffff;
    border: none;
    border-radius: var(--r-lg);
    padding: 15px 36px;
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    cursor: pointer;
    box-shadow: 0 4px 20px rgba(41,181,232,0.40), 0 1px 4px rgba(0,0,0,0.12);
    transition: transform 0.2s ease, box-shadow 0.2s ease, filter 0.2s ease;
    text-decoration: none;
}
.lp-hero-cta:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(41,181,232,0.50), 0 2px 8px rgba(0,0,0,0.14);
    filter: brightness(1.05);
}
.lp-hero-cta-arrow { font-size: 1.15rem; }
.lp-hero-stats {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 2.5rem;
    margin-top: 3rem;
    padding-top: 2rem;
    border-top: 1px solid var(--bd-1);
}
.lp-hero-stat { text-align: center; }
.lp-hero-stat-val {
    font-size: 1.6rem;
    font-weight: 800;
    color: var(--tx-0);
    letter-spacing: -0.03em;
    line-height: 1;
}
.lp-hero-stat-lbl {
    font-size: 11px;
    color: var(--tx-3);
    font-weight: 500;
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.lp-hero-stat-divider {
    width: 1px;
    height: 36px;
    background: var(--bd-1);
}

/* ── KPI GRID ─────────────────────────────────────────────── */
.kpi-section {
    margin: 0.5rem 0 2rem;
}
.kpi-section-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--tx-3);
    font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.kpi-section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--bd-1);
}
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 14px;
}
@media (max-width: 1100px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px)  { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }

.kpi-card {
    background: var(--bg-card);
    border: 1px solid var(--bd-1);
    border-radius: var(--r-xl);
    padding: 20px 18px 16px;
    box-shadow: var(--sh-sm);
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    cursor: default;
}
.kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: var(--sh-md);
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: var(--r-xl) var(--r-xl) 0 0;
}
.kpi-card.k-critical::before { background: var(--critical); }
.kpi-card.k-warning::before  { background: var(--warning); }
.kpi-card.k-primary::before  { background: var(--primary); }
.kpi-card.k-secondary::before { background: var(--secondary); }
.kpi-card.k-success::before  { background: var(--success); }
.kpi-card.k-accent::before   { background: var(--accent); }

.kpi-card::after {
    content: '';
    position: absolute;
    bottom: -20px; right: -20px;
    width: 80px; height: 80px;
    border-radius: 50%;
    opacity: 0.06;
}
.kpi-card.k-critical::after  { background: var(--critical); }
.kpi-card.k-warning::after   { background: var(--warning); }
.kpi-card.k-primary::after   { background: var(--primary); }
.kpi-card.k-secondary::after { background: var(--secondary); }
.kpi-card.k-success::after   { background: var(--success); }
.kpi-card.k-accent::after    { background: var(--accent); }

.kpi-icon-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
}
.kpi-icon {
    width: 36px;
    height: 36px;
    border-radius: var(--r-md);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
}
.ki-critical { background: var(--critical-lt); }
.ki-warning  { background: var(--warning-lt);  }
.ki-primary  { background: var(--primary-lt);  }
.ki-secondary{ background: var(--secondary-lt);}
.ki-success  { background: var(--success-lt);  }
.ki-accent   { background: var(--accent-lt);   }

.kpi-trend {
    font-size: 9.5px;
    font-weight: 700;
    font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    padding: 2px 7px;
    border-radius: var(--r-full);
    letter-spacing: 0.04em;
}
.kt-up   { background: var(--critical-bg); color: var(--critical); border: 1px solid var(--critical-bd); }
.kt-down { background: var(--success-bg);  color: var(--success);  border: 1px solid var(--success-bd); }
.kt-neu  { background: var(--bg-muted);    color: var(--tx-3);     border: 1px solid var(--bd-1); }

.kpi-value {
    font-size: 1.85rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1.05;
    margin-bottom: 4px;
    font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    color: var(--tx-0);
}
.kpi-value.v-critical  { color: var(--critical); }
.kpi-value.v-warning   { color: var(--warning);  }
.kpi-value.v-primary   { color: var(--primary);  }
.kpi-value.v-secondary { color: var(--secondary);}
.kpi-value.v-success   { color: var(--success);  }
.kpi-value.v-accent    { color: var(--accent);   }

.kpi-label {
    font-size: 10.5px;
    font-weight: 600;
    color: var(--tx-3);
    text-transform: uppercase;
    letter-spacing: 0.07em;
}

/* ── FEATURE CARDS ───────────────────────────────────────── */
.feat-section {
    margin: 2.5rem 0 3rem;
}
.feat-section-header {
    text-align: center;
    margin-bottom: 2.5rem;
}
.feat-section-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--primary);
    margin-bottom: 0.75rem;
    background: var(--primary-bg);
    border: 1px solid var(--primary-bd);
    border-radius: var(--r-full);
    padding: 4px 14px;
}
.feat-section-title {
    font-size: 1.9rem;
    font-weight: 800;
    color: var(--tx-0);
    letter-spacing: -0.025em;
    margin: 0 0 0.5rem;
}
.feat-section-sub {
    font-size: 1rem;
    color: var(--tx-2);
    max-width: 520px;
    margin: 0 auto;
    line-height: 1.6;
}
.feat-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
}
@media (max-width: 900px) { .feat-grid { grid-template-columns: 1fr; } }

.feat-card {
    background: var(--bg-card);
    border: 1px solid var(--bd-1);
    border-radius: var(--r-2xl);
    padding: 28px 26px 24px;
    box-shadow: var(--sh-sm);
    position: relative;
    overflow: hidden;
    transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
}
.feat-card:hover {
    transform: translateY(-4px);
    box-shadow: var(--sh-lg);
}
.feat-card.fc-extract:hover { border-color: var(--primary-bd); }
.feat-card.fc-detect:hover  { border-color: var(--secondary-bd); }
.feat-card.fc-protect:hover { border-color: var(--accent-bd); }

.feat-card-bg {
    position: absolute;
    top: 0; right: 0;
    width: 180px; height: 180px;
    border-radius: 0 var(--r-2xl) 0 50%;
    opacity: 0.04;
}
.fc-extract .feat-card-bg  { background: var(--primary); }
.fc-detect  .feat-card-bg  { background: var(--secondary); }
.fc-protect .feat-card-bg  { background: var(--accent); }

.feat-card-icon-wrap {
    width: 52px;
    height: 52px;
    border-radius: var(--r-lg);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    margin-bottom: 18px;
    position: relative;
    z-index: 1;
}
.fc-extract .feat-card-icon-wrap  { background: var(--primary-lt);   box-shadow: 0 0 0 6px rgba(41,181,232,0.08); }
.fc-detect  .feat-card-icon-wrap  { background: var(--secondary-lt);  box-shadow: 0 0 0 6px rgba(37,99,235,0.08); }
.fc-protect .feat-card-icon-wrap  { background: var(--accent-lt);     box-shadow: 0 0 0 6px rgba(109,94,245,0.08); }

.feat-card-step {
    position: absolute;
    top: 22px;
    right: 22px;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 800;
    font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    background: var(--bg-muted);
    border: 1px solid var(--bd-1);
    color: var(--tx-3);
    z-index: 2;
}

.feat-card-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: var(--tx-0);
    letter-spacing: -0.02em;
    margin: 0 0 4px;
    position: relative;
    z-index: 1;
}
.feat-card-desc {
    font-size: 0.88rem;
    color: var(--tx-2);
    line-height: 1.6;
    margin: 0 0 20px;
    position: relative;
    z-index: 1;
}
.feat-tag-row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    position: relative;
    z-index: 1;
}
.feat-tag {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10.5px;
    font-weight: 600;
    padding: 4px 11px;
    border-radius: var(--r-full);
    border: 1px solid;
    letter-spacing: 0.02em;
    transition: transform 0.15s;
}
.feat-tag:hover { transform: scale(1.04); }
.ft-extract { background: var(--primary-bg);   border-color: var(--primary-bd);   color: var(--primary-dk); }
.ft-detect  { background: var(--secondary-bg);  border-color: var(--secondary-bd);  color: var(--secondary); }
.ft-protect { background: var(--accent-bg);     border-color: var(--accent-bd);     color: var(--accent); }

/* ── TRUST FOOTER STRIP ──────────────────────────────────── */
.trust-strip {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 2.5rem;
    padding: 1.75rem 2rem;
    background: var(--bg-card);
    border: 1px solid var(--bd-1);
    border-radius: var(--r-2xl);
    box-shadow: var(--sh-sm);
    margin-top: 1rem;
    margin-bottom: 2rem;
    flex-wrap: wrap;
}
.trust-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    font-weight: 600;
    color: var(--tx-2);
}
.trust-icon {
    font-size: 16px;
}
.trust-divider {
    width: 1px;
    height: 24px;
    background: var(--bd-1);
}

/* ── CTA BUTTON (Streamlit override) ─────────────────────── */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #2563EB 0%, #29B5E8 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 14px 40px !important;
    font-size: 1.02rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em !important;
    box-shadow: 0 4px 20px rgba(41,181,232,0.38), 0 1px 4px rgba(0,0,0,0.12) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
    min-height: 52px !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 30px rgba(41,181,232,0.50), 0 2px 8px rgba(0,0,0,0.14) !important;
}

/* ── SECTION DIVIDER ─────────────────────────────────────── */
.sec-divider {
    display: flex;
    align-items: center;
    gap: 14px;
    margin: 2rem 0 1.5rem;
}
.sec-divider-line { flex: 1; height: 1px; background: var(--bd-1); }
.sec-divider-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--tx-3);
    font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    white-space: nowrap;
}

/* ── MODE CARDS (hidden settings panel) ──────────────────── */
.mode-card {
    background: var(--bg-card);
    border: 1.5px solid var(--bd-1);
    border-radius: var(--r-xl);
    padding: 1.4rem;
    margin-bottom: 1rem;
    transition: border-color 0.2s, box-shadow 0.2s;
    box-shadow: var(--sh-xs);
}
.mode-card:hover {
    border-color: var(--primary-bd);
    box-shadow: var(--sh-sm);
}
.mode-card.active {
    border-color: var(--primary);
    background: var(--primary-bg);
    box-shadow: 0 0 0 3px rgba(41,181,232,0.10);
}
.mode-title {
    color: var(--tx-0);
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 0.3rem;
}
.mode-desc {
    color: var(--tx-2);
    font-size: 0.87rem;
    line-height: 1.55;
}
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: var(--r-full);
    font-size: 0.72rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.badge-demo   { background: var(--success-bg);   color: var(--success);   border: 1px solid var(--success-bd); }
.badge-tables { background: var(--secondary-bg);  color: var(--secondary);  border: 1px solid var(--secondary-bd); }
.badge-pdf    { background: var(--critical-bg);   color: var(--critical);  border: 1px solid var(--critical-bd); }

/* ── STEP BOXES ──────────────────────────────────────────── */
.step-box {
    background: var(--bg-card);
    border: 1px solid var(--bd-1);
    border-radius: var(--r-lg);
    padding: 1.1rem 1.4rem;
    margin-bottom: 0.8rem;
    box-shadow: var(--sh-xs);
}
.step-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--secondary), var(--primary));
    color: white;
    font-size: 0.78rem;
    font-weight: 800;
    margin-right: 0.6rem;
}

/* ── BACK BUTTON ─────────────────────────────────────────── */
div[data-testid="stButton"] > button[kind="secondary"] {
    background: var(--bg-card) !important;
    color: var(--tx-1) !important;
    border: 1.5px solid var(--bd-1) !important;
    border-radius: var(--r-lg) !important;
    font-weight: 600 !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    border-color: var(--primary-bd) !important;
    box-shadow: var(--sh-sm) !important;
}
</style>
"""


def _get_session():
    return get_active_session()


def _get_mode(session):
    rows = session.sql(
        "SELECT setting_value FROM config.app_settings WHERE setting_key='DATA_MODE'"
    ).collect()
    return rows[0][0] if rows else "DEMO"


def _kpi_row(session):
    try:
        kpi = session.sql("SELECT * FROM gold.portfolio_kpi").collect()
        if not kpi or kpi[0]["TOTAL_LEAKAGE_EVENTS"] == 0:
            return None
        return kpi[0]
    except Exception:
        return None


def render():
    st.markdown(_CSS, unsafe_allow_html=True)
    session = _get_session()
    mode = _get_mode(session)

    # ── Top Navigation Bar ─────────────────────────────────────────
    st.markdown("""
    <div class="lp-nav">
        <div class="lp-nav-brand">
            <div class="lp-nav-logo">◈</div>
            <div>
                <div class="lp-nav-name">Contract Intelligence</div>
            </div>
        </div>
        <div class="lp-nav-right">
            <div class="lp-nav-badge">
                <div class="lp-nav-badge-dot"></div>
                Demo Environment
            </div>
            <div class="lp-nav-sf-pill">⬡ Snowflake Cortex AI</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Mode Toggle (DEMO / YOUR DATA) ────────────────────────────────
    toggle_col1, toggle_col2, toggle_col3 = st.columns([2, 3, 2])
    with toggle_col2:
        mode_label = "Your Data" if mode == "CONSUMER" else "Demo Mode"
        is_consumer = mode == "CONSUMER"
        toggled = st.toggle(
            f"**{mode_label}**  —  {'Connected to your stage' if is_consumer else 'Using sample data'}",
            value=is_consumer,
            key="mode_toggle"
        )
        if toggled and mode != "CONSUMER":
            session.sql("CALL config.switch_to_consumer()").collect()
            st.rerun()
        elif not toggled and mode != "DEMO":
            session.sql("CALL config.switch_to_demo()").collect()
            st.rerun()

    # ── Hero Section ───────────────────────────────────────────────
    st.markdown("""
    <div class="lp-hero">
        <div class="lp-hero-eyebrow">
            <span class="lp-hero-eyebrow-icon">🏆</span>
            AI-Powered Revenue Intelligence
        </div>
        <h1 class="lp-hero-title">
            <span>Contract Intelligence</span>
        </h1>
        <p class="lp-hero-subtitle">
            AI-powered Contract Intelligence &amp;<br>Revenue Leakage Prevention Platform
        </p>
        <p class="lp-hero-desc">
            Analyze contracts, detect revenue leakage, identify compliance risks, and
            visualize portfolio insights using Snowflake Cortex AI and intelligent
            rule-based analytics.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Single Primary CTA ─────────────────────────────────────────
    col_left, col_cta, col_right = st.columns([1, 1.4, 1])
    with col_cta:
        if st.button("View Demo Dashboard →", use_container_width=True, type="primary"):
            st.session_state.page = "dashboard"
            st.rerun()

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Trust Strip ────────────────────────────────────────────────
    st.markdown("""
    <div class="trust-strip">
        <div class="trust-item"><span class="trust-icon">🔒</span> SOC 2 Ready</div>
        <div class="trust-divider"></div>
        <div class="trust-item"><span class="trust-icon">❄️</span> Snowflake Native App</div>
        <div class="trust-divider"></div>
        <div class="trust-item"><span class="trust-icon">🤖</span> Cortex AI Powered</div>
        <div class="trust-divider"></div>
        <div class="trust-item"><span class="trust-icon">📄</span> PDF Extraction</div>
        <div class="trust-divider"></div>
        <div class="trust-item"><span class="trust-icon">⚡</span> Real-time Detection</div>
        <div class="trust-divider"></div>
        <div class="trust-item"><span class="trust-icon">📊</span> 6 Leakage Rules</div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI Cards (if results exist) ───────────────────────────────
    kpi = _kpi_row(session)
    if kpi:
        crit = kpi["CRITICAL_EVENTS"]
        high = kpi["HIGH_EVENTS"]
        total = kpi["TOTAL_LEAKAGE_USD"]
        events = kpi["TOTAL_LEAKAGE_EVENTS"]
        contracts = kpi["TOTAL_CONTRACTS"]

        st.markdown("""
        <div class="sec-divider">
            <div class="sec-divider-line"></div>
            <div class="sec-divider-label">Live Portfolio Metrics</div>
            <div class="sec-divider-line"></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi-card k-critical">
                <div class="kpi-icon-row">
                    <div class="kpi-icon ki-critical">💰</div>
                    <div class="kpi-trend kt-up">▲ LIVE</div>
                </div>
                <div class="kpi-value v-critical">${total:,.0f}</div>
                <div class="kpi-label">Total Leakage</div>
            </div>
            <div class="kpi-card k-secondary">
                <div class="kpi-icon-row">
                    <div class="kpi-icon ki-secondary">⚡</div>
                    <div class="kpi-trend kt-neu">EVENTS</div>
                </div>
                <div class="kpi-value v-secondary">{events}</div>
                <div class="kpi-label">Leakage Events</div>
            </div>
            <div class="kpi-card k-critical">
                <div class="kpi-icon-row">
                    <div class="kpi-icon ki-critical">🚨</div>
                    <div class="kpi-trend kt-up">CRITICAL</div>
                </div>
                <div class="kpi-value v-critical">{crit}</div>
                <div class="kpi-label">Critical</div>
            </div>
            <div class="kpi-card k-warning">
                <div class="kpi-icon-row">
                    <div class="kpi-icon ki-warning">⚠️</div>
                    <div class="kpi-trend kt-up">HIGH</div>
                </div>
                <div class="kpi-value v-warning">{high}</div>
                <div class="kpi-label">High Severity</div>
            </div>
            <div class="kpi-card k-primary">
                <div class="kpi-icon-row">
                    <div class="kpi-icon ki-primary">📋</div>
                    <div class="kpi-trend kt-neu">ACTIVE</div>
                </div>
                <div class="kpi-value v-primary">{contracts}</div>
                <div class="kpi-label">Contracts Affected</div>
            </div>
            <div class="kpi-card k-accent">
                <div class="kpi-icon-row">
                    <div class="kpi-icon ki-accent">🔧</div>
                    <div class="kpi-trend kt-down">CONFIG</div>
                </div>
                <div class="kpi-value v-accent" style="font-size:1.1rem;padding-top:0.35rem;">{mode}</div>
                <div class="kpi-label">Data Mode</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Feature Cards ──────────────────────────────────────────────
    st.markdown("""
    <div class="feat-section">
        <div class="feat-section-header">
            <div class="feat-section-eyebrow">⚙️ Platform Capabilities</div>
            <h2 class="feat-section-title">Everything You Need to Stop Revenue Leakage</h2>
            <p class="feat-section-sub">
                From contract ingestion to real-time risk monitoring — one unified AI platform
                built natively on Snowflake.
            </p>
        </div>
        <div class="feat-grid">
            <div class="feat-card fc-extract">
                <div class="feat-card-bg"></div>
                <div class="feat-card-step">01</div>
                <div class="feat-card-icon-wrap">🔍</div>
                <div class="feat-card-title">Extract</div>
                <div class="feat-card-desc">
                    Automatically parse and extract structured data from contract PDFs using
                    Snowflake Cortex Document AI and advanced OCR.
                </div>
                <div class="feat-tag-row">
                    <span class="feat-tag ft-extract">AI OCR</span>
                    <span class="feat-tag ft-extract">Cortex Document AI</span>
                    <span class="feat-tag ft-extract">Metadata Extraction</span>
                    <span class="feat-tag ft-extract">Clause Detection</span>
                </div>
            </div>
            <div class="feat-card fc-detect">
                <div class="feat-card-bg"></div>
                <div class="feat-card-step">02</div>
                <div class="feat-card-icon-wrap">🎯</div>
                <div class="feat-card-title">Detect</div>
                <div class="feat-card-desc">
                    Run intelligent rule-based and AI-assisted engines to surface billing
                    gaps, SLA breaches, and compliance risks across your portfolio.
                </div>
                <div class="feat-tag-row">
                    <span class="feat-tag ft-detect">Revenue Leakage Rules</span>
                    <span class="feat-tag ft-detect">Risk Scoring</span>
                    <span class="feat-tag ft-detect">Billing Validation</span>
                    <span class="feat-tag ft-detect">Compliance Analysis</span>
                </div>
            </div>
            <div class="feat-card fc-protect">
                <div class="feat-card-bg"></div>
                <div class="feat-card-step">03</div>
                <div class="feat-card-icon-wrap">🛡️</div>
                <div class="feat-card-title">Protect</div>
                <div class="feat-card-desc">
                    Visualize revenue health, get AI-powered recommendations, and generate
                    credit notes — all from a single executive dashboard.
                </div>
                <div class="feat-tag-row">
                    <span class="feat-tag ft-protect">Executive Dashboard</span>
                    <span class="feat-tag ft-protect">Portfolio KPIs</span>
                    <span class="feat-tag ft-protect">Revenue Insights</span>
                    <span class="feat-tag ft-protect">Smart Recommendations</span>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Data Source Configuration ─────────────────────────────────
    st.markdown("""
    <div class="sec-divider">
        <div class="sec-divider-line"></div>
        <div class="sec-divider-label">Data Source Configuration</div>
        <div class="sec-divider-line"></div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        active = "active" if mode == "DEMO" else ""
        st.markdown(f"""
        <div class="mode-card {active}">
            <span class="badge badge-demo">DEMO</span>
            <div class="mode-title">Sample Contracts</div>
            <div class="mode-desc">
                Explore 130+ real-format contract scenarios pre-extracted by the AI pipeline.
                No setup required — instant results to explore app capabilities.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Use Demo Data", use_container_width=True, key="btn_demo"):
            session.sql("CALL config.switch_to_demo()").collect()
            st.rerun()

    with c2:
        active = "active" if mode == "CONSUMER" else ""
        st.markdown(f"""
        <div class="mode-card {active}">
            <span class="badge badge-tables">YOUR DATA</span>
            <div class="mode-title">Enterprise Data Ingestion</div>
            <div class="mode-desc">
                Upload your data in native enterprise formats. The app processes
                PDFs, JSON, and CSV files directly from your Snowflake stage.
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Use My Data", use_container_width=True, key="btn_consumer", type="primary"):
            session.sql("CALL config.switch_to_consumer()").collect()
            st.rerun()

    st.markdown("---")

    # ── Consumer mode: show data ingestion panel ───────────────────
    if mode == "CONSUMER":
        _render_consumer_data_panel(session)


def _render_consumer_data_panel(session):
    """Render the 4 data source upload panel for Consumer mode."""

    st.markdown("### Your Data Stage")

    # ── Stage Configuration Status ─────────────────────────────────────
    # Consumer grants READ on their stage, then selects it here via dropdowns.
    try:
        rows = session.sql(
            "SELECT setting_value FROM config.app_settings WHERE setting_key='CONSUMER_STAGE'"
        ).collect()
        stage_bound = bool(rows and rows[0][0])
        current_stage = rows[0][0] if stage_bound else None
    except Exception:
        stage_bound = False
        current_stage = None

    if not stage_bound:
        st.warning(
            "No data stage is configured. Grant the app READ access to your stage, "
            "then select it below."
        )
        st.code(
            "GRANT USAGE ON DATABASE <db> TO APPLICATION CONTRACT_INTEL_APP;\n"
            "GRANT USAGE ON SCHEMA <db.schema> TO APPLICATION CONTRACT_INTEL_APP;\n"
            "GRANT READ ON STAGE <db.schema.stage> TO APPLICATION CONTRACT_INTEL_APP;",
            language="sql"
        )

        # Cascading dropdowns: Database → Schema → Stage
        try:
            dbs = session.sql("SHOW DATABASES").collect()
            db_names = [r["name"] for r in dbs if r["name"] not in ("CONTRACT_INTEL_APP", "SNOWFLAKE")]
        except Exception:
            db_names = []

        sel_db = st.selectbox("Database", options=db_names, index=None,
                              placeholder="Select database...", key="lp_sel_db")

        schema_names = []
        if sel_db:
            try:
                schemas = session.sql(f'SHOW SCHEMAS IN DATABASE "{sel_db}"').collect()
                schema_names = [r["name"] for r in schemas if r["name"] != "INFORMATION_SCHEMA"]
            except Exception:
                pass

        sel_schema = st.selectbox("Schema", options=schema_names, index=None,
                                  placeholder="Select schema...", key="lp_sel_schema")

        stage_names = []
        if sel_db and sel_schema:
            try:
                stages = session.sql(f'SHOW STAGES IN SCHEMA "{sel_db}"."{sel_schema}"').collect()
                stage_names = [r["name"] for r in stages if r.get("type", "INTERNAL") == "INTERNAL"]
            except Exception:
                pass

        sel_stage = st.selectbox("Stage", options=stage_names, index=None,
                                 placeholder="Select stage...", key="lp_sel_stage")

        if st.button("Save Data Stage", type="primary", key="btn_save_stage_lp"):
            if sel_db and sel_schema and sel_stage:
                fqn = f"{sel_db}.{sel_schema}.{sel_stage}"
                session.sql(f"CALL config.set_data_stage('{fqn}')").collect()
                st.success(f"Stage set to: {fqn}")
                st.rerun()
            else:
                st.error("Please select a database, schema, and stage.")
        return

    st.success(f"Data stage connected: **{current_stage}**. Upload your files, then run the pipeline.")

    st.markdown("---")
    st.markdown("### Upload Your Enterprise Data")
    st.markdown(
        "The app ingests data from **4 enterprise sources** in their native formats. "
        "Upload files to your stage, then click **Run Ingestion Pipeline** to process them."
    )

    # ── 4 Data Source Cards ────────────────────────────────────────
    d1, d2 = st.columns(2)

    with d1:
        st.markdown("""
        <div class="mode-card">
            <span class="badge badge-pdf">PDF</span>
            <div class="mode-title">Contract Details</div>
            <div class="mode-desc">
                Upload your contract documents as PDF files. Cortex AI extracts
                contract terms, SLA parameters, penalty rates, unit pricing,
                auto-renewal clauses, and risk indicators automatically.
            </div>
            <div style="margin-top:10px;font-size:0.82rem;color:var(--tx-3);">
                Stage path: <code>/contracts/*.pdf</code>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="mode-card">
            <span class="badge badge-tables">CSV</span>
            <div class="mode-title">ERP Data (Billing & Financials)</div>
            <div class="mode-desc">
                Upload billing transactions and financial records from your ERP
                system (SAP, Oracle, NetSuite, etc.) as CSV files. Used to detect
                billing mismatches and unbilled overages.
            </div>
            <div style="margin-top:10px;font-size:0.82rem;color:var(--tx-3);">
                Stage path: <code>/erp/*.csv</code>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with d2:
        st.markdown("""
        <div class="mode-card">
            <span class="badge badge-demo">JSON</span>
            <div class="mode-title">CRM Data (Customer Relationships)</div>
            <div class="mode-desc">
                Upload customer relationship data from your CRM (Salesforce,
                HubSpot, Dynamics, etc.) as JSON. Provides customer context for
                industry segmentation and portfolio analysis.
            </div>
            <div style="margin-top:10px;font-size:0.82rem;color:var(--tx-3);">
                Stage path: <code>/crm/*.json</code>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="mode-card">
            <span class="badge badge-demo">JSON</span>
            <div class="mode-title">OPS Data (Operational Events)</div>
            <div class="mode-desc">
                Upload operational events from monitoring systems, ticketing
                platforms, or IoT feeds as JSON. Used to detect SLA breaches,
                delivery failures, and quality defects.
            </div>
            <div style="margin-top:10px;font-size:0.82rem;color:var(--tx-3);">
                Stage path: <code>/ops/*.json</code>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Upload instructions ────────────────────────────────────────
    with st.expander("How to upload files to your stage"):
        st.markdown("""
**Option 1: Snowsight UI (drag-and-drop)**
1. Navigate to your stage in Snowsight
2. Drag and drop your files into the appropriate subfolder

**Option 2: SnowSQL / SQL**
```sql
-- Contract PDFs
PUT file:///path/to/contracts/*.pdf @your_stage/contracts/ AUTO_COMPRESS=FALSE;

-- CRM JSON files
PUT file:///path/to/crm_export.json @your_stage/crm/ AUTO_COMPRESS=FALSE;

-- ERP CSV files
PUT file:///path/to/billing_export.csv @your_stage/erp/ AUTO_COMPRESS=FALSE;

-- OPS JSON files
PUT file:///path/to/events_export.json @your_stage/ops/ AUTO_COMPRESS=FALSE;
```
        """)

    with st.expander("Expected data fields per source"):
        st.markdown("""
| Source | Format | Key Fields |
|--------|--------|-----------|
| **Contracts** | PDF | Contract ID, customer, annual value, penalty %, SLA hours, unit rate, overage rate, start/end dates |
| **CRM** | JSON | `customer_id`, `customer_name`, `industry`, `segment`, `region`, `country` |
| **ERP** | CSV | `transaction_id`, `contract_id`, `customer_id`, `billed_amount`, `unit_price`, `quantity`, `payment_status` |
| **OPS** | JSON | `event_id`, `contract_id`, `customer_id`, `event_type`, `turnaround_hours`, `delivery_pct`, `defect_pct`, `overage_units` |

*Column names are flexible — use the Column Mapping section below to map your fields.*
        """)

    st.markdown("---")

    # ── Column Mapping UI ──────────────────────────────────────────
    _render_column_mapping_ui(session)

    st.markdown("---")

    # ── Pipeline execution buttons ─────────────────────────────────
    st.markdown("### Run Processing Pipeline")

    col_ingest, col_detect = st.columns(2)

    with col_ingest:
        if st.button("Run Ingestion Pipeline", use_container_width=True, type="primary", key="btn_ingest"):
            with st.spinner("Processing files from stage... (PDFs via Cortex AI, JSON/CSV via auto-parse)"):
                try:
                    res = session.sql("CALL app.run_ingestion_pipeline()").collect()
                    st.success(res[0][0])
                except Exception as e:
                    err_msg = str(e)
                    if any(term in err_msg.lower() for term in ["does not exist", "not authorized", "cortex", "permission"]):
                        st.error("**Cortex AI is not enabled or authorized.**")
                        st.markdown(
                            "To run the PDF extraction pipeline, grant the `CORTEX_USER` privilege via the app settings "
                            "in Snowsight or the Snowflake Permission UI."
                        )
                    else:
                        st.error(f"Pipeline error: {e}")

    with col_detect:
        if st.button("Run Leakage Detection", use_container_width=True, key="btn_detect"):
            with st.spinner("Running 6-rule leakage detection engine..."):
                try:
                    res = session.sql("CALL app.run_leakage_detection()").collect()
                    st.success(res[0][0])
                    st.rerun()
                except Exception as e:
                    st.error(f"Detection error: {e}")

    # ── Preview ingested data ──────────────────────────────────────
    try:
        counts = session.sql("""
            SELECT
                (SELECT COUNT(*) FROM raw.consumer_master_contracts) AS contracts,
                (SELECT COUNT(*) FROM raw.consumer_customers_local) AS customers,
                (SELECT COUNT(*) FROM raw.consumer_billing_local) AS billing,
                (SELECT COUNT(*) FROM raw.consumer_events_local) AS events
        """).collect()
        row = counts[0]
        if any(row[col] > 0 for col in ["CONTRACTS", "CUSTOMERS", "BILLING", "EVENTS"]):
            st.markdown("#### Ingested Data Summary")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Contracts (PDF)", row["CONTRACTS"])
            m2.metric("Customers (CRM)", row["CUSTOMERS"])
            m3.metric("Billing (ERP)", row["BILLING"])
            m4.metric("Events (OPS)", row["EVENTS"])

            # Check if leakage detection has been run
            try:
                leakage_count = session.sql(
                    "SELECT COUNT(*) AS n FROM analytics.leakage_events"
                ).collect()[0]["N"]
            except Exception:
                leakage_count = 0

            if leakage_count > 0:
                st.markdown("---")
                st.success(f"Leakage detection complete — **{leakage_count}** events found. View the dashboard for full analysis.")
                if st.button("View Revenue Leakage Dashboard", type="primary",
                             use_container_width=True, key="btn_goto_dashboard_consumer"):
                    st.session_state.page = "dashboard"
                    st.rerun()
            else:
                st.info(
                    "Data ingested successfully. Run **Leakage Detection** above to analyze "
                    "your contracts for revenue leakage, then access the dashboard."
                )
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
# COLUMN MAPPING UI
# Reads file headers from stage, lets consumer map their fields to app fields.
# ════════════════════════════════════════════════════════════════════════════

# App-expected fields per data source (PDF excluded — AI handles extraction)
_CRM_FIELDS = {
    "customer_id": "STRING",
    "customer_name": "STRING",
    "industry": "STRING",
    "segment": "STRING",
    "region": "STRING",
    "country": "STRING",
    "account_manager": "STRING",
    "arr_usd": "NUMBER",
    "risk_score": "NUMBER",
    "sf_account_id": "STRING",
}

_ERP_FIELDS = {
    "contract_id": "STRING",
    "customer_id": "STRING",
    "invoice_number": "STRING",
    "transaction_date": "DATE",
    "billed_amount": "NUMBER",
    "billing_period_year": "STRING",
    "billing_period_month": "STRING",
    "service_type": "STRING",
    "payment_status": "STRING",
    "sap_document_type": "STRING",
    "sap_company_code": "STRING",
}

_OPS_FIELDS = {
    "event_id": "STRING",
    "contract_id": "STRING",
    "customer_id": "STRING",
    "event_type": "STRING",
    "event_date": "DATE",
    "start_timestamp": "TIMESTAMP",
    "end_timestamp": "TIMESTAMP",
    "turnaround_hours": "NUMBER",
    "procedure_code": "STRING",
    "service_code": "STRING",
    "quantity": "NUMBER",
    "reported_value": "NUMBER",
    "delivery_pct": "NUMBER",
    "defect_pct": "NUMBER",
    "units_ordered": "NUMBER",
    "uptime_pct": "NUMBER",
    "user_count": "NUMBER",
    "overage_units": "NUMBER",
    "status": "STRING",
    "record_source": "STRING",
}

# Default column mappings per source (used for auto-selecting dropdowns)
_DEFAULT_MAPS = {
    "crm": {
        "CUSTOMER_ID": "_internal_customer_id", "CUSTOMER_NAME": "Name",
        "INDUSTRY": "_industry_internal", "SEGMENT": "_segment",
        "REGION": "_region", "COUNTRY": "BillingCountry",
        "ACCOUNT_MANAGER": "_account_manager", "ARR_USD": "AnnualRevenue",
        "RISK_SCORE": "_risk_score", "SF_ACCOUNT_ID": "Id"
    },
    "erp": {
        "CONTRACT_ID": "_contract_id", "CUSTOMER_ID": "KUNAG", "INVOICE_NUMBER": "VBELN",
        "TRANSACTION_DATE": "FKDAT", "BILLED_AMOUNT": "NETWR",
        "BILLING_PERIOD_YEAR": "GJAHR", "BILLING_PERIOD_MONTH": "POPER",
        "SERVICE_TYPE": "_industry", "PAYMENT_STATUS": "_has_mismatch",
        "SAP_DOCUMENT_TYPE": "FKART", "SAP_COMPANY_CODE": "BUKRS"
    },
    "ops": {
        "EVENT_ID": "event_id", "CONTRACT_ID": "contract_ref", "CUSTOMER_ID": "customer_ref",
        "EVENT_TYPE": "event_type", "EVENT_DATE": "event_date",
        "START_TIMESTAMP": "start_timestamp", "END_TIMESTAMP": "end_timestamp",
        "TURNAROUND_HOURS": "turnaround_hours", "PROCEDURE_CODE": "procedure_code",
        "SERVICE_CODE": "service_code", "QUANTITY": "quantity",
        "REPORTED_VALUE": "reported_value", "DELIVERY_PCT": "delivery_pct",
        "DEFECT_PCT": "defect_pct", "UNITS_ORDERED": "units_ordered",
        "UPTIME_PCT": "uptime_pct", "USER_COUNT": "user_count",
        "OVERAGE_UNITS": "overage_units", "STATUS": "status",
        "RECORD_SOURCE": "record_source"
    }
}


def _detect_stage_fields(session, pattern, format_type):
    """Read field names from staged files by calling a stored procedure."""
    try:
        if format_type == "json":
            rows = session.sql(f"CALL app.detect_json_fields('{pattern}')").collect()
            if rows and rows[0][0]:
                import json
                result = json.loads(rows[0][0])
                if isinstance(result, dict) and "error" in result:
                    return []
                if isinstance(result, list):
                    return [str(f) for f in result if f is not None]
        elif format_type == "csv":
            rows = session.sql(f"CALL app.detect_csv_fields('{pattern}')").collect()
            if rows and rows[0][0]:
                import json
                result = json.loads(rows[0][0])
                if isinstance(result, dict) and "error" in result:
                    return []
                if isinstance(result, list):
                    return [str(f) for f in result if f is not None]
    except Exception:
        pass
    return []


def _get_saved_mappings(session, source_name):
    """Retrieve previously saved column mappings for a source."""
    try:
        rows = session.sql(f"""
            SELECT app_column, consumer_column
            FROM config.column_mappings
            WHERE reference_name = '{source_name}'
        """).collect()
        return {r["APP_COLUMN"]: r["CONSUMER_COLUMN"] for r in rows}
    except Exception:
        return {}


def _render_column_mapping_ui(session):
    """Render the column mapping interface for CRM, ERP, and OPS data sources."""

    st.markdown("### Column Mapping")
    st.markdown(
        "Map your data fields to the fields the app expects. "
        "Click **Detect Fields** to read column names from your uploaded files, "
        "then use the dropdowns to map each field."
    )

    # Tabs for each data source (PDF doesn't need mapping)
    tab_crm, tab_erp, tab_ops = st.tabs(["CRM (JSON)", "ERP (CSV)", "OPS (JSON)"])

    with tab_crm:
        _render_source_mapping(
            session,
            source_name="crm",
            source_label="CRM",
            pattern=".*crm.*[.]json",
            format_type="json",
            app_fields=_CRM_FIELDS,
        )

    with tab_erp:
        _render_source_mapping(
            session,
            source_name="erp",
            source_label="ERP",
            pattern=".*erp.*[.]csv",
            format_type="csv",
            app_fields=_ERP_FIELDS,
        )

    with tab_ops:
        _render_source_mapping(
            session,
            source_name="ops",
            source_label="OPS",
            pattern=".*ops.*[.]json",
            format_type="json",
            app_fields=_OPS_FIELDS,
        )


def _render_source_mapping(session, source_name, source_label, pattern, format_type, app_fields):
    """Render mapping UI for a single data source."""

    # Initialize session state for detected fields
    state_key = f"detected_fields_{source_name}"

    if state_key not in st.session_state:
        st.session_state[state_key] = []

    # Detect fields button
    if st.button(f"Detect Fields from {source_label} Files", key=f"detect_{source_name}"):
        detected = _detect_stage_fields(session, pattern, format_type)
        if detected:
            st.session_state[state_key] = detected
            st.success(f"Found {len(detected)} fields: {', '.join(detected)}")
        else:
            st.warning(
                f"No {source_label} files found in stage. Upload your files first, "
                f"then click Detect Fields."
            )

    detected_fields = st.session_state[state_key]
    saved_mappings = _get_saved_mappings(session, source_name)

    if not detected_fields and not saved_mappings:
        st.info(
            f"Upload your {source_label} files to the stage, then click **Detect Fields** "
            f"to see your column names and create mappings."
        )
        return

    # If no detected fields but we have saved mappings, use consumer columns from mappings
    if not detected_fields and saved_mappings:
        detected_fields = list(saved_mappings.values())

    # Show mapping dropdowns
    st.markdown(f"**Map your {source_label} fields to app fields:**")

    options = ["-- skip --"] + detected_fields
    new_mappings = {}

    # Create two-column layout for mapping
    col_app, col_consumer = st.columns(2)
    with col_app:
        st.markdown("**App Field** (required)")
    with col_consumer:
        st.markdown("**Your Field** (from file)")

    for app_field, data_type in app_fields.items():
        col_a, col_c = st.columns(2)
        with col_a:
            st.markdown(f"`{app_field}` ({data_type})")
        with col_c:
            # Default to saved mapping or try to auto-match
            default_idx = 0
            if app_field.upper() in saved_mappings:
                saved_val = saved_mappings[app_field.upper()]
                if saved_val in options:
                    default_idx = options.index(saved_val)
            elif app_field in detected_fields:
                # Auto-match if exact name exists
                default_idx = options.index(app_field)
            else:
                # Try case-insensitive match (with and without underscore prefix)
                matched = False
                for i, f in enumerate(detected_fields):
                    f_clean = f.lower().lstrip('_')
                    if f.lower() == app_field.lower() or f_clean == app_field.lower():
                        default_idx = i + 1
                        matched = True
                        break
                # If still no match, check default map for this source
                if not matched and source_name in _DEFAULT_MAPS:
                    default_csv_col = _DEFAULT_MAPS[source_name].get(app_field.upper(), "")
                    for i, f in enumerate(detected_fields):
                        if f.upper() == default_csv_col.upper():
                            default_idx = i + 1
                            break

            selected = st.selectbox(
                f"Map to {app_field}",
                options=options,
                index=default_idx,
                key=f"map_{source_name}_{app_field}",
                label_visibility="collapsed",
            )
            if selected != "-- skip --":
                new_mappings[app_field] = selected

    # Save mappings button
    if st.button(f"Save {source_label} Mappings", key=f"save_{source_name}", type="primary"):
        if not new_mappings:
            st.warning("No mappings to save. Please select at least one field mapping.")
        else:
            for app_col, consumer_col in new_mappings.items():
                safe_source = str(source_name).replace("'", "''")
                safe_app = str(app_col).upper().replace("'", "''")
                safe_consumer = str(consumer_col).replace("'", "''")
                session.sql(f"""
                    CALL config.set_column_mapping('{safe_source}', '{safe_app}', '{safe_consumer}')
                """).collect()
            st.success(f"Saved {len(new_mappings)} field mappings for {source_label}.")

    # Show current mappings summary
    if saved_mappings:
        with st.expander(f"Current {source_label} mappings ({len(saved_mappings)} fields)"):
            for app_col, consumer_col in saved_mappings.items():
                st.markdown(f"- `{consumer_col}` → **{app_col}**")

