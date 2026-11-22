# 📊 DalalScanner — Agentic AI Research Assistant for Indian Stock Markets

<p align="center">
  <strong>Automating NSE & BSE stock market research with Agentic AI, deterministic financial math, and source-grounded intelligence.</strong>
  <br/><br/>
  An AI-powered equity research workbench that helps investors track what happened in their watchlist, why it happened, and verify every figure against underlying market and exchange data.
  <br/><br/>
  <a href="https://dalalscanner-agentic-ai-research-assistant.streamlit.app/"><strong>🚀 Live Application</strong></a>
</p>

---

## 💡 Why DalalScanner?

Investors who actively track a watchlist spend significant time every day gathering scattered information across multiple platforms:

- Stock prices, index benchmarks, and intraday/daily volume trends.
- Financial news feeds and company announcements.
- NSE corporate filings, quarterly results, and PDF/XBRL disclosures.
- Historical strategy behavior and position sizing math.

General-purpose AI chatbots can summarize financial text, but they introduce a major problem: **trust and verifiability.** They may hallucinate numbers, round inconsistently, make unsupported claims, or omit source citations. In financial research, even a small numerical discrepancy undermines decision-making.

### The Idea

Build an Agentic AI research workbench that separates **deterministic computation** from **LLM synthesis**:

- Fetches live/delayed market data, financial news RSS feeds, and NSE exchange disclosures.
- Computes all financial metrics, technical indicators, backtest outcomes, and position sizes in Python rather than letting an LLM guess numbers.
- Enforces strict Pydantic schemas and deterministic post-generation verification (`evals/verifier.py`) on every figure and citation ID.
- Links every claim back to its underlying source (`[TICKER_N1]` news IDs or `[Page X]` filing citations).

**Goal:** Reduce repetitive daily research while keeping AI-generated financial intelligence transparent, traceable, and auditable.

---

## 🎯 What DalalScanner Does

  <img width="1920" height="1200" alt="Screenshot 2026-11-22 000819" src="https://github.com/user-attachments/assets/83b325cb-deb4-4992-a68f-d52ed0edec48" />

DalalScanner unifies market briefs, technical screening, historical backtesting, position sizing, and NSE corporate filings inside a five-view Streamlit workbench:

`Briefs` · `Radar` · `Backtest` · `Risk Plan` · `Filings`

---

### 1. 🤖 Verified Market Briefs — `Briefs`

<img width="1299" height="947" alt="2026-11-22 02 38 42 dalalscanner-agentic-ai-research-assistant streamlit app 9a27e92334cf" src="https://github.com/user-attachments/assets/356841e7-0cd2-4610-b13b-0dc4a12adbcd" />

Automates structured daily research briefs for custom watchlists and headline indices (`NIFTY 50`, `SENSEX`, `NIFTY BANK`, `INDIA VIX`).

- **Strict Grounding:** Combines `openai/gpt-oss-120b` (via Groq) with Pydantic structured outputs and deterministic numeric/citation verification.
- **Audit Proof:** Every ticker brief includes an expandable ground-truth audit table comparing `yfinance` metrics against brief outputs alongside verified source links.
- **Session Management:** Supports custom watchlists, NSE factsheet index packs, and JSON export/import for watchlists and risk preferences.

---

### 2. 📈 Technical Screener & Radar — `Radar`

<img width="1920" height="1200" alt="Screenshot 2026-11-22 022539" src="https://github.com/user-attachments/assets/661f3453-acdb-45fa-abee-792629363996" />
<img width="1462" height="499" alt="2026-11-22 02 26 23 dalalscanner-agentic-ai-research-assistant streamlit app b480cc9735f9" src="https://github.com/user-attachments/assets/6d57496e-9a76-4876-9fd4-cc697852b03b" />

A multi-factor technical scanner evaluating equities against trend, momentum, and intraday opening-range levels.

- **Indicators Computed:** Daily 41-EMA distance and extension checks, 20-day relative volume, distance from 52-week highs, and 15-minute Opening Range Breakout (ORB) status.
- **Grounded Scan Explanations:** Generates a verified summary of scan results with deterministic numeric verification against the computed dataframe.

---

### 3. 📊 Historical Strategy Backtesting Lab — `Backtest`

