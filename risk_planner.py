from __future__ import annotations

import os
from typing import Any
import numpy as np
import pandas as pd
import requests
import yfinance as yf

try:
    import streamlit as st
except ImportError:
    st = None


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


def _get_groq_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key and st is not None:
        try:
            key = str(st.secrets.get("GROQ_API_KEY", "")).strip()
        except Exception:
            key = ""
    return key


def get_last_close_price(ticker: str, brief_prices: dict[str, Any] | None = None) -> float:
    """Reuses Tab 1 verified brief close price if available, otherwise fetches from yfinance."""
    if brief_prices and ticker in brief_prices:
        p_info = brief_prices[ticker]
        for k in ("close_price", "close", "last_close"):
            val = p_info.get(k)
            if val is not None and float(val) > 0:
                return round(float(val), 2)
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if hist is not None and not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return 1000.0


def get_trade_idea_defaults(ticker: str, is_long: bool = True) -> dict[str, float | str]:
    """
    Pre-fills Entry from the latest price and Stop-Loss from the last 15-min candle's
    low (for Long) or high (for Short), falling back to 1.5% if intraday data is unavailable.
    """
    last_px = get_last_close_price(ticker)
    try:
        intraday = yf.Ticker(ticker).history(period="5d", interval="15m")
        if intraday is not None and not intraday.empty:
            latest_bar = intraday.iloc[-1]
            entry_val = round(float(latest_bar["Close"]), 2)
            if is_long:
                raw_sl = round(float(latest_bar["Low"]), 2)
                if raw_sl < entry_val:
                    sl_val = raw_sl
                    note = f"Last 15m candle low (₹{raw_sl:,.2f})"
                else:
                    sl_val = round(entry_val * 0.992, 2)
                    note = f"0.8% buffer below 15m close (₹{entry_val:,.2f})"
            else:
                raw_sl = round(float(latest_bar["High"]), 2)
                if raw_sl > entry_val:
                    sl_val = raw_sl
                    note = f"Last 15m candle high (₹{raw_sl:,.2f})"
                else:
                    sl_val = round(entry_val * 1.008, 2)
                    note = f"0.8% buffer above 15m close (₹{entry_val:,.2f})"
            return {"entry": entry_val, "sl": sl_val, "source": note}
    except Exception:
        pass

    fallback_sl = round(last_px * (0.985 if is_long else 1.015), 2)
    return {"entry": last_px, "sl": fallback_sl, "source": "1.5% default buffer"}


def estimate_indian_roundtrip_charges(turnover_buy: float, turnover_sell: float, is_intraday: bool = True) -> float:
    """
    Realistic Indian NSE statutory + brokerage charges estimate:
    - Brokerage: 0.03% capped at ₹20/order (Intraday) or ₹0 (CNC Delivery)
    - STT: 0.025% on sell side (Intraday) or 0.1% on buy + sell (Delivery)
    - NSE Transaction Charge: 0.00307% on total turnover
    - Stamp Duty: 0.003% on buy (Intraday) or 0.015% on buy (Delivery)
    - SEBI Fee: 0.0001% on total turnover
    - GST: 18% on (Brokerage + NSE Transaction + SEBI Fee)
    """
    total_turnover = turnover_buy + turnover_sell
    if is_intraday:
        brok = min(turnover_buy * 0.0003, 20.0) + min(turnover_sell * 0.0003, 20.0)
        stt = turnover_sell * 0.00025
        stamp = turnover_buy * 0.00003
    else:
        brok = 0.0
        stt = total_turnover * 0.001
        stamp = turnover_buy * 0.00015

    exch_txn = total_turnover * 0.0000307
    sebi = total_turnover * 0.000001
    gst = 0.18 * (brok + exch_txn + sebi)
    return round(brok + stt + exch_txn + stamp + sebi + gst, 2)


