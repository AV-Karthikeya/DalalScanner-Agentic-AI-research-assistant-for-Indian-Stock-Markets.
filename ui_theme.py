
import re
import streamlit as st


EDUPLEX_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

/* =========================================================
   1. GLOBAL THEME
   ========================================================= */

html, body, [class*="css"], .stApp {
    font-family: 'Plus Jakarta Sans', -apple-system,
    BlinkMacSystemFont, sans-serif !important;
    background-color: #F6F7FB !important;
    color: #181920 !important;
}

.block-container {
    padding-top: 5rem !important;
    padding-bottom: 2.5rem;
    max-width: 1420px;
}

[data-testid="stMain"] {
    background-color: #F6F7FB !important;
    color: #181920 !important;
}

/* Stronger main content typography */

[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] h4 {
    color: #181920 !important;
    font-weight: 700 !important;
}

[data-testid="stMain"] p,
[data-testid="stMain"] li,
[data-testid="stMain"] label {
    color: #252936;
}

[data-testid="stMain"] [data-testid="stCaptionContainer"],
[data-testid="stMain"] .stCaption {
    color: #586174 !important;
}

[data-testid="stMain"] [data-testid="stWidgetLabel"] p {
    color: #0B0C10 !important;
    font-weight: 600 !important;
}

/* =========================================================
   2. SIDEBAR
   ========================================================= */

section[data-testid="stSidebar"] {
    background-color: #181920 !important;
    border-right: none !important;
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1.25rem !important;
    padding-left: 1.1rem !important;
    padding-right: 1.1rem !important;
}

section[data-testid="stSidebar"] * {
    color: #A1A5B7;
}

/* Brand */

.ds-brand {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin-bottom: 1.5rem;
    padding: 0.2rem 0.25rem;
}

.ds-brand-mark {
    width: 34px;
    height: 34px;
    border-radius: 999px;
    background-color: #FFFFFF;
    color: #181920 !important;
    font-weight: 800;
    font-size: 0.95rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}

.ds-brand-name {
    font-size: 1.22rem;
    font-weight: 700;
    color: #FFFFFF !important;
    letter-spacing: -0.02em;
}

/* Watchlist Queue Label — Improved Contrast */
div[data-testid="stCaptionContainer"],
div[data-testid="stCaptionContainer"] p {
    color: #454B5A !important;
    opacity: 1 !important;
    font-weight: 600 !important;
}

/* =========================================================
   3. SIDEBAR PILL NAVIGATION
   Uses st.pills() instead of st.radio()
   ========================================================= */

section[data-testid="stSidebar"] div[data-testid="stPills"] {
    width: 100% !important;
}

section[data-testid="stSidebar"] div[data-testid="stPills"] > div {
    display: flex !important;
    flex-direction: column !important;
    align-items: stretch !important;
    gap: 7px !important;
    width: 100% !important;
}

section[data-testid="stSidebar"] div[data-testid="stPills"] button {
    width: 100% !important;
    justify-content: flex-start !important;
    text-align: left !important;
    background-color: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 13px !important;
    padding: 0.65rem 0.9rem !important;
    color: #C2C6D2 !important;
    font-weight: 500 !important;
    box-shadow: none !important;
    transition: all 0.18s ease !important;
}

section[data-testid="stSidebar"] div[data-testid="stPills"] button:hover {
    background-color: rgba(255,255,255,0.08) !important;
    color: #FFFFFF !important;
}

/* Active navigation pill */

section[data-testid="stSidebar"] div[data-testid="stPills"] button[aria-pressed="true"] {
    background-color: #D9F26B !important;
    color: #181920 !important;
    border-color: #D9F26B !important;
    font-weight: 700 !important;
}

section[data-testid="stSidebar"] div[data-testid="stPills"] button[aria-pressed="true"] * {
    color: #181920 !important;
}

/* Sidebar expanders */

section[data-testid="stSidebar"] details summary {
    color: #E5E7EB !important;
}

section[data-testid="stSidebar"] details summary:hover {
    color: #FFFFFF !important;
}

