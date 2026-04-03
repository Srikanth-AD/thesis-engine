"""
Layer 5 — News RSS

Headlines from Yahoo Finance, Seeking Alpha, Nasdaq, Motley Fool (per-ticker)
plus CNBC, MarketWatch, Reuters (general market context).
All public RSS feeds. No API keys required.
"""
import time
from datetime import datetime

import feedparser
import requests


def _parse_feed(url, timeout=8):
    """Fetch and parse RSS feed with timeout."""
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "thesis-engine/1.0"})
        return feedparser.parse(r.content)
    except Exception:
        return feedparser.FeedParserDict(entries=[])


# Per-ticker RSS feeds ({ticker} is replaced)
FEEDS = {
    "Yahoo Finance": "https://finance.yahoo.com/rss/headline?s={ticker}",
    "Seeking Alpha": "https://seekingalpha.com/symbol/{ticker}.xml",
    "Nasdaq": "https://www.nasdaq.com/feed/rssoutbound?symbol={ticker}",
    "Motley Fool": "https://www.fool.com/a/feeds/ticker/{ticker}",
}

# General market feeds (shared context across all tickers)
GENERAL_FEEDS = {
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    "Reuters": "https://feeds.reuters.com/reuters/businessNews",
}

# Keyword-based sentiment (simple but robust)
POSITIVE_WORDS = {
    "beats", "beat", "surges", "gains", "wins", "upgrades", "record",
    "bullish", "strong", "growth", "profit", "raises", "expands",
    "partnership", "contract", "approved", "launch",
}
NEGATIVE_WORDS = {
    "misses", "miss", "falls", "drops", "cuts", "downgrade", "concern",
    "loss", "debt", "lawsuit", "fraud", "declining", "warning",
    "layoffs", "dilution", "short", "investigation", "recall",
}


def _sentiment(title):
    """Score headline sentiment from keyword matches."""
    title_lower = title.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in title_lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w in title_lower)
    if pos > neg:
        return "positive"
    elif neg > pos:
        return "negative"
    return "neutral"


def _age_label(entry):
    """Human-readable age of a news item."""
    try:
        import email.utils
        published = entry.get("published", "")
        if published:
            dt = datetime(*email.utils.parsedate(published)[:6])
            diff = datetime.now() - dt
            if diff.seconds < 3600:
                return f"{diff.seconds // 60}min ago"
            elif diff.days == 0:
                return f"{diff.seconds // 3600}h ago"
            else:
                return f"{diff.days}d ago"
    except Exception:
        pass
    return "recent"


def fetch_news_rss(tickers):
    """
    Fetch per-ticker and general market news from RSS feeds.

    Returns dict keyed by ticker (top 5 headlines each)
    plus '__general__' key for market-wide news.
    """
    results = {}

    for ticker in tickers:
        ticker_news = []
        for source, url_template in FEEDS.items():
            try:
                url = url_template.format(ticker=ticker)
                feed = _parse_feed(url)
                for entry in feed.entries[:3]:
                    title = entry.get("title", "")
                    ticker_news.append({
                        "source": source,
                        "title": title[:150],
                        "url": entry.get("link", ""),
                        "age": _age_label(entry),
                        "sentiment": _sentiment(title),
                    })
                time.sleep(0.3)
            except Exception:
                continue
        results[ticker] = ticker_news[:5]

    # General market context
    general = []
    for source, url in GENERAL_FEEDS.items():
        try:
            feed = _parse_feed(url)
            for entry in feed.entries[:3]:
                title = entry.get("title", "")
                general.append({
                    "source": source,
                    "title": title[:150],
                    "age": _age_label(entry),
                    "sentiment": _sentiment(title),
                })
            time.sleep(0.3)
        except Exception:
            continue

    results["__general__"] = general[:6]
    return results
