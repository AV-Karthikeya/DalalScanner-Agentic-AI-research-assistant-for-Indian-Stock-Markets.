from __future__ import annotations

import math
import os
from typing import Any
import pandas as pd
import requests
import yfinance as yf

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

STRATEGY_SPECS: dict[str, dict[str, str]] = {
    "9:15 AM Opening Range Breakout (15m Intraday)": {
        "timeframe": "15m",
        "mode": "intraday",
        "description": (
            "**Rule:** Captures the opening institutional auction (`09:15–09:30 AM IST`). "
            "A breakout above the 9:15 candle's High triggers a **LONG** (Stop Loss at candle Low); "
            "a breakdown below the Low triggers a **SHORT** (Stop Loss at candle High). "
            "Positions exit at the `1:R` target, Stop Loss, or square off automatically at market close. "
            "*Best in trending gap-and-go sessions; vulnerable to morning whipsaws on range-bound days.*"
        ),
    },
    "12:00 PM Mid-Day Range Breakout (15m Intraday)": {
        "timeframe": "15m",
        "mode": "intraday",
        "description": (
            "**Rule:** Filters out noisy morning volatility by waiting until midday (`12:00–12:15 PM IST`). "
            "Uses the 12:00 PM 15-minute candle as the trigger box—breaking above High enters **LONG** "
            "(SL at 12:00 PM candle Low) and breaking below Low enters **SHORT** (SL at candle High), "
            "with mandatory EOD square-off. *Ideal for catching midday institutional continuation moves.*"
        ),
    },
    "2:00 PM Afternoon Range Breakout (15m Intraday)": {
        "timeframe": "15m",
        "mode": "intraday",
        "description": (
            "**Rule:** Targets the late-session momentum window (`02:00–02:15 PM IST`), giving the trade "
            "75–90 minutes of closing liquidity to hit its target before the 3:30 PM bell. "
            "Enters **LONG** above the 2:00 PM candle High or **SHORT** below its Low, with SL at the opposite "
            "end of the 2:00 PM candle. *Designed for clean late-day directional breakouts.*"
        ),
    },
    "21-EMA Crossover (5m Intraday)": {
        "timeframe": "5m",
        "mode": "intraday",
        "description": (
            "**Rule:** Uses 5-minute candles and a 21-period Exponential Moving Average. "
            "When a 5m candle crosses and closes **above** the 21-EMA, it triggers a **LONG** with Stop Loss "
            "placed right below that signal candle's Low; closing **below** the 21-EMA triggers a **SHORT** "
            "with SL above the signal candle's High. Respects your **Max Trades/Day** cap and squares off at EOD."
        ),
    },
    "41-EMA Bullish Crossover (1h Swing)": {
        "timeframe": "1h",
        "mode": "swing",
        "description": (
            "**Rule:** Multi-day positional swing setup on **1-hour candles**. When an hourly candle crosses "
            "and closes **above** the 41-EMA during market hours, it triggers a **BUY (Long)** at the candle close "
            "with Stop Loss placed right below that signal candle's Low. Holds overnight across sessions until "
            "either the `1:R` target or Stop Loss is hit. *Filters intraday noise to ride multi-day trends.*"
        ),
    },
}


def _record_whole_share_trade(
    trades: list[dict[str, Any]],
    entry_date: str,
    exit_date: str,
    side: str,
    entry_time: str,
    entry_price: float,
    sl_price: float,
    target_price: float,
    exit_price: float,
    outcome: str,
    capital_per_trade: float,
) -> None:
    qty = math.floor(capital_per_trade / entry_price)
    if qty <= 0:
        return
    deployed = round(qty * entry_price, 2)
    if side == "LONG":
        pnl_inr = round(qty * (exit_price - entry_price), 2)
    else:
        pnl_inr = round(qty * (entry_price - exit_price), 2)
    pnl_pct = round((pnl_inr / deployed) * 100, 2) if deployed > 0 else 0.0

    trades.append(
        {
            "Entry Date": entry_date,
            "Exit Date": exit_date,
            "Side": side,
            "Entry Time": entry_time,
            "Qty": qty,
            "Deployed (₹)": deployed,
            "Entry (₹)": round(entry_price, 2),
            "SL (₹)": round(sl_price, 2),
            "Target (₹)": round(target_price, 2),
            "Exit (₹)": round(exit_price, 2),
            "Outcome": outcome,
            "PnL (%)": pnl_pct,
            "PnL (₹)": pnl_inr,
        }
    )


