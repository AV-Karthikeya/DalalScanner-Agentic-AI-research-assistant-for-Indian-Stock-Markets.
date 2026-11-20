import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import quote_plus
import feedparser
import requests
from config import WATCHLIST

try:
    import streamlit as st
except ImportError:
    st = None

PULSE_FEED_URL = "https://pulse.zerodha.com/feed.php"
INDEX_KEYWORDS = (
    "nifty",
    "sensex",
    "bank nifty",
    "india vix",
    "stock market",
    "equities",
    "rupee",
    "rbi",
    "fii",
    "dii",
    "bse",
    "nse",
)


def _clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_pulse_uncached() -> List[Dict[str, str]]:
    """Fetches recent headlines from Pulse by Zerodha RSS feed."""
    try:
        resp = requests.get(
            PULSE_FEED_URL,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception:
        return []

    items: List[Dict[str, str]] = []
    for entry in feed.entries:
        raw_title = _clean_text(entry.get("title", ""))
        if not raw_title:
            continue

        source_name = "Pulse by Zerodha"
        clean_title = raw_title
        if " - " in raw_title:
            head_part, tail_part = raw_title.rsplit(" - ", 1)
            if 1 <= len(tail_part.split()) <= 5:
                clean_title = head_part.strip()
                source_name = f"Pulse ({tail_part.strip()})"

        summary_text = _clean_text(entry.get("summary", ""))
        items.append(
            {
                "title": clean_title,
                "source": source_name,
                "published": entry.get("published", ""),
                "url": entry.get("link", ""),
                "snippet": summary_text,
            }
        )
    return items


if st is not None:
    @st.cache_data(ttl=300, show_spinner=False)
    def _get_all_pulse_items() -> List[Dict[str, str]]:
        return _fetch_pulse_uncached()
else:
    def _get_all_pulse_items() -> List[Dict[str, str]]:
        return _fetch_pulse_uncached()


def _get_pulse_matches(ticker: str, company_name: str, limit: int = 3) -> List[Dict[str, str]]:
    """Filters cached Pulse items relevant to the requested ticker or index."""
    all_items = _get_all_pulse_items()
    if not all_items:
        return []

    sym_clean = ticker.lstrip("^").replace(".NS", "").replace(".BO", "").strip().upper()
    matched: List[Dict[str, str]] = []

    if ticker.startswith("^"):
        for it in all_items:
            hay = f"{it['title']} {it['snippet']}".lower()
            if any(kw in hay for kw in INDEX_KEYWORDS):
                matched.append(it)
                if len(matched) >= limit:
                    break
        return matched

    aliases: set[str] = set()
    if sym_clean and len(sym_clean) >= 2:
        aliases.add(sym_clean.lower())
    if company_name:
        cleaned_comp = re.sub(
            r"\b(limited|ltd|corp|corporation|inc|co|india|bank of|the)\b",
            " ",
            company_name.lower(),
        )
        cleaned_comp = re.sub(r"\s+", " ", cleaned_comp).strip()
        if len(cleaned_comp) >= 3:
            aliases.add(cleaned_comp)
        first_two = " ".join(cleaned_comp.split()[:2]).strip()
        if len(first_two) >= 4:
            aliases.add(first_two)

    for it in all_items:
        hay = f"{it['title']} {it['snippet']}".lower()
        if any(
            re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", hay)
            for alias in aliases
        ):
            matched.append(it)
            if len(matched) >= limit:
                break

    return matched


def get_ticker_news(
    ticker: str,
    company_name: str,
    max_articles: int = 5,
    lookback: str = "2d",
) -> Dict[str, Any]:
    """
    Fetches recent Indian financial news headlines for a given NSE/BSE ticker or index
    from Pulse by Zerodha and Google News RSS, deduplicates them, and assigns
    deterministic citation IDs for grounding checks.
    """
    short_code = ticker.lstrip("^").replace(".NS", "").replace(".BO", "")
    query = quote_plus(f'"{company_name}" OR "{short_code}" NSE stock when:{lookback}')
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

    google_articles: List[Dict[str, Any]] = []
    google_err: str | None = None
    try:
        resp = requests.get(rss_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:max_articles]:
            source_name = entry.get("source", {}).get("title", "Unknown Source")
            raw_title = _clean_text(entry.get("title", ""))
            clean_title = raw_title.rsplit(" - ", 1)[0].strip() if " - " in raw_title else raw_title
            if clean_title:
                google_articles.append(
                    {
                        "title": clean_title,
                        "source": source_name,
                        "published": entry.get("published", ""),
                        "url": entry.get("link", ""),
                    }
                )
    except Exception as exc:
        google_err = str(exc)

    pulse_matches = _get_pulse_matches(ticker=ticker, company_name=company_name, limit=max(2, max_articles // 2 + 1))

    merged: List[Dict[str, Any]] = []
    seen_titles: set[str] = set()
    for art in list(pulse_matches) + google_articles:
        title = _clean_text(str(art.get("title", "")))
        norm = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        if not norm or norm in seen_titles:
            continue
        seen_titles.add(norm)
        merged.append(
            {
                "title": title,
                "source": art.get("source", "Unknown Source"),
                "published": art.get("published", ""),
                "url": art.get("url", ""),
            }
        )
        if len(merged) >= max_articles:
            break

    for idx, item in enumerate(merged, start=1):
        item["citation_id"] = f"{short_code}_N{idx}"

    if not merged and google_err:
        return {
            "ticker": ticker,
            "company_name": company_name,
            "status": "error",
            "error": google_err,
            "article_count": 0,
            "articles": [],
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "ticker": ticker,
        "company_name": company_name,
        "status": "ok",
        "article_count": len(merged),
        "articles": merged,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def get_watchlist_news(
    max_articles_per_ticker: int = 5,
    watchlist: list[dict] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Fetches recent news snapshots for every stock in the watchlist."""
    target_list = watchlist if watchlist is not None else WATCHLIST
    results: Dict[str, Dict[str, Any]] = {}
    for item in target_list:
        ticker = item["ticker"]
        results[ticker] = get_ticker_news(
            ticker=ticker,
            company_name=item["name"],
            max_articles=max_articles_per_ticker,
        )
    return results


if __name__ == "__main__":
    news_data = get_watchlist_news(max_articles_per_ticker=3)
    print(json.dumps(news_data, indent=2))