/* =========================================================
   4. SIDEBAR PROMO CARD
   ========================================================= */

.ds-sidebar-promo {
    background-color: #D9F26B;
    border-radius: 20px;
    padding: 1.05rem 1rem;
    margin-top: 1.25rem;
    color: #181920 !important;
}

.ds-sidebar-promo-title {
    font-size: 0.92rem;
    font-weight: 700;
    color: #181920 !important;
    line-height: 1.25;
    margin-bottom: 0.35rem;
}

.ds-sidebar-promo-sub {
    font-size: 0.76rem;
    color: #2D3139 !important;
    line-height: 1.35;
}

/* =========================================================
   5. CARDS AND CONTAINERS
   ========================================================= */

div[data-testid="stVerticalBlockBorderWrapper"] > div {
    background-color: #FFFFFF !important;
    border: 1px solid #ECEEF4 !important;
    border-radius: 20px !important;
    box-shadow: 0 2px 10px rgba(24,25,32,0.03) !important;
    padding: 0.35rem 0.5rem;
}

/* =========================================================
   6. BUTTONS
   ========================================================= */

/* Primary buttons */

.stApp button[kind="primary"],
.stApp button[data-testid="stBaseButton-primary"] {
    background-color: #D9F26B !important;
    border: 1px solid #C8E452 !important;
    border-radius: 999px !important;
    color: #181920 !important;
    font-weight: 700 !important;
    box-shadow: none !important;
}

.stApp button[kind="primary"]:hover,
.stApp button[data-testid="stBaseButton-primary"]:hover {
    background-color: #CBE94F !important;
    color: #181920 !important;
}

/* Secondary buttons */

.stApp button[kind="secondary"],
.stApp button[data-testid="stBaseButton-secondary"] {
    background-color: #FFFFFF !important;
    border: 1px solid #DDE1EB !important;
    border-radius: 999px !important;
    color: #181920 !important;
    font-weight: 600 !important;
    box-shadow: none !important;
}

.stApp button[kind="secondary"]:hover,
.stApp button[data-testid="stBaseButton-secondary"]:hover {
    background-color: #F0F2F8 !important;
    border-color: #181920 !important;
    color: #181920 !important;
}

/* Popover buttons, including Save list */

.stApp div[data-testid="stPopover"] > button {
    background-color: #FFFFFF !important;
    border: 1px solid #DDE1EB !important;
    border-radius: 999px !important;
    color: #181920 !important;
    font-weight: 600 !important;
    box-shadow: none !important;
}

.stApp div[data-testid="stPopover"] > button:hover {
    background-color: #F0F2F8 !important;
    border-color: #181920 !important;
    color: #181920 !important;
}

/* Popover content */

div[data-testid="stPopoverBody"] {
    background-color: #FFFFFF !important;
    color: #181920 !important;
    border: 1px solid #E5E8F0 !important;
    border-radius: 16px !important;
}

/* Disabled buttons */

.stApp button:disabled {
    background-color: #E9EBF1 !important;
    color: #747B8C !important;
    border-color: #E0E3EA !important;
    opacity: 0.85 !important;
}

/* =========================================================
   7. INPUTS AND SELECTBOXES
   ========================================================= */

[data-testid="stMain"] input,
[data-testid="stMain"] textarea {
    color: #181920 !important;
    background-color: #FFFFFF !important;
}

[data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-baseweb="input"] > div,
[data-testid="stMain"] textarea {
    border-color: #D9DDE8 !important;
    background-color: #FFFFFF !important;
}

[data-testid="stMain"] [data-baseweb="select"] *,
[data-testid="stMain"] [data-baseweb="input"] * {
    color: #181920 !important;
}

/* =========================================================
   8. HEADER AND STATUS
   ========================================================= */

.ds-title {
    font-size: 1.75rem;
    font-weight: 700;
    color: #181920 !important;
    margin: 0;
    letter-spacing: -0.02em;
}

