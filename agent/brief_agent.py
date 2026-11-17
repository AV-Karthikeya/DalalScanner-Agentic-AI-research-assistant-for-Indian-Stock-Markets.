import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from config import WATCHLIST
from tools.news import get_watchlist_news
from tools.prices import get_watchlist_prices

load_dotenv()


# 1. Strict Pydantic Schema for each ticker's brief
class TickerBrief(BaseModel):
    ticker: str = Field(description="NSE ticker symbol, e.g., RELIANCE.NS")
    company_name: str
    sentiment: str = Field(description="One of: Bullish, Bearish, Neutral")
    close_price: float = Field(description="Exact latest close price from price data")
    day_change_pct: float = Field(description="Exact 1-day percentage change from price data")
    five_day_change_pct: Optional[float] = Field(description="Exact 5-day percentage change from price data")
    volume_zscore: float = Field(description="Exact 20-day volume z-score from price data")
    headline_summary: str = Field(
        description="2-3 sentence factual brief synthesizing price action and news. Every number MUST match raw price data."
    )
    key_drivers: List[str] = Field(
        description="1 to 3 concise bullet points explaining price or news drivers."
    )
    cited_ids: List[str] = Field(
        description="List of exact citation_id strings (e.g., RELIANCE_N1) from the provided news articles that support the claims."
    )


def generate_ticker_brief(
    client: OpenAI,
    ticker_info: Dict[str, str],
    price_data: Dict[str, Any],
    news_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Calls Groq (Llama 3.3 70B) with strict Pydantic JSON schema enforcement."""
    prompt = f"""
You are a disciplined NSE equity research analyst. Generate a verified daily brief for {ticker_info['name']} ({ticker_info['ticker']}).

STRICT GROUNDING RULES:
1. Use ONLY the numbers provided in RAW_PRICE_DATA. Do NOT round differently, estimate, or invent any financial figures.
2. Base your news commentary ONLY on the headlines in RAW_NEWS_DATA.
3. For every news claim you include, you MUST list its exact `citation_id` (e.g., "{ticker_info['ticker'].replace('.NS', '')}_N1") in `cited_ids`. If no news is relevant, return an empty list `[]`.

RAW_PRICE_DATA:
{json.dumps(price_data, indent=2)}

RAW_NEWS_DATA:
{json.dumps(news_data, indent=2)}
"""

    completion = client.beta.chat.completions.parse(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": "You are a factual financial analyst outputting strict JSON."},
            {"role": "user", "content": prompt},
        ],
        response_format=TickerBrief,
        temperature=0.1,
    )

    parsed = completion.choices[0].message.parsed
    return parsed.model_dump()


def run_watchlist_agent(watchlist: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Fetches raw tool outputs for the watchlist and generates structured briefs."""
    target_list = watchlist if watchlist is not None else WATCHLIST
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found. Make sure it is saved in your .env file.")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    print("Fetching ground-truth prices...")
    raw_prices = get_watchlist_prices(watchlist=target_list)

    print("Fetching ground-truth news...")
    raw_news = get_watchlist_news(max_articles_per_ticker=5, watchlist=target_list)

    briefs: Dict[str, Dict[str, Any]] = {}
    for item in target_list:
        ticker = item["ticker"]
        print(f"Generating structured brief for {ticker}...")
        briefs[ticker] = generate_ticker_brief(
            client=client,
            ticker_info=item,
            price_data=raw_prices[ticker],
            news_data=raw_news[ticker],
        )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_prices": raw_prices,
        "raw_news": raw_news,
        "briefs": briefs,
    }


if __name__ == "__main__":
    output = run_watchlist_agent()
    print(json.dumps(output["briefs"], indent=2))