<img width="1022" height="959" alt="2026-11-22 02 27 30 dalalscanner-agentic-ai-research-assistant streamlit app 777f0aa9971c" src="https://github.com/user-attachments/assets/d024971b-70ce-42cf-94bc-63efd3321e1e" />
![Uploading 2026-11-22 02.26.23 dalalscanner-agentic-ai-research-assistant.streamlit.app b480cc9735f9.jpg…]()
<img width="1677" height="659" alt="2026-11-22 02 28 00 dalalscanner-agentic-ai-research-assistant streamlit app 70d7e3943c25" src="https://github.com/user-attachments/assets/faed515c-fe03-4fc9-9913-1ba660cd0c11" />


A rule-based historical simulation engine for intraday and swing setups on NSE equities.

- **Configurable Parameters:** Supports 15m intraday (e.g., 9:15 AM Opening Range Breakout) and daily swing strategies, custom lookback windows, risk-to-reward ratios, capital per trade, and daily trade caps.
- **Verified AI Review Notes:** Synthesizes win-rate asymmetry, exit breakdowns (Target vs. Stop-Loss vs. EOD square-off), and parameter insights verified directly against backtest metrics.

---

### 4. 🛡️ Position Sizing & Portfolio Risk Planner — `Risk Plan`

<img width="834" height="989" alt="2026-11-22 02 31 42 dalalscanner-agentic-ai-research-assistant streamlit app 61c9acc79971" src="https://github.com/user-attachments/assets/cd983c70-2607-42ff-be19-d6a4ca8212f6" />

A deterministic position-sizing and risk-budgeting calculator supporting both **Long (Buy)** and **Short (Sell)** setups.

- **Single-Stock & Watchlist Modes:** Sizes share quantities from your maximum rupee or percentage loss limit, supporting **Delivery (1x cash)** and **Intraday (5x margin)**.
- **Visual Price Ladder & AI Risk Audit:** Displays a to-scale Stop-Loss / Entry / Target ladder, statutory STT/GST/stamp fee estimates, breakeven levels, equal-risk watchlist allocation with 60-day correlation warnings, CSV export, and an AI risk check.

---

### 5. 📰 NSE Corporate Filings & Grounded Document Analyzer — `Filings`

<img width="1921" height="1056" alt="2026-11-22 02 34 29 dalalscanner-agentic-ai-research-assistant streamlit app 171afc51e7a9" src="https://github.com/user-attachments/assets/856b3aa0-8d1a-4687-9468-216e437805c1" />
<img width="1409" height="939" alt="2026-11-22 02 36 11 dalalscanner-agentic-ai-research-assistant streamlit app eba33bbfc2cb" src="https://github.com/user-attachments/assets/d5b56cf7-5895-40cb-986a-22d863c73d91" />


Connects tracked equities directly to live NSE exchange disclosures and cited document Q&A (`nse_filings_engine.py` & `report_analyzer.py`).

- **Live Exchange Feeds:** Fetches quarterly financial results (`Q1–Q4`), corporate announcements, corporate actions, board meetings, and shareholding history.
- **Cited PDF & XBRL Q&A:** Extracts relevant passages from NSE announcement PDFs or XBRL filings and answers analytical questions with explicit `[Page X]` citations.

---

### 📖 Key Market & Technical Terms Explained

For readers unfamiliar with Indian equity trading terminology used across **Radar**, **Backtest**, and **Risk Plan**:

- **15m ORB (15-Minute Opening Range Breakout):** Tracks the high and low of the first 15-minute market candle after the NSE/BSE open (**9:15 AM – 9:30 AM IST**). A price move above that range signals an upward breakout (`Above range`), while a drop below signals downward pressure.
- **Daily 41-EMA (41-Day Exponential Moving Average):** A medium-term trend filter weighting recent closing prices more heavily. DalalScanner uses it to classify whether the Nifty 50 is in a bullish or bearish regime and flags individual stocks as `Extended` if they stretch too far above their 41-EMA.
- **20D Relative Volume (`Rel Vol`):** Compares a stock's current trading volume against its 20-day average volume (e.g., `1.82x` means 82% higher participation than normal).
- **20D Volume Z-Score:** Measures how many standard deviations today's volume is from its 20-day mean—helping confirm whether a price move is backed by unusual institutional activity.
- **52W High Distance (`From 52W High %`):** Shows how close a stock is trading to its highest price over the past 52 weeks.
- **Delivery (1x) vs. Intraday (5x):** In **Risk Plan**, **Delivery** sizes positions using 100% available cash for multi-day holding, whereas **Intraday** accounts for standard 5x broker margin with same-day square-off.


## 🔍 What Makes DalalScanner Different?

**Financial research should be verifiable, not just convincing.**

