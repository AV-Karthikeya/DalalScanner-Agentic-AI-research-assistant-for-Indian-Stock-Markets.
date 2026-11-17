import re
from typing import Any, Dict, List


def verify_ticker_brief(
    brief: Dict[str, Any],
    raw_price: Dict[str, Any],
    raw_news: Dict[str, Any],
    tolerance: float = 0.02,
) -> Dict[str, Any]:
    """
    Deterministically verifies an LLM-generated TickerBrief against raw tool outputs.
    Checks:
      1. Structured numeric fields match raw_price within tolerance.
      2. Numeric values mentioned inside headline_summary exist in raw_price or raw_news.
      3. All cited_ids exist in raw_news['articles'].
    """
    issues: List[str] = []

    # --- Check 1: Structured Numeric Fields vs. Ground Truth ---
    numeric_fields = [
        ("close_price", "close"),
        ("day_change_pct", "day_change_pct"),
        ("five_day_change_pct", "five_day_change_pct"),
        ("volume_zscore", "volume_zscore"),
    ]
    for brief_key, raw_key in numeric_fields:
        b_val = brief.get(brief_key)
        r_val = raw_price.get(raw_key)
        if b_val is not None and r_val is not None:
            if abs(float(b_val) - float(r_val)) > tolerance:
                issues.append(
                    f"Numeric mismatch on {brief_key}: brief={b_val} vs raw={r_val}"
                )

    # --- Check 2: Narrative Numbers Grounding ---
    # Build set of allowed numbers from raw_price and raw_news titles
    allowed_numbers = set()
    for val in raw_price.values():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            allowed_numbers.add(round(abs(float(val)), 2))

    valid_articles = raw_news.get("articles", [])
    news_text = " ".join(a.get("title", "") for a in valid_articles)
    for num_str in re.findall(r"\d+(?:\.\d+)?", news_text):
        allowed_numbers.add(round(float(num_str), 2))

   # Strip ISO dates (e.g., 2026-11-17) and citation IDs (e.g., HDFCBANK_N3, ^NSEBANK_N1, NSEBANK_N1)
    summary_clean = brief.get("headline_summary", "").replace(",", "")
    summary_clean = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", summary_clean)
    summary_clean = re.sub(r"\^?[A-Z0-9]+_N\d+\b", "", summary_clean)

    # Ignore calendar day/month numbers, years, and "NIFTY 50" index name token
    date_ignores = set(range(1, 32)) | {50.0, 2025.0, 2026.0, 2027.0}

    for num_str in re.findall(r"\d+(?:\.\d+)?", summary_clean):
        num_val = round(float(num_str), 2)
        if num_val in date_ignores:
            continue
        is_grounded = any(abs(num_val - allowed) <= tolerance for allowed in allowed_numbers)
        if not is_grounded:
            issues.append(f"Ungrounded number '{num_str}' found in headline_summary")

    # --- Check 3: Citation ID Grounding ---
    valid_ids = {a["citation_id"] for a in valid_articles}
    cited_ids = brief.get("cited_ids", [])

    for cid in cited_ids:
        if cid not in valid_ids:
            issues.append(f"Hallucinated citation_id: '{cid}' not in raw news")

    if valid_articles and not cited_ids:
        issues.append("No citation_ids provided despite available news articles")

    passed = len(issues) == 0
    return {
        "ticker": brief.get("ticker"),
        "passed": passed,
        "status": "VERIFIED" if passed else "FLAGGED",
        "issue_count": len(issues),
        "issues": issues,
        "verified_citations": [c for c in cited_ids if c in valid_ids],
    }


def verify_all_briefs(agent_output: Dict[str, Any]) -> Dict[str, Any]:
    """Runs deterministic verification across every stock in the watchlist."""
    raw_prices = agent_output["raw_prices"]
    raw_news = agent_output["raw_news"]
    briefs = agent_output["briefs"]

    results: Dict[str, Any] = {}
    passed_count = 0

    for ticker, brief in briefs.items():
        verdict = verify_ticker_brief(
            brief=brief,
            raw_price=raw_prices[ticker],
            raw_news=raw_news[ticker],
        )
        results[ticker] = verdict
        if verdict["passed"]:
            passed_count += 1

    return {
        "total_tickers": len(briefs),
        "passed_count": passed_count,
        "pass_rate_pct": round((passed_count / max(len(briefs), 1)) * 100, 1),
        "per_ticker": results,
    }