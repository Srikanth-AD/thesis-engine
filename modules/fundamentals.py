"""
Layer 2 — Fundamentals

Valuation (P/E, P/S, EV/EBITDA), margins, balance sheet health,
short interest, and analyst consensus from Finnhub.
Free tier covers all endpoints used here.
"""
import os
import time

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


def fetch_fundamentals(tickers):
    """
    Fetch fundamental data for each ticker.

    Returns dict keyed by ticker with valuation, growth, margins,
    balance sheet, and analyst consensus data.
    """
    results = {}

    for ticker in tickers:
        try:
            m = _get("/stock/metric", {"symbol": ticker, "metric": "all"})
            metric = m.get("metric", {})

            # Analyst recommendations — take most recent period
            rec_data = _get("/stock/recommendation", {"symbol": ticker})
            rec = {}
            if isinstance(rec_data, list) and rec_data:
                latest = rec_data[0]
                total = sum([
                    latest.get("strongBuy", 0),
                    latest.get("buy", 0),
                    latest.get("hold", 0),
                    latest.get("sell", 0),
                    latest.get("strongSell", 0),
                ])
                if total > 0:
                    buys = latest.get("strongBuy", 0) + latest.get("buy", 0)
                    if buys / total > 0.7:
                        consensus = "Strong Buy"
                    elif buys / total > 0.5:
                        consensus = "Buy"
                    elif latest.get("hold", 0) / total > 0.5:
                        consensus = "Hold"
                    else:
                        consensus = "Mixed"
                    rec = {
                        "consensus": consensus,
                        "count": total,
                        "strong_buy": latest.get("strongBuy", 0),
                        "buy": latest.get("buy", 0),
                        "hold": latest.get("hold", 0),
                        "sell": latest.get("sell", 0) + latest.get("strongSell", 0),
                    }

            # Price target consensus
            pt_data = _get("/stock/price-target", {"symbol": ticker})
            price_target = None
            if isinstance(pt_data, dict) and pt_data.get("targetMean"):
                price_target = round(pt_data["targetMean"], 2)

            results[ticker] = {
                # Valuation
                "pe": metric.get("peBasicExclExtraTTM"),
                "fwd_pe": metric.get("peExclExtraHighAnnual"),
                "ps": metric.get("psTTM"),
                "pb": metric.get("pbQuarterly"),
                "ev_ebitda": metric.get("evEbitdaTTM"),
                # Growth
                "revenue_growth": metric.get("revenueGrowthTTMYoy"),
                "eps_growth": metric.get("epsGrowth3Y"),
                # Margins
                "gross_margin": metric.get("grossMarginTTM"),
                "op_margin": metric.get("operatingMarginTTM"),
                "net_margin": metric.get("netMarginTTM"),
                # Balance sheet
                "debt_equity": metric.get("totalDebt/totalEquityAnnual"),
                "current_ratio": metric.get("currentRatioAnnual"),
                "fcf": metric.get("fcfMarginTTM"),
                # Market
                "mkt_cap": metric.get("marketCapitalization"),
                "short_interest": metric.get("shortInterestShareFloat"),
                # Analyst
                "analyst_consensus": rec.get("consensus", "N/A"),
                "analyst_count": rec.get("count", 0),
                "analyst_buys": rec.get("strong_buy", 0) + rec.get("buy", 0),
                "analyst_holds": rec.get("hold", 0),
                "analyst_sells": rec.get("sell", 0),
                "price_target": price_target,
            }
            time.sleep(0.2)

        except Exception as e:
            results[ticker] = {"error": str(e)}

    return results
