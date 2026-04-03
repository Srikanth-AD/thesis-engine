"""
Layer 13 -- Congress Trades (Quiver Quantitative)

Congress members must disclose stock trades within 45 days (STOCK Act).
Politicians on relevant committees carry higher signal weight.
Free tier available at quiverquant.com.
"""
import os
import time
from datetime import datetime, timedelta

import requests

QUIVER_KEY  = os.environ.get("QUIVER_API_KEY", "")
QUIVER_BASE = "https://api.quiverquant.com/beta"


# Committee keywords mapped to the sectors they oversee.
# When a congress member on one of these committees trades a stock in
# the corresponding sector, the signal quality is rated HIGH.
#
# Tickers are resolved dynamically from the portfolio's sector field
# rather than being hardcoded here. See _build_committee_ticker_map().
SECTOR_COMMITTEES = {
    "armed services":    ["defense", "aerospace", "space"],
    "armed forces":      ["defense", "aerospace"],
    "intelligence":      ["defense", "cybersecurity"],
    "foreign relations": ["defense", "aerospace", "space"],
    "defense":           ["defense", "aerospace"],
    "science":           ["semiconductor", "ai", "technology", "data center"],
    "technology":        ["semiconductor", "ai", "technology", "data center"],
    "commerce":          ["semiconductor", "technology"],
    "innovation":        ["semiconductor", "ai", "technology"],
    "finance":           ["finance", "banking", "fintech"],
    "banking":           ["finance", "banking", "fintech"],
    "space":             ["space", "aerospace"],
    "health":            ["healthcare", "biotech", "medical device"],
    "energy":            ["energy", "data center", "utilities"],
}


def _build_committee_ticker_map(portfolio):
    """
    Dynamically build a mapping from committee keywords to tickers
    based on the portfolio's sector assignments.

    Args:
        portfolio: Parsed portfolio config (stocks.yaml).

    Returns:
        Dict mapping committee keyword -> list of ticker strings.
    """
    committee_tickers = {key: [] for key in SECTOR_COMMITTEES}

    if not portfolio:
        return committee_tickers

    for stock in portfolio.get("portfolio", []):
        ticker = stock.get("ticker", "")
        sector = stock.get("sector", "").lower()
        thesis = stock.get("thesis", "").lower()
        # Combine sector and thesis for broader matching
        combined = f"{sector} {thesis}"

        for committee_key, sectors in SECTOR_COMMITTEES.items():
            if any(s in combined for s in sectors):
                if ticker not in committee_tickers[committee_key]:
                    committee_tickers[committee_key].append(ticker)

    return committee_tickers


def _is_relevant_committee(committee, ticker, committee_ticker_map):
    """
    Check if a committee member's trade in this ticker has high
    information value.

    Args:
        committee:            Committee name string from the trade data.
        ticker:               Stock ticker being traded.
        committee_ticker_map: Mapping from committee keywords to tickers.

    Returns:
        True if the committee oversees a sector relevant to this ticker.
    """
    if not committee:
        return False
    comm_lower = committee.lower()
    for key, relevant_tickers in committee_ticker_map.items():
        if key in comm_lower and ticker in relevant_tickers:
            return True
    return False


def fetch_congress_trades(tickers, portfolio=None):
    """
    Fetch recent congress trades for a list of tickers.

    Flags trades by members on committees relevant to the stock's sector.
    The committee-to-ticker mapping is built dynamically from the portfolio
    configuration rather than being hardcoded.

    Args:
        tickers:   List of ticker symbol strings.
        portfolio: Optional parsed portfolio config for committee relevance.

    Returns:
        Dict keyed by ticker with list of recent congress trades.
        Each trade includes:
        - name:               Congress member name.
        - chamber:            Senate or House.
        - committee:          Committee assignment.
        - transaction:        Buy or sell.
        - amount_range:       Reported dollar range.
        - transaction_date:   Date of the trade.
        - report_date:        Date trade was reported.
        - relevant_committee: True if committee oversees relevant sector.
        - signal_quality:     'HIGH' or 'MEDIUM'.
    """
    if not QUIVER_KEY:
        return {t: {"error": "QUIVER_API_KEY not set"} for t in tickers}

    # Build dynamic committee-to-ticker mapping
    committee_ticker_map = _build_committee_ticker_map(portfolio)

    results = {}
    headers = {
        "accept":        "application/json",
        "X-CSRFToken":   QUIVER_KEY,
        "Authorization": f"Token {QUIVER_KEY}",
    }

    cutoff = datetime.now() - timedelta(days=180)

    for ticker in tickers:
        try:
            r = requests.get(
                f"{QUIVER_BASE}/historical/congress/{ticker}",
                headers=headers,
                timeout=15,
            )

            if r.status_code != 200:
                results[ticker] = {"error": f"HTTP {r.status_code}"}
                time.sleep(0.3)
                continue

            data = r.json()
            if not isinstance(data, list):
                results[ticker] = []
                continue

            ticker_trades = []
            for trade in data:
                try:
                    tx_date_str = trade.get("TransactionDate", "")
                    if tx_date_str:
                        tx_date = datetime.strptime(tx_date_str[:10], "%Y-%m-%d")
                        if tx_date < cutoff:
                            continue

                    name      = trade.get("Representative", trade.get("Senator", "Unknown"))
                    chamber   = trade.get("Chamber", "Congress")
                    tx_type   = trade.get("Transaction", "Purchase")
                    amount    = trade.get("Amount", "")
                    committee = trade.get("Committee", "")
                    report_dt = trade.get("ReportDate", "")

                    relevant = _is_relevant_committee(
                        committee, ticker, committee_ticker_map
                    )

                    ticker_trades.append({
                        "name":               name,
                        "chamber":            chamber,
                        "committee":          committee,
                        "transaction":        tx_type,
                        "amount_range":       amount,
                        "transaction_date":   tx_date_str[:10] if tx_date_str else "N/A",
                        "report_date":        report_dt[:10] if report_dt else "N/A",
                        "relevant_committee": relevant,
                        "signal_quality":     "HIGH" if relevant else "MEDIUM",
                    })
                except Exception:
                    continue

            # Sort: relevant committee trades first, then by date
            ticker_trades.sort(
                key=lambda x: (0 if x["relevant_committee"] else 1,
                               x.get("transaction_date", "")),
            )
            ticker_trades = ticker_trades[:5]  # Keep top 5

            results[ticker] = ticker_trades
            time.sleep(0.3)

        except Exception as e:
            results[ticker] = {"error": str(e)}

    return results
