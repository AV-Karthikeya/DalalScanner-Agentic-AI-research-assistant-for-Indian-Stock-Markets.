import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.verifier import verify_ticker_brief

with open("data/latest_brief.json", "r", encoding="utf-8") as f:
    report = json.load(f)

sample_ticker = next(iter(report["briefs"]))
clean_brief = report["briefs"][sample_ticker]
raw_price = report["raw_prices"][sample_ticker]
raw_news = report["raw_news"][sample_ticker]

tests = []

# 1. Corrupt close price (+₹250 hallucination)
bad_price = copy.deepcopy(clean_brief)
bad_price["close_price"] = round(clean_brief["close_price"] + 250.0, 2)
tests.append(("Injected +250 price hallucination", bad_price))

# 2. Inject fake citation ID
bad_cite = copy.deepcopy(clean_brief)
bad_cite["key_drivers"] = [
    f"Strong institutional buying driven by Q3 beat [{sample_ticker.split('.')[0]}_N99]."
]
tests.append(("Injected non-existent citation ID (_N99)", bad_cite))

# 3. Inject ungrounded number in narrative prose
bad_num = copy.deepcopy(clean_brief)
bad_num["headline_summary"] += " Management also announced a massive ₹4,500 crore buyback."
tests.append(("Injected ungrounded ₹4,500 crore figure in prose", bad_num))

print(f"\n=== Deterministic Verifier Fault-Injection Suite ({sample_ticker}) ===")
caught = 0
for label, corrupted in tests:
    res = verify_ticker_brief(corrupted, raw_price, raw_news)
    status = "CAUGHT (FLAGGED)" if not res["passed"] else "MISSED"
    if not res["passed"]:
        caught += 1
    details = (
        res.get("errors")
        or res.get("issues")
        or res.get("flags")
        or res.get("reasons")
        or {k: v for k, v in res.items() if k != "passed"}
    )
    print(f"[{status}] {label} -> Details: {details}")

print(f"\nFault Catch Rate: {caught}/{len(tests)} ({round(caught/len(tests)*100, 1)}%)\n")