.ds-status {
    font-size: 0.82rem;
    color: #586174 !important;
    margin-top: 0.2rem;
    margin-bottom: 0.9rem;
}

/* =========================================================
   9. INDEX CARDS
   ========================================================= */

.ed-course-card {
    background-color: #FFFFFF;
    border: 1px solid #ECEEF4;
    border-radius: 20px;
    padding: 1.05rem 1.15rem;
    box-shadow: 0 2px 10px rgba(24,25,32,0.03);
    height: 100%;
}

.ed-course-top {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.85rem;
}

.ed-icon-circle {
    width: 38px;
    height: 38px;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.82rem;
    color: #181920;
    flex-shrink: 0;
}

.ed-course-name {
    font-size: 0.95rem;
    font-weight: 700;
    color: #181920 !important;
    line-height: 1.2;
}

.ed-course-sub {
    font-size: 0.76rem;
    color: #586174 !important;
    margin-top: 0.1rem;
}

.ed-course-foot {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-top: 1px solid #F1F3F8;
    padding-top: 0.65rem;
}

.ed-foot-lbl {
    font-size: 0.72rem;
    color: #687087 !important;
    margin-bottom: 0.15rem;
}

.ed-foot-val {
    font-size: 1.12rem;
    font-weight: 700;
    color: #181920 !important;
    font-variant-numeric: tabular-nums;
}

/* =========================================================
   10. DARK HERO CARD
   ========================================================= */

.ed-dark-hero {
    background-color: #181920;
    border-radius: 22px;
    padding: 1.25rem 1.3rem;
    color: #FFFFFF !important;
    margin-bottom: 0.85rem;
}

.ed-dark-hero-badge {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    color: #D9F26B !important;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}

.ed-dark-hero-title {
    font-size: 1.2rem;
    font-weight: 700;
    color: #FFFFFF !important;
    margin-bottom: 0.35rem;
}

.ed-dark-hero-sub {
    font-size: 0.8rem;
    color: #C0C5D3 !important;
    line-height: 1.4;
}

/* =========================================================
   11. MINI CARDS
   ========================================================= */

.ed-mini-card {
    background-color: #FFFFFF;
    border: 1px solid #ECEEF4;
    border-radius: 20px;
    padding: 0.95rem 1.1rem;
    box-shadow: 0 2px 10px rgba(24,25,32,0.03);
    margin-bottom: 0.85rem;
}

/* =========================================================
   12. KPI CARDS
   ========================================================= */

.ds-kpi-card {
    background-color: #FFFFFF;
    border: 1px solid #ECEEF4;
    border-radius: 20px;
    padding: 1rem 1.15rem;
    box-shadow: 0 2px 10px rgba(24,25,32,0.03);
    height: 100%;
}

.ds-kpi-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.4rem;
}

.ds-kpi-label {
    font-size: 0.78rem;
    font-weight: 600;
    color: #586174 !important;
}

.ds-kpi-tag {
    font-size: 0.7rem;
    font-weight: 600;
    color: #181920 !important;
    border-radius: 999px;
    padding: 0.14rem 0.55rem;
    background-color: #F1F3F8;
}

.ds-kpi-val {
    font-size: 1.45rem;
    font-weight: 700;
    color: #181920 !important;
    line-height: 1.18;
    margin-bottom: 0.4rem;
    font-variant-numeric: tabular-nums;
}

.ds-kpi-foot {
    font-size: 0.76rem;
    color: #586174 !important;
}

/* =========================================================
   13. RISK PLANNER CARDS
   ========================================================= */

.rp-card {
    background-color: #F6F7FB;
    border: 1px solid #E5E8F0;
    border-radius: 16px;
    padding: 14px 16px;
    height: 100%;
}

.rp-card-cream {
    background-color: #D9F26B;
    border: 1px solid #C8E452;
    border-radius: 16px;
    padding: 14px 16px;
    height: 100%;
    color: #181920 !important;
}

.rp-card-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #586174 !important;
    margin-bottom: 5px;
}

.rp-card-cream .rp-card-label {
    color: #2D3139 !important;
}

