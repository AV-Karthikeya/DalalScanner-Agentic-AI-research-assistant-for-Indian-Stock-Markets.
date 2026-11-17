import json
import time
from datetime import datetime, timezone
from typing import Any, Dict
import numpy as np
import yfinance as yf
from config import TICKERS


def get_ticker_price_snapshot(
    ticker: str, lookback_days: str = "1mo", max_retries: int = 3
) -> Dict[str, Any]:
    """
    Fetches recent OHLCV data for an NSE/BSE ticker or index with retry backoff
    and computes deterministic price, return, and volume-anomaly metrics.
    """
    hist = None
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=lookback_days, interval="1d", auto_adjust=True)
            if df is not None and not df.empty and len(df) >= 2:
                hist = df
                break
            last_err = f"Insufficient historical rows returned for {ticker}"
        except Exception as exc:
            last_err = str(exc)

        if attempt < max_retries:
            time.sleep(1.5 * attempt)

    if hist is None or hist.empty or len(hist) < 2:
        return {
            "ticker": ticker,
            "status": "unavailable",
            "error": last_err or f"Data unavailable for {ticker}",
        }

    is_index = ticker.startswith("^")
    hist = hist.dropna(subset=["Close"])
    if len(hist) < 2:
        return {
            "ticker": ticker,
            "status": "unavailable",
            "error": f"Insufficient valid Close rows for {ticker}",
        }

    latest = hist.iloc[-1]
    prev = hist.iloc[-2]

    latest_close = round(float(latest["Close"]), 2)
    prev_close = round(float(prev["Close"]), 2)
    day_change = round(latest_close - prev_close, 2)
    day_change_pct = round((day_change / prev_close) * 100, 2) if prev_close else 0.0

    if len(hist) >= 6:
        close_5d_ago = float(hist.iloc[-6]["Close"])
        five_day_change_pct = (
            round(((latest_close - close_5d_ago) / close_5d_ago) * 100, 2)
            if close_5d_ago
            else None
        )
    else:
        five_day_change_pct = None

    # Indices on Yahoo Finance often report 0 volume; treat index volume metrics as N/A
    latest_vol = int(latest["Volume"]) if "Volume" in latest and not np.isnan(latest["Volume"]) else 0
    if is_index or latest_vol == 0:
        avg_vol_20d_out = None
        volume_ratio = None
        volume_zscore = None
        unusual_volume = False
    else:
        baseline = hist.iloc[:-1].tail(20)
        avg_vol_20d = float(baseline["Volume"].mean()) if len(baseline) > 0 else float(latest_vol)
        std_vol_20d = float(baseline["Volume"].std(ddof=0)) if len(baseline) > 1 else 0.0
        avg_vol_20d_out = int(round(avg_vol_20d))
        volume_ratio = round(latest_vol / avg_vol_20d, 2) if avg_vol_20d > 0 else 1.0
        volume_zscore = (
            round((latest_vol - avg_vol_20d) / std_vol_20d, 2) if std_vol_20d > 0 else 0.0
        )
        unusual_volume = bool(volume_zscore >= 2.0)

    returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna().tail(20)
    realized_vol_20d_pct = (
        round(float(returns.std() * np.sqrt(252) * 100), 2) if len(returns) > 1 else None
    )

    trade_date = hist.index[-1].strftime("%Y-%m-%d")

    return {
        "ticker": ticker,
        "status": "ok",
        "trade_date": trade_date,
        "currency": "INR",
        "open": round(float(latest["Open"]), 2),
        "high": round(float(latest["High"]), 2),
        "low": round(float(latest["Low"]), 2),
        "close": latest_close,
        "prev_close": prev_close,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "five_day_change_pct": five_day_change_pct,
        "volume": None if is_index else latest_vol,
        "avg_volume_20d": avg_vol_20d_out,
        "volume_ratio": volume_ratio,
        "volume_zscore": volume_zscore,
        "unusual_volume": unusual_volume,
        "realized_vol_20d_pct": realized_vol_20d_pct,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def get_watchlist_prices(watchlist: list[dict] | None = None) -> Dict[str, Dict[str, Any]]:
    """Fetches price snapshots for all tickers in the watchlist."""
    tickers = [item["ticker"] for item in watchlist] if watchlist is not None else TICKERS
    return {ticker: get_ticker_price_snapshot(ticker) for ticker in tickers}


if __name__ == "__main__":
    snapshots = get_watchlist_prices()
    print(json.dumps(snapshots, indent=2))