"""
Layer 11 -- Hedge Fund 13F Holdings

SEC requires funds with >$100M AUM to file quarterly 13F disclosures.
There is a 45-day reporting lag, but the data shows structural
institutional conviction. Free via SEC EDGAR. No key needed.
"""
import time

import requests

EDGAR_HEADERS = {"User-Agent": "thesis-engine/1.0"}
EDGAR_BASE    = "https://data.sec.gov"
EDGAR_SEARCH  = "https://efts.sec.gov/LATEST/search-index"

# Notable funds to flag if they hold portfolio stocks
NOTABLE_FUNDS = {
    "citadel", "tiger global", "coatue", "dragoneer", "baillie gifford",
    "jpmorgan", "vanguard", "blackrock", "fidelity", "ark invest",
    "pershing square", "sequoia", "a16z", "softbank",
}


def _search_13f_for_ticker(ticker, limit=5):
    """
    Search EDGAR for 13F filings mentioning a ticker.

    Args:
        ticker: Stock ticker symbol.
        limit:  Maximum number of filings to return.

    Returns:
        List of filing dicts with entity, file_date, and period.
    """
    try:
        params = {
            "q":         f'"{ticker}"',
            "forms":     "13F-HR",
            "dateRange": "custom",
            "startdt":   "2025-10-01",  # Last ~2 quarters
        }
        r = requests.get(
            EDGAR_SEARCH,
            params=params,
            headers=EDGAR_HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return []

        hits = r.json().get("hits", {}).get("hits", [])
        filings = []
        for hit in hits[:limit]:
            src = hit.get("_source", {})
            filings.append({
                "entity":    src.get("entity_name", "Unknown Fund"),
                "file_date": src.get("file_date", ""),
                "period":    src.get("period_of_report", ""),
            })
        return filings

    except Exception:
        return []


def fetch_hedge_funds(tickers):
    """
    Fetch 13F filing data for each ticker.

    Note: Full 13F parsing (exact share counts) requires XBRL parsing.
    This layer focuses on fund count and notable names, which is the
    most actionable signal.

    Args:
        tickers: List of ticker symbol strings.

    Returns:
        Dict keyed by ticker with:
        - fund_count:         Number of 13F filings found.
        - notable:            Comma-separated notable fund names.
        - most_recent_filing: Date of the most recent filing.
        - note:               Reminder about 13F reporting lag.
    """
    results = {}

    for ticker in tickers:
        try:
            filings = _search_13f_for_ticker(ticker, limit=20)

            fund_names = [f["entity"].lower() for f in filings]
            fund_count = len(filings)

            # Check for notable funds
            notable_holders = []
            for name in fund_names:
                for notable in NOTABLE_FUNDS:
                    if notable in name:
                        for f in filings:
                            if notable in f["entity"].lower():
                                notable_holders.append(f["entity"])
                        break

            # Most recent filing date
            recent_dates = sorted(
                [f["file_date"] for f in filings if f.get("file_date")],
                reverse=True,
            )
            most_recent = recent_dates[0] if recent_dates else "N/A"

            results[ticker] = {
                "fund_count":         fund_count,
                "notable":            ", ".join(set(notable_holders[:4])) if notable_holders else "None flagged",
                "most_recent_filing": most_recent,
                "note":               "13F data: ~45 day lag, shows prior quarter holdings",
            }

            time.sleep(0.5)

        except Exception as e:
            results[ticker] = {"error": str(e)}

    return results
