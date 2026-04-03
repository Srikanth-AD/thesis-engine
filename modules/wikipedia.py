"""
Layer 10 -- Wikipedia Page Views

Page view spikes are a real-time proxy for public attention.
A 3x spike typically means something newsworthy is happening.
Free Wikimedia API, no key needed.
"""
import time
from datetime import datetime, timedelta

import requests

WIKI_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

# Map ticker to Wikipedia article title.
# Add or customize entries for your portfolio. Some company names differ
# from their article titles on Wikipedia.
TICKER_TO_WIKI = {
    "AAPL": "Apple_Inc.",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "TSLA": "Tesla,_Inc.",
    "AMZN": "Amazon_(company)",
    "GOOGL": "Alphabet_Inc.",
    "META": "Meta_Platforms",
}


def _get_views(article, days=35):
    """
    Fetch daily page views for a Wikipedia article.

    Args:
        article: Wikipedia article title (underscored format).
        days:    Number of days of history to fetch.

    Returns:
        List of daily view counts, or empty list on failure.
    """
    try:
        end   = datetime.now() - timedelta(days=1)
        start = end - timedelta(days=days)
        url   = (
            f"{WIKI_API}/en.wikipedia/all-access/all-agents/"
            f"{article}/daily/"
            f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
        )
        r = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "thesis-engine/1.0"},
        )
        if r.status_code == 200:
            items = r.json().get("items", [])
            return [i["views"] for i in items]
    except Exception:
        pass
    return []


def fetch_wikipedia_views(tickers, portfolio=None):
    """
    Fetch Wikipedia page view data and detect attention spikes.

    Args:
        tickers:   List of ticker symbol strings.
        portfolio: Optional parsed portfolio config. If provided, company
                   names are used to look up Wikipedia articles.

    Returns:
        Dict keyed by ticker with:
        - views_today:    Most recent day's view count.
        - avg_7d:         7-day average views.
        - avg_30d:        30-day average views.
        - spike_multiple: Ratio of 7d avg to 30d avg.
        - spike:          True if spike_multiple > 2.5.
        - article:        Wikipedia article name used.
    """
    results = {}

    # Build name map from portfolio if provided
    name_map = {}
    if portfolio:
        for s in portfolio.get("portfolio", []):
            # Convert "Apple Inc." to "Apple_Inc."
            wiki_name = s.get("name", "").replace(" ", "_")
            name_map[s["ticker"]] = wiki_name

    for ticker in tickers:
        # Try hardcoded map first, then portfolio name, then ticker itself
        article = (
            TICKER_TO_WIKI.get(ticker)
            or name_map.get(ticker)
            or ticker
        )

        try:
            views = _get_views(article, days=35)

            if not views or len(views) < 7:
                results[ticker] = {"error": "insufficient view data"}
                continue

            today_views = views[-1]
            avg_30d     = sum(views[:-5]) / max(len(views) - 5, 1)
            avg_7d      = sum(views[-7:]) / 7

            spike_multiple = (avg_7d / avg_30d) if avg_30d > 0 else 1.0

            results[ticker] = {
                "views_today":    today_views,
                "avg_7d":         round(avg_7d),
                "avg_30d":        round(avg_30d),
                "spike_multiple": round(spike_multiple, 2),
                "spike":          spike_multiple > 2.5,
                "article":        article,
            }

        except Exception as e:
            results[ticker] = {"error": str(e)}

        time.sleep(0.3)

    return results
