# 📊 DalalScanner — Agentic AI Research Assistant for Indian Stock Markets

<p align="center">
  <strong>Automating stock market research with Agentic AI, real financial data, and source-grounded intelligence.</strong>
  <br/><br/>
  An AI-powered research assistant that helps investors understand what happened in their watchlist, why it happened, and where the information comes from.
  <br/><br/>
  <a href="https://dalalscanner-agentic-ai-research-assistant.streamlit.app/"><strong>🚀 Live Application</strong></a>
</p>

---

## 💡 Why DalalScanner?

Investors who actively track a watchlist of stocks spend a significant amount of time every day gathering information from different sources.

Understanding why a stock moved often requires manually checking:

- Stock prices and historical market data.
- Financial news and company announcements.
- NSE and BSE exchange filings, along with relevant SEC/global disclosures.
- Historical performance and market trends.

This information is scattered across multiple platforms, making daily research repetitive, time-consuming, and difficult to organize.

General-purpose AI chatbots can summarize financial information, but they introduce another problem: **trust and verifiability.**

They may generate inaccurate numbers, make unsupported claims, provide incomplete explanations, or fail to cite original sources. For financial research, where even a small numerical error can influence a decision, this is a serious limitation.

### The Idea

Build an Agentic AI system that automates the daily stock research workflow.

Instead of manually collecting information from multiple sources, investors should be able to track a watchlist and receive a structured research brief that:

- Fetches relevant market data, financial news, and exchange filings.
- Calculates financial figures from retrieved data rather than relying on an LLM to estimate or generate numbers.
- Identifies relevant developments that help explain stock movements.
- Links research claims back to their underlying sources.
- Provides a structured view of market activity, historical performance, and risk.

The objective is simple:

**Reduce repetitive research work while making AI-generated financial intelligence transparent, traceable, and reliable.**

---

## 🎯 What DalalScanner Does

DalalScanner brings together financial research, market screening, historical backtesting, and risk analysis inside a unified five-tab Streamlit workbench.

The application is organized into:

`Briefs` · `Radar` · `Backtest` · `Risk Plan` · `Filings`

### 1. 🤖 Agentic AI Research Assistant — Briefs

The Briefs module focuses on automating structured market research for user-selected watchlists and indices.

Key capabilities:

- Coordinates market research and daily brief generation.
- Combines AI-generated research narratives with deterministic numerical calculations.
- Supports numerical and citation verification to make research outputs auditable.
- Supports custom session watchlists.
- Provides JSON export/import for saving and restoring watchlists and risk preferences.

### 2. 📈 Market Data & Technical Radar — Radar

A dedicated screening engine designed to help identify important technical conditions across tracked equities.

Key capabilities:

- Daily 41-EMA positioning.
- Relative volume analysis.
- Distance from 52-week highs.
- 15-minute Opening Range Breakout (ORB) status.
- Scan explanations grounded in computed screening results.

### 3. 📰 News & Exchange Filings — Filings

Financial market movements often need to be understood in the context of company announcements and regulatory disclosures.

DalalScanner incorporates a dedicated NSE filings research engine.

Key capabilities:

- NSE corporate announcements.
- Quarterly results.
- Corporate actions.
- Board meeting information.
- Shareholding history.
- Filing-related research and analysis.
- Grounded Q&A over available filing PDFs and XBRL links.

The objective is to connect company developments with tracked equities and reduce the time spent manually searching through exchange disclosures.

### 4. 📊 Historical Strategy Analysis — Backtest

A dedicated backtesting engine for evaluating historical trading strategies.

Key capabilities:

- Intraday and swing strategy simulation.
- Configurable historical lookback windows.
- Customizable risk-to-reward ratios.
- Capital-per-trade configuration.
- Daily trade limits.
- Trade logs and cumulative PnL curves.
- Performance summaries.

This module helps evaluate strategy behavior against historical data rather than relying solely on assumptions.

### 5. 🛡️ Risk Planning — Risk Plan

A risk planning module designed to support more structured position sizing and capital allocation.

Key capabilities:

- Maximum affordable share quantity calculations.
- Cash-based Delivery mode (1x).
- Margin-based Intraday mode (5x).
- Synchronized stop-loss price controls.
- Visual risk/reward price ladder.
- Whole-watchlist equal-risk allocation.
- Correlation warnings.
- CSV export.
- Return horizon projections.

### 6. 📑 Financial Report Analysis

DalalScanner also includes a dedicated report analysis component.

The `report_analyzer.py` module supports financial report and filing analysis, helping turn financial documents into structured research insights with source references.

---

## 🔍 What Makes DalalScanner Different?

The central design principle behind DalalScanner is that:

**Financial research should be verifiable, not just convincing.**

| Dimension | General-Purpose AI | DalalScanner's Approach |
|---|---|---|
| Numerical accuracy | May generate unsupported or approximate figures | Uses retrieved data and deterministic calculations |
| Source attribution | Can produce uncited claims | Connects research claims to supporting sources |
| Research workflow | Primarily conversational | Structured research, screening, backtesting and risk tools |
| Financial analysis | Depends heavily on prompts and context | Dedicated analytical Python engines |
| Reliability | Difficult to evaluate objectively | Automated evaluation through `evals/` and testing through `tests/` |

