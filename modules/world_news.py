"""
Layer 7 -- World News & Geopolitics (GDELT)

GDELT monitors global news in 100+ languages, updates every 15 minutes.
No API key required. Completely free.
Maps geopolitical events to portfolio sector exposures.
"""
import time
from datetime import datetime

import requests

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


# Themes relevant to common portfolio sectors.
# Customize these to match the sectors in your portfolio.
PORTFOLIO_THEMES = {
    "AI_DATA_CENTERS": [
        "artificial intelligence", "data center", "hyperscaler",
        "AI infrastructure", "GPU", "semiconductor", "cloud computing",
    ],
    "DEFENSE_SPACE": [
        "missile defense", "Pentagon", "DoD contract",
        "defense spending", "NATO", "hypersonic", "space launch",
    ],
    "MACRO_RISK": [
        "Federal Reserve", "inflation", "interest rate", "tariff",
        "semiconductor export", "China tech", "supply chain",
    ],
    "ENERGY_OIL": [
        "Strait of Hormuz", "oil price", "energy crisis",
        "OPEC", "oil supply",
    ],
    "ROBOTICS_AI": [
        "warehouse automation", "surgical robot", "humanoid robot",
        "AI regulation", "EU AI Act", "robot deployment",
    ],
}


def _search_gdelt(query, hours_back=6, max_records=10):
    """
    Query GDELT Doc API for recent articles matching a theme.

    Args:
        query:       Search term string.
        hours_back:  How far back to search (hours).
        max_records: Maximum articles to return.

    Returns:
        List of article dicts from GDELT, or empty list on failure.
    """
    try:
        params = {
            "query":      query,
            "mode":       "artlist",
            "maxrecords": max_records,
            "timespan":   f"{hours_back}h",
            "format":     "json",
            "sort":       "DateDesc",
        }
        r = requests.get(GDELT_DOC_API, params=params, timeout=15)
        if r.status_code == 200:
            return r.json().get("articles", [])
    except Exception:
        pass
    return []


def _get_gdelt_tone(query, hours_back=6):
    """
    Get average tone for a query from GDELT TV API.

    Returns:
        Float tone score (-10 to +10), or None on failure.
    """
    try:
        params = {
            "query":    query,
            "mode":     "tonechart",
            "timespan": f"{hours_back}h",
            "format":   "json",
        }
        r = requests.get(
            "https://api.gdeltproject.org/api/v2/tv/tv",
            params=params,
            timeout=10,
        )
        # Fall back to doc API for tone since tv may not work for all queries
    except Exception:
        pass
    return None


def fetch_world_news(portfolio):
    """
    Fetch geopolitical news and compute tone scores per theme.

    Args:
        portfolio: Parsed portfolio config (stocks.yaml).

    Returns:
        Dict with:
        - tone_score:      Overall geopolitical tone (float).
        - tone_label:      Human-readable tone label.
        - top_events:      List of significant event strings.
        - theme_summaries: Events grouped by theme with average tone.
        - timestamp:       ISO timestamp of when data was fetched.
    """
    results = {
        "tone_score":      None,
        "tone_label":      "N/A",
        "top_events":      [],
        "theme_summaries": {},
        "timestamp":       datetime.now().isoformat(),
    }

    try:
        all_events = []
        theme_summaries = {}

        # Search for each theme relevant to portfolio
        for theme, keywords in PORTFOLIO_THEMES.items():
            theme_events = []
            # Pick first 2 key terms per theme to avoid rate limits
            search_terms = keywords[:2]

            for term in search_terms:
                articles = _search_gdelt(term, hours_back=8, max_records=5)
                for a in articles[:3]:
                    title    = a.get("title", "")
                    url      = a.get("url", "")
                    source   = a.get("domain", "unknown")
                    seendate = a.get("seendate", "")[:10]
                    tone     = float(a.get("tone", 0)) if a.get("tone") else 0

                    event_str = f"[{seendate}] ({source}) {title[:100]}"
                    if event_str not in all_events:
                        all_events.append(event_str)
                        theme_events.append({
                            "title":  title[:100],
                            "tone":   tone,
                            "date":   seendate,
                            "source": source,
                        })
                time.sleep(0.5)  # Gentle on GDELT

            if theme_events:
                avg_tone = sum(e["tone"] for e in theme_events) / len(theme_events)
                theme_summaries[theme] = {
                    "events":   theme_events[:3],
                    "avg_tone": round(avg_tone, 2),
                }

        # Assemble overall results
        results["theme_summaries"] = theme_summaries
        results["top_events"]      = all_events[:8]

        # Compute overall tone across all themes
        all_tones = [td["avg_tone"] for td in theme_summaries.values()]
        if all_tones:
            overall_tone = sum(all_tones) / len(all_tones)
            results["tone_score"] = round(overall_tone, 2)
            if overall_tone < -3:
                results["tone_label"] = "highly conflicted"
            elif overall_tone < 0:
                results["tone_label"] = "elevated tension"
            elif overall_tone < 2:
                results["tone_label"] = "neutral"
            else:
                results["tone_label"] = "cooperative"

    except Exception as e:
        results["error"] = str(e)

    return results
