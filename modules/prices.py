"""
Layer 1 — Prices & P/L

Fetches live quotes from Finnhub and calculates P/L vs blended cost basis.
Supports multi-tranche positions with automatic weighted-average cost.
Free tier: 60 calls/min.
"""
import os
import time
from datetime import datetime

import requests

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
BASE = "https://finnhub.io/api/v1"


def _get(endpoint, params=None):
    """Make a Finnhub API call with automatic token injection."""
    params = params or {}
    params["token"] = FINNHUB_KEY
    try:
        r = requests.get(f"{BASE}{endpoint}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _blended_cost(purchases):
    """
    Calculate weighted average cost basis across multiple purchase tranches.

    Returns:
        (blended_price, total_shares, total_invested)
    """
    total_dollars = sum(p["dollars"] for p in purchases)
    total_shares = sum(p["dollars"] / p["price_per_share"] for p in purchases)
    if total_shares == 0:
        return 0, 0, 0
    blended = total_dollars / total_shares
    return blended, total_shares, total_dollars


def fetch_prices(tickers, portfolio):
    """
    Fetch live prices and calculate P/L for each ticker.

    Returns dict keyed by ticker, plus portfolio-level P/L aggregates
    under keys prefixed with '__'.
    """
    results = {}
    total_invested = 0
    total_current = 0

    stock_map = {s["ticker"]: s for s in portfolio["portfolio"]}

    for ticker in tickers:
        try:
            q = _get("/quote", {"symbol": ticker})
            if "error" in q or q.get("c", 0) == 0:
                results[ticker] = {"error": f"No quote data: {q.get('error', 'empty')}"}
                continue

            price = q.get("c", 0)
            prev = q.get("pc", price)
            high = q.get("h", price)
            low = q.get("l", price)
            open_ = q.get("o", price)

            change = price - prev
            change_pct = (change / prev * 100) if prev else 0

            # 52-week range from metric endpoint
            profile = _get("/stock/metric", {"symbol": ticker, "metric": "all"})
            metric = profile.get("metric", {})
            w52_high = metric.get("52WeekHigh", 0)
            w52_low = metric.get("52WeekLow", 0)

            if w52_high and w52_low and w52_high != w52_low:
                w52_pos = (price - w52_low) / (w52_high - w52_low) * 100
                w52_label = f"{w52_pos:.0f}% of 52wk range (L${w52_low:.2f}-H${w52_high:.2f})"
            else:
                w52_label = "N/A"

            vol_today = q.get("v", 0) or 0

            # P/L calculation from purchase tranches
            stock = stock_map.get(ticker, {})
            purchases = stock.get("purchases", [])
            blended, shares, invested = _blended_cost(purchases)

            current_value = shares * price
            pnl = current_value - invested
            pnl_pct = (pnl / invested * 100) if invested else 0

            total_invested += invested
            total_current += current_value

            results[ticker] = {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "prev_close": round(prev, 2),
                "day_high": round(high, 2),
                "day_low": round(low, 2),
                "open": round(open_, 2),
                "52w_position": w52_label,
                "blended_cost": round(blended, 2),
                "shares": round(shares, 4),
                "invested": round(invested, 2),
                "current_value": round(current_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 1),
                "volume_today": vol_today,
                "timestamp": datetime.now().isoformat(),
            }
            time.sleep(0.12)

        except Exception as e:
            results[ticker] = {"error": str(e)}

    # Portfolio-level aggregates
    if total_invested > 0:
        portfolio_pnl_pct = (total_current - total_invested) / total_invested * 100
        results["__portfolio_pnl_pct__"] = round(portfolio_pnl_pct, 1)
        results["__total_invested__"] = round(total_invested, 2)
        results["__total_current__"] = round(total_current, 2)
        results["__total_pnl__"] = round(total_current - total_invested, 2)

    return results