.rp-card-val {
    font-size: 1.65rem;
    font-weight: 700;
    line-height: 1.15;
    color: #181920 !important;
    margin-bottom: 5px;
    font-variant-numeric: tabular-nums;
}

.rp-card-sub {
    font-size: 0.75rem;
    color: #586174 !important;
}

.rp-card-cream .rp-card-sub {
    color: #2D3139 !important;
}

/* =========================================================
   14. RISK PLANNER STEPPER
   ========================================================= */

.ds-stepper {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background-color: #FFFFFF;
    border: 1px solid #ECEEF4;
    border-radius: 999px;
    padding: 0.55rem 1.2rem;
    margin-bottom: 0.85rem;
}

.ds-step-node {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.8rem;
    font-weight: 600;
    color: #181920 !important;
}

.ds-step-dot {
    width: 22px;
    height: 22px;
    border-radius: 999px;
    background-color: #D9F26B;
    color: #181920 !important;
    font-size: 0.74rem;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}

.ds-step-line {
    flex: 1;
    height: 1px;
    background-color: #E2E5F0;
    margin: 0 0.85rem;
}

/* =========================================================
   15. GAIN, LOSS AND VERIFICATION BADGES
   ========================================================= */

.ds-gain {
    color: #16A34A !important;
    font-weight: 700;
}

.ds-gain-dark {
    color: #14532D !important;
    font-weight: 700;
}

.ds-loss {
    color: #DC2626 !important;
    font-weight: 700;
}

.ds-badge {
    display: inline-block;
    font-size: 0.73rem;
    font-weight: 700;
    padding: 0.16rem 0.58rem;
    border-radius: 999px;
}

.ds-badge-verified {
    color: #181920 !important;
    background-color: #D9F26B;
}

.ds-badge-flagged {
    color: #FFFFFF !important;
    background-color: #DC2626;
}

/* =========================================================
   16. BRIEF CARDS
   ========================================================= */

.ds-flat-card {
    background-color: #FFFFFF;
    border: 1px solid #ECEEF4;
    border-radius: 20px;
    padding: 1.05rem 1.25rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 2px 10px rgba(24,25,32,0.03);
}

.ds-card-bullish {
    border-left: 4px solid #16A34A;
}

.ds-card-bearish {
    border-left: 4px solid #DC2626;
}

.ds-card-neutral {
    border-left: 4px solid #94A3B8;
}

/* =========================================================
   17. DATA TABLES
   ========================================================= */

[data-testid="stMain"] [data-testid="stDataFrame"] {
    border: 1px solid #E5E8F0 !important;
    border-radius: 12px !important;
}

/* =========================================================
   18. ACCESSIBILITY AND FOCUS
   ========================================================= */

.stApp button:focus-visible,
.stApp input:focus-visible {
    outline: 2px solid #A6C83C !important;
    outline-offset: 2px !important;
}

/* =========================================================
   19. RESPONSIVE LAYOUT
   ========================================================= */

@media (max-width: 768px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    .ds-stepper {
        flex-wrap: wrap;
        gap: 0.5rem;
    }

    .ds-step-line {
        display: none;
    }

    .ed-course-card {
        padding: 0.9rem;
    }
}

/* =========================================================
   20. MAIN-AREA PILLS AND PLACEHOLDERS
   ========================================================= */

[data-testid="stMain"] [data-testid="stPills"] button,
[data-testid="stMain"] [data-testid="stButtonGroup"] button,
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"] {
    background-color: #E9ECF5 !important;
    border: 1px solid #B8BFD3 !important;
    border-radius: 999px !important;
    box-shadow: none !important;
}

[data-testid="stMain"] [data-testid="stPills"] button,
[data-testid="stMain"] [data-testid="stButtonGroup"] button,
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"],
[data-testid="stMain"] [data-testid="stPills"] button *,
[data-testid="stMain"] [data-testid="stButtonGroup"] button *,
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"] * {
    color: #181920 !important;
    -webkit-text-fill-color: #181920 !important;
    font-weight: 600 !important;
}

