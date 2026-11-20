"""Unified radar (daily 41-EMA, relative volume, 52W proximity, 15m opening-range status)
plus deterministic-checked AI scan explanation.

Returns a DataFrame with NUMERIC columns (format them in the UI) and puts run-level
info in df.attrs:
    df.attrs["nifty_regime"], df.attrs["failed"], df.attrs["as_of"]
Read attrs right after the call, before sorting/filtering the frame.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import pandas as pd
import requests
import yfinance as yf

try:
    import streamlit as st
except ImportError:
    st = None

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"

EXTENDED_PCT = 10.0      # flag stocks this far above the daily 41-EMA
REL_VOL_MIN = 1.5
NEAR_HIGH_PCT = -5.0     # within 5% of 52-week high


def _get_groq_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key and st is not None:
        try:
            key = str(st.secrets.get("GROQ_API_KEY", "")).strip()
        except Exception:
            key = ""
    return key


def _nifty_regime() -> str:
    try:
        h = yf.Ticker("^NSEI").history(period="1y", interval="1d").dropna(subset=["Close"])
        if len(h) >= 41:
            ema = h["Close"].ewm(span=41, adjust=False).mean().iloc[-1]
            return "Bullish (above daily 41-EMA)" if h["Close"].iloc[-1] > ema else "Bearish (below daily 41-EMA)"
    except Exception:
        pass
    return "Unknown"


def _orb_status(tk: yf.Ticker, daily_last_date) -> dict:
    """Opening range = first 15m candle (09:15). Status uses the LAST 15m close."""
    empty = {"ORB High": None, "ORB Low": None, "ORB Status": "No intraday data"}
    try:
        h = tk.history(period="5d", interval="15m").dropna(subset=["Close"])
        if h.empty:
            return empty
        last_day = h.index[-1].date()
        if last_day != daily_last_date:
            return {**empty, "ORB Status": "Intraday data not for latest session"}
        bars = h[h.index.date == last_day]
        if len(bars) < 2 or bars.index[0].strftime("%H:%M") != "09:15":
            return {**empty, "ORB Status": "Opening candle missing"}
        hi, lo = float(bars["High"].iloc[0]), float(bars["Low"].iloc[0])
        last = float(bars["Close"].iloc[-1])
        status = "Above range" if last > hi else "Below range" if last < lo else "Inside range"
        return {"ORB High": round(hi, 2), "ORB Low": round(lo, 2), "ORB Status": status}
    except Exception:
        return empty


def _compute_radar_uncached(tickers_tuple: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    syms = [t for t in tickers_tuple if not t.startswith("^")]
    if not syms:
        return [], {"nifty_regime": _nifty_regime(), "failed": [], "as_of": None}

    regime = _nifty_regime()
    rows: list[dict[str, Any]] = []
    failed: list[str] = []
    last_daily_date = None

    for sym in syms:
        name = sym.replace(".NS", "").replace(".BO", "")
        try:
            tk = yf.Ticker(sym)
            d = tk.history(period="1y", interval="1d").dropna(subset=["Close"])
            d = d[~d.index.duplicated(keep="last")]
            if len(d) < 45:
                failed.append(f"{name} (not enough history)")
                continue

            last_daily_date = d.index[-1].date()
            close, prev = float(d["Close"].iloc[-1]), float(d["Close"].iloc[-2])
            ema41 = float(d["Close"].ewm(span=41, adjust=False).mean().iloc[-1])
            avg_vol = float(d["Volume"].iloc[-21:-1].mean())
            rel_vol = round(float(d["Volume"].iloc[-1]) / avg_vol, 2) if avg_vol > 0 else None
            high52 = float(d["High"].max())

            dist_ema = (close - ema41) / ema41 * 100
            from_high = (close - high52) / high52 * 100
            orb = _orb_status(tk, last_daily_date)

            score = sum([
                close > ema41,
                rel_vol is not None and rel_vol >= REL_VOL_MIN,
                from_high >= NEAR_HIGH_PCT,
                orb["ORB Status"] == "Above range",
            ])
            rows.append({
                "Ticker": name,
                "Close": round(close, 2),
                "1D": round((close - prev) / prev * 100, 2),
                "41-EMA": round(ema41, 2),
                "vs 41-EMA": round(dist_ema, 2),
                "Rel Vol": rel_vol,
                "From 52W High": round(from_high, 2),
                "ORB High": orb["ORB High"],
                "ORB Low": orb["ORB Low"],
                "ORB Status": orb["ORB Status"],
                "Extended": bool(dist_ema > EXTENDED_PCT),
                "Score": int(score),
            })
        except Exception as e:
            failed.append(f"{name} ({type(e).__name__})")

    attrs = {
        "nifty_regime": regime,
        "failed": failed,
        "as_of": str(last_daily_date) if rows and last_daily_date else None,
    }
    return rows, attrs


if st is not None:
    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_radar_payload(tickers_tuple: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return _compute_radar_uncached(tickers_tuple)
else:
    def _cached_radar_payload(tickers_tuple: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return _compute_radar_uncached(tickers_tuple)


def run_unified_radar(tickers: list[str]) -> pd.DataFrame:
    """Cached (~5 min) unified scan returning numeric columns and df.attrs metadata."""
    syms = tuple(t for t in tickers if not t.startswith("^"))
    if not syms:
        return pd.DataFrame()

    rows, attrs = _cached_radar_payload(syms)
    df = pd.DataFrame(rows)
    df.attrs["nifty_regime"] = attrs.get("nifty_regime", "Unknown")
    df.attrs["failed"] = list(attrs.get("failed", []))
    df.attrs["as_of"] = attrs.get("as_of")
    return df


def _extract_allowed_numbers(rows: list[dict[str, Any]], as_of: str | None) -> set[float]:
    """Collects exact numbers, scanner constants, and derived ORB margins present in the scan rows."""
    allowed: set[float] = {
        0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 15.0, 20.0, 41.0, 52.0,
        float(len(rows)),
    }
    if as_of:
        for part in re.findall(r"\d+(?:\.\d+)?", str(as_of)):
            try:
                allowed.add(round(float(part), 2))
            except ValueError:
                pass

    for r in rows:
        for k, v in r.items():
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) and pd.notna(v):
                fv = float(v)
                allowed.add(round(fv, 2))
                allowed.add(round(abs(fv), 2))
                allowed.add(round(fv, 1))
                allowed.add(round(abs(fv), 1))

        c_val = r.get("Close")
        orb_hi = r.get("ORB High")
        orb_lo = r.get("ORB Low")
        if isinstance(c_val, (int, float)) and pd.notna(c_val):
            if isinstance(orb_hi, (int, float)) and pd.notna(orb_hi):
                diff_hi = round(abs(float(c_val) - float(orb_hi)), 2)
                allowed.add(diff_hi)
                allowed.add(round(diff_hi, 1))
            if isinstance(orb_lo, (int, float)) and pd.notna(orb_lo):
                diff_lo = round(abs(float(c_val) - float(orb_lo)), 2)
                allowed.add(diff_lo)
                allowed.add(round(diff_lo, 1))
    return allowed


def verify_scan_explanation(text: str, rows: list[dict[str, Any]], as_of: str | None) -> dict[str, Any]:
    """Deterministically checks that every numeric token in the AI explanation matches the scan data."""
    allowed = _extract_allowed_numbers(rows, as_of)
    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", text)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}\b", "", cleaned)

    found_tokens = re.findall(r"(?<![A-Za-z0-9_])-?\d+(?:\.\d+)?%?", cleaned)
    mismatches: list[str] = []
    checked_numbers: list[float] = []

    for tok in found_tokens:
        num_str = tok.rstrip("%")
        try:
            val = float(num_str)
        except ValueError:
            continue
        checked_numbers.append(val)
        candidates = {round(val, 2), round(abs(val), 2), round(val, 1), round(abs(val), 1)}
        if not (candidates & allowed):
            mismatches.append(tok)

    return {
        "passed": len(mismatches) == 0,
        "mismatches": mismatches,
        "checked_count": len(checked_numbers),
    }


def explain_radar_scan(
    rows: list[dict[str, Any]],
    nifty_regime: str,
    as_of: str | None,
    groq_model: str = DEFAULT_GROQ_MODEL,
) -> dict[str, Any]:
    """
    Explains deterministic scan results using ONLY scan rows (JSON), Nifty regime, and as-of date,
    then runs deterministic numeric verification.
    """
    if not rows:
        return {
            "raw_text": "No equity rows available to explain.",
            "verification": {"passed": False, "mismatches": ["No rows"], "checked_count": 0},
        }

    payload_json = json.dumps(
        {
            "as_of": as_of,
            "nifty_regime": nifty_regime,
            "rows": rows,
        },
        indent=2,
    )

    system_prompt = (
        "You explain a deterministic NSE stock radar table in plain English. "
        "STRICT RULE: Use ONLY numbers present in the provided JSON (or exact Close - ORB High / ORB Low differences if explicitly stating ORB margin). "
        "Never invent external prices, targets, or unstated percentages. "
        "Return:\n"
        "1. A single-line **Overview** summarizing ORB / breadth / Nifty regime.\n"
        "2. One bullet per stock (`- **TICKER (Score X/4):** ...`) explaining why the score is what it is, plus one concrete caution (such as 'extended', 'low volume', or 'ORB margin only ₹X.XX')."
    )

    content = ""
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
                        {"role": "user", "content": payload_json},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 550,
                },
                timeout=20,
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    content = (choices[0]["message"]["content"] or "").strip()
        except Exception:
            content = ""

    if not content:
        above_cnt = sum(1 for r in rows if r.get("ORB Status") == "Above range")
        overview_line = (
            f"{above_cnt} of {len(rows)} stocks are above their 15m opening range as of {as_of or 'latest session'} "
            f"with Nifty at {nifty_regime}."
        )
        bullets: list[str] = []
        for r in rows:
            tkr = r.get("Ticker", "STOCK")
            sc = r.get("Score", 0)
            rv = r.get("Rel Vol")
            ema_d = r.get("vs 41-EMA")
            orb_st = r.get("ORB Status", "-")
            ext = bool(r.get("Extended", False))

            cautions: list[str] = []
            if ext:
                cautions.append(f"extended ({ema_d}% above daily 41-EMA)")
            if rv is not None and float(rv) < REL_VOL_MIN:
                cautions.append(f"low volume ({rv}x)")
            if isinstance(r.get("Close"), (int, float)) and isinstance(r.get("ORB High"), (int, float)) and orb_st == "Above range":
                margin = round(float(r["Close"]) - float(r["ORB High"]), 2)
                if margin <= 10.0:
                    cautions.append(f"ORB margin only ₹{margin:.2f}")
            if not cautions:
                cautions.append(f"ORB status: {orb_st}")

            bullets.append(
                f"- **{tkr} (Score {sc}/4):** Daily 41-EMA gap is {ema_d}%, 20D relative volume is {rv}x, and ORB is {orb_st}; "
                f"caution: {', '.join(cautions)}."
            )
        content = f"**Overview:** {overview_line}\n\n" + "\n".join(bullets)

    verification = verify_scan_explanation(content, rows, as_of)
    return {
        "raw_text": content,
        "verification": verification,
    }