def _run_session_orb(
    df: pd.DataFrame,
    session_hour: int,
    session_minute: int,
    rr_ratio: float,
    capital_per_trade: float,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    df = df.copy()
    df["TradeDate"] = df.index.date

    for t_date, day_df in df.groupby("TradeDate"):
        anchor_mask = (day_df.index.hour == session_hour) & (day_df.index.minute == session_minute)
        if not anchor_mask.any():
            continue

        anchor_pos = int(anchor_mask.argmax())
        if anchor_pos + 1 >= len(day_df):
            continue

        orb_bar = day_df.iloc[anchor_pos]
        orb_high = float(orb_bar["High"])
        orb_low = float(orb_bar["Low"])
        if orb_high - orb_low <= 0:
            continue

        position = None
        entry_price = sl_price = target_price = 0.0
        entry_time = ""

        for idx, row in day_df.iloc[anchor_pos + 1 :].iterrows():
            high = float(row["High"])
            low = float(row["Low"])

            if position is None:
                if high > orb_high:
                    position = "LONG"
                    entry_price = orb_high
                    sl_price = orb_low
                    target_price = entry_price + ((entry_price - sl_price) * rr_ratio)
                    entry_time = idx.strftime("%H:%M")
                elif low < orb_low:
                    position = "SHORT"
                    entry_price = orb_low
                    sl_price = orb_high
                    target_price = entry_price - ((sl_price - entry_price) * rr_ratio)
                    entry_time = idx.strftime("%H:%M")
            else:
                if position == "LONG":
                    if low <= sl_price:
                        _record_whole_share_trade(
                            trades, str(t_date), str(t_date), "LONG", entry_time,
                            entry_price, sl_price, target_price, sl_price, "SL Hit", capital_per_trade
                        )
                        position = "DONE"
                        break
                    elif high >= target_price:
                        _record_whole_share_trade(
                            trades, str(t_date), str(t_date), "LONG", entry_time,
                            entry_price, sl_price, target_price, target_price, "Target Hit", capital_per_trade
                        )
                        position = "DONE"
                        break
                elif position == "SHORT":
                    if high >= sl_price:
                        _record_whole_share_trade(
                            trades, str(t_date), str(t_date), "SHORT", entry_time,
                            entry_price, sl_price, target_price, sl_price, "SL Hit", capital_per_trade
                        )
                        position = "DONE"
                        break
                    elif low <= target_price:
                        _record_whole_share_trade(
                            trades, str(t_date), str(t_date), "SHORT", entry_time,
                            entry_price, sl_price, target_price, target_price, "Target Hit", capital_per_trade
                        )
                        position = "DONE"
                        break

        if position in ("LONG", "SHORT"):
            eod_close = float(day_df["Close"].iloc[-1])
            _record_whole_share_trade(
                trades, str(t_date), str(t_date), position, entry_time,
                entry_price, sl_price, target_price, eod_close, "EOD Square-Off", capital_per_trade
            )

    return trades


def _run_21ema_intraday(
    df: pd.DataFrame,
    rr_ratio: float,
    capital_per_trade: float,
    max_trades_per_day: int,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    df = df.copy()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["PrevClose"] = df["Close"].shift(1)
    df["PrevEMA21"] = df["EMA21"].shift(1)
    df["TradeDate"] = df.index.date

    for t_date, day_df in df.groupby("TradeDate"):
        if len(day_df) < 5:
            continue

        day_trades = 0
        position = None
        entry_price = sl_price = target_price = 0.0
        entry_time = ""

        for i in range(1, len(day_df) - 1):
            row = day_df.iloc[i]
            idx = day_df.index[i]
            high = float(row["High"])
            low = float(row["Low"])
            close = float(row["Close"])
            ema = float(row["EMA21"])
            prev_c = float(row["PrevClose"])
            prev_ema = float(row["PrevEMA21"])

            if pd.isna(prev_c) or pd.isna(prev_ema):
                continue

            if position is not None:
                if position == "LONG":
                    if low <= sl_price:
                        _record_whole_share_trade(
                            trades, str(t_date), str(t_date), "LONG", entry_time,
                            entry_price, sl_price, target_price, sl_price, "SL Hit", capital_per_trade
                        )
                        position = None
                    elif high >= target_price:
                        _record_whole_share_trade(
                            trades, str(t_date), str(t_date), "LONG", entry_time,
                            entry_price, sl_price, target_price, target_price, "Target Hit", capital_per_trade
                        )
                        position = None
                elif position == "SHORT":
                    if high >= sl_price:
                        _record_whole_share_trade(
                            trades, str(t_date), str(t_date), "SHORT", entry_time,
                            entry_price, sl_price, target_price, sl_price, "SL Hit", capital_per_trade
                        )
                        position = None
                    elif low <= target_price:
                        _record_whole_share_trade(
                            trades, str(t_date), str(t_date), "SHORT", entry_time,
                            entry_price, sl_price, target_price, target_price, "Target Hit", capital_per_trade
                        )
                        position = None

            if position is None and day_trades < max_trades_per_day:
                if prev_c <= prev_ema and close > ema and close > low:
                    position = "LONG"
                    entry_price = close
                    sl_price = low
                    target_price = entry_price + ((entry_price - sl_price) * rr_ratio)
                    entry_time = idx.strftime("%H:%M")
                    day_trades += 1
                elif prev_c >= prev_ema and close < ema and high > close:
                    position = "SHORT"
                    entry_price = close
                    sl_price = high
                    target_price = entry_price - ((sl_price - entry_price) * rr_ratio)
                    entry_time = idx.strftime("%H:%M")
                    day_trades += 1

        if position in ("LONG", "SHORT"):
            eod_close = float(day_df["Close"].iloc[-1])
            _record_whole_share_trade(
                trades, str(t_date), str(t_date), position, entry_time,
                entry_price, sl_price, target_price, eod_close, "EOD Square-Off", capital_per_trade
            )

    return trades


def _run_41ema_swing(
    df: pd.DataFrame,
    rr_ratio: float,
    capital_per_trade: float,
    max_trades_per_day: int,
) -> list[dict[str, Any]]:
    """
    1-Hour Swing Strategy:
    - Buy when a 1h candle crosses and closes above 41-EMA during the day.
    - Stop Loss placed right below the signal candle's Low.
    - Holds across multiple days until Target (1:R) or SL is hit.
    """
    trades: list[dict[str, Any]] = []
    df = df.copy()
    df["EMA41"] = df["Close"].ewm(span=41, adjust=False).mean()
    df["PrevClose"] = df["Close"].shift(1)
    df["PrevEMA41"] = df["EMA41"].shift(1)

    position = None
    entry_price = sl_price = target_price = 0.0
    entry_date = ""
    entry_time = ""
    daily_entry_counts: dict[str, int] = {}

    for i in range(41, len(df)):
        row = df.iloc[i]
        idx = df.index[i]
        cur_date = str(idx.date())
        high = float(row["High"])
        low = float(row["Low"])
        close = float(row["Close"])
        ema = float(row["EMA41"])
        prev_c = float(row["PrevClose"])
        prev_ema = float(row["PrevEMA41"])

        if position == "LONG":
            if low <= sl_price:
                _record_whole_share_trade(
                    trades, entry_date, cur_date, "LONG", entry_time,
                    entry_price, sl_price, target_price, sl_price, "SL Hit", capital_per_trade
                )
                position = None
            elif high >= target_price:
                _record_whole_share_trade(
                    trades, entry_date, cur_date, "LONG", entry_time,
                    entry_price, sl_price, target_price, target_price, "Target Hit", capital_per_trade
                )
                position = None

        if position is None:
            used_today = daily_entry_counts.get(cur_date, 0)
            if used_today < max_trades_per_day and prev_c <= prev_ema and close > ema and close > low:
                position = "LONG"
                entry_price = close
                sl_price = round(low * 0.999, 2)
                risk = max(entry_price - sl_price, entry_price * 0.002)
                target_price = entry_price + (risk * rr_ratio)
                entry_date = cur_date
                entry_time = idx.strftime("%H:%M")
                daily_entry_counts[cur_date] = used_today + 1

    if position == "LONG":
        last_close = float(df["Close"].iloc[-1])
        last_date = str(df.index[-1].date())
        _record_whole_share_trade(
            trades, entry_date, last_date, "LONG", entry_time,
            entry_price, sl_price, target_price, last_close, "Open / Mark-to-Market", capital_per_trade
        )

    return trades


def run_strategy_backtest(
    ticker: str,
    strategy_name: str,
    lookback_days: int = 30,
    rr_ratio: float = 2.0,
    capital_per_trade: float = 100000.0,
    max_trades_per_day: int = 1,
) -> dict[str, Any]:
    """Unified dispatcher for all 5 backtesting strategies."""
    spec = STRATEGY_SPECS.get(strategy_name)
    if not spec:
        return {"error": f"Unknown strategy: {strategy_name}"}

    tf = spec["timeframe"]
    capped_days = min(lookback_days, 59) if tf in ("5m", "15m") else min(lookback_days, 720)

    tk = yf.Ticker(ticker)
    df = tk.history(period=f"{capped_days}d", interval=tf)
    if df.empty or len(df) < 15:
        return {"error": f"Insufficient {tf} market data returned for {ticker}."}

    if strategy_name.startswith("9:15 AM"):
        trades = _run_session_orb(df, 9, 15, rr_ratio, capital_per_trade)
    elif strategy_name.startswith("12:00 PM"):
        trades = _run_session_orb(df, 12, 0, rr_ratio, capital_per_trade)
    elif strategy_name.startswith("2:00 PM"):
        trades = _run_session_orb(df, 14, 0, rr_ratio, capital_per_trade)
    elif strategy_name.startswith("21-EMA"):
        trades = _run_21ema_intraday(df, rr_ratio, capital_per_trade, max_trades_per_day)
    elif strategy_name.startswith("41-EMA"):
        trades = _run_41ema_swing(df, rr_ratio, capital_per_trade, max_trades_per_day)
    else:
        trades = []

    if not trades:
        return {"error": f"No triggers fired for '{strategy_name}' on {ticker} in the last {capped_days} days."}

    trades_df = pd.DataFrame(trades)
    wins = int((trades_df["PnL (₹)"] > 0).sum())
    losses = int((trades_df["PnL (₹)"] <= 0).sum())
    total_trades = len(trades_df)
    win_rate = round((wins / total_trades) * 100, 1)
    net_pnl = round(float(trades_df["PnL (₹)"].sum()), 2)
    net_roi_pct = round((net_pnl / capital_per_trade) * 100, 2) if capital_per_trade > 0 else 0.0

    avg_win = round(float(trades_df.loc[trades_df["PnL (₹)"] > 0, "PnL (₹)"].mean()), 2) if wins > 0 else 0.0
    avg_loss = round(float(trades_df.loc[trades_df["PnL (₹)"] <= 0, "PnL (₹)"].mean()), 2) if losses > 0 else 0.0
    trades_df["Cumulative PnL (₹)"] = trades_df["PnL (₹)"].cumsum().round(2)

    return {
        "ticker": ticker,
        "strategy_name": strategy_name,
        "timeframe": tf,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "net_pnl_inr": net_pnl,
        "net_roi_pct": net_roi_pct,
        "avg_win_inr": avg_win,
        "avg_loss_inr": avg_loss,
        "trades_df": trades_df,
    }


def generate_ai_backtest_insights(bt_res: dict[str, Any]) -> str:
    """Uses Groq (openai/gpt-oss-120b) to evaluate deterministic backtest statistics."""
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    df: pd.DataFrame = bt_res["trades_df"]

    long_count = int((df["Side"] == "LONG").sum())
    short_count = int((df["Side"] == "SHORT").sum())
    eod_count = int((df["Outcome"] == "EOD Square-Off").sum())
    target_count = int((df["Outcome"] == "Target Hit").sum())
    sl_count = int((df["Outcome"] == "SL Hit").sum())
    best_trade = float(df["PnL (₹)"].max())
    worst_trade = float(df["PnL (₹)"].min())

    stats_summary = (
        f"Instrument: {bt_res['ticker']} | Strategy: {bt_res['strategy_name']} ({bt_res['timeframe']})\n"
        f"Total Trades: {bt_res['total_trades']} ({long_count} Long, {short_count} Short)\n"
        f"Win Rate: {bt_res['win_rate_pct']}% ({bt_res['wins']}W / {bt_res['losses']}L)\n"
        f"Net PnL: ₹{bt_res['net_pnl_inr']:,.2f} (ROI on Capital: {bt_res['net_roi_pct']:+.2f}%)\n"
        f"Average Win: ₹{bt_res['avg_win_inr']:,.2f} | Average Loss: ₹{bt_res['avg_loss_inr']:,.2f}\n"
        f"Best Trade: ₹{best_trade:,.2f} | Worst Trade: ₹{worst_trade:,.2f}\n"
        f"Exits Breakdown: {target_count} Target Hit, {sl_count} SL Hit, {eod_count} EOD Square-Off"
    )

    if not groq_key:
        return (
            f"**Deterministic Edge Summary (Set `GROQ_API_KEY` for full AI review):**\n\n"
            f"- **Expectancy Profile:** {bt_res['win_rate_pct']}% win rate with Avg Win `₹{bt_res['avg_win_inr']:,.2f}` vs. Avg Loss `₹{bt_res['avg_loss_inr']:,.2f}`.\n"
            f"- **Exit Distribution:** {target_count} full targets hit, {sl_count} stop-losses hit, and {eod_count} trades closed at EOD."
        )

    prompt = (
        "You are an institutional quantitative trading analyst evaluating a backtest on an Indian NSE stock. "
        "Using ONLY the exact statistics below, write 3 concise, complete bullet points covering:\n"
        "1. **Strategy Edge & Payoff Asymmetry** (evaluate Win Rate vs. Avg Win/Avg Loss).\n"
        "2. **Execution & Exit Leakage** (analyze EOD square-offs vs. Target/SL hits).\n"
        "3. **Actionable Parameter Adjustment** (suggest a concrete tweak to R:R, session timing, or max trades/day).\n"
        "Do not invent any numbers not provided below.\n\n"
        f"{stats_summary}"
    )

    try:
        resp = requests.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": DEFAULT_GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2048,
                "reasoning_effort": "low",
            },
            timeout=25,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass

    return f"**Backtest Summary:**\n\n{stats_summary}"