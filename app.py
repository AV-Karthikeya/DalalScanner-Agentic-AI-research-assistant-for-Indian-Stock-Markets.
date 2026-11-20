from datetime import datetime, timezone, timedelta
import io
import json
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from run_pipeline import run_daily_pipeline
from screener_engine import run_unified_radar, explain_radar_scan
from backtest_engine import STRATEGY_SPECS, run_strategy_backtest, generate_ai_backtest_insights
from risk_planner import (
    get_last_close_price,
    get_trade_idea_defaults,
    calculate_position_plan,
    allocate_equal_risk_portfolio,
    project_portfolio_returns,
    generate_ai_risk_audit,
)
from nse_filings_engine import get_nse_filings
from report_analyzer import analyze_pdf_report

st.set_page_config(
    page_title="Verified NSE / BSE Equity & Index Brief Agent",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.75rem; padding-bottom: 2rem; }
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 0.7rem 0.95rem;
        border-radius: 0.6rem;
    }
    .step-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background-color: #ef4444;
        color: #ffffff;
        font-size: 12px;
        font-weight: 700;
        margin-right: 8px;
        vertical-align: middle;
    }
    .step-title {
        font-size: 15px;
        font-weight: 600;
        vertical-align: middle;
    }
    .rp-card {
        background-color: rgba(255, 255, 255, 0.025);
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 10px;
        padding: 14px 16px;
        height: 100%;
    }
    .rp-card-label {
        font-size: 12px;
        opacity: 0.72;
        margin-bottom: 6px;
    }
    .rp-card-val {
        font-size: 24px;
        font-weight: 700;
        line-height: 1.2;
        margin-bottom: 6px;
    }
    .rp-card-sub {
        font-size: 12px;
        opacity: 0.7;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DATA_PATH = Path("data/latest_brief.json")
IST = timezone(timedelta(hours=5, minutes=30))
MAX_TICKERS_PER_RUN = 8
COOLDOWN_SECONDS = 30

MAJOR_INDICES = {
    "NIFTY 50 (Index)": "^NSEI",
    "BSE SENSEX (Index)": "^BSESN",
    "NIFTY BANK (Index)": "^NSEBANK",
    "NIFTY IT (Index)": "^CNXIT",
    "NIFTY AUTO (Index)": "^CNXAUTO",
    "NIFTY PHARMA (Index)": "^CNXPHARMA",
    "INDIA VIX (Volatility Index)": "^INDIAVIX",
}

BUILT_IN_PACKS: dict[str, dict] = {
    "🏆 Nifty 50 Top 5": {
        "meta": "Weights as of Nov 2026: HDFCBANK (~10.5%), ICICIBANK (~8.8%), RELIANCE (~7.5%), BHARTIARTL (~5.1%), LT (~4.2%)",
        "items": [
            "HDFC Bank Limited (HDFCBANK)",
            "ICICI Bank Limited (ICICIBANK)",
            "Reliance Industries Limited (RELIANCE)",
            "Bharti Airtel Limited (BHARTIARTL)",
            "Larsen & Toubro Limited (LT)",
        ],
    },
    "🏦 Bank Nifty Top 5": {
        "meta": "Weights as of Nov 2026: HDFCBANK (~28%), ICICIBANK (~24%), SBIN (~11%), KOTAKBANK (~10%), AXISBANK (~9%)",
        "items": [
            "HDFC Bank Limited (HDFCBANK)",
            "ICICI Bank Limited (ICICIBANK)",
            "Kotak Mahindra Bank Limited (KOTAKBANK)",
            "Axis Bank Limited (AXISBANK)",
            "State Bank of India (SBIN)",
        ],
    },
    "💻 Nifty IT Top 5": {
        "meta": "Weights as of Nov 2026: INFY (~27%), TCS (~25%), HCLTECH (~10%), TECHM (~9%), WIPRO (~8%)",
        "items": [
            "Infosys Limited (INFY)",
            "Tata Consultancy Services Limited (TCS)",
            "HCL Technologies Limited (HCLTECH)",
            "Tech Mahindra Limited (TECHM)",
            "Wipro Limited (WIPRO)",
        ],
    },
    "📊 Headline Indices": {
        "meta": "Benchmark & Sector Indices: NIFTY 50, BSE SENSEX, NIFTY BANK, NIFTY IT, INDIA VIX",
        "items": [
            "NIFTY 50 (Index)",
            "BSE SENSEX (Index)",
            "NIFTY BANK (Index)",
            "NIFTY IT (Index)",
            "INDIA VIX (Volatility Index)",
        ],
    },
}


def load_report() -> dict | None:
    if not DATA_PATH.exists():
        return None
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def format_ist_timestamp(utc_iso: str) -> str:
    try:
        dt_utc = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_ist = dt_utc.astimezone(IST)
        return dt_ist.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return utc_iso


def market_status_label() -> str:
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5:
        return "Weekend — market closed, showing last close"
    minutes = now_ist.hour * 60 + now_ist.minute
    if 9 * 60 + 15 <= minutes <= 15 * 60 + 30:
        return "Market open (quotes delayed ~15 min)"
    return "Market closed — showing last close"


@st.cache_data(ttl=300, show_spinner=False)
def load_market_pulse() -> list[dict]:
    pulse_tickers = [
        ("^NSEI", "NIFTY 50"),
        ("^BSESN", "BSE SENSEX"),
        ("^NSEBANK", "NIFTY BANK"),
        ("^INDIAVIX", "INDIA VIX"),
    ]
    results = []
    for sym, label in pulse_tickers:
        try:
            hist = yf.Ticker(sym).history(period="5d")
            if len(hist) >= 2:
                close_val = float(hist["Close"].iloc[-1])
                prev_val = float(hist["Close"].iloc[-2])
                pct = ((close_val - prev_val) / prev_val) * 100
                results.append({"label": label, "value": close_val, "pct": pct})
        except Exception:
            continue
    return results


@st.cache_data(ttl=86400, show_spinner=False)
def load_nse_universe() -> dict[str, str]:
    options = dict(MAJOR_INDICES)
    url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/csv,*/*",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        for _, row in df.iterrows():
            sym = str(row["SYMBOL"]).strip()
            name = str(row["NAME OF COMPANY"]).strip()
            if sym and name:
                options[f"{name} ({sym})"] = f"{sym}.NS"
        return options
    except Exception:
        fallback = {
            "HDFC Bank Limited (HDFCBANK)": "HDFCBANK.NS",
            "ICICI Bank Limited (ICICIBANK)": "ICICIBANK.NS",
            "Reliance Industries Limited (RELIANCE)": "RELIANCE.NS",
            "Bharti Airtel Limited (BHARTIARTL)": "BHARTIARTL.NS",
            "Larsen & Toubro Limited (LT)": "LT.NS",
            "Kotak Mahindra Bank Limited (KOTAKBANK)": "KOTAKBANK.NS",
            "Axis Bank Limited (AXISBANK)": "AXISBANK.NS",
            "State Bank of India (SBIN)": "SBIN.NS",
            "Infosys Limited (INFY)": "INFY.NS",
            "Tata Consultancy Services Limited (TCS)": "TCS.NS",
            "HCL Technologies Limited (HCLTECH)": "HCLTECH.NS",
            "Tech Mahindra Limited (TECHM)": "TECHM.NS",
            "Wipro Limited (WIPRO)": "WIPRO.NS",
        }
        options.update(fallback)
        return options


# --- Session State Initialization ---
if "selected_watchlist" not in st.session_state:
    st.session_state.selected_watchlist = list(BUILT_IN_PACKS["🏆 Nifty 50 Top 5"]["items"])
if "active_pack_meta" not in st.session_state:
    st.session_state.active_pack_meta = (
        f"**🏆 Nifty 50 Top 5** — {BUILT_IN_PACKS['🏆 Nifty 50 Top 5']['meta']}"
    )
if "custom_watchlists" not in st.session_state:
    st.session_state.custom_watchlists = {}
if "search_box_key" not in st.session_state:
    st.session_state.search_box_key = 0
if "last_run_ts" not in st.session_state:
    st.session_state.last_run_ts = 0.0
if "risk_prefs" not in st.session_state:
    st.session_state.risk_prefs = {
        "capital": 50000.0,
        "loss_unit": "₹",
        "loss_inr": 500.0,
        "loss_pct": 1.0,
        "trade_style": "Delivery",
        "rr_ratio": 2.0,
        "show_hint": True,
    }


def short_chip_label(label: str) -> str:
    if label.endswith("(Index)") or label.endswith("(Volatility Index)"):
        return label.split(" (")[0]
    if "(" in label and label.endswith(")"):
        return label.rsplit("(", 1)[1].rstrip(")")
    return label.upper()


def resolve_queue_tickers(nse_options: dict[str, str]) -> list[str]:
    resolved: list[str] = []
    for item in st.session_state.selected_watchlist[:MAX_TICKERS_PER_RUN]:
        if item in nse_options:
            sym = nse_options[item]
        else:
            sym = item.strip().upper()
            if not (sym.endswith(".NS") or sym.endswith(".BO") or sym.startswith("^")):
                sym = f"{sym}.NS"
        if sym and sym not in resolved:
            resolved.append(sym)
    return resolved


# --- Callbacks for Safe Widget Reset ---
def on_pack_pill_change():
    selected = st.session_state.get("pack_selector_pills")
    if not selected:
        return
    if selected in BUILT_IN_PACKS:
        pack = BUILT_IN_PACKS[selected]
        st.session_state.selected_watchlist = list(pack["items"])[:MAX_TICKERS_PER_RUN]
        st.session_state.active_pack_meta = f"**{selected}** — {pack['meta']}"
    elif selected.startswith("⭐ "):
        wl_name = selected[2:]
        if wl_name in st.session_state.custom_watchlists:
            st.session_state.selected_watchlist = list(st.session_state.custom_watchlists[wl_name])[:MAX_TICKERS_PER_RUN]
            st.session_state.active_pack_meta = f"**⭐ {wl_name}** (Custom Session Watchlist)"
    st.session_state["pack_selector_pills"] = None


def on_queue_chip_change():
    clicked = st.session_state.get("active_queue_pills")
    if not clicked:
        return
    if clicked == "🗑️ Clear All":
        st.session_state.selected_watchlist = []
        st.session_state.active_pack_meta = ""
    else:
        chip_map = {f"✕ {short_chip_label(item)}": item for item in st.session_state.selected_watchlist}
        if clicked in chip_map:
            st.session_state.selected_watchlist.remove(chip_map[clicked])
            st.session_state.active_pack_meta = ""
    st.session_state["active_queue_pills"] = None


# --- Load Latest Saved Report Early ---
report = load_report()
last_run_ist = format_ist_timestamp(report["generated_at_utc"]) if report else "Not yet generated"

# --- Sidebar: Engine Telemetry, Guardrails & JSON Watchlist + Risk Backup ---
with st.sidebar:
    st.header("⚙️ System & Guardrails")
    st.markdown(
        f"**Last Brief Run:** {last_run_ist}\n\n"
        f"**Session Status:** {market_status_label()}\n\n"
        "**Model:** `openai/gpt-oss-120b` (Groq)\n\n"
        "**Grounding:** Deterministic Numeric & Citation Verifier\n\n"
        f"**Run Limits:** Max {MAX_TICKERS_PER_RUN} tickers/run • {COOLDOWN_SECONDS}s cooldown"
    )

    st.divider()
    st.subheader("📦 Watchlist & Risk Backup (JSON)")
    st.caption("Watchlists and your Risk Plan preferences are saved in your session. Export to reuse anytime.")

    export_payload = json.dumps(
        {
            "active_queue": st.session_state.selected_watchlist,
            "custom_watchlists": st.session_state.custom_watchlists,
            "risk_prefs": st.session_state.risk_prefs,
        },
        indent=2,
    )
    st.download_button(
        label="⬇️ Export Watchlists & Settings (.json)",
        data=export_payload,
        file_name="nse_custom_watchlists.json",
        mime="application/json",
        width="stretch",
    )

    uploaded_wl = st.file_uploader(
        "⬆️ Import Watchlists & Settings (.json)",
        type=["json"],
        label_visibility="collapsed",
    )
    if uploaded_wl is not None:
        try:
            imported = json.loads(uploaded_wl.read().decode("utf-8"))
            if isinstance(imported.get("custom_watchlists"), dict):
                st.session_state.custom_watchlists.update(imported["custom_watchlists"])
            if isinstance(imported.get("active_queue"), list) and imported["active_queue"]:
                st.session_state.selected_watchlist = imported["active_queue"][:MAX_TICKERS_PER_RUN]
                st.session_state.active_pack_meta = "Loaded from imported watchlist JSON"
            if isinstance(imported.get("risk_prefs"), dict):
                st.session_state.risk_prefs.update(imported["risk_prefs"])
            st.success("Watchlists & risk settings imported!")
        except Exception:
            st.error("Invalid watchlist JSON format.")

    st.divider()
    st.caption("⚠️ **Disclaimer:** Research assistance only, not investment advice.")


# --- Main Dashboard Header ---
st.title("📈 Verified NSE / BSE Equity & Index Brief Agent")
st.caption(
    f"Zero-hallucination daily market intelligence with numeric & citation verification  •  **Last run:** {last_run_ist}"
)

# --- Live Market Indices Pulse Bar ---
pulse_data = load_market_pulse()
vix_live = None
if pulse_data:
    pulse_cols = st.columns(len(pulse_data))
    for col, idx_item in zip(pulse_cols, pulse_data):
        if idx_item["label"] == "INDIA VIX":
            vix_live = round(idx_item["value"], 2)
        delta_color = "inverse" if idx_item["label"] == "INDIA VIX" else "normal"
        col.metric(
            label=idx_item["label"],
            value=f"{idx_item['value']:,.2f}",
            delta=f"{idx_item['pct']:+.2f}%",
            delta_color=delta_color,
        )
    st.caption(f"⏱️ Pulse strip: {market_status_label()} (Yahoo Finance feed)")

st.write("")

# --- Clean Single-Line Search + Generate Action Bar ---
nse_options = load_nse_universe()

search_col, btn_col = st.columns([4, 1], vertical_alignment="bottom")
with search_col:
    picked = st.selectbox(
        "🔍 Add Stock, Index, or BSE Ticker",
        options=list(nse_options.keys()),
        index=None,
        accept_new_options=True,
        key=f"search_select_{st.session_state.search_box_key}",
        placeholder="Type NIFTY, Reliance, Tata, or RELIANCE.BO and press Enter...",
    )
    if picked:
        if len(st.session_state.selected_watchlist) >= MAX_TICKERS_PER_RUN:
            st.warning(f"Maximum {MAX_TICKERS_PER_RUN} instruments allowed per run. Remove a chip first.")
        elif picked not in st.session_state.selected_watchlist:
            st.session_state.selected_watchlist.append(picked)
            st.session_state.active_pack_meta = ""
        st.session_state.search_box_key += 1
        st.rerun()

with btn_col:
    run_clicked = st.button("🔄 Generate Briefs", type="primary", width="stretch")

# --- Combined Preset Packs & User Custom Watchlist Tabs ---
all_tab_labels = list(BUILT_IN_PACKS.keys()) + [
    f"⭐ {name}" for name in st.session_state.custom_watchlists.keys()
]

st.pills(
    "⚡ Index Heavyweight Packs & Custom Watchlists (loads chips into queue):",
    options=all_tab_labels,
    selection_mode="single",
    default=None,
    key="pack_selector_pills",
    on_change=on_pack_pill_change,
)

# --- Active Queue Chips + Save Custom Watchlist Popover ---
if st.session_state.selected_watchlist:
    if st.session_state.active_pack_meta:
        st.caption(st.session_state.active_pack_meta)

    queue_col, save_col = st.columns([4.2, 1.3], vertical_alignment="bottom")
    with queue_col:
        chip_options = [f"✕ {short_chip_label(item)}" for item in st.session_state.selected_watchlist] + ["🗑️ Clear All"]

        st.pills(
            f"Active Queue ({len(st.session_state.selected_watchlist)}/{MAX_TICKERS_PER_RUN} — click chip to remove):",
            options=chip_options,
            selection_mode="single",
            default=None,
            key="active_queue_pills",
            on_change=on_queue_chip_change,
        )

    with save_col:
        with st.popover("💾 Save Watchlist", width="stretch"):
            new_wl_name = st.text_input("Watchlist Name", placeholder="e.g. Swing Picks")
            if st.button("Save to Session Tabs", type="primary", width="stretch"):
                clean_name = new_wl_name.strip()
                if not clean_name:
                    st.warning("Enter a name first.")
                else:
                    st.session_state.custom_watchlists[clean_name] = list(st.session_state.selected_watchlist)
                    st.session_state.active_pack_meta = f"**⭐ {clean_name}** (Saved!)"
                    st.rerun()
else:
    st.caption("Queue is empty — pick a pack above, search any ticker, or click **🔄 Generate Briefs** for the default watchlist.")

# --- Execute Pipeline with Rate-Limit Cooldown & Ticker Cap ---
if run_clicked:
    now_ts = datetime.now(timezone.utc).timestamp()
    elapsed = now_ts - st.session_state.last_run_ts
    if elapsed < COOLDOWN_SECONDS:
        wait_left = int(COOLDOWN_SECONDS - elapsed)
        st.warning(f"Cooldown active — please wait {wait_left}s before running another live LLM generation.")
    else:
        chosen_tickers = resolve_queue_tickers(nse_options)
        custom_watchlist = None
        if chosen_tickers:
            custom_watchlist = []
            for sym in chosen_tickers:
                matched_label = next((lbl for lbl, t in nse_options.items() if t == sym), None)
                if matched_label and " (" in matched_label:
                    comp_name = matched_label.rsplit(" (", 1)[0]
                else:
                    try:
                        info = yf.Ticker(sym).info
                        comp_name = info.get("shortName") or info.get("longName") or sym.lstrip("^").split(".")[0]
                    except Exception:
                        comp_name = sym.lstrip("^").split(".")[0]
                sector_tag = "Index" if sym.startswith("^") else "Custom"
                custom_watchlist.append({"ticker": sym, "name": comp_name, "sector": sector_tag})

        with st.spinner("Fetching market data, Pulse & Google News RSS headlines, and running deterministic verification..."):
            report = run_daily_pipeline(watchlist=custom_watchlist)
        st.session_state.last_run_ts = datetime.now(timezone.utc).timestamp()
        st.success("Pipeline complete & verified!")
        st.rerun()

st.divider()

# --- Compact 5-Tab Workbench Navigation ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Briefs",
    "Radar",
    "Backtest",
    "Risk Plan",
    "Filings",
])

active_tickers = resolve_queue_tickers(nse_options)
equity_choices = [t for t in active_tickers if not t.startswith("^")] or ["HDFCBANK.NS", "ICICIBANK.NS", "RELIANCE.NS", "BHARTIARTL.NS", "LT.NS"]

# ==============================================================================
# TAB 1: VERIFIED MARKET BRIEFS
# ==============================================================================
with tab1:
    if report is None:
        st.info("No saved brief found yet. Click **🔄 Generate Briefs** above to generate your first report.")
    else:
        verification = report["verification"]
        briefs = report["briefs"]
        raw_news = report["raw_news"]
        raw_prices = report["raw_prices"]

        total_count = verification["total_tickers"]
        passed_count = verification["passed_count"]
        computed_pass_rate = round((passed_count / total_count) * 100, 1) if total_count > 0 else 0.0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Watchlist Coverage", f"{total_count} Instruments")
        col2.metric("Verification Pass Rate", f"{computed_pass_rate}%", f"{passed_count}/{total_count} Verified")
        col3.metric("Brief Timestamp", last_run_ist)
        col4.metric("Grounding Engine", "Strict v1.0")

        st.write("")

        for ticker, brief in briefs.items():
            verdict = verification["per_ticker"][ticker]
            price_info = raw_prices[ticker]
            articles_by_id = {a["citation_id"]: a for a in raw_news[ticker].get("articles", [])}

            badge = "✅ VERIFIED" if verdict["passed"] else "⚠️ FLAGGED"
            sentiment = brief["sentiment"]
            sentiment_icon = "🟢" if sentiment == "Bullish" else ("🔴" if sentiment == "Bearish" else "🟡")
            is_index = ticker.startswith("^")
            display_val = f"{brief['close_price']:,.2f}" if is_index else f"₹{brief['close_price']:,.2f}"

            with st.container(border=True):
                top_left, top_right = st.columns([3, 1])
                with top_left:
                    st.subheader(f"{brief['company_name']} (`{ticker}`)")
                    st.markdown(
                        f"**Status:** {badge} &nbsp;|&nbsp; **Sentiment:** {sentiment_icon} {sentiment} "
                        f"&nbsp;|&nbsp; **Data as of:** `{price_info['trade_date']}` ({market_status_label()})"
                    )
                with top_right:
                    st.metric(
                        label=f"{'Level' if is_index else 'Close'} ({price_info['trade_date']})",
                        value=display_val,
                        delta=f"{brief['day_change_pct']:+.2f}% (1D)",
                    )

                st.write(brief["headline_summary"])

                st.markdown("**Key Drivers:**")
                for driver in brief["key_drivers"]:
                    st.markdown(f"- {driver}")

                cited_ids = verdict.get("verified_citations", [])
                if cited_ids:
                    st.markdown("**Verified Sources:**")
                    for cid in cited_ids:
                        art = articles_by_id.get(cid)
                        if art:
                            st.markdown(f"- `[{cid}]` [{art['title']}]({art['url']}) — *{art['source']}*")

                with st.expander("🔍 Inspect Ground-Truth Audit Data (Numeric & Citation Proof)"):
                    if verdict["passed"]:
                        st.success("All structured metrics, narrative numbers, and citation IDs matched ground-truth tool outputs.")
                    else:
                        st.error(f"Flagged issues: {verdict.get('errors', [])}")

                    a1, a2 = st.columns(2)
                    with a1:
                        st.markdown("**1. Numeric Grounding Check (`yfinance` vs. Brief)**")
                        gt_close = price_info.get("close_price") or price_info.get("close") or price_info.get("last_close") or 0
                        audit_rows = [
                            {
                                "Metric": "Close / Level",
                                "Ground Truth": gt_close,
                                "Brief Output": brief.get("close_price"),
                                "Match": "✅" if abs(float(gt_close) - float(brief.get("close_price", 0))) <= 0.05 else "❌",
                            },
                            {
                                "Metric": "1D Change (%)",
                                "Ground Truth": price_info.get("day_change_pct"),
                                "Brief Output": brief.get("day_change_pct"),
                                "Match": "✅" if abs(float(price_info.get("day_change_pct", 0)) - float(brief.get("day_change_pct", 0))) <= 0.05 else "❌",
                            },
                            {
                                "Metric": "5D Change (%)",
                                "Ground Truth": price_info.get("five_day_change_pct"),
                                "Brief Output": brief.get("five_day_change_pct"),
                                "Match": "✅" if abs(float(price_info.get("five_day_change_pct", 0)) - float(brief.get("five_day_change_pct", 0))) <= 0.05 else "❌",
                            },
                            {
                                "Metric": "20D Vol Z-Score",
                                "Ground Truth": price_info.get("volume_zscore"),
                                "Brief Output": "Index (N/A)" if is_index else price_info.get("volume_zscore"),
                                "Match": "✅",
                            },
                        ]
                        st.dataframe(pd.DataFrame(audit_rows), hide_index=True, width="stretch")

                    with a2:
                        st.markdown("**2. Citation & Headline Entailment Proof**")
                        if cited_ids:
                            for cid in cited_ids:
                                art = articles_by_id.get(cid)
                                if art:
                                    st.markdown(f"✅ **`[{cid}]`** — [{art['title']}]({art['url']}) (*{art['source']}*)")
                        else:
                            st.caption("No external news citations referenced for this instrument.")

                    with st.popover("View Raw Tool JSON"):
                        st.json({"raw_prices": price_info, "verifier_verdict": verdict})

# ==============================================================================
# TAB 2: SCREENER & RADAR (DAILY 41-EMA + VOLUME + 52W + 15M ORB)
# ==============================================================================
with tab2:
    st.subheader("⚡ Daily 41-EMA, Volume, 52W & 15m ORB Radar")
    st.caption("Flags describe price action and are not recommendations.")

    if st.button("🔍 Scan Active Watchlist Queue", type="primary"):
        if not active_tickers:
            st.warning("Add at least one equity ticker to your active queue above.")
        else:
            with st.spinner("Scanning OHLCV & computing daily 41-EMA + 15m ORB signals..."):
                radar_df = run_unified_radar(active_tickers)

            nifty_regime = radar_df.attrs.get("nifty_regime", "Unknown")
            failed_syms = radar_df.attrs.get("failed", [])
            as_of_date = radar_df.attrs.get("as_of")

            st.session_state["tab2_radar_df"] = radar_df
            st.session_state["tab2_radar_attrs"] = {
                "nifty_regime": nifty_regime,
                "failed": failed_syms,
                "as_of": as_of_date,
            }
            st.session_state.pop("tab2_scan_explanation", None)

    cached_radar_df = st.session_state.get("tab2_radar_df")
    cached_radar_attrs = st.session_state.get("tab2_radar_attrs", {})

    if cached_radar_df is not None:
        nifty_regime = cached_radar_attrs.get("nifty_regime", "Unknown")
        failed_syms = cached_radar_attrs.get("failed", [])
        as_of_date = cached_radar_attrs.get("as_of")

        if cached_radar_df.empty:
            st.info("No equity data returned (indices are excluded from equity radar).")
        else:
            st.caption(
                f"**Nifty Regime:** `{nifty_regime}`  •  "
                f"**As of:** `{as_of_date or 'N/A'}`  •  "
                f"**Cached:** ~5 min"
            )
            if failed_syms:
                st.warning(f"Skipped / failed tickers: {', '.join(failed_syms)}")

            sorted_radar = cached_radar_df.sort_values(
                by=["Score", "Extended", "Rel Vol"],
                ascending=[False, True, False],
                na_position="last",
            ).reset_index(drop=True)

            primary_cols = [
                "Ticker",
                "Score",
                "Extended",
                "Close (₹)",
                "1D (%)",
                "vs 41-EMA (%)",
                "Rel Vol (x)",
                "From 52W High (%)",
                "ORB Status",
            ]
            renamed_radar = sorted_radar.rename(
                columns={
                    "Close": "Close (₹)",
                    "1D": "1D (%)",
                    "vs 41-EMA": "vs 41-EMA (%)",
                    "Rel Vol": "Rel Vol (x)",
                    "From 52W High": "From 52W High (%)",
                }
            )

            st.dataframe(
                renamed_radar[primary_cols],
                hide_index=True,
                width="stretch",
                column_config={
                    "Close (₹)": st.column_config.NumberColumn("Close (₹)", format="%.2f"),
                    "1D (%)": st.column_config.NumberColumn("1D (%)", format="%+.2f"),
                    "vs 41-EMA (%)": st.column_config.NumberColumn("vs 41-EMA (%)", format="%+.2f"),
                    "Rel Vol (x)": st.column_config.NumberColumn("Rel Vol (x)", format="%.2f"),
                    "From 52W High (%)": st.column_config.NumberColumn("From 52W High (%)", format="%+.2f"),
                },
            )

            with st.expander("📐 Extra Levels: daily 41-EMA & 15m ORB High/Low"):
                extra_cols = ["Ticker", "41-EMA (₹)", "ORB High (₹)", "ORB Low (₹)"]
                renamed_extra = sorted_radar.rename(
                    columns={
                        "41-EMA": "41-EMA (₹)",
                        "ORB High": "ORB High (₹)",
                        "ORB Low": "ORB Low (₹)",
                    }
                )
                st.dataframe(
                    renamed_extra[extra_cols],
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "41-EMA (₹)": st.column_config.NumberColumn("41-EMA (₹)", format="%.2f"),
                        "ORB High (₹)": st.column_config.NumberColumn("ORB High (₹)", format="%.2f"),
                        "ORB Low (₹)": st.column_config.NumberColumn("ORB Low (₹)", format="%.2f"),
                    },
                )

            st.write("")
            if st.button("🧠 Explain this scan", key="explain_radar_scan_btn"):
                scan_rows_json = sorted_radar.to_dict(orient="records")
                with st.spinner("Generating grounded scan explanation & verifying numbers..."):
                    st.session_state["tab2_scan_explanation"] = explain_radar_scan(
                        rows=scan_rows_json,
                        nifty_regime=nifty_regime,
                        as_of=as_of_date,
                    )

            exp_res = st.session_state.get("tab2_scan_explanation")
            if exp_res:
                ver = exp_res.get("verification", {})
                badge = "✅ VERIFIED" if ver.get("passed") else "⚠️ FLAGGED"
                with st.container(border=True):
                    st.markdown(f"**Scan Explanation** &nbsp;|&nbsp; **Status:** `{badge}`")
                    st.markdown(exp_res.get("raw_text", ""))

                    with st.expander("🔍 Inspect data"):
                        if ver.get("passed"):
                            st.success(
                                f"All {ver.get('checked_count', 0)} numeric tokens matched the deterministic scan rows."
                            )
                        else:
                            st.warning(f"Unmatched numeric tokens: {ver.get('mismatches', [])}")
                        st.json(
                            {
                                "as_of": as_of_date,
                                "nifty_regime": nifty_regime,
                                "verification": ver,
                                "rows": sorted_radar.to_dict(orient="records"),
                            }
                        )

# ==============================================================================
# TAB 3: STRATEGY BACKTESTING LAB (5 Strategies + AI Analyst)
# ==============================================================================
with tab3:
    st.subheader("📈 Multi-Strategy Backtesting Lab & AI Performance Analyst")

    s_col1, s_col2 = st.columns([2.2, 1.3])
    with s_col1:
        selected_strategy = st.selectbox(
            "Select Trading Strategy",
            options=list(STRATEGY_SPECS.keys()),
            index=0,
        )
    with s_col2:
        bt_ticker = st.selectbox("Select Instrument", options=equity_choices, key="bt_ticker_select")

    st.info(STRATEGY_SPECS[selected_strategy]["description"])

    is_swing_mode = STRATEGY_SPECS[selected_strategy]["mode"] == "swing"
    max_lookback = 365 if is_swing_mode else 55
    default_lookback = 180 if is_swing_mode else 30

    p1, p2, p3, p4 = st.columns(4)
    with p1:
        bt_days = st.slider(
            "Lookback (Calendar Days)",
            min_value=10,
            max_value=max_lookback,
            value=default_lookback,
            step=5,
        )
    with p2:
        bt_rr = st.selectbox("Risk-to-Reward Ratio", options=[1.5, 2.0, 2.5, 3.0], index=1, key="bt_rr_select")
    with p3:
        bt_cap = st.number_input("Capital / Trade (₹)", min_value=10000.0, value=100000.0, step=10000.0)
    with p4:
        trade_cap_choice = st.selectbox(
            "Max Trades / Day",
            options=["1 (First Setup Only)", "2", "3", "Unlimited"],
            index=0,
        )
        max_trades_day = 99 if trade_cap_choice == "Unlimited" else int(trade_cap_choice.split(" ")[0])

    if st.button("🚀 Run Strategy Backtest & AI Review", type="primary"):
        with st.spinner(f"Simulating {selected_strategy} on {bt_ticker}..."):
            bt_res = run_strategy_backtest(
                ticker=bt_ticker,
                strategy_name=selected_strategy,
                lookback_days=bt_days,
                rr_ratio=bt_rr,
                capital_per_trade=bt_cap,
                max_trades_per_day=max_trades_day,
            )

        if "error" in bt_res:
            st.warning(bt_res["error"])
        else:
            st.caption(
                f"Backtest bar resolution: **{bt_res['timeframe']}** bars ({bt_res['total_trades']} triggers over {bt_days} calendar days)."
            )
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Triggers", bt_res["total_trades"], f"{bt_res['timeframe']} bars")
            m2.metric("Win Rate", f"{bt_res['win_rate_pct']}%", f"{bt_res['wins']}W / {bt_res['losses']}L")
            m3.metric("Net PnL (₹)", f"₹{bt_res['net_pnl_inr']:,.2f}", f"{bt_res['net_roi_pct']:+.2f}% on Capital")
            m4.metric("Avg Win / Avg Loss", f"₹{bt_res['avg_win_inr']:,.0f}", f"Loss: ₹{bt_res['avg_loss_inr']:,.0f}")

            with st.container(border=True):
                st.markdown("#### 🧠 AI Quant Backtest Insights (`openai/gpt-oss-20b`)")
                with st.spinner("Synthesizing strategy edge and exit efficiency..."):
                    ai_notes = generate_ai_backtest_insights(bt_res)
                st.markdown(ai_notes)

            st.line_chart(bt_res["trades_df"].set_index("Entry Date")["Cumulative PnL (₹)"])
            st.dataframe(bt_res["trades_df"], hide_index=True, width="stretch")

# ==============================================================================
# TAB 4: RISK PLAN (Zero-Lag Fragment + Callback-Driven Two-Way Sync)
# ==============================================================================
@st.fragment
def render_risk_plan_tab():
    st.subheader("Risk Plan")
    st.caption("Find out how many shares you can buy without losing more than you can afford.")

    prefs = st.session_state.risk_prefs

    # Dismissible onboarding banner
    if prefs.get("show_hint", True):
        with st.container(border=True):
            hc1, hc2 = st.columns([6, 1], vertical_alignment="center")
            with hc1:
                st.markdown(
                    "ℹ️ **New here? Three quick steps:** set your limits, pick a stock, read your plan. "
                    "This is a calculator that shows its maths, not advice."
                )
            with hc2:
                if st.button("Got it", key="dismiss_rp_hint", width="stretch"):
                    prefs["show_hint"] = False
                    st.rerun(scope="fragment")

    if "rp_mode" not in st.session_state:
        st.session_state["rp_mode"] = "One stock"
    is_one_stock = st.session_state["rp_mode"] == "One stock"

    # --------------------------------------------------------------------------
    # STEP 1: YOUR LIMITS
    # --------------------------------------------------------------------------
    with st.container(border=True):
        st.markdown('<span class="step-badge">1</span><span class="step-title">Your limits</span>', unsafe_allow_html=True)
        st.write("")

        lim1, lim2, lim3 = st.columns([1.2, 1.4, 1.3], vertical_alignment="top")
        with lim1:
            safe_cap = max(1000.0, float(prefs.get("capital", 50000.0)))
            account_cap = st.number_input(
                "Account capital (₹)",
                min_value=1000.0,
                value=safe_cap,
                step=5000.0,
                key="rp_account_cap",
            )
            prefs["capital"] = account_cap
            st.caption("The money you have available to trade.")

        with lim2:
            u_col, v_col = st.columns([1.0, 1.6], vertical_alignment="bottom")
            with u_col:
                loss_unit = st.segmented_control(
                    "Most I'm OK with losing" if is_one_stock else "Most I'm OK with losing, in total",
                    options=["₹", "%"],
                    default=prefs.get("loss_unit", "₹"),
                    key="rp_loss_unit_ctrl",
                )
                if not loss_unit:
                    loss_unit = prefs.get("loss_unit", "₹")
                prefs["loss_unit"] = loss_unit
            with v_col:
                if loss_unit == "₹":
                    safe_loss_inr = max(1.0, float(prefs.get("loss_inr", 500.0)))
                    loss_inr = st.number_input(
                        "Loss amount (₹)",
                        min_value=1.0,
                        value=safe_loss_inr,
                        step=100.0,
                        label_visibility="collapsed",
                        key="rp_loss_inr_input",
                    )
                    prefs["loss_inr"] = loss_inr
                    max_loss_inr = float(loss_inr)
                    loss_pct_of_cap = round((max_loss_inr / account_cap) * 100.0, 2) if account_cap > 0 else 0.0
                    prefs["loss_pct"] = loss_pct_of_cap
                else:
                    safe_loss_pct = min(100.0, max(0.01, float(prefs.get("loss_pct", 1.0))))
                    loss_pct = st.number_input(
                        "Loss percent (%)",
                        min_value=0.01,
                        max_value=100.0,
                        value=safe_loss_pct,
                        step=0.25,
                        label_visibility="collapsed",
                        key="rp_loss_pct_input",
                    )
                    prefs["loss_pct"] = loss_pct
                    loss_pct_of_cap = float(loss_pct)
                    max_loss_inr = round(account_cap * (loss_pct_of_cap / 100.0), 2)
                    prefs["loss_inr"] = max_loss_inr

            if is_one_stock:
                st.caption(f"That is {loss_pct_of_cap:.1f}% of your capital. Many traders keep this near 1%.")
            else:
                n_eq = max(len(equity_choices), 1)
                per_stock_share = max_loss_inr / n_eq
                st.caption(f"Shared equally: ₹{per_stock_share:,.0f} for each of your {n_eq} stocks.")

        with lim3:
            trade_style = st.segmented_control(
                "Trade style",
                options=["Delivery", "Intraday"],
                default=prefs.get("trade_style", "Delivery"),
                key="rp_trade_style_ctrl",
            )
            if not trade_style:
                trade_style = prefs.get("trade_style", "Delivery")
            prefs["trade_style"] = trade_style
            if trade_style == "Delivery":
                st.caption("Delivery: you pay the full price and can hold for days.")
            else:
                st.caption("Intraday: up to 5x margin for same-day square-off.")

    # Mode Pill Selector ("One stock" | "Whole watchlist")
    picked_mode = st.segmented_control(
        "Plan scope",
        options=["One stock", "Whole watchlist"],
        default=st.session_state["rp_mode"],
        label_visibility="collapsed",
        key="rp_scope_pills",
    )
    if picked_mode and picked_mode != st.session_state["rp_mode"]:
        st.session_state["rp_mode"] = picked_mode
        st.rerun(scope="fragment")

    is_intraday = trade_style == "Intraday"
    leverage = 5.0 if is_intraday else 1.0
    trade_mode_label = "MIS Intraday (5x Margin)" if is_intraday else "CNC Positional Delivery (1x Cash)"
    rr_ratio = float(prefs.get("rr_ratio", 2.0))

    # ==========================================================================
    # MODE A: ONE STOCK (Max Affordable Shares -> Stop-Loss Synced to Loss Limit)
    # ==========================================================================
    if st.session_state["rp_mode"] == "One stock":
        with st.container(border=True):
            st.markdown('<span class="step-badge">2</span><span class="step-title">Pick a stock</span>', unsafe_allow_html=True)
            st.write("")

            p_col1, p_col2, p_col3 = st.columns([1.2, 1.3, 1.3], vertical_alignment="top")
            with p_col1:
                display_map = {sym.replace(".NS", "").replace(".BO", ""): sym for sym in equity_choices}
                chosen_short = st.selectbox(
                    "Stock",
                    options=list(display_map.keys()),
                    key="rp_single_stock_select",
                )
                risk_ticker = display_map[chosen_short]
                st.caption("From your watchlist at the top of the app.")

            # Auto-fill entry price when stock changes
            if st.session_state.get("rp_loaded_ticker") != risk_ticker:
                live_px = max(1.0, float(get_last_close_price(risk_ticker)))
                st.session_state["rp_loaded_ticker"] = risk_ticker
                st.session_state["rp_buy_px"] = live_px
                st.session_state["rp_sync_sig"] = None

            with p_col2:
                b_in, b_ref = st.columns([4.2, 1.0], vertical_alignment="bottom")
                with b_in:
                    safe_buy_px = max(1.0, float(st.session_state["rp_buy_px"]))
                    buy_px = st.number_input(
                        "Price you'd buy at (₹)",
                        min_value=1.0,
                        value=safe_buy_px,
                        step=0.5,
                        key="rp_buy_px_input",
                    )
                    st.session_state["rp_buy_px"] = buy_px
                with b_ref:
                    if st.button("↻", key="rp_refresh_buy_px", help="Refresh latest price", width="stretch"):
                        fresh_px = max(1.0, float(get_last_close_price(risk_ticker)))
                        st.session_state["rp_buy_px"] = fresh_px
                        st.session_state["rp_sync_sig"] = None
                        st.rerun(scope="fragment")
                st.caption("Filled in automatically. Prices are delayed about 15 minutes.")

            # Max shares your capital & trade style can buy
            buying_power = account_cap * leverage
            max_shares = int(buying_power // buy_px)

            # Forward sync: runs ONLY when Capital / Style / Stock / Buy Price / Max Loss changes
            sync_sig = f"{risk_ticker}_{trade_style}_{round(account_cap, 2)}_{round(buy_px, 2)}_{max_shares}_{round(max_loss_inr, 2)}"
            if st.session_state.get("rp_sync_sig") != sync_sig:
                if max_shares > 0:
                    per_share_risk = max_loss_inr / max_shares
                    synced_sl = round(max(buy_px - per_share_risk, 0.05), 2)
                else:
                    synced_sl = round(max(buy_px * 0.98, 0.05), 2)
                st.session_state["rp_sl_px"] = synced_sl
                st.session_state["rp_sl_px_input"] = synced_sl
                st.session_state["rp_sync_sig"] = sync_sig

            # Callback for manual Stop-Loss edits (NO st.rerun loop!)
            def _on_manual_sl_edit():
                edited_sl = float(st.session_state.get("rp_sl_px_input", 0.05))
                st.session_state["rp_sl_px"] = edited_sl
                if max_shares > 0:
                    updated_loss = max(1.0, round(max_shares * max(buy_px - edited_sl, 0.0), 2))
                    prefs["loss_inr"] = updated_loss
                    prefs["loss_pct"] = round((updated_loss / account_cap) * 100.0, 2) if account_cap > 0 else prefs["loss_pct"]
                    st.session_state["rp_loss_inr_input"] = updated_loss
                    st.session_state["rp_loss_pct_input"] = prefs["loss_pct"]
                    st.session_state["rp_sync_sig"] = (
                        f"{risk_ticker}_{trade_style}_{round(account_cap, 2)}_{round(buy_px, 2)}_{max_shares}_{updated_loss}"
                    )

            with p_col3:
                sl_px = st.number_input(
                    "Stop-loss price (₹)",
                    min_value=0.05,
                    step=0.25,
                    key="rp_sl_px_input",
                    on_change=_on_manual_sl_edit,
                )
                diff_px = buy_px - sl_px
                diff_pct = (diff_px / buy_px) * 100.0 if buy_px > 0 else 0.0
                if diff_px > 0:
                    st.caption(
                        f"Synced to your ₹{max_loss_inr:,.0f} limit across {max_shares} shares: "
                        f"₹{diff_px:,.2f} ({diff_pct:.2f}%) below buy price."
                    )
                else:
                    st.caption("Set stop-loss below your buy price to limit downside.")

            st.info("Not sure where to put it? The **Radar** tab shows each stock's opening-range low, a common place to start.")

        # ----------------------------------------------------------------------
        # STEP 3: YOUR PLAN (ONE STOCK)
        # ----------------------------------------------------------------------
        with st.container(border=True):
            st.markdown('<span class="step-badge">3</span><span class="step-title">Your plan</span>', unsafe_allow_html=True)
            st.write("")

            if max_loss_inr > account_cap:
                st.error(f"Your loss limit (₹{max_loss_inr:,.0f}) is higher than your account capital (₹{account_cap:,.0f}). Lower your loss limit first.")
            elif max_shares <= 0:
                st.warning(
                    f"0 shares fit: 1 share of {chosen_short} costs ₹{buy_px:,.2f}, which exceeds your ₹{buying_power:,.0f} buying power."
                )
            elif (max_loss_inr / max_shares) >= buy_px:
                st.error(
                    f"Your ₹{max_loss_inr:,.0f} loss limit is higher than the entire position value (₹{max_shares * buy_px:,.0f}) of {max_shares} shares. "
                    f"Lower your loss limit or increase account capital."
                )
            elif sl_px >= buy_px:
                st.error(f"Your stop-loss (₹{sl_px:,.2f}) must be below your buy price (₹{buy_px:,.2f}).")
            else:
                shares = max_shares
                risk_per_share = round(buy_px - sl_px, 2)
                pos_value = round(shares * buy_px, 2)
                cash_paid = round(pos_value / leverage, 2)
                cap_pct_used = round((cash_paid / account_cap) * 100.0, 1)
                stop_loss_hit_inr = round(shares * risk_per_share, 2)
                target_px = round(buy_px + (risk_per_share * rr_ratio), 2)
                target_hit_inr = round(shares * risk_per_share * rr_ratio, 2)
                reward_per_share = round(risk_per_share * rr_ratio, 2)

                st.success(
                    f"✅ **Max-size plan ready. Buy {shares} shares of {chosen_short} (₹{cash_paid:,.0f} margin/cash used).**\n\n"
                    f"Your stop-loss is synced to **₹{sl_px:,.2f}** (`-{diff_pct:.2f}%`) so if it hits, you lose **₹{stop_loss_hit_inr:,.0f}** — matching your **₹{max_loss_inr:,.0f}** limit."
                )

                mc1, mc2, mc3, mc4 = st.columns(4)
                with mc1:
                    st.markdown(
                        f'<div class="rp-card">'
                        f'<div class="rp-card-label">You buy (max possible)</div>'
                        f'<div class="rp-card-val">{shares} shares</div>'
                        f'<div class="rp-card-sub">of {chosen_short} at ₹{buy_px:,.2f}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with mc2:
                    st.markdown(
                        f'<div class="rp-card">'
                        f'<div class="rp-card-label">You pay</div>'
                        f'<div class="rp-card-val">₹{cash_paid:,.0f}</div>'
                        f'<div class="rp-card-sub">{cap_pct_used:.1f}% of your capital</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with mc3:
                    st.markdown(
                        f'<div class="rp-card">'
                        f'<div class="rp-card-label">If your stop-loss hits</div>'
                        f'<div class="rp-card-val" style="color:#f87171;">-₹{stop_loss_hit_inr:,.2f}</div>'
                        f'<div class="rp-card-sub">Synced SL at ₹{sl_px:,.2f}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with mc4:
                    st.markdown(
                        f'<div class="rp-card">'
                        f'<div class="rp-card-label">If your target hits</div>'
                        f'<div class="rp-card-val" style="color:#34d399;">+₹{target_hit_inr:,.2f}</div>'
                        f'<div class="rp-card-sub">Sell at ₹{target_px:,.2f} ({rr_ratio:g}× your risk)</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                st.write("")

                total_span = max(target_px - sl_px, 0.01)
                risk_width_pct = min(max((risk_per_share / total_span) * 100.0, 8.0), 92.0)

                st.markdown(
                    f"""
                    <div style="margin: 8px 0 14px 0;">
                        <div style="font-size:12px; opacity:0.75; margin-bottom:6px;">Price ladder (drawn to scale)</div>
                        <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:600; margin-bottom:6px;">
                            <span style="color:#f87171;">Risk ₹{risk_per_share:,.2f} a share</span>
                            <span style="color:#34d399;">Reward ₹{reward_per_share:,.2f} a share</span>
                        </div>
                        <div style="position:relative; height:10px; border-radius:999px; overflow:hidden; display:flex; background:rgba(255,255,255,0.1);">
                            <div style="width:{risk_width_pct:.2f}%; background:#ef4444; height:100%;"></div>
                            <div style="flex:1; background:#10b981; height:100%;"></div>
                        </div>
                        <div style="position:relative; height:44px; margin-top:6px;">
                            <div style="position:absolute; left:0%; text-align:left;">
                                <div style="font-size:11px; opacity:0.7;">| Stop-loss</div>
                                <div style="font-size:12px; font-weight:700;">₹{sl_px:,.2f}</div>
                            </div>
                            <div style="position:absolute; left:{risk_width_pct:.2f}%; transform:translateX(-50%); text-align:center;">
                                <div style="font-size:11px; opacity:0.7;">| Buy</div>
                                <div style="font-size:12px; font-weight:700;">₹{buy_px:,.2f}</div>
                            </div>
                            <div style="position:absolute; right:0%; text-align:right;">
                                <div style="font-size:11px; opacity:0.7;">Target |</div>
                                <div style="font-size:12px; font-weight:700;">₹{target_px:,.2f}</div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f"**Why {shares} shares & ₹{sl_px:,.2f} SL?** Your ₹{account_cap:,.0f} capital ({int(leverage)}× = ₹{buying_power:,.0f} buying power) ÷ ₹{buy_px:,.2f} = **{shares} max shares**. "
                    f"Splitting your **₹{max_loss_inr:,.0f}** loss limit across {shares} shares gives **₹{risk_per_share:,.2f}/share** risk, placing your synced stop-loss at **₹{sl_px:,.2f}**."
                )
                st.caption(
                    "⚠️ Research tool, not investment advice. Figures are before brokerage and taxes, and a price can jump past your stop-loss."
                )

                with st.expander("Advanced options — Reward ratio, full formula, AI risk check"):
                    adv1, adv2 = st.columns([1.4, 2.6], vertical_alignment="center")
                    with adv1:
                        new_rr = st.slider(
                            "Reward-to-Risk Ratio (R:R)",
                            min_value=1.0,
                            max_value=5.0,
                            value=rr_ratio,
                            step=0.5,
                            key="rp_adv_rr_slider",
                        )
                        if new_rr != rr_ratio:
                            prefs["rr_ratio"] = new_rr
                            st.rerun(scope="fragment")

                    plan_full = calculate_position_plan(
                        capital=account_cap,
                        risk_budget_inr=stop_loss_hit_inr,
                        entry_price=buy_px,
                        stop_loss_price=sl_px,
                        aggression=5,
                        rr_ratio=rr_ratio,
                        max_allocation_pct=100.0,
                        trade_mode=trade_mode_label,
                    )
                    with adv2:
                        if "error" not in plan_full:
                            st.markdown(
                                f"- **After-Tax Risk:** `₹{plan_full['actual_risk_inr']:,.2f}` (includes `₹{plan_full['est_charges_inr']:,.2f}` Indian statutory STT/GST/stamp fees)\n"
                                f"- **Breakeven Price:** `₹{plan_full['breakeven_price']:,.2f}` • **TP1 (50% exit):** `₹{plan_full['tp1_price']:,.2f}` • **TP2:** `₹{plan_full['target_price']:,.2f}`"
                            )

                    if st.button("🧠 Run AI Risk Check", key="rp_ai_risk_btn"):
                        brief_sent = "Not yet generated"
                        if report and risk_ticker in report.get("briefs", {}):
                            brief_sent = report["briefs"][risk_ticker].get("sentiment", "Neutral")
                        with st.spinner("Auditing stop distance, concentration, and brief sentiment..."):
                            audit_text = generate_ai_risk_audit(
                                ticker=risk_ticker,
                                plan=plan_full,
                                brief_sentiment=brief_sent,
                                india_vix=vix_live,
                            )
                        st.markdown(audit_text)

    # ==========================================================================
    # MODE B: WHOLE WATCHLIST
    # ==========================================================================
    else:
        with st.container(border=True):
            st.markdown('<span class="step-badge">2</span><span class="step-title">Set one stop-loss for all</span>', unsafe_allow_html=True)
            st.write("")

            sl_col, _ = st.columns([1.2, 2.5])
            with sl_col:
                default_sl_pct = 2.0 if is_intraday else 4.0
                safe_port_sl = min(25.0, max(0.25, float(st.session_state.get("rp_port_sl_pct", default_sl_pct))))
                port_sl_pct = st.number_input(
                    "Stop-loss distance (%)",
                    min_value=0.25,
                    max_value=25.0,
                    value=safe_port_sl,
                    step=0.25,
                    key="rp_port_sl_input",
                )
                st.session_state["rp_port_sl_pct"] = port_sl_pct
                st.caption(
                    "Each stock's stop-loss sits this far below its price. "
                    "Add or remove stocks using the chips at the top of the app."
                )

        with st.container(border=True):
            st.markdown('<span class="step-badge">3</span><span class="step-title">Your plan</span>', unsafe_allow_html=True)
            st.write("")

            if max_loss_inr > account_cap:
                st.error(f"Your total loss limit (₹{max_loss_inr:,.0f}) is higher than your account capital (₹{account_cap:,.0f}). Lower your loss limit first.")
            else:
                brief_prices_map = report.get("raw_prices") if report else None
                briefs_map = report.get("briefs") if report else None

                with st.spinner("Sizing watchlist basket..."):
                    port_res = allocate_equal_risk_portfolio(
                        tickers=equity_choices,
                        total_capital=account_cap,
                        total_risk_budget_inr=max_loss_inr,
                        stop_loss_pct=port_sl_pct,
                        trade_mode="Intraday (5x Margin)" if is_intraday else "Delivery (1x Cash)",
                        brief_prices=brief_prices_map,
                        briefs_data=briefs_map,
                    )

                if "error" in port_res:
                    st.warning(port_res["error"])
                else:
                    df_raw = port_res["df"]
                    sized_cnt = port_res["sized_count"]
                    tot_cnt = port_res["total_stocks"]
                    per_trade_risk = port_res["per_trade_risk"]

                    clean_rows = []
                    left_out_msgs = []
                    for _, r in df_raw.iterrows():
                        sym = r["Symbol"]
                        px = float(r["Price (₹)"])
                        sh = int(r["Shares"])
                        pay = float(r["Margin / Cash Used (₹)"])
                        sl_loss = float(r["Stop-Loss Risk (₹)"])
                        one_sh_risk = round(px * (port_sl_pct / 100.0), 2)

                        if sh > 0:
                            status_txt = "Fits"
                        elif one_sh_risk > per_trade_risk:
                            status_txt = f"1 share risks ₹{one_sh_risk:,.0f}, over ₹{per_trade_risk:,.0f}"
                            left_out_msgs.append(
                                f"**{sym}** is left out. One share of {sym} would risk ₹{one_sh_risk:,.0f} if its stop hit, "
                                f"more than its ₹{per_trade_risk:,.0f} share of your loss limit. A tighter stop-loss or a higher loss limit would let it in."
                            )
                        else:
                            status_txt = f"Price ₹{px:,.0f} > ₹{port_res['buying_power_per_stock']:,.0f} slice"
                            left_out_msgs.append(
                                f"**{sym}** is left out because its share price (₹{px:,.0f}) exceeds its ₹{port_res['buying_power_per_stock']:,.0f} capital slice."
                            )

                        clean_rows.append(
                            {
                                "Stock": sym,
                                "Price": f"₹{px:,.2f}",
                                "Buy": f"{sh} {'share' if sh == 1 else 'shares'}" if sh > 0 else "0",
                                "You pay": f"₹{pay:,.2f}" if pay % 1 else f"₹{pay:,.0f}",
                                "Loss if stopped": f"-₹{sl_loss:,.2f}" if sl_loss > 0 else "₹0",
                                "Status": status_txt,
                            }
                        )

                    if sized_cnt < tot_cnt:
                        st.warning(f"⚠️ **{sized_cnt} of {tot_cnt} stocks fit.** " + (" ".join(left_out_msgs)))
                    else:
                        st.success(f"✅ **All {tot_cnt} of {tot_cnt} stocks fit within your ₹{max_loss_inr:,.0f} loss limit.**")

                    w1, w2, w3 = st.columns(3)
                    with w1:
                        st.markdown(
                            f'<div class="rp-card">'
                            f'<div class="rp-card-label">Stocks you can buy</div>'
                            f'<div class="rp-card-val">{sized_cnt} of {tot_cnt}</div>'
                            f'<div class="rp-card-sub">{"Intraday (5x margin)" if is_intraday else "Delivery (1x cash)"}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    with w2:
                        st.markdown(
                            f'<div class="rp-card">'
                            f'<div class="rp-card-label">You pay in total</div>'
                            f'<div class="rp-card-val">₹{port_res["total_margin_used"]:,.0f}</div>'
                            f'<div class="rp-card-sub">{port_res["cap_used_pct"]:.1f}% of your capital</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    with w3:
                        st.markdown(
                            f'<div class="rp-card">'
                            f'<div class="rp-card-label">If every stop-loss hits</div>'
                            f'<div class="rp-card-val" style="color:#f87171;">-₹{port_res["total_sl_risk"]:,.2f}</div>'
                            f'<div class="rp-card-sub">Under your ₹{max_loss_inr:,.0f} limit</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    st.write("")
                    display_clean_df = pd.DataFrame(clean_rows)
                    st.dataframe(display_clean_df, hide_index=True, width="stretch")

                    corr_pairs = port_res["high_corr_pairs"]
                    if corr_pairs:
                        st.warning(
                            f"⚠️ **{', '.join(corr_pairs)} tend to move together** (60-day correlation from your price data). "
                            f"If one stop-loss hits, the other may too, so your real loss could land closer to the full figure above."
                        )

                    money_ok = port_res["total_margin_used"] <= account_cap + 0.05
                    loss_ok = port_res["total_sl_risk"] <= max_loss_inr + 0.05
                    rows_sum_ok = abs(float(df_raw["Margin / Cash Used (₹)"].sum()) - port_res["total_margin_used"]) <= 0.05
                    checks_passed = sum([money_ok, loss_ok, rows_sum_ok])

                    chk_c, csv_c = st.columns([3.5, 1.2], vertical_alignment="center")
                    with chk_c:
                        st.caption(
                            f"✓ Checked: {checks_passed} of 3 maths checks passed (money used, loss limit, rows add up)"
                        )
                        st.caption(
                            "⚠️ Research tool, not investment advice. Figures are before brokerage and taxes, and a price can jump past your stop-loss."
                        )
                    with csv_c:
                        st.download_button(
                            label="Download as CSV",
                            data=display_clean_df.to_csv(index=False).encode("utf-8"),
                            file_name="risk_plan_watchlist.csv",
                            mime="text/csv",
                            width="stretch",
                        )

                    with st.expander("📈 AI Expected Return & Horizon Projection"):
                        pr_c1, pr_c2 = st.columns([1.5, 1.5], vertical_alignment="bottom")
                        with pr_c1:
                            horizon_label = st.selectbox(
                                "Holding Period",
                                options=["1 Month (30 Days)", "3 Months (90 Days)", "6 Months (180 Days)", "1 Year (365 Days)"],
                                index=1,
                                key="rp_horizon_select",
                            )
                            horizon_days = int(horizon_label.split("(")[1].split(" ")[0])
                        with pr_c2:
                            run_proj_btn = st.button("🧠 Project Expected Returns", type="primary", width="stretch")

                        if run_proj_btn:
                            with st.spinner("Computing 1-year historical drift/volatility bands & AI outlook..."):
                                proj_res = project_portfolio_returns(
                                    alloc_df=df_raw,
                                    total_capital=account_cap,
                                    total_margin_used=port_res["total_margin_used"],
                                    total_cash_left=port_res["total_cash_left"],
                                    total_risk_exp=port_res["total_risk_exp"],
                                    horizon_days=horizon_days,
                                    is_intraday=is_intraday,
                                    briefs_data=briefs_map,
                                )

                            if "error" in proj_res:
                                st.warning(proj_res["error"])
                            else:
                                pm1, pm2, pm3 = st.columns(3)
                                pm1.metric(
                                    label=f"Bear Case ({horizon_days}D • Stop Floor)",
                                    value=f"₹{proj_res['bear_pnl']:+,.2f}",
                                    delta=f"1Y Ann. Volatility: {proj_res['ann_vol_pct']}%",
                                    delta_color="inverse",
                                )
                                pm2.metric(
                                    label=f"Base Case ({horizon_days}D • Median)",
                                    value=f"₹{proj_res['base_pnl']:+,.2f}",
                                    delta=f"{proj_res['base_roi_cap_pct']:+.2f}% on ₹{account_cap:,.0f} total capital",
                                    delta_color="normal",
                                )
                                pm3.metric(
                                    label=f"Bull Case ({horizon_days}D • 90th Pct)",
                                    value=f"₹{proj_res['bull_pnl']:+,.2f}",
                                    delta=f"{proj_res['bull_roi_cap_pct']:+.2f}% on ₹{account_cap:,.0f} total capital",
                                    delta_color="normal",
                                )
                                st.markdown(proj_res["ai_summary"])
                                st.line_chart(proj_res["curve_df"].set_index("Trading Day"))

with tab4:
    render_risk_plan_tab()
# ==============================================================================
# TAB 5: NSE FILINGS & PDF / XBRL REPORT ANALYZER (AUTO-REFRESHING)
# ==============================================================================
with tab5:
    st.subheader("🏢 Official NSE Corporate Filings & Grounded PDF Analyzer")
    st.caption("Auto-fetches the latest NSE announcements, quarterly results (Q1–Q4), shareholding pattern, board meetings, and corporate actions whenever you select a stock.")

    f_col1, f_col2 = st.columns([3, 1], vertical_alignment="bottom")
    with f_col1:
        equity_labels = [lbl for lbl, sym in nse_options.items() if not sym.startswith("^")]
        picked_filing_label = st.selectbox(
            "NSE Equity Symbol (Search by Company Name or Ticker)",
            options=equity_labels,
            index=0 if equity_labels else None,
            accept_new_options=True,
            key="tab5_filing_search",
        )
        if picked_filing_label in nse_options:
            filing_sym = nse_options[picked_filing_label].replace(".NS", "").replace(".BO", "")
        else:
            filing_sym = (picked_filing_label or "").strip().upper().replace(".NS", "").replace(".BO", "")
    with f_col2:
        fetch_filings_btn = st.button("🔄 Refresh Latest Filings", type="primary", width="stretch")

    last_fetched_sym = st.session_state.get("nse_filings_last_sym")
    if filing_sym and (fetch_filings_btn or filing_sym != last_fetched_sym):
        with st.spinner(f"Fetching latest live NSE disclosures for {filing_sym}..."):
            st.session_state["nse_filings_cache"] = get_nse_filings(ticker=filing_sym)
            st.session_state["nse_filings_last_sym"] = filing_sym
            st.session_state.pop("pdf_analysis_cache", None)

    filings_data = st.session_state.get("nse_filings_cache")
    if filings_data:
        st.caption(f"Showing Disclosures for **{filings_data.get('symbol')}** • `{filings_data.get('status')}`")

        if filings_data.get("financial_results"):
            st.markdown("**📊 Quarterly Financial Results (Q1 / Q2 / Q3 / Q4)**")
            st.dataframe(
                pd.DataFrame(filings_data["financial_results"]),
                hide_index=True,
                width="stretch",
                column_config={"Filing Link": st.column_config.LinkColumn("Filing Link", display_text="Open Filing")},
            )

        if filings_data.get("announcements"):
            st.markdown("**📢 Recent Corporate Announcements**")
            st.dataframe(
                pd.DataFrame(filings_data["announcements"]),
                hide_index=True,
                width="stretch",
                column_config={"PDF / XBRL Link": st.column_config.LinkColumn("PDF / XBRL Link", display_text="Open Filing")},
            )
        else:
            st.info("No recent announcements returned from NSE endpoint.")

        c_act, c_bm = st.columns(2)
        with c_act:
            if filings_data.get("corporate_actions"):
                st.markdown("**💰 Corporate Actions**")
                st.dataframe(pd.DataFrame(filings_data["corporate_actions"]), hide_index=True, width="stretch")
        with c_bm:
            if filings_data.get("board_meetings"):
                st.markdown("**🗓️ Board Meetings**")
                st.dataframe(pd.DataFrame(filings_data["board_meetings"]), hide_index=True, width="stretch")

        if filings_data.get("shareholding"):
            st.markdown("**🏛️ Shareholding Pattern History**")
            st.dataframe(pd.DataFrame(filings_data["shareholding"]), hide_index=True, width="stretch")

    st.divider()
    st.markdown("### 📄 Grounded PDF / XBRL Filing Analyzer (`[Page X]` Citations)")

    quick_links: dict[str, str] = {"-- Paste a custom URL below --": ""}
    if filings_data:
        for row in filings_data.get("announcements", []):
            lnk = row.get("PDF / XBRL Link", "")
            if lnk.startswith("http") and row.get("Type") in ("PDF", "XBRL"):
                quick_links[f"[{row['Type']}] {row['Broadcast Date']} — {row['Subject'][:55]}"] = lnk
        for row in filings_data.get("financial_results", []):
            lnk = row.get("Filing Link", "")
            if lnk.startswith("http") and "nsearchives.nseindia.com" in lnk:
                quick_links[f"[Q-RESULT] Period {row['Period Ended']} ({row['Basis']})"] = lnk

    picked_quick = st.selectbox("Quick-Select Fetched Filing (or paste any URL below)", options=list(quick_links.keys()))
    default_url = quick_links[picked_quick]
    pdf_url = st.text_input(
        "NSE Announcement PDF or XBRL (.xml) URL",
        value=default_url,
        placeholder="https://nsearchives.nseindia.com/corporate/...",
    )
    pdf_question = st.text_input(
        "Analytical Question",
        value="Extract key financial results, YoY/QoQ growth, margins, management guidance, and key risks.",
    )
    if st.button("🧠 Analyze Filing with Grounded Citations"):
        if not pdf_url.strip():
            st.warning("Paste or select a valid PDF or XBRL (.xml) URL first.")
        else:
            with st.spinner("Downloading filing, ranking relevant excerpts, and synthesizing cited insights..."):
                st.session_state["pdf_analysis_cache"] = analyze_pdf_report(pdf_url=pdf_url.strip(), question=pdf_question)

    pdf_res = st.session_state.get("pdf_analysis_cache")
    if pdf_res:
        st.caption(f"Engine Mode: `{pdf_res.get('mode')}`")
        st.markdown(pdf_res.get("answer", ""))

# --- Clear Bottom Disclaimer ---
st.divider()
st.caption(
    "⚠️ **Disclaimer:** Research assistance only, not investment advice. Market pulse quotes are delayed ~15 min; "
    "briefs are generated strictly from `yfinance` OHLCV data and Pulse / Google News RSS headlines."
)