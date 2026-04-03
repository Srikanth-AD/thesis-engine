"""
Layer 8 -- Reddit Sentiment (PRAW)

Monitors r/wallstreetbets, r/stocks, r/investing, r/SecurityAnalysis, and more.
Tracks mention counts, velocity, sentiment, and top posts per ticker.
Free tier -- no cost beyond the Reddit API credentials.
"""
import os
import time
from datetime import datetime, timedelta

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False


# Subreddits to monitor for ticker mentions
SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "SecurityAnalysis",
    "StockMarket",
    "options",
]

# Sentiment keyword sets for simple lexicon-based scoring
BULL_WORDS = {
    "bullish", "buy", "long", "moon", "calls", "upside", "breakout",
    "undervalued", "buying", "hold", "strong", "growth", "beat",
    "pumped", "rocket", "squeeze",
}
BEAR_WORDS = {
    "bearish", "sell", "short", "puts", "dump", "overvalued", "crash",
    "bubble", "fraud", "lawsuit", "dilution", "downgrade", "miss",
    "falling", "weak", "concern", "warning",
}


def _sentiment_score(text):
    """
    Simple lexicon-based sentiment scoring.

    Returns:
        One of 'bullish', 'bearish', or 'neutral'.
    """
    text_lower = text.lower()
    bull = sum(1 for w in BULL_WORDS if w in text_lower)
    bear = sum(1 for w in BEAR_WORDS if w in text_lower)
    if bull > bear:
        return "bullish"
    elif bear > bull:
        return "bearish"
    return "neutral"


def _is_quality_post(post):
    """Filter for higher-quality content (not pure meme)."""
    flair = str(post.link_flair_text or "").lower()
    is_dd = "dd" in flair or "discussion" in flair or "analysis" in flair
    has_text = len(post.selftext) > 100
    high_score = post.score > 100
    return is_dd or has_text or high_score


def fetch_reddit_sentiment(tickers):
    """
    Fetch Reddit sentiment data for a list of tickers.

    Args:
        tickers: List of ticker symbol strings.

    Returns:
        Dict keyed by ticker with:
        - mentions_24h:  Mention count in last 24 hours.
        - mentions_7d:   Mention count in last 7 days.
        - velocity_pct:  Percentage change vs 7-day daily average.
        - bullish_pct:   Percentage of bullish mentions.
        - bearish_pct:   Percentage of bearish mentions.
        - top_posts:     Top 3 posts by score.
        - spike:         True if velocity > 100%.
    """
    if not PRAW_AVAILABLE:
        return {t: {"error": "praw not installed"} for t in tickers}

    # Check credentials
    client_id     = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent    = os.environ.get("REDDIT_USER_AGENT", "thesis-engine/1.0")

    if not client_id or not client_secret:
        return {t: {"error": "Reddit credentials not set"} for t in tickers}

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except Exception as e:
        return {t: {"error": f"Reddit auth failed: {e}"} for t in tickers}

    results = {}
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    cutoff_7d  = datetime.utcnow() - timedelta(days=7)

    for ticker in tickers:
        try:
            mentions_24h = 0
            mentions_7d  = 0
            sentiments   = []
            top_posts    = []

            for sub_name in SUBREDDITS:
                try:
                    subreddit = reddit.subreddit(sub_name)
                    search_results = list(subreddit.search(
                        f"{ticker} OR ${ticker}",
                        sort="new",
                        time_filter="week",
                        limit=25,
                    ))

                    for post in search_results:
                        created   = datetime.utcfromtimestamp(post.created_utc)
                        text      = f"{post.title} {post.selftext[:200]}"
                        sentiment = _sentiment_score(text)

                        if created > cutoff_7d:
                            mentions_7d += 1
                            sentiments.append(sentiment)
                        if created > cutoff_24h:
                            mentions_24h += 1

                        # Collect top posts by score
                        if post.score > 50 and ticker.upper() in post.title.upper():
                            top_posts.append({
                                "title":     post.title[:120],
                                "score":     post.score,
                                "subreddit": sub_name,
                                "url":       f"https://reddit.com{post.permalink}",
                                "flair":     post.link_flair_text,
                                "quality":   _is_quality_post(post),
                                "sentiment": sentiment,
                            })

                    time.sleep(0.5)  # Rate limit respect

                except Exception:
                    continue

            # Sort top posts by score descending
            top_posts.sort(key=lambda x: x["score"], reverse=True)

            # Compute sentiment breakdown
            bull_count = sentiments.count("bullish")
            bear_count = sentiments.count("bearish")
            total_sent = len(sentiments)
            bull_pct   = (bull_count / total_sent * 100) if total_sent > 0 else 50

            # Velocity: 24h mentions vs 7-day daily average
            daily_avg    = mentions_7d / 7 if mentions_7d > 0 else 1
            velocity_pct = ((mentions_24h - daily_avg) / daily_avg * 100) if daily_avg > 0 else 0

            results[ticker] = {
                "mentions_24h": mentions_24h,
                "mentions_7d":  mentions_7d,
                "velocity_pct": round(velocity_pct, 0),
                "bullish_pct":  round(bull_pct, 0),
                "bearish_pct":  round(100 - bull_pct, 0) if total_sent else 50,
                "top_post":     top_posts[0] if top_posts else None,
                "top_posts":    top_posts[:3],
                "spike":        velocity_pct > 100,
            }

        except Exception as e:
            results[ticker] = {"error": str(e)}

    return results