| Dimension | General-Purpose AI | DalalScanner's Approach |
|---|---|---|
| **Numerical accuracy** | May approximate or hallucinate figures | Computes all prices, indicators, PnL, and sizing in deterministic Python |
| **Source attribution** | Often produces uncited claims | Ties every news claim to `citation_id`s and filing insights to `[Page X]` |
| **Research workflow** | Unstructured single-chat interface | Dedicated `Briefs`, `Radar`, `Backtest`, `Risk Plan`, and `Filings` modules |
| **Verification** | Relies on user manual checking | Automated verification layer (`evals/verifier.py`) flags mismatches |

### 🧪 Reliability Through Evaluation

Every generated brief and analytical note is checked across three dimensions:

1. **Numeric Grounding:** Ensures close prices, 1D/5D changes, volume z-scores, scan metrics, and backtest statistics match deterministic tool outputs within strict tolerances.
2. **Citation Entailment:** Verifies that every cited ID maps to a real retrieved headline or filing page.
3. **Material Event Recall:** Surfaces relevant corporate announcements, earnings disclosures, and price/volume anomalies for tracked tickers.

---

## 🏗️ Project Architecture

```text
DalalScanner/
│
├── .devcontainer/          # Development container configuration
├── .streamlit/             # Streamlit light-theme configuration
├── agent/                  # Agentic AI orchestration and Pydantic schemas
├── data/                   # Saved brief JSON snapshots
├── evals/                  # Deterministic numeric & citation verifier
├── tests/                  # Unit and integration tests
├── tools/                  # Price (yfinance) and news (Pulse + Google News RSS) tools
│
├── app.py                  # Main Streamlit five-view workbench
├── ui_theme.py             # Custom light-mode bento CSS and UI components
├── config.py               # Watchlist presets and constants
├── screener_engine.py      # 41-EMA, relative volume, 52W and 15m ORB radar
├── backtest_engine.py      # Historical strategy backtesting engine
├── risk_planner.py         # Long/Short position sizing and portfolio risk planner
├── nse_filings_engine.py   # NSE corporate filings and disclosures fetcher
├── report_analyzer.py      # PDF / XBRL report analyzer with [Page X] citations
├── run_pipeline.py         # End-to-end daily brief pipeline runner
├── requirements.txt        # Python dependencies
└── README.md
```

---

## 🛠️ Technology Stack & Data Sources

| **Layer** | **Technology / Source** | **Purpose** |
|---|---|---|
| **Frontend & UI** | Streamlit, Custom CSS (`ui_theme.py`) | Interactive 5-view research workbench |
| **LLM & Schemas** | Groq (`openai/gpt-oss-120b`), Pydantic | Structured brief synthesis, scan explanations, and cited Q&A |
| **Analytics & Verification** | Python, Pandas, NumPy, `evals/verifier.py` | Technical indicators, backtesting, risk math, and numeric audit checks |
| **OHLCV & Indices** | Yahoo Finance (`yfinance`) | Equity & index prices (~15 min delayed) |
| **Financial News** | Pulse by Zerodha RSS & Google News India RSS | Deduplicated market headlines with deterministic `citation_id`s |
| **Exchange Disclosures** | NSE India (`nseindia.com` & `nsearchives.nseindia.com`) | Equity master list, quarterly results, corporate actions, PDFs & XBRL |

## ⚙️ Installation & Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/AV-Karthikeya/DalalScanner-Agentic-AI-research-assistant-for-Indian-Stock-Markets.git

cd DalalScanner-Agentic-AI-research-assistant-for-Indian-Stock-Markets
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
```

- **Windows:** `venv\Scripts\activate`
- **macOS / Linux:** `source venv/bin/activate`

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root (or configure Streamlit Secrets for cloud deployment):

```env
GROQ_API_KEY=your_groq_api_key_here
```

### 5. Run the application

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

## ⚠️ Disclaimer

DalalScanner is an experimental financial research and analytical workbench built for educational, informational, and research purposes. Market quotes are delayed (~15 minutes) and AI-generated summaries may contain omissions. Nothing in this application constitutes financial or investment advice. Always verify figures against official exchange disclosures before making trading or investment decisions.

---

## 👨‍💻 Author

**A V Karthikeya**

Computer Science Engineer · AI/ML · Generative AI · Agentic AI · Python

- **GitHub:** [AV-Karthikeya](https://github.com/AV-Karthikeya)
- **Live Application:** [DalalScanner](https://dalalscanner-agentic-ai-research-assistant.streamlit.app/)
