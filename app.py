from datetime import datetime, timezone, timedelta
import io
import json
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from run_pipeline import run_daily_pipeline

st.set_page_config(
    page_title="Verified NSE / BSE Equity & Index Brief Agent",
    page_icon="📈",
    layout="wide",
)

# Subtle CSS polish for sleeker cards and compact spacing
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

# Focused, high-signal index heavyweight presets (weights as of Nov 2026)
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
    """Converts an ISO UTC timestamp string into a clean IST display string."""
    try:
        dt_utc = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_ist = dt_utc.astimezone(IST)
        return dt_ist.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return utc_iso


def market_status_label() -> str:
    """Returns honest NSE market session status in IST (Mon-Fri, 9:15 AM - 3:30 PM IST)."""
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5:
        return "Weekend — market closed, showing last close"
    minutes = now_ist.hour * 60 + now_ist.minute
    if 9 * 60 + 15 <= minutes <= 15 * 60 + 30:
        return "Market open (quotes delayed ~15 min)"
    return "Market closed — showing last close"


@st.cache_data(ttl=300, show_spinner=False)
def load_market_pulse() -> list[dict]:
    """Fetches snapshot for headline Indian market indices (cached 5 mins)."""
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
    """Combines major NSE/BSE indices with active NSE-listed equities."""
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
    # Startup default: pre-load Nifty 50 Top 5 chips into the queue
    st.session_state.selected_watchlist = list(BUILT_IN_PACKS["🏆 Nifty 50 Top 5"]["items"])
if "active_pack_meta" not in st.session_state:
    st.session_state.active_pack_meta = (
        f"**🏆 Nifty 50 Top 5** — {BUILT_IN_PACKS['🏆 Nifty 50 Top 5']['meta']}"
    )
if "custom_watchlists" not in st.session_state:
    # Session-only custom watchlists (with JSON export/import for portability)
    st.session_state.custom_watchlists = {}
if "search_box_key" not in st.session_state:
    st.session_state.search_box_key = 0
if "last_run_ts" not in st.session_state:
    st.session_state.last_run_ts = 0.0


def short_chip_label(label: str) -> str:
    """Formats 'Reliance Industries Limited (RELIANCE)' -> 'RELIANCE' for clean horizontal chips."""
    if label.endswith("(Index)") or label.endswith("(Volatility Index)"):
        return label.split(" (")[0]
    if "(" in label and label.endswith(")"):
        return label.rsplit("(", 1)[1].rstrip(")")
    return label.upper()


# --- Load Latest Saved Report Early (for CI status & immediate display) ---
report = load_report()
last_run_ist = format_ist_timestamp(report["generated_at_utc"]) if report else "Not yet generated"