[data-testid="stMain"] [data-testid="stPills"] button:hover,
[data-testid="stMain"] [data-testid="stButtonGroup"] button:hover,
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"]:hover {
    background-color: #D9DEEC !important;
    border-color: #181920 !important;
}

[data-testid="stMain"] [data-testid="stPills"] button[aria-pressed="true"],
[data-testid="stMain"] [data-testid="stPills"] button[aria-checked="true"],
[data-testid="stMain"] [data-testid="stPills"] button[data-testid="stBaseButton-pillsActive"],
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-pressed="true"],
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"],
[data-testid="stMain"] [data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"],
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][aria-pressed="true"],
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][aria-checked="true"],
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][data-testid="stBaseButton-pillsActive"] {
    background-color: #181920 !important;
    border: 1px solid #181920 !important;
}

[data-testid="stMain"] [data-testid="stPills"] button[aria-pressed="true"],
[data-testid="stMain"] [data-testid="stPills"] button[aria-checked="true"],
[data-testid="stMain"] [data-testid="stPills"] button[data-testid="stBaseButton-pillsActive"],
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-pressed="true"],
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"],
[data-testid="stMain"] [data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"],
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][aria-pressed="true"],
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][aria-checked="true"],
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][data-testid="stBaseButton-pillsActive"],
[data-testid="stMain"] [data-testid="stPills"] button[aria-pressed="true"] *,
[data-testid="stMain"] [data-testid="stPills"] button[aria-checked="true"] *,
[data-testid="stMain"] [data-testid="stPills"] button[data-testid="stBaseButton-pillsActive"] *,
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-pressed="true"] *,
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"] *,
[data-testid="stMain"] [data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"] *,
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][aria-pressed="true"] *,
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][aria-checked="true"] *,
[data-testid="stMain"] button[data-testid^="stBaseButton-pills"][data-testid="stBaseButton-pillsActive"] * {
    color: #D9F26B !important;
    -webkit-text-fill-color: #D9F26B !important;
    font-weight: 700 !important;
}

[data-testid="stMain"] input::placeholder,
[data-testid="stMain"] textarea::placeholder {
    color: #8A90A3 !important;
    -webkit-text-fill-color: #8A90A3 !important;
    opacity: 1 !important;
}

/* =========================================================
   21. TOP HEADER BAR (Deploy / menu)
   ========================================================= */

header[data-testid="stHeader"],
[data-testid="stHeader"] {
    background-color: #181920 !important;   /* header colour (matches sidebar) */
}

header *,
[data-testid="stToolbar"],
[data-testid="stToolbar"] *,
[data-testid="stToolbarActions"] *,
[data-testid="stAppDeployButton"],
[data-testid="stAppDeployButton"] *,
[data-testid="stMainMenu"],
[data-testid="stMainMenu"] *,
.stDeployButton,
.stDeployButton * {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    opacity: 1 !important;
}

[data-testid="stToolbar"] svg,
[data-testid="stMainMenu"] svg {
    fill: none !important;
    stroke: #FFFFFF !important;
}

[data-testid="stMainMenu"] button {
    background-color: transparent !important;
}

[data-testid="stAppDeployButton"]:hover,
[data-testid="stMainMenu"] button:hover {
    background-color: rgba(255,255,255,0.16) !important;
}

