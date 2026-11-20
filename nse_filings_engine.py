from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")

NSE_BASE = "https://www.nseindia.com"
NSE_FILINGS_PAGE = f"{NSE_BASE}/companies-listing/corporate-filings-announcements"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_FILINGS_PAGE,
    "X-Requested-With": "XMLHttpRequest",
}


def _create_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    for seed_url in (
        NSE_FILINGS_PAGE,
        f"{NSE_BASE}/companies-listing/corporate-filings-financial-results",
        NSE_BASE,
    ):
        try:
            resp = session.get(seed_url, timeout=8)
            if resp.status_code == 200 and session.cookies:
                break
        except Exception:
            continue
    return session


def _fetch_json(session: requests.Session, url: str, params: dict[str, Any]) -> Any:
    resp = session.get(url, params=params, timeout=12)
    if resp.status_code in (401, 403):
        session.get(NSE_FILINGS_PAGE, timeout=10)
        resp = session.get(url, params=params, timeout=12)
    resp.raise_for_status()
    return resp.json()


def _parse_nse_date(raw: str) -> datetime:
    cleaned = " ".join((raw or "").strip().split())
    if not cleaned or cleaned == "-":
        return datetime.min
    formats = (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%d/%m/%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return datetime.min


def _ym_key(raw_date: str) -> str:
    """Normalizes any date string to 'YYYY-MM' (e.g., 30-SEP-2026 -> 2026-09)."""
    dt = _parse_nse_date(raw_date)
    return dt.strftime("%Y-%m") if dt != datetime.min else ""


def _fmt_lakhs(val: Any) -> str:
    if val is None or str(val).strip() in ("", "-", "None", "nan"):
        return "-"
    try:
        num = float(str(val).replace(",", ""))
        return f"{num:,.2f}"
    except ValueError:
        return str(val).strip()


def _get_yf_quarterly_fallback(symbol: str) -> dict[str, dict[str, str]]:
    """Fallback quarterly Revenue, Net Profit (in ₹ Lakhs), and EPS from yfinance keyed by YYYY-MM."""
    out: dict[str, dict[str, str]] = {}
    try:
        tkr = yf.Ticker(f"{symbol}.NS")
        q_inc = tkr.quarterly_income_stmt
        if q_inc is None or q_inc.empty:
            return out
        for col_dt in q_inc.columns:
            ym = col_dt.strftime("%Y-%m")
            rev_raw = q_inc.loc["Total Revenue", col_dt] if "Total Revenue" in q_inc.index else None
            pat_raw = q_inc.loc["Net Income", col_dt] if "Net Income" in q_inc.index else None
            eps_raw = q_inc.loc["Basic EPS", col_dt] if "Basic EPS" in q_inc.index else None
            out[ym] = {
                "rev": f"{float(rev_raw) / 1e5:,.2f}" if rev_raw is not None and pd.notna(rev_raw) else "-",
                "pat": f"{float(pat_raw) / 1e5:,.2f}" if pat_raw is not None and pd.notna(pat_raw) else "-",
                "eps": f"{float(eps_raw):,.2f}" if eps_raw is not None and pd.notna(eps_raw) else "-",
            }
    except Exception:
        pass
    return out


def get_nse_filings(ticker: str, lookback_days: int = 365) -> dict[str, Any]:
    """
    Fetches the latest live NSE corporate disclosures up to the current IST timestamp:
    1. Corporate Announcements (with PDF, XBRL .xml, or NSE Portal links)
    2. Corporate Actions (Dividends, Bonus, Splits up to upcoming ex-dates)
    3. Board Meetings (newest-first up to upcoming meetings)
    4. Quarterly Financial Results via NSE's Integrated Filing API (2025-2026 Q1/Q2/Q3/Q4)
    5. Shareholding Pattern History (newest quarters first)
    """
    symbol = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    now_ist = datetime.now(IST)
    to_str = now_ist.strftime("%d-%m-%Y")
    from_str = (now_ist - timedelta(days=lookback_days)).strftime("%d-%m-%Y")
    actions_from_str = (now_ist - timedelta(days=1095)).strftime("%d-%m-%Y")
    actions_to_str = (now_ist + timedelta(days=90)).strftime("%d-%m-%Y")

    session = _create_nse_session()
    announcements: list[dict[str, str]] = []
    corporate_actions: list[dict[str, str]] = []
    board_meetings: list[dict[str, str]] = []
    financial_results: list[dict[str, str]] = []
    shareholding: list[dict[str, str]] = []
    errors: list[str] = []

    # 1. Corporate Announcements (newest-first up to today)
    try:
        raw_ann = _fetch_json(
            session,
            f"{NSE_BASE}/api/corporate-announcements",
            params={
                "index": "equities",
                "symbol": symbol,
                "from_date": from_str,
                "to_date": to_str,
            },
        )
        rows = raw_ann if isinstance(raw_ann, list) else raw_ann.get("data", [])
        rows = sorted(
            rows,
            key=lambda r: _parse_nse_date(str(r.get("an_dt") or r.get("sort_date") or "")),
            reverse=True,
        )
        for r in rows[:25]:
            raw_link = str(r.get("attchmntFile") or r.get("xbrl") or "").strip()
            if raw_link and not raw_link.startswith("http"):
                raw_link = f"https://nsearchives.nseindia.com/corporate/{raw_link.lstrip('/')}"
            if not raw_link:
                raw_link = f"{NSE_FILINGS_PAGE}?symbol={symbol}"
                file_type = "NSE Portal"
            else:
                file_type = "XBRL" if raw_link.lower().endswith(".xml") else "PDF"

            announcements.append(
                {
                    "Broadcast Date": str(r.get("an_dt") or r.get("exchdisstime") or "-"),
                    "Subject": str(r.get("desc") or r.get("subject") or "-"),
                    "Details": str(r.get("attchmntText") or r.get("sm_name") or "-"),
                    "Type": file_type,
                    "PDF / XBRL Link": raw_link,
                }
            )
    except Exception as exc:
        errors.append(f"Announcements: {exc}")

    # 2. Corporate Actions (newest-first including upcoming ex-dates)
    try:
        raw_act = _fetch_json(
            session,
            f"{NSE_BASE}/api/corporates-corporateActions",
            params={
                "index": "equities",
                "symbol": symbol,
                "from_date": actions_from_str,
                "to_date": actions_to_str,
            },
        )
        act_rows = raw_act if isinstance(raw_act, list) else raw_act.get("data", [])
        act_rows = sorted(
            act_rows,
            key=lambda r: _parse_nse_date(str(r.get("exDate") or r.get("recDate") or "")),
            reverse=True,
        )
        for r in act_rows[:15]:
            corporate_actions.append(
                {
                    "Ex-Date": str(r.get("exDate") or "-"),
                    "Record Date": str(r.get("recDate") or "-"),
                    "Purpose": str(r.get("subject") or "-"),
                    "Face Value": str(r.get("faceVal") or "-"),
                }
            )
    except Exception as exc:
        errors.append(f"Actions: {exc}")

    # 3. Board Meetings (newest-first including upcoming meetings)
    try:
        raw_bm = _fetch_json(
            session,
            f"{NSE_BASE}/api/corporate-board-meetings",
            params={
                "index": "equities",
                "symbol": symbol,
                "from_date": from_str,
                "to_date": actions_to_str,
            },
        )
        bm_rows = raw_bm if isinstance(raw_bm, list) else raw_bm.get("data", [])
        bm_rows = sorted(
            bm_rows,
            key=lambda r: _parse_nse_date(str(r.get("bm_date") or r.get("bm_timestamp") or "")),
            reverse=True,
        )
        for r in bm_rows[:15]:
            board_meetings.append(
                {
                    "Meeting Date": str(r.get("bm_date") or "-"),
                    "Purpose": str(r.get("bm_purpose") or "-"),
                    "Details": str(r.get("bm_desc") or "-"),
                }
            )
    except Exception as exc:
        errors.append(f"Board Meetings: {exc}")

    # 4. Quarterly Financial Results via NSE Integrated Filing API (2025-2026) + legacy fallback
    try:
        res_rows: list[dict[str, Any]] = []
        try:
            raw_int = _fetch_json(
                session,
                f"{NSE_BASE}/api/integrated-filing-results",
                params={
                    "index": "equities",
                    "type": "Integrated Filing- Financials",
                    "symbol": symbol,
                    "page": 1,
                    "size": 25,
                },
            )
            if isinstance(raw_int, list):
                res_rows = raw_int
            elif isinstance(raw_int, dict):
                res_rows = raw_int.get("data") or raw_int.get("rows") or []
        except Exception:
            res_rows = []

        # Fallback to legacy pre-2025 endpoint only if integrated-filing-results returned empty
        if not res_rows:
            raw_legacy = _fetch_json(
                session,
                f"{NSE_BASE}/api/corporates-financial-results",
                params={"index": "equities", "symbol": symbol, "period": "Quarterly"},
            )
            res_rows = raw_legacy if isinstance(raw_legacy, list) else raw_legacy.get("data", [])

        comp_map: dict[str, dict[str, Any]] = {}
        try:
            raw_comp = _fetch_json(
                session,
                f"{NSE_BASE}/api/results-comparision",
                params={"index": "equities", "symbol": symbol},
            )
            comp_list = raw_comp.get("resCmpData", []) if isinstance(raw_comp, dict) else []
            for c in comp_list:
                ym = _ym_key(str(c.get("re_to_dt") or ""))
                if ym:
                    comp_map[ym] = c
        except Exception:
            pass

        yf_fallback = _get_yf_quarterly_fallback(symbol)

        res_rows = sorted(
            res_rows,
            key=lambda r: (
                _parse_nse_date(str(r.get("qe_Date") or r.get("toDate") or "")),
                _parse_nse_date(str(r.get("broadcast_Date") or r.get("creation_Date") or r.get("filingDate") or "")),
            ),
            reverse=True,
        )

        for r in res_rows[:12]:
            period_end = str(r.get("qe_Date") or r.get("toDate") or "-").strip()
            filing_dt = str(r.get("broadcast_Date") or r.get("creation_Date") or r.get("filingDate") or "-").strip()
            ym = _ym_key(period_end)
            comp = comp_map.get(ym, {})
            yf_q = yf_fallback.get(ym, {})

            filing_link = str(r.get("xbrl") or r.get("attchmntFile") or r.get("ixbrl") or "").strip()
            if filing_link and not filing_link.startswith("http"):
                filing_link = f"https://nsearchives.nseindia.com/corporate/{filing_link.lstrip('/')}"
            if not filing_link:
                filing_link = f"{NSE_BASE}/companies-listing/corporate-filings-financial-results?symbol={symbol}"

            rev_raw = r.get("income") or comp.get("re_tot_inc") or comp.get("re_net_sale")
            pat_raw = r.get("proLossAftTax") or comp.get("re_net_profit")
            eps_raw = r.get("reBasicEPS") or comp.get("re_basic_eps")

            rev_str = _fmt_lakhs(rev_raw) if rev_raw not in (None, "", "-") else yf_q.get("rev", "-")
            pat_str = _fmt_lakhs(pat_raw) if pat_raw not in (None, "", "-") else yf_q.get("pat", "-")
            eps_str = _fmt_lakhs(eps_raw) if eps_raw not in (None, "", "-") else yf_q.get("eps", "-")

            financial_results.append(
                {
                    "Period Ended": period_end,
                    "Filing Date": filing_dt,
                    "Audit": str(r.get("audited") or "-"),
                    "Basis": str(r.get("consolidated") or "-"),
                    "Revenue / Income (₹ Lakhs)": rev_str,
                    "Net Profit / PAT (₹ Lakhs)": pat_str,
                    "Basic EPS (₹)": eps_str,
                    "Filing Link": filing_link,
                }
            )
    except Exception as exc:
        errors.append(f"Financial Results: {exc}")

    # 5. Shareholding Pattern History (newest quarters first)
    try:
        raw_sh = _fetch_json(
            session,
            f"{NSE_BASE}/api/corporate-share-holdings-master",
            params={"index": "equities", "symbol": symbol},
        )
        sh_rows = raw_sh if isinstance(raw_sh, list) else raw_sh.get("data", [])
        sh_rows = sorted(
            sh_rows,
            key=lambda r: _parse_nse_date(str(r.get("date") or "")),
            reverse=True,
        )
        for r in sh_rows[:8]:
            shareholding.append(
                {
                    "Quarter Ended": str(r.get("date") or "-"),
                    "Promoter & Group (%)": str(r.get("pr_and_prgrp") or "-"),
                    "Public (%)": str(r.get("public_val") or "-"),
                    "Employee Trusts (%)": str(r.get("employeeTrusts") or "-"),
                }
            )
    except Exception as exc:
        errors.append(f"Shareholding: {exc}")

    fetched_ts = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")
    status = (
        f"Live NSE Feed ({from_str} to {to_str} • Fetched {fetched_ts}) — {len(announcements)} announcements, {len(financial_results)} quarters"
        if not errors
        else f"Partial Live NSE Feed ({'; '.join(errors)})"
    )

    return {
        "symbol": symbol,
        "status": status,
        "announcements": announcements,
        "corporate_actions": corporate_actions,
        "board_meetings": board_meetings,
        "financial_results": financial_results,
        "shareholding": shareholding,
    }