def calculate_position_plan(
    capital: float,
    risk_budget_inr: float,
    entry_price: float,
    stop_loss_price: float,
    aggression: int = 5,
    rr_ratio: float = 2.0,
    max_allocation_pct: float = 100.0,
    trade_mode: str = "MIS Intraday (5x Margin)",
) -> dict[str, Any]:
    """
    Computes exact share quantity, Indian MIS/CNC margin, post-tax breakeven,
    TP1 (50% scale-out at 1:1.5) & TP2 target prices, and true net PnL.
    """
    if entry_price <= 0 or stop_loss_price <= 0 or entry_price == stop_loss_price:
        return {"error": "Entry Price and Stop-Loss Price must be positive and distinct."}

    is_long = entry_price > stop_loss_price
    side = "LONG" if is_long else "SHORT"
    risk_per_share = abs(entry_price - stop_loss_price)

    if aggression <= 5:
        agg_mult = 0.5 + (aggression - 1) * 0.125
    else:
        agg_mult = 1.0 + (aggression - 5) * 0.15

    adjusted_risk_inr = risk_budget_inr * agg_mult
    raw_qty = int(adjusted_risk_inr // risk_per_share)

    is_intraday = "MIS" in trade_mode
    leverage = 5.0 if is_intraday else 1.0
    max_capital_allowed = capital * (max_allocation_pct / 100.0)
    max_buying_power = max_capital_allowed * leverage

    max_qty_by_cap = int(max_buying_power // entry_price)
    was_capped = raw_qty > max_qty_by_cap
    qty = max(0, min(raw_qty, max_qty_by_cap))

    if qty == 0:
        return {
            "error": (
                f"Calculated quantity is 0 shares. Risk per share (₹{risk_per_share:,.2f}) exceeds "
                f"your risk budget (₹{adjusted_risk_inr:,.2f}) or capital limit."
            )
        }

    position_value = round(qty * entry_price, 2)
    margin_required = round(position_value / leverage, 2)
    cap_util_pct = round((margin_required / capital) * 100, 2) if capital > 0 else 0.0

    tp1_mult = min(1.5, rr_ratio)
    if is_long:
        tp1_price = round(entry_price + (risk_per_share * tp1_mult), 2)
        target_price = round(entry_price + (risk_per_share * rr_ratio), 2)
    else:
        tp1_price = round(entry_price - (risk_per_share * tp1_mult), 2)
        target_price = round(entry_price - (risk_per_share * rr_ratio), 2)

    gross_risk = round(qty * risk_per_share, 2)
    gross_profit = round(qty * risk_per_share * rr_ratio, 2)

    sl_charges = estimate_indian_roundtrip_charges(
        turnover_buy=qty * (entry_price if is_long else stop_loss_price),
        turnover_sell=qty * (stop_loss_price if is_long else entry_price),
        is_intraday=is_intraday,
    )
    tp_charges = estimate_indian_roundtrip_charges(
        turnover_buy=qty * (entry_price if is_long else target_price),
        turnover_sell=qty * (target_price if is_long else entry_price),
        is_intraday=is_intraday,
    )

    net_risk = round(gross_risk + sl_charges, 2)
    net_profit = round(gross_profit - tp_charges, 2)
    charge_per_share = round(tp_charges / qty, 2)
    breakeven_price = round(entry_price + charge_per_share, 2) if is_long else round(entry_price - charge_per_share, 2)
    min_win_rate = round((net_risk / (net_risk + net_profit)) * 100, 1) if (net_risk + net_profit) > 0 else 0.0

    return {
        "side": side,
        "trade_mode": trade_mode,
        "recommended_qty": qty,
        "was_capped": was_capped,
        "entry_price": round(entry_price, 2),
        "stop_loss_price": round(stop_loss_price, 2),
        "breakeven_price": breakeven_price,
        "tp1_price": tp1_price,
        "target_price": target_price,
        "risk_per_share": round(risk_per_share, 2),
        "sl_move_pct": round((risk_per_share / entry_price) * 100, 2),
        "position_value_inr": position_value,
        "margin_required_inr": margin_required,
        "capital_utilization_pct": cap_util_pct,
        "aggression_multiplier": f"{agg_mult:.2f}x",
        "est_charges_inr": tp_charges,
        "actual_risk_inr": net_risk,
        "net_profit_inr": net_profit,
        "rr_ratio": rr_ratio,
        "min_win_rate_pct": min_win_rate,
    }


def allocate_equal_risk_portfolio(
    tickers: list[str],
    total_capital: float,
    total_risk_budget_inr: float,
    stop_loss_pct: float = 3.0,
    trade_mode: str = "Delivery (1x Cash)",
    brief_prices: dict[str, Any] | None = None,
    briefs_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Simple broker-style Equal-Risk Watchlist Split supporting both:
    - Delivery (1x Cash / CNC): 1x buying power, CNC statutory charges
    - Intraday (5x Margin / MIS): 5x buying power, MIS brokerage & STT
    Splits Stop-Loss Risk (qty * stop_dist) and Est. Charges separately for complete math clarity.
    """
    clean_tickers = [t for t in tickers if not t.startswith("^")]
    if not clean_tickers:
        return {"df": pd.DataFrame(), "error": "Add at least one equity stock to your watchlist."}

    is_intraday = "Intraday" in trade_mode
    leverage = 5.0 if is_intraday else 1.0
    total_buying_power = total_capital * leverage

    n = len(clean_tickers)
    per_trade_risk = total_risk_budget_inr / n
    buying_power_per_stock = total_buying_power / n

    raw_rows: list[dict[str, Any]] = []
    returns_map: dict[str, pd.Series] = {}
    slice_exceeded_syms: list[str] = []
    risk_blocked_syms: list[str] = []

    for sym in clean_tickers:
        short_sym = sym.replace(".NS", "")
        px = get_last_close_price(sym, brief_prices=brief_prices)
        used_brief_px = bool(brief_prices and sym in brief_prices)

        try:
            hist = yf.Ticker(sym).history(period="3mo")
            if hist is not None and not hist.empty:
                if not used_brief_px:
                    px = round(float(hist["Close"].iloc[-1]), 2)
                ret_series = hist["Close"].pct_change().dropna().tail(60)
                if len(ret_series) >= 10:
                    returns_map[short_sym] = ret_series
        except Exception:
            pass

        if px <= 0:
            continue

        stop_dist = round(px * (stop_loss_pct / 100.0), 2)
        sl_px = round(max(px - stop_dist, 0.05), 2)
        stop_dist = max(px - sl_px, 0.05)

        qty_by_risk = int(per_trade_risk // stop_dist)
        qty_by_bp = int(buying_power_per_stock // px)
        qty = max(0, min(qty_by_risk, qty_by_bp))

        pos_value = round(qty * px, 2)
        margin_used = round(pos_value / leverage, 2)
        stop_loss_risk = round(qty * stop_dist, 2)
        est_charges = (
            estimate_indian_roundtrip_charges(pos_value, qty * sl_px, is_intraday=is_intraday)
            if qty > 0
            else 0.0
        )
        total_max_loss = round(stop_loss_risk + est_charges, 2)

        brief_sent = "-"
        if briefs_data and sym in briefs_data:
            brief_sent = str(briefs_data[sym].get("sentiment") or "-")

        if px > buying_power_per_stock:
            slice_exceeded_syms.append(short_sym)
            status = f"❌ Price ₹{px:,.0f} > ₹{buying_power_per_stock:,.0f} slice"
            binding = "Slice limit"
        elif qty == 0:
            risk_blocked_syms.append(short_sym)
            status = f"❌ 1 share risk (₹{stop_dist:,.0f}) > ₹{per_trade_risk:,.0f}"
            binding = "Risk budget"
        elif qty_by_bp < qty_by_risk:
            status = "⚠️ Capital-capped"
            binding = "Capital slice"
        else:
            status = "✅ Fits"
            binding = "Risk budget"

        raw_rows.append(
            {
                "Include": True,
                "Symbol": short_sym,
                "Sentiment": brief_sent,
                "Price (₹)": px,
                f"Stop Loss (-{stop_loss_pct}%)": sl_px,
                "Shares": qty,
                "Position Value (₹)": pos_value,
                "Margin / Cash Used (₹)": margin_used,
                "Weight (%)": 0.0,
                "Stop-Loss Risk (₹)": stop_loss_risk,
                "Est. Charges (₹)": est_charges,
                "Total Max Loss (₹)": total_max_loss,
                "Limited By": binding,
                "Status": status,
            }
        )

    df = pd.DataFrame(raw_rows)
    if df.empty:
        return {"df": df, "error": "Could not retrieve prices for the selected symbols."}

    total_margin_used = round(float(df["Margin / Cash Used (₹)"].sum()), 2)
    total_pos_value = round(float(df["Position Value (₹)"].sum()), 2)
    total_cash_left = round(max(0.0, total_capital - total_margin_used), 2)
    total_sl_risk = round(float(df["Stop-Loss Risk (₹)"].sum()), 2)
    total_est_charges = round(float(df["Est. Charges (₹)"].sum()), 2)
    total_risk_exp = round(float(df["Total Max Loss (₹)"].sum()), 2)

    if total_margin_used > 0:
        df["Weight (%)"] = df["Margin / Cash Used (₹)"].apply(
            lambda m: round((m / total_margin_used) * 100.0, 1)
        )

    # 60-day pairwise correlation check
    high_corr_pairs: list[str] = []
    avg_corr = 0.0
    if len(returns_map) >= 2:
        ret_df = pd.DataFrame(returns_map).dropna()
        if len(ret_df) >= 10:
            corr_mat = ret_df.corr()
            cols = list(corr_mat.columns)
            pair_vals: list[float] = []
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    c_val = float(corr_mat.iloc[i, j])
                    pair_vals.append(c_val)
                    if c_val >= 0.55:
                        high_corr_pairs.append(f"{cols[i]} & {cols[j]} ({c_val:.2f})")
            if pair_vals:
                avg_corr = round(sum(pair_vals) / len(pair_vals), 2)

    sized_count = int((df["Shares"] > 0).sum())

    return {
        "df": df,
        "is_intraday": is_intraday,
        "leverage": leverage,
        "total_stocks": len(df),
        "sized_count": sized_count,
        "slice_exceeded_syms": slice_exceeded_syms,
        "risk_blocked_syms": risk_blocked_syms,
        "per_trade_risk": round(per_trade_risk, 2),
        "buying_power_per_stock": round(buying_power_per_stock, 2),
        "total_capital": round(total_capital, 2),
        "total_buying_power": round(total_buying_power, 2),
        "total_pos_value": total_pos_value,
        "total_margin_used": total_margin_used,
        "total_cash_left": total_cash_left,
        "cap_used_pct": round((total_margin_used / total_capital) * 100.0, 1) if total_capital > 0 else 0.0,
        "total_risk_budget": round(total_risk_budget_inr, 2),
        "total_sl_risk": total_sl_risk,
        "total_est_charges": total_est_charges,
        "total_risk_exp": total_risk_exp,
        "risk_pct_of_cap": round((total_risk_exp / total_capital) * 100.0, 2) if total_capital > 0 else 0.0,
        "budget_used_pct": round((total_risk_exp / total_risk_budget_inr) * 100.0, 1) if total_risk_budget_inr > 0 else 0.0,
        "avg_corr": avg_corr,
        "high_corr_pairs": high_corr_pairs,
    }


def project_portfolio_returns(
    alloc_df: pd.DataFrame,
    total_capital: float,
    total_margin_used: float,
    total_cash_left: float,
    total_risk_exp: float,
    horizon_days: int = 90,
    is_intraday: bool = False,
    briefs_data: dict[str, Any] | None = None,
    groq_model: str = DEFAULT_GROQ_MODEL,
) -> dict[str, Any]:
    """
    Computes deterministic historical return & volatility projections (10th, 50th, 90th percentiles)
    on the user's exact allocated share quantities, then asks Groq to interpret the numbers
    alongside Tab 1 verified brief sentiments.
    """
    active_df = alloc_df[alloc_df["Shares"] > 0].copy()
    if active_df.empty or total_margin_used <= 0:
        return {"error": "At least one stock must have > 0 shares to project returns."}

    trading_days = max(1, int(round(horizon_days * (252.0 / 365.0))))

    symbols = active_df["Symbol"].tolist()
    pos_values = active_df["Position Value (₹)"].to_numpy(dtype=float)
    total_pos_val = float(pos_values.sum())
    weights = pos_values / total_pos_val

    ret_dict: dict[str, pd.Series] = {}
    for sym in symbols:
        try:
            hist = yf.Ticker(f"{sym}.NS").history(period="1y")
            if hist is not None and len(hist) >= 30:
                ret_dict[sym] = hist["Close"].pct_change().dropna()
        except Exception:
            pass

    if not ret_dict:
        return {"error": "Insufficient 1-year historical price data to compute return bands."}

    ret_df = pd.DataFrame(ret_dict).dropna()
    valid_syms = list(ret_df.columns)
    valid_mask = [s in valid_syms for s in symbols]
    w_valid = weights[valid_mask]
    w_valid = w_valid / w_valid.sum()

    port_daily_rets = ret_df[valid_syms].to_numpy() @ w_valid
    ann_return = float(np.mean(port_daily_rets) * 252)
    ann_vol = float(np.std(port_daily_rets, ddof=1) * np.sqrt(252))

    t_years = trading_days / 252.0
    drift = (ann_return - 0.5 * (ann_vol ** 2)) * t_years
    shock = ann_vol * np.sqrt(t_years)

    p10_mult = float(np.exp(drift - 1.2816 * shock)) - 1.0
    p50_mult = float(np.exp(drift)) - 1.0
    p90_mult = float(np.exp(drift + 1.2816 * shock)) - 1.0

    raw_bear_pnl = round(total_pos_val * p10_mult, 2)
    bear_pnl_with_stops = round(max(raw_bear_pnl, -total_risk_exp), 2)
    base_pnl = round(total_pos_val * p50_mult, 2)
    bull_pnl = round(total_pos_val * p90_mult, 2)

    steps = max(2, min(trading_days, 24))
    step_days = np.linspace(0, trading_days, steps)
    curve_rows = []
    for d in step_days:
        ty = d / 252.0
        dr = (ann_return - 0.5 * (ann_vol ** 2)) * ty
        sh = ann_vol * np.sqrt(ty)
        bear_v = total_capital + max(total_pos_val * (np.exp(dr - 1.2816 * sh) - 1.0), -total_risk_exp)
        base_v = total_capital + total_pos_val * (np.exp(dr) - 1.0)
        bull_v = total_capital + total_pos_val * (np.exp(dr + 1.2816 * sh) - 1.0)
        curve_rows.append(
            {
                "Trading Day": int(round(d)),
                "Bear Case (Stop-Protected ₹)": round(bear_v, 2),
                "Base Case (Median ₹)": round(base_v, 2),
                "Bull Case (90th Pct ₹)": round(bull_v, 2),
            }
        )
    curve_df = pd.DataFrame(curve_rows)

    sent_notes = []
    for sym in valid_syms:
        full_t = f"{sym}.NS"
        s_tag = briefs_data[full_t].get("sentiment", "Neutral") if (briefs_data and full_t in briefs_data) else "No brief"
        sent_notes.append(f"{sym}: {s_tag}")

    deployed_pct = round((total_margin_used / total_capital) * 100.0, 1) if total_capital > 0 else 0.0
    prompt_context = (
        f"Holding Horizon: {horizon_days} calendar days (~{trading_days} NSE trading days)\n"
        f"Mode: {'Intraday (5x)' if is_intraday else 'Delivery (1x Cash)'}\n"
        f"Total Capital: ₹{total_capital:,.2f} | Deployed Cash/Margin: ₹{total_margin_used:,.2f} ({deployed_pct}%) | Idle Cash: ₹{total_cash_left:,.2f}\n"
        f"Active Positions: {', '.join(valid_syms)}\n"
        f"1Y Historical Annualized Return: {ann_return * 100:.1f}% | Annualized Volatility: {ann_vol * 100:.1f}%\n"
        f"Projected PnL over {horizon_days}D:\n"
        f"- Bear Case (Stop-Protected): ₹{bear_pnl_with_stops:+,.2f} (Uncapped 10th pct: ₹{raw_bear_pnl:+,.2f})\n"
        f"- Base Case (Median): ₹{base_pnl:+,.2f} ({(base_pnl / total_capital) * 100:+.2f}% on total capital)\n"
        f"- Bull Case (90th Pct): ₹{bull_pnl:+,.2f} ({(bull_pnl / total_capital) * 100:+.2f}% on total capital)\n"
        f"Tab 1 Brief Sentiments: {', '.join(sent_notes)}"
    )

    system_prompt = (
        "You are an institutional Indian Equity Portfolio Analyst. Interpret the pre-computed return projection above "
        "in 3 crisp bullet points without inventing any new numbers:\n"
        "1. **Expected Return vs. Cash Drag**: Comment on the Base/Bull rupee gain and how uninvested idle cash affects total account ROI.\n"
        "2. **Downside Protection**: Compare the uncapped 10th-percentile drawdown against the stop-loss protected floor.\n"
        "3. **Catalyst & Brief Alignment**: Connect the active stocks' verified brief sentiments and sector overlap to the holding horizon."
    )

    ai_summary = ""
    groq_key = _get_groq_api_key()
    if groq_key:
        try:
            resp = requests.post(
                GROQ_CHAT_URL,
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": groq_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt_context},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 450,
                },
                timeout=20,
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    ai_summary = choices[0]["message"]["content"].strip()
        except Exception:
            pass

    if not ai_summary:
        ai_summary = (
            f"- **Expected Return & Cash Drag:** Over **{horizon_days} days**, your deployed `₹{total_margin_used:,.0f}` projects a median gain of "
            f"**`₹{base_pnl:+,.0f}`** (`{(base_pnl / total_capital) * 100:+.2f}%` on total `₹{total_capital:,.0f}`), with `{100 - deployed_pct:.1f}%` (`₹{total_cash_left:,.0f}`) sitting in idle cash.\n"
            f"- **Downside Protection:** While an uncapped 10th-percentile drop could lose `₹{abs(raw_bear_pnl):,.0f}`, your active stop-losses cap max loss near **`₹{abs(bear_pnl_with_stops):,.0f}`**.\n"
            f"- **Brief Alignment:** Current Tab 1 signals (`{', '.join(sent_notes)}`) govern near-term momentum across this basket."
        )

    return {
        "horizon_days": horizon_days,
        "trading_days": trading_days,
        "ann_return_pct": round(ann_return * 100, 1),
        "ann_vol_pct": round(ann_vol * 100, 1),
        "bear_pnl": bear_pnl_with_stops,
        "base_pnl": base_pnl,
        "bull_pnl": bull_pnl,
        "base_roi_cap_pct": round((base_pnl / total_capital) * 100, 2) if total_capital > 0 else 0.0,
        "bull_roi_cap_pct": round((bull_pnl / total_capital) * 100, 2) if total_capital > 0 else 0.0,
        "curve_df": curve_df,
        "ai_summary": ai_summary,
    }


def generate_ai_risk_audit(
    ticker: str,
    plan: dict[str, Any],
    brief_sentiment: str = "Neutral",
    india_vix: float | None = None,
    groq_model: str = DEFAULT_GROQ_MODEL,
) -> str:
    """Audits a proposed trade plan for stop-loss fragility, leverage, and brief alignment."""
    vix_str = f"{india_vix:.2f}" if india_vix is not None else "Unavailable"
    summary_context = (
        f"Ticker: {ticker}\n"
        f"Direction & Product: {plan['side']} | {plan['trade_mode']}\n"
        f"Entry: ₹{plan['entry_price']} | Stop-Loss: ₹{plan['stop_loss_price']} ({plan['sl_move_pct']}% distance)\n"
        f"Breakeven (post-charges): ₹{plan['breakeven_price']} | TP1 (1:1.5): ₹{plan['tp1_price']} | TP2 (1:{plan['rr_ratio']}): ₹{plan['target_price']}\n"
        f"Recommended Qty: {plan['recommended_qty']} shares | Margin/Capital Used: ₹{plan['margin_required_inr']} ({plan['capital_utilization_pct']}% of account)\n"
        f"Net Risk (incl. Indian STT/Brokerage): ₹{plan['actual_risk_inr']} | Net Target Profit: ₹{plan['net_profit_inr']}\n"
        f"Latest Brief Sentiment: {brief_sentiment}\n"
        f"Live India VIX: {vix_str}"
    )

    system_prompt = (
        "You are an institutional Indian Equity Risk Manager. Audit this exact pre-trade sizing plan. "
        "Provide 3 concise, high-impact bullet points covering:\n"
        "1. **Stop-Loss & Noise Check**: Is the stop-loss % distance wide enough to survive normal NSE intraday/swing noise without getting wicked out?\n"
        "2. **Capital Concentration & Leverage Risk**: Evaluate the capital utilization %, MIS leverage exposure, and tax/slippage drag.\n"
        "3. **Sentiment & Execution Rule**: Check alignment between trade direction, verified news sentiment, and TP1 scaling."
    )

    groq_key = _get_groq_api_key()
    if groq_key:
        try:
            resp = requests.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": groq_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": summary_context},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
                timeout=20,
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    content = choices[0]["message"]["content"].strip()
                    if content:
                        return content
        except Exception:
            pass

    stop_note = (
        "Tight stop (<0.7%) — vulnerable to normal NSE opening volatility."
        if plan["sl_move_pct"] < 0.7
        else f"Healthy {plan['sl_move_pct']}% stop distance gives breathing room above intraday noise."
    )
    cap_note = (
        f"High capital concentration ({plan['capital_utilization_pct']}% of account) — avoid stacking correlated sector trades."
        if plan["capital_utilization_pct"] > 50
        else f"Balanced capital allocation ({plan['capital_utilization_pct']}% of account) preserves dry powder."
    )
    return (
        f"- **Stop-Loss & Noise Check:** {stop_note}\n"
        f"- **Capital Concentration & Charges:** {cap_note} Estimated statutory + brokerage cost is `₹{plan['est_charges_inr']}` (breakeven at `₹{plan['breakeven_price']}`).\n"
        f"- **Execution Rule:** Verified brief sentiment is **{brief_sentiment}**. Book 50% at **TP1 (`₹{plan['tp1_price']}`)** and trail stop to breakeven (`₹{plan['breakeven_price']}`)."
    )