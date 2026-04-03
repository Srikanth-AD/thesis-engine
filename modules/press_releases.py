"""
Layer 6 — Press Releases & SEC 8-K Filings

Three sources per ticker:
  1. SEC EDGAR 8-K filings (legally required material disclosures)
  2. Finnhub press releases endpoint
  3. GlobeNewswire + BusinessWire RSS feeds

8-K is the most important -- catches dilutive offerings, contract
awards, and executive changes that companies can't hide in PR spin.
"""
import os
import time
from datetime import datetime, timedelta

import feedparser
import requests

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"
EDGAR_HEADERS = {"User-Agent": "thesis-engine/1.0"}

# 8-K item codes that matter most for investors
MATERIAL_8K_ITEMS = {
    "1.01": "Material Definitive Agreement (contract/partnership)",
    "1.02": "Termination of Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "2.01": "Completion of Acquisition or Disposition",
    "2.02": "Results of Operations (earnings)",
    "2.03": "Creation of Direct Financial Obligation (DEBT RAISE)",
    "2.04": "Triggering Events for Acceleration of Financial Obligation",
    "3.01": "Notice of Delisting",
    "3.02": "Unregistered Sales of Equity Securities (DILUTION)",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure/Appointment of Directors or Officers (EXEC CHANGE)",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements",
}

DILUTION_ITEMS = {"3.02", "2.03"}
CONTRACT_ITEMS = {"1.01", "2.01"}
EXEC_CHANGE_ITEMS = {"5.02"}


def _classify_pr(title, items=None):
    """Classify press release type from title keywords and 8-K item codes."""
    title_lower = title.lower()
    items = items or []

    # 8-K item codes take priority over title keywords
    if any(i in DILUTION_ITEMS for i in items):
        return "dilution"
    if any(i in CONTRACT_ITEMS for i in items):
        return "contract"
    if any(i in EXEC_CHANGE_ITEMS for i in items):
        return "executive"

    if any(w in title_lower for w in ["offering", "shares", "placement", "dilut"]):
        return "dilution"
    if any(w in title_lower for w in ["contract", "award", "partnership", "agreement", "wins"]):
        return "contract"
    if any(w in title_lower for w in ["appoints", "names", "hires", "departs", "resigns", "ceo", "cfo"]):
        return "executive"
    if any(w in title_lower for w in ["earnings", "revenue", "results", "quarter"]):
        return "earnings"
    return "general"


def _fetch_edgar_8k(ticker, days_back=7):
    """Fetch recent 8-K filings from SEC EDGAR full-text search."""
    results = []
    try:
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        params = {
            "q": f'"{ticker}"',
            "forms": "8-K",
            "dateRange": "custom",
            "startdt": from_date,
        }
        r = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params=params,
            headers=EDGAR_HEADERS,
            timeout=15,
        )
        data = r.json()
        hits = data.get("hits", {}).get("hits", [])

        for hit in hits[:3]:
            source = hit.get("_source", {})
            file_date = source.get("file_date", "")
            entity = source.get("entity_name", ticker)
            form_type = source.get("form_type", "8-K")
            items_raw = source.get("items", "")
            item_nums = [i.strip() for i in str(items_raw).split(",") if i.strip()]
            item_descs = [MATERIAL_8K_ITEMS.get(i, i) for i in item_nums if i in MATERIAL_8K_ITEMS]
            pr_type = _classify_pr(entity, item_nums)

            results.append({
                "source": "SEC 8-K",
                "date": file_date,
                "title": f"{entity}: {form_type} -- {', '.join(item_descs) if item_descs else 'Material Event'}",
                "type": pr_type,
                "items": item_nums,
                "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=8-K",
                "summary": f"Items: {items_raw}" if items_raw else "",
            })
        time.sleep(0.3)
    except Exception:
        pass
    return results


def _fetch_finnhub_pr(ticker, days_back=7):
    """Fetch press releases from Finnhub."""
    results = []
    try:
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = datetime.now().strftime("%Y-%m-%d")
        params = {
            "symbol": ticker,
            "from": from_date,
            "to": to_date,
            "token": FINNHUB_KEY,
        }
        r = requests.get(f"{FINNHUB_BASE}/press-releases", params=params, timeout=10)
        data = r.json()
        for item in data.get("majorDevelopment", [])[:3]:
            headline = item.get("headline", "")
            results.append({
                "source": "Finnhub PR",
                "date": item.get("datetime", "")[:10],
                "title": headline[:150],
                "type": _classify_pr(headline),
                "url": item.get("url", ""),
                "summary": item.get("description", "")[:200] if item.get("description") else "",
            })
        time.sleep(0.15)
    except Exception:
        pass
    return results


def _fetch_wire_rss(ticker, company_name=""):
    """Fetch from GlobeNewswire and BusinessWire RSS feeds."""
    results = []
    feeds = [
        f"https://www.globenewswire.com/RssFeed/company/{ticker}",
        f"https://feed.businesswire.com/rss/home/?rss=G22&ticker={ticker}",
    ]
    if company_name:
        name_slug = company_name.lower().replace(" ", "-")
        feeds.append(f"https://www.globenewswire.com/RssFeed/subjectcode/{name_slug}")

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:
                title = entry.get("title", "")
                source_label = "GlobeNewswire" if "globenewswire" in feed_url else "BusinessWire"
                results.append({
                    "source": source_label,
                    "date": entry.get("published", "")[:10],
                    "title": title[:150],
                    "type": _classify_pr(title),
                    "url": entry.get("link", ""),
                    "summary": "",
                })
            time.sleep(0.3)
        except Exception:
            continue
    return results


def fetch_press_releases(tickers, portfolio=None):
    """
    Fetch press releases from SEC EDGAR, Finnhub, and wire services.

    Returns dict keyed by ticker. Dilution and contract events sort first.
    """
    results = {}
    stock_map = {}
    if portfolio:
        stock_map = {s["ticker"]: s for s in portfolio.get("portfolio", [])}

    for ticker in tickers:
        company_name = stock_map.get(ticker, {}).get("name", "")
        all_prs = []
        all_prs += _fetch_edgar_8k(ticker)
        all_prs += _fetch_finnhub_pr(ticker)
        all_prs += _fetch_wire_rss(ticker, company_name)

        # Deduplicate by title prefix
        seen_titles = set()
        unique_prs = []
        for pr in all_prs:
            key = pr["title"][:50].lower()
            if key not in seen_titles:
                seen_titles.add(key)
                unique_prs.append(pr)

        # Sort: dilution first, then contract, executive, general
        priority = {"dilution": 0, "contract": 1, "executive": 2, "earnings": 3, "general": 4}
        unique_prs.sort(key=lambda x: priority.get(x.get("type", "general"), 4))
        results[ticker] = unique_prs[:5]

    return results