</style>
"""


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(text: str) -> str:
    cleaned = _EMOJI_RE.sub("", text or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def apply_theme() -> None:
    st.markdown(EDUPLEX_CSS, unsafe_allow_html=True)


def render_delta_text(
    value: float,
    suffix: str = "%",
    invert_sign: bool = False,
) -> str:
    if value > 0:
        cls = "ds-loss" if invert_sign else "ds-gain"
        arrow = "▲"
    elif value < 0:
        cls = "ds-gain" if invert_sign else "ds-loss"
        arrow = "▼"
    else:
        cls = ""
        arrow = ""

    sign_str = (
        f"{value:+.2f}{suffix}"
        if suffix == "%"
        else f"{value:+,.2f}{suffix}"
    )

    if not cls:
        return f"<span>{sign_str}</span>"

    return f'<span class="{cls}">{arrow} {sign_str}</span>'


def render_course_index_card(
    label: str,
    subtitle: str,
    value: float,
    pct: float,
    badge_text: str = "N50",
    circle_bg: str = "#FCE7F3",
    invert_sign: bool = False,
) -> str:
    """White index card with pastel icon badge and two-column footer."""

    delta_html = render_delta_text(
        pct,
        "%",
        invert_sign=invert_sign,
    )

    return (
        f'<div class="ed-course-card">'
        f'  <div class="ed-course-top">'
        f'    <span class="ed-icon-circle" '
        f'style="background-color:{circle_bg};">'
        f'{strip_emoji(badge_text)}</span>'
        f'    <div>'
        f'      <div class="ed-course-name">'
        f'{strip_emoji(label)}</div>'
        f'      <div class="ed-course-sub">'
        f'{strip_emoji(subtitle)}</div>'
        f'    </div>'
        f'  </div>'
        f'  <div class="ed-course-foot">'
        f'    <div>'
        f'      <div class="ed-foot-lbl">Last Close</div>'
        f'      <div class="ed-foot-val">{value:,.2f}</div>'
        f'    </div>'
        f'    <div style="text-align:right;">'
        f'      <div class="ed-foot-lbl">1D Change</div>'
        f'      <div style="font-size:0.95rem;">'
        f'{delta_html}</div>'
        f'    </div>'
        f'  </div>'
        f'</div>'
    )


def render_kpi_card(
    label: str,
    value: float,
    pct: float,
    tag: str = "Index",
    foot_note: str = "vs prev close",
    invert_sign: bool = False,
) -> str:
    return render_course_index_card(
        label=label,
        subtitle=f"{tag} · {foot_note}",
        value=value,
        pct=pct,
        badge_text=tag[:3].upper(),
        invert_sign=invert_sign,
    )


def render_stat_card(
    label: str,
    value_text: str,
    sub_html: str = "",
    tag: str = "",
) -> str:
    tag_html = (
        f'<span class="ds-kpi-tag">{strip_emoji(tag)}</span>'
        if tag else ""
    )

    foot_html = (
        f'<div class="ds-kpi-foot">{sub_html}</div>'
        if sub_html else ""
    )

    return (
        f'<div class="ds-kpi-card">'
        f'  <div class="ds-kpi-top">'
        f'    <span class="ds-kpi-label">'
        f'{strip_emoji(label)}</span>'
        f'    {tag_html}'
        f'  </div>'
        f'  <div class="ds-kpi-val">'
        f'{strip_emoji(value_text)}</div>'
        f'  {foot_html}'
        f'</div>'
    )


def render_risk_stepper(
    step1_label: str = "Your limits",
    step2_label: str = "Stock & stop-loss",
    step3_label: str = "Your plan",
) -> str:
    return (
        f'<div class="ds-stepper">'
        f'  <div class="ds-step-node">'
        f'    <span class="ds-step-dot">1</span>'
        f'    <span>{strip_emoji(step1_label)}</span>'
        f'  </div>'
        f'  <div class="ds-step-line"></div>'
        f'  <div class="ds-step-node">'
        f'    <span class="ds-step-dot">2</span>'
        f'    <span>{strip_emoji(step2_label)}</span>'
        f'  </div>'
        f'  <div class="ds-step-line"></div>'
        f'  <div class="ds-step-node">'
        f'    <span class="ds-step-dot">3</span>'
        f'    <span>{strip_emoji(step3_label)}</span>'
        f'  </div>'
        f'</div>'
    )


def render_verification_badge(passed: bool) -> str:
    if passed:
        return (
            '<span class="ds-badge ds-badge-verified">'
            'Verified</span>'
        )

    return (
        '<span class="ds-badge ds-badge-flagged">'
        'Flagged</span>'
    )
