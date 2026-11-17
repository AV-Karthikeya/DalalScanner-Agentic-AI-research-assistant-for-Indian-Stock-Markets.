import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import quote_plus
import feedparser
import requests
from config import WATCHLIST


def get_ticker_news(
    ticker: str,
    company_name: str,
    max_articles: int = 5,
    lookback: str = "2d",
) -> Dict[str, Any]:
    """
    Fetches recent Indian financial news headlines for a given NSE ticker via
    Google News RSS and assigns deterministic citation IDs for Day 4 grounding checks.
    """
    short_code = ticker.replace(".NS", "")
    query = quote_plus(f'"{company_name}" OR "{short_code}" NSE stock when:{lookback}')
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

    try:
        resp = requests.get(rss_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        return {
            "ticker": ticker,
            "status": "error",
            "error": str(exc),
            "articles": [],
        }

    articles: List[Dict[str, Any]] = []
    for idx, entry in enumerate(feed.entries[:max_articles], start=1):
        source_name = entry.get("source", {}).get("title", "Unknown Source")
        raw_title = entry.get("title", "").strip()
        clean_title = raw_title.rsplit(" - ", 1)[0].strip() if " - " in raw_title else raw_title

        articles.append(
            {
                "citation_id": f"{short_code}_N{idx}",
                "title": clean_title,
                "source": source_name,
                "published": entry.get("published", ""),
                "url": entry.get("link", ""),
            }
        )

    return {
        "ticker": ticker,
        "company_name": company_name,
        "status": "ok",
        "article_count": len(articles),
        "articles": articles,
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