# --- Sidebar: Engine Telemetry, Guardrails & JSON Watchlist Backup ---
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
    st.subheader("📦 Watchlist Backup (JSON)")
    st.caption("Custom watchlists are stored for your current session. Export to reuse anytime.")

    export_payload = json.dumps(
        {
            "active_queue": st.session_state.selected_watchlist,
            "custom_watchlists": st.session_state.custom_watchlists,
        },
        indent=2,
    )
    st.download_button(
        label="⬇️ Export Watchlists (.json)",
        data=export_payload,
        file_name="nse_custom_watchlists.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded_wl = st.file_uploader(
        "⬆️ Import Watchlists (.json)",
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
            st.success("Watchlists imported!")
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
if pulse_data:
    pulse_cols = st.columns(len(pulse_data))
    for col, idx_item in zip(pulse_cols, pulse_data):
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
    run_clicked = st.button("🔄 Generate Briefs", type="primary", use_container_width=True)

# --- Combined Preset Packs & User Custom Watchlist Tabs ---
all_tab_labels = list(BUILT_IN_PACKS.keys()) + [
    f"⭐ {name}" for name in st.session_state.custom_watchlists.keys()
]

selected_tab = st.pills(
    "⚡ Index Heavyweight Packs & Custom Watchlists (loads chips into queue):",
    options=all_tab_labels,
    selection_mode="single",
    default=None,
)

if selected_tab:
    if selected_tab in BUILT_IN_PACKS:
        pack = BUILT_IN_PACKS[selected_tab]
        st.session_state.selected_watchlist = list(pack["items"])[:MAX_TICKERS_PER_RUN]
        st.session_state.active_pack_meta = f"**{selected_tab}** — {pack['meta']}"
        st.rerun()
    elif selected_tab.startswith("⭐ "):
        wl_name = selected_tab[2:]
        if wl_name in st.session_state.custom_watchlists:
            st.session_state.selected_watchlist = list(st.session_state.custom_watchlists[wl_name])[:MAX_TICKERS_PER_RUN]
            st.session_state.active_pack_meta = f"**⭐ {wl_name}** (Custom Session Watchlist)"
            st.rerun()

# --- Active Queue Chips + Save Custom Watchlist Popover ---
if st.session_state.selected_watchlist:
    if st.session_state.active_pack_meta:
        st.caption(st.session_state.active_pack_meta)

    queue_col, save_col = st.columns([4.2, 1.3], vertical_alignment="bottom")
    with queue_col:
        chip_options = [f"✕ {short_chip_label(item)}" for item in st.session_state.selected_watchlist] + ["🗑️ Clear All"]
        chip_map = {f"✕ {short_chip_label(item)}": item for item in st.session_state.selected_watchlist}

        clicked_chip = st.pills(
            f"Active Queue ({len(st.session_state.selected_watchlist)}/{MAX_TICKERS_PER_RUN} — click chip to remove):",
            options=chip_options,
            selection_mode="single",
            default=None,
        )
        if clicked_chip == "🗑️ Clear All":
            st.session_state.selected_watchlist = []
            st.session_state.active_pack_meta = ""
            st.rerun()
        elif clicked_chip and clicked_chip in chip_map:
            st.session_state.selected_watchlist.remove(chip_map[clicked_chip])
            st.session_state.active_pack_meta = ""
            st.rerun()

    with save_col:
        with st.popover("💾 Save Watchlist", use_container_width=True):
            new_wl_name = st.text_input("Watchlist Name", placeholder="e.g. Swing Picks")
            if st.button("Save to Session Tabs", type="primary", use_container_width=True):
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
        chosen_tickers: list[str] = []
        for item in st.session_state.selected_watchlist[:MAX_TICKERS_PER_RUN]:
            if item in nse_options:
                sym = nse_options[item]
            else:
                sym = item.strip().upper()
                if not (sym.endswith(".NS") or sym.endswith(".BO") or sym.startswith("^")):
                    sym = f"{sym}.NS"
            if sym and sym not in chosen_tickers:
                chosen_tickers.append(sym)

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

        with st.spinner("Fetching market data, RSS headlines, and running deterministic verification..."):
            report = run_daily_pipeline(watchlist=custom_watchlist)
        st.session_state.last_run_ts = datetime.now(timezone.utc).timestamp()
        st.success("Pipeline complete & verified!")
        st.rerun()

st.divider()

# --- Render Verified Brief Cards ---
if report is None:
    st.info("No saved brief found yet. Click **🔄 Generate Briefs** above to generate your first report.")
    st.stop()

verification = report["verification"]
briefs = report["briefs"]
raw_news = report["raw_news"]
raw_prices = report["raw_prices"]

# Dynamically compute pass rate from actual verification results (never hardcoded)
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

        # Hero Ground-Truth Audit Drawer: side-by-side numeric checks & source verification
        with st.expander("🔍 Inspect Ground-Truth Audit Data (Numeric & Citation Proof)"):
            if verdict["passed"]:
                st.success("All structured metrics, narrative numbers, and citation IDs matched ground-truth tool outputs.")
            else:
                st.error(f"Flagged issues: {verdict.get('errors', [])}")

            a1, a2 = st.columns(2)
            with a1:
                st.markdown("**1. Numeric Grounding Check (`yfinance` vs. Brief)**")
                audit_rows = [
                    {
                        "Metric": "Close / Level",
                        "Ground Truth": price_info.get("close_price"),
                        "Brief Output": brief.get("close_price"),
                        "Match": "✅" if abs(float(price_info.get("close_price", 0)) - float(brief.get("close_price", 0))) <= 0.05 else "❌",
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
                st.dataframe(pd.DataFrame(audit_rows), hide_index=True, use_container_width=True)

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

# --- Clear Bottom Disclaimer ---
st.divider()
st.caption(
    "⚠️ **Disclaimer:** Research assistance only, not investment advice. Market pulse quotes are delayed ~15 min; "
    "briefs are generated strictly from `yfinance` OHLCV data and Google News RSS headlines."
)