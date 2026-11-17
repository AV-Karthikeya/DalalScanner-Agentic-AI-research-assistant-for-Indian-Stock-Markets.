import json
from datetime import datetime, timezone
from pathlib import Path
from agent.brief_agent import run_watchlist_agent
from evals.verifier import verify_all_briefs
from tools.prices import get_ticker_price_snapshot


def _latest_saved_trade_date(latest_path: Path) -> str | None:
    if not latest_path.exists():
        return None
    try:
        with open(latest_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        for info in existing.get("raw_prices", {}).values():
            if info.get("trade_date"):
                return info["trade_date"]
    except Exception:
        return None
    return None


def run_daily_pipeline(
    watchlist: list[dict] | None = None,
    skip_if_no_new_trading_day: bool = False,
) -> dict:
    """Runs end-to-end data fetch, LLM brief generation, verification, and JSON storage."""
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    latest_path = data_dir / "latest_brief.json"

    if skip_if_no_new_trading_day and watchlist is None and latest_path.exists():
        saved_date = _latest_saved_trade_date(latest_path)
        benchmark = get_ticker_price_snapshot("^NSEI")
        live_date = benchmark.get("trade_date")
        if saved_date and live_date and saved_date == live_date:
            print(
                f"Market holiday / no new trading session since {saved_date}. "
                "Skipping duplicate brief generation."
            )
            with open(latest_path, "r", encoding="utf-8") as f:
                return json.load(f)

    print("=== Step 1: Running Watchlist Brief Agent ===")
    agent_output = run_watchlist_agent(watchlist=watchlist)

    print("\n=== Step 2: Running Deterministic Verifier ===")
    verification = verify_all_briefs(agent_output)

    full_report = {
        "generated_at_utc": agent_output["generated_at_utc"],
        "verification": verification,
        "briefs": agent_output["briefs"],
        "raw_prices": agent_output["raw_prices"],
        "raw_news": agent_output["raw_news"],
    }

    date_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated_path = data_dir / f"brief_{date_tag}.json"

    for path in (latest_path, dated_path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(full_report, f, indent=2, ensure_ascii=False)

    print(f"\nSaved verified report to {latest_path} and {dated_path}")
    print(
        f"Verification Pass Rate: {verification['passed_count']}/{verification['total_tickers']} "
        f"({verification['pass_rate_pct']}%)"
    )
    for ticker, verdict in verification["per_ticker"].items():
        print(f"  - {ticker}: {verdict['status']} | Issues: {verdict['issues']}")

    return full_report


if __name__ == "__main__":
    run_daily_pipeline(skip_if_no_new_trading_day=True)