### 🧪 Reliability Through Evaluation

An important part of this project is evaluating the quality of AI-generated research rather than assuming that a convincing response is necessarily accurate.

The evaluation framework focuses on three core dimensions:

**1. Groundedness**

Are generated claims supported by retrieved evidence and relevant citations?

**2. Numeric Accuracy**

Are financial figures consistent with the underlying market data and deterministic calculations?

**3. Material Event Recall**

Does the system identify and surface important developments relevant to the stocks being researched?

The goal is to make reliability measurable and testable rather than relying entirely on subjective assessments of AI-generated responses.

---

## 🏗️ Project Architecture

DalalScanner follows a modular Python architecture that separates the application interface, research orchestration, analytical engines, data utilities, and evaluation components.

```text
DalalScanner/
│
├── .devcontainer/          # Development container configuration
│
├── agent/                  # Agentic AI orchestration and verification
│
├── data/                   # Saved brief JSON snapshots and data resources
│
├── evals/                  # AI output evaluation suite
│
├── tests/                  # Unit and integration tests
│
├── tools/                  # External data and utility tools
│
├── app.py                  # Main Streamlit five-tab workbench
│
├── config.py               # Application configuration and constants
│
├── screener_engine.py      # 41-EMA, volume, 52W and 15m ORB radar
│
├── backtest_engine.py      # Historical strategy backtesting engine
│
├── nse_filings_engine.py   # NSE corporate filings and disclosures
│
├── report_analyzer.py      # PDF / XBRL report analysis and cited Q&A
│
├── risk_planner.py         # Position sizing and risk planning
│
├── run_pipeline.py         # Research pipeline execution
│
├── requirements.txt        # Python dependencies
│
├── .gitignore
│
└── README.md
```

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application and analytical logic |
| Streamlit | Interactive web application |
| Agentic AI | Research orchestration and AI-assisted workflows |
| Financial Market Data | Market analysis and numerical calculations |
| NSE / BSE | Indian exchange filings and disclosures |
| SEC / Global Disclosures | Broader financial research context where supported |
| Automated Evaluation | Groundedness, numeric accuracy and event recall |
| JSON / CSV | Data export and structured storage |

---

## ⚙️ Installation & Setup

Follow these steps to run DalalScanner locally.

### Prerequisites

- Python (compatible with the dependencies in `requirements.txt`).
- Git.
- Required API credentials, if applicable.

### 1. Clone the repository

```bash
git clone https://github.com/AV-Karthikeya/DalalScanner-Agentic-AI-research-assistant-for-Indian-Stock-Markets.git
```

### 2. Navigate to the project directory

```bash
cd DalalScanner-Agentic-AI-research-assistant-for-Indian-Stock-Markets
```

### 3. Create a virtual environment

```bash
python -m venv venv
```

Activate the environment:

**Windows**

```bash
venv\Scripts\activate
```

**macOS / Linux**

```bash
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure environment variables

Configure the API keys and environment variables required by the application.

For Streamlit deployments, use Streamlit Secrets where appropriate.

Never commit API keys, credentials, or other sensitive configuration values to GitHub.

### 6. Run the application

```bash
streamlit run app.py
```

The application will be available locally at:

```text
http://localhost:8501
```

---

## 🧪 Testing & Evaluation

The repository includes dedicated directories for testing and evaluating application behavior.

| Component | Responsibility |
|---|---|
| `tests/` | Unit and integration testing |
| `evals/` | Evaluation of AI-generated research |
| `run_pipeline.py` | Research pipeline execution |

The evaluation framework focuses on groundedness, numerical accuracy, and recall of material events.

---

## 🔮 Future Enhancements

Potential areas for further development include:

- More advanced multi-agent research orchestration.
- Expanded financial data and news integrations.
- Improved source verification and evidence tracking.
- More comprehensive portfolio and risk analytics.
- Enhanced historical strategy evaluation.
- Improved explainability of AI-generated research.
- More comprehensive evaluation of financial research outputs.
- Automated and personalized daily research briefs.

---

## ⚠️ Disclaimer

DalalScanner is an experimental financial research and analytical application developed for educational, informational, and research purposes.

Market data may be delayed, incomplete, or subject to source limitations. AI-generated outputs may contain inaccuracies or omissions.

This application does not provide financial or investment advice and does not guarantee investment returns. Users should independently verify information using original sources before making financial decisions.

---

## 👨‍💻 Author

**A V Karthikeya**

Computer Science Engineer | AI/ML | Generative AI | Agentic AI | Python

- GitHub: [AV-Karthikeya](https://github.com/AV-Karthikeya)
- Live Application: [DalalScanner](https://dalalscanner-agentic-ai-research-assistant.streamlit.app/)

---

<p align="center">
  ⭐ If you find DalalScanner interesting, consider giving this repository a star!
  <br/><br/>
  <strong>Built with Python, AI, and a focus on trustworthy financial research.</strong>
</p>
