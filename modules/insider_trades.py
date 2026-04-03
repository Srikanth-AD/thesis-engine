"""
Layer 12 -- Insider Trades (SEC Form 4)

Executives must file within 2 business days of a trade.
Insider BUYING is one of the strongest signals in finance.
Coordinated C-suite selling is a major red flag.
Free via SEC EDGAR and Finnhub.
"""
import os
import time
from datetime import datetime, timedelta

import requests

FINNHUB_KEY   = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE  = "https://finnhub.io/api/v1"
EDGAR_HEADERS = {"User-Agent": "thesis-engine/1.0"}

# C-suite titles that carry more weight in insider trade analysis
CSUITE_TITLES = {
    "ceo", "cfo", "coo", "cto", "president", "founder",
    "executive chairman", "chief",
}


def _is_csuite(title):
    """Check whether an insider title matches a C-suite role."""
    if not title:
        return False
    return any(t in title.lower() for t in CSUITE_TITLES)


def _fetch_finnhub_insiders(ticker, days_back=90):
    """
    Fetch insider transactions from Finnhub.

    Args:
        ticker:    Stock ticker symbol.
        days_back: Number of days of history to fetch.

    Returns:
        List of transaction dicts from Finnhub, or empty list on failure.
    """
    try:
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date   = datetime.now().strftime("%Y-%m-%d")
        params = {
            "symbol": ticker,
            "from":   from_date,
            "to":     to_date,
            "token":  FINNHUB_KEY,
        }
        r = requests.get(
            f"{FINNHUB_BASE}/stock/insider-transactions",
            params=params,
            timeout=10,
        )
        data = r.json()
        return data.get("data", [])
    except Exception:
        return []


def fetch_insider_trades(tickers):
    """
    Fetch and analyze insider trades for a list of tickers.

    Args:
        tickers: List of ticker symbol strings.

    Returns:
        Dict keyed by ticker with:
        - trades:              List of recent trades (up to 10).
        - net_buy_sell:        Net dollar value (positive = net buying).
        - total_bought:        Total dollar value of purchases.
        - total_sold:          Total dollar value of sales.
        - net_sentiment:       'bullish', 'bearish', or 'neutral'.
        - coordinated_warning: Warning string if multiple C-suite sales detected.
        - csuite_sale_count:   Number of significant C-suite sales.
    """
    results = {}

    for ticker in tickers:
        try:
            raw_trades = _fetch_finnhub_insiders(ticker)

            if not raw_trades:
                results[ticker] = {
                    "trades": [],
                    "net_sentiment": "neutral",
                    "note": "no recent insider activity",
                }
                continue

            trades = []
            total_bought = 0.0
            total_sold   = 0.0
            csuite_sales = []

            for t in raw_trades:
                transaction_type = t.get("transactionCode", "")
                is_buy  = transaction_type in ("P", "A")  # Purchase, Award
                is_sell = transaction_type in ("S", "D")  # Sale, Disposition

                if not (is_buy or is_sell):
                    continue

                shares = abs(t.get("share", 0) or 0)
                price  = t.get("price", 0) or 0
                value  = shares * price
                name   = t.get("name", "Unknown")
                title  = t.get("officerTitle", "")
                date   = t.get("transactionDate", "")

                trade = {
                    "date":          date,
                    "insider_name":  name,
                    "insider_title": title,
                    "is_buy":        is_buy,
                    "shares":        shares,
                    "price":         price,
                    "value":         round(value, 0),
                    "is_csuite":     _is_csuite(title),
                }
                trades.append(trade)

                if is_buy:
                    total_bought += value
                elif is_sell:
                    total_sold += value
                    if _is_csuite(title) and value > 500_000:
                        csuite_sales.append(f"{name} ({title}): ${value:,.0f}")

            # Net sentiment
            net = total_bought - total_sold
            if net > 100_000:
                net_sentiment = "bullish"
            elif net < -500_000:
                net_sentiment = "bearish"
            else:
                net_sentiment = "neutral"

            # Flag coordinated C-suite selling
            coordinated_warning = None
            if len(csuite_sales) >= 2:
                coordinated_warning = (
                    "COORDINATED C-SUITE SELLING: " + "; ".join(csuite_sales)
                )

            results[ticker] = {
                "trades":              trades[:10],
                "net_buy_sell":        round(net, 0),
                "total_bought":        round(total_bought, 0),
                "total_sold":          round(total_sold, 0),
                "net_sentiment":       net_sentiment,
                "coordinated_warning": coordinated_warning,
                "csuite_sale_count":   len(csuite_sales),
            }

            time.sleep(0.2)

        except Exception as e:
            results[ticker] = {"error": str(e